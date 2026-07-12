"""Aggregations behind the parent dashboard and weekly report (P1/P3).

Streak counts consecutive calendar days (UTC) with at least one scored
utterance; practice time sums session durations over the last 7 days.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PhonemeProfile, TherapySession, TreatmentPlan

WEEK_DAYS = 7


def build_parent_summary(db: Session, child_id: uuid.UUID) -> dict:
    now = datetime.now(timezone.utc)
    today = now.date()
    week_start = now - timedelta(days=WEEK_DAYS - 1)

    profiles = list(
        db.scalars(
            select(PhonemeProfile).where(PhonemeProfile.child_id == child_id)
        )
    )

    # Streak: consecutive active days ending today (or yesterday, so an
    # unfinished today doesn't break the chain).
    active_days = {p.created_at.date() for p in profiles}
    cursor = today if today in active_days else today - timedelta(days=1)
    streak = 0
    while cursor in active_days:
        streak += 1
        cursor -= timedelta(days=1)

    sessions = list(
        db.scalars(
            select(TherapySession).where(
                TherapySession.child_id == child_id,
                TherapySession.created_at >= week_start,
            )
        )
    )
    seconds_by_day: dict = {}
    for session in sessions:
        day = session.created_at.date()
        seconds_by_day[day] = (
            seconds_by_day.get(day, 0) + (session.duration_sec or 0)
        )
    daily = [
        {"day": day, "seconds": seconds_by_day.get(day, 0)}
        for i in range(WEEK_DAYS)
        for day in [today - timedelta(days=WEEK_DAYS - 1 - i)]
    ]

    week_profiles = [
        p for p in profiles if p.created_at >= week_start
    ]
    by_phoneme: dict[str, list[PhonemeProfile]] = {}
    for p in sorted(week_profiles, key=lambda r: r.created_at):
        by_phoneme.setdefault(p.phoneme, []).append(p)
    phoneme_rows = sorted(
        (
            {
                "phoneme": phoneme,
                "attempts": len(rows),
                "first_gop": rows[0].gop_score,
                "latest_gop": rows[-1].gop_score,
                "latest_error_type": rows[-1].error_type,
            }
            for phoneme, rows in by_phoneme.items()
        ),
        key=lambda r: r["latest_gop"],  # weakest first
    )

    latest_plan = db.scalars(
        select(TreatmentPlan)
        .where(TreatmentPlan.child_id == child_id)
        .order_by(TreatmentPlan.created_at.desc())
        .limit(1)
    ).first()

    return {
        "streak_days": streak,
        "week_practice_seconds": sum(d["seconds"] for d in daily),
        "week_attempts": len(week_profiles),
        "daily": daily,
        "phonemes": phoneme_rows,
        "plan": (
            {
                "target_phonemes": latest_plan.target_phonemes,
                "status": latest_plan.status,
            }
            if latest_plan
            else None
        ),
    }
