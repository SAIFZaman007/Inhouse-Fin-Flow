"""
app/shared/pagination.py
=========================
Generic page-based pagination helpers used across all list endpoints.

Default page size: 50 items per page.
Maximum page size: 100 items per page.
"""
import math
from typing import Generic, List, TypeVar

from fastapi import Query
from pydantic import BaseModel

T = TypeVar("T")


class PageParams:
    """
    FastAPI dependency — inject with ``params: PageParams = Depends()``.

    Query parameters
    ─────────────────
    page       int   Page number (1-indexed).           Default: 1
    page_size  int   Items per page.  Range: 1–100.     Default: 50
    """

    def __init__(
        self,
        page: int = Query(
            default=1, ge=1,
            description="Page number (1-indexed).",
        ),
        page_size: int = Query(
            default=50, ge=1, le=100,
            description="Items per page (max 100). Default: 50.",
        ),
    ):
        self.page      = page
        self.page_size = page_size

    @property
    def skip(self) -> int:
        """Offset for Prisma ``skip``."""
        return (self.page - 1) * self.page_size

    @property
    def take(self) -> int:
        """Limit for Prisma ``take``."""
        return self.page_size


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Standard paginated envelope returned by all list endpoints.

    Build with ``PaginatedResponse.build(items, total, params)``.
    """
    items:       List[T]
    total:       int
    page:        int
    page_size:   int
    total_pages: int

    @classmethod
    def build(
        cls,
        items:  List[T],
        total:  int,
        params: PageParams,
    ) -> "PaginatedResponse[T]":
        return cls(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
            total_pages=math.ceil(total / params.page_size) if total > 0 else 1,
        )