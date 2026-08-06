"""Shared request dependencies: period parsing and role resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.analytics.common import Grain, period_bounds
from app.core.db import get_session
from app.models import Facility

MAX_WINDOW_DAYS = 400


@dataclass
class Period:
    start: date
    end: date
    grain: Grain

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def get_period(
    start: date | None = Query(None, description="Inclusive start date (YYYY-MM-DD)"),
    end: date | None = Query(None, description="Inclusive end date (YYYY-MM-DD)"),
    grain: Grain = Query("day", description="Bucket size for trend series"),
    preset: str | None = Query(
        None,
        description="Convenience window: today, yesterday, last_7d, last_30d, mtd, qtd, ytd",
    ),
) -> Period:
    """Resolve a reporting window from explicit dates or a preset."""
    today = date.today()

    if preset:
        presets = {
            "today": (today, today),
            "yesterday": (today - timedelta(days=1), today - timedelta(days=1)),
            "last_7d": (today - timedelta(days=6), today),
            "last_30d": (today - timedelta(days=29), today),
            "last_90d": (today - timedelta(days=89), today),
            "mtd": (period_bounds("month", today)[0], today),
            "qtd": (period_bounds("quarter", today)[0], today),
            "ytd": (period_bounds("year", today)[0], today),
        }
        if preset not in presets:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown preset '{preset}'. Valid: {', '.join(sorted(presets))}",
            )
        start, end = presets[preset]
    else:
        end = end or today
        start = start or (end - timedelta(days=29))

    if end < start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail="end must be on or after start")
    if (end - start).days + 1 > MAX_WINDOW_DAYS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Requested window spans {(end - start).days + 1} days; the maximum is "
                f"{MAX_WINDOW_DAYS}. Narrow the range or use a coarser grain."
            ),
        )
    return Period(start=start, end=end, grain=grain)


def get_facility(
    facility_id: int = Query(1, ge=1, description="Facility identifier"),
    session: Session = Depends(get_session),
) -> Facility:
    facility = session.get(Facility, facility_id)
    if facility is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail=f"Facility {facility_id} not found")
    return facility
