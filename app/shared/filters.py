from datetime import date
from typing import Optional
from fastapi import Query


class DateRangeFilter:
    def __init__(
        self,
        date_from: Optional[date] = Query(default=None, alias="from", description="Start date (YYYY-MM-DD)"),
        date_to: Optional[date] = Query(default=None, alias="to", description="End date (YYYY-MM-DD)"),
    ):
        self.date_from = date_from
        self.date_to = date_to

    def to_prisma_filter(self) -> dict:
        """Returns a Prisma-compatible date filter dict for the `date` field."""
        f = {}
        if self.date_from:
            f["gte"] = self.date_from
        if self.date_to:
            f["lte"] = self.date_to
        return f if f else {}