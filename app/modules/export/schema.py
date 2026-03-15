"""
app/modules/export/schema.py
==============================
Shared query-parameter schema for all Excel export endpoints.
"""
from datetime import date
from typing import Optional

from fastapi import Query

from app.shared.constants import ExportPeriod


class ExportQueryParams:
    """
    Dependency-injectable export parameters.

    Usage in router:
        params: ExportQueryParams = Depends()

    Period rules:
      daily   → requires `export_date` (defaults to today if omitted)
      weekly  → requires `export_date` (Monday of that week is computed)
      monthly → requires `year` + `month`
      yearly  → requires `year`
      all     → no date parameters required; exports the entire dataset

    Alternatively, `date_from` / `date_to` can be supplied for any period
    to override the auto-computed range (useful for custom date windows).
    Note: `date_from` / `date_to` are ignored when period=all.
    """

    def __init__(
        self,
        period: ExportPeriod = Query(
            ...,
            description=(
                "Export granularity: daily | weekly | monthly | yearly | all. "
                "Use 'all' to export the complete dataset with no date filter."
            ),
        ),
        export_date: Optional[date] = Query(
            default=None,
            description=(
                "Reference date for daily/weekly exports (YYYY-MM-DD). "
                "Defaults to today for daily; week containing this date for weekly."
            ),
        ),
        year: Optional[int] = Query(
            default=None,
            ge=2000,
            le=2100,
            description="Year for monthly/yearly exports.",
        ),
        month: Optional[int] = Query(
            default=None,
            ge=1,
            le=12,
            description="Month (1–12) for monthly exports.",
        ),
        date_from: Optional[date] = Query(
            default=None,
            alias="from",
            description=(
                "Override range start (YYYY-MM-DD). "
                "Takes precedence over period. Ignored when period=all."
            ),
        ),
        date_to: Optional[date] = Query(
            default=None,
            alias="to",
            description=(
                "Override range end (YYYY-MM-DD). "
                "Takes precedence over period. Ignored when period=all."
            ),
        ),
    ):
        self.period = period
        self.export_date = export_date
        self.year = year
        self.month = month
        self.date_from = date_from
        self.date_to = date_to