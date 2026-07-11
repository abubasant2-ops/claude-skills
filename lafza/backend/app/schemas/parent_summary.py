from datetime import date

from pydantic import BaseModel


class DailyPracticeOut(BaseModel):
    day: date
    seconds: int


class PhonemeReportRowOut(BaseModel):
    phoneme: str
    attempts: int
    first_gop: int
    latest_gop: int
    latest_error_type: str | None


class PlanSummaryOut(BaseModel):
    target_phonemes: list[str]
    status: str


class ParentSummaryOut(BaseModel):
    """P1/P3 — parent dashboard + simplified weekly report payload."""

    streak_days: int
    week_practice_seconds: int
    week_attempts: int
    daily: list[DailyPracticeOut]  # 7 entries, oldest → today
    phonemes: list[PhonemeReportRowOut]  # weakest first
    plan: PlanSummaryOut | None
