"""
app/shared/filters.py
======================
Reusable date-range filter dependency — used by every module endpoint that
supports date filtering (Fiverr, Upwork, snapshots, orders, etc.).

CRITICAL — PRISMA datetime.date BUG:
  All schema date fields are declared as `DateTime @db.Date`.
  prisma-client-py's internal JSON serialiser only accepts datetime.datetime,
  NOT datetime.date — passing a bare date raises:
      TypeError: Type <class 'datetime.date'> not serializable
  Every Prisma WHERE clause therefore uses datetime.datetime objects via the
  to_dt_start / to_dt_end module-level helpers exported for service layers.

Backward compatibility:
  The legacy ``DateRangeFilter`` accepted only ``from`` / ``to`` query params
  and exposed them as ``self.date_from`` / ``self.date_to``.  That interface
  is fully preserved — both attribute names and query-param aliases still work.
  The class is now a strict superset: it also supports
  ``period`` | ``export_date`` | ``year`` | ``month``.
"""
from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import Query


# ── Module-level helpers ──────────────────────────────────────────────────────
# Import these in any service that constructs Prisma WHERE dicts.

def to_dt_start(d: date) -> datetime:
    """date → datetime at 00:00:00.000000 (inclusive start of day)."""
    return datetime.combine(d, time.min)


def to_dt_end(d: date) -> datetime:
    """date → datetime at 23:59:59.999999 (inclusive end of day)."""
    return datetime.combine(d, time.max)


# ─────────────────────────────────────────────────────────────────────────────

class DateRangeFilter:
    """
    FastAPI dependency — unified date-range filter.

    Supports two usage modes that can be combined freely:

    1. **Simple from/to** (legacy, fully preserved):
           GET /endpoint?from=2025-01-01&to=2025-03-31
       Attributes: ``self.date_from``, ``self.date_to``  (Optional[date])

    2. **Period-based** (new):
           GET /endpoint?period=weekly
           GET /endpoint?period=monthly&year=2025&month=3
           GET /endpoint?period=daily&export_date=2025-03-12
       Attribute: ``self.period``  ("daily" | "weekly" | "monthly" | "yearly" | "all")

    Priority: explicit ``from`` / ``to`` always overrides ``period``.

    Inject with:
        filters: DateRangeFilter = Depends()

    Pass ``filters.to_prisma_filter()`` directly into Prisma ``where`` dicts.
    """

    def __init__(
        self,
        period: Optional[str] = Query(
            default="all",
            description=(
                "Granularity: daily | weekly | monthly | yearly | all. "
                "Default: all (no date restriction)."
            ),
        ),
        export_date: Optional[str] = Query(
            default=None,
            alias="export_date",
            description=(
                "Reference date (YYYY-MM-DD) used for daily/weekly. "
                "Defaults to today."
            ),
            pattern=r"^\d{4}-\d{2}-\d{2}$",
        ),
        year: Optional[int] = Query(
            default=None, ge=2000, le=2100,
            description="Year for monthly / yearly periods.",
        ),
        month: Optional[int] = Query(
            default=None, ge=1, le=12,
            description="Month (1–12) for monthly period.",
        ),
        # ── from / to — FastAPI coerces YYYY-MM-DD → date automatically ───────
        # Stored as Optional[date] to preserve the legacy interface exactly.
        date_from: Optional[date] = Query(
            default=None,
            alias="from",
            description="Explicit range start (YYYY-MM-DD). Overrides period.",
        ),
        date_to: Optional[date] = Query(
            default=None,
            alias="to",
            description="Explicit range end (YYYY-MM-DD). Overrides period.",
        ),
    ):
        self.period      = (period or "all").lower()
        self.export_date = export_date
        self.year        = year
        self.month       = month

        # ── from / to stored under BOTH naming conventions ────────────────────
        # ``date_from`` / ``date_to``  — legacy names used by existing callers
        # ``from_date`` / ``to_date``  — names used by new service code
        # Both point to the same values; neither is deprecated.
        self.date_from = date_from   # legacy
        self.date_to   = date_to     # legacy
        self.from_date = date_from   # new alias
        self.to_date   = date_to     # new alias

    # ── public API ────────────────────────────────────────────────────────────

    def window(self) -> tuple[Optional[date], Optional[date]]:
        """
        Compute the (start, end) inclusive date pair for the current settings.
        Returns (None, None) when no filter is active (period='all', no from/to).

        Priority: explicit from/to > period > all.
        """
        # Explicit from/to always wins
        if self.date_from and self.date_to:
            return self.date_from, self.date_to

        today = date.today()

        if self.period == "daily":
            d = self._parse_str(self.export_date) or today
            return d, d

        if self.period == "weekly":
            d = self._parse_str(self.export_date) or today
            start = d - timedelta(days=d.weekday())   # Monday of the ISO week
            return start, start + timedelta(days=6)   # Sunday

        if self.period == "monthly":
            y = self.year  or today.year
            m = self.month or today.month
            start = date(y, m, 1)
            end   = (
                date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
            ) - timedelta(days=1)
            return start, end

        if self.period == "yearly":
            y = self.year or today.year
            return date(y, 1, 1), date(y, 12, 31)

        return None, None   # "all" — no restriction

    def to_prisma_filter(self) -> dict:
        """
        Return a Prisma-compatible date-field filter dict.

        ALWAYS uses datetime.datetime objects (gte / lte) — never bare
        datetime.date — to avoid prisma-client-py's JSON serialisation
        TypeError.  Returns {} when no filter is active (period='all').

        Usage in a service:
            date_f = filters.to_prisma_filter()
            where: dict = {"profileId": profile_id}
            if date_f:
                where["date"] = date_f
        """
        start, end = self.window()
        if start is None:
            return {}
        return {
            "gte": to_dt_start(start),
            "lte": to_dt_end(end if end is not None else start),
        }

    def meta(self) -> dict:
        """Serialisable filter metadata for embedding in API response envelopes."""
        start, end = self.window()
        return {
            "period": self.period,
            "dateRange": {
                "from": start.isoformat() if start else None,
                "to":   end.isoformat()   if end   else None,
            },
        }

    # ── private ───────────────────────────────────────────────────────────────

    def _parse_str(self, raw: Optional[str]) -> Optional[date]:
        """Parse an ISO date string → date, or return None on failure."""
        if not raw:
            return None
        try:
            return date.fromisoformat(raw)
        except ValueError:
            return None