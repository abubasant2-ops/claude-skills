"""Aggregations behind the therapist dashboard (T1 caseload, T2 heatmap)."""

import uuid
from datetime import datetime, timedelta, timezone
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Child, PhonemeProfile, TherapySession, TreatmentPlan

ADHERENCE_WINDOW_DAYS = 7
DELTA_WINDOW_DAYS = 30


def _latest_and_earliest_per_cell(
    profiles: list[PhonemeProfile],
) -> tuple[dict, dict]:
    latest: dict[tuple[str, str], PhonemeProfile] = {}
    earliest: dict[tuple[str, str], PhonemeProfile] = {}
    for row in sorted(profiles, key=lambda r: r.created_at):
        key = (row.phoneme, row.position)
        earliest.setdefault(key, row)
        latest[key] = row
    return latest, earliest


def build_caseload(db: Session) -> list[dict]:
    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=ADHERENCE_WINDOW_DAYS - 1)
    delta_start = now - timedelta(days=DELTA_WINDOW_DAYS)

    rows = []
    for child in db.scalars(select(Child).order_by(Child.created_at)):
        profiles = list(
            db.scalars(
                select(PhonemeProfile).where(
                    PhonemeProfile.child_id == child.id
                )
            )
        )
        sessions = list(
            db.scalars(
                select(TherapySession).where(
                    TherapySession.child_id == child.id
                )
            )
        )

        active_days = {
            p.created_at.date() for p in profiles if p.created_at >= week_start
        } | {
            s.created_at.date() for s in sessions if s.created_at >= week_start
        }
        adherence = len(active_days) / ADHERENCE_WINDOW_DAYS

        window_profiles = [p for p in profiles if p.created_at >= delta_start]
        latest, earliest = _latest_and_earliest_per_cell(window_profiles)
        gop_mean = (
            round(mean(p.gop_score for p in latest.values()))
            if latest
            else None
        )
        gop_delta = (
            round(
                mean(p.gop_score for p in latest.values())
                - mean(p.gop_score for p in earliest.values())
            )
            if latest
            else None
        )

        latest_plan = db.scalars(
            select(TreatmentPlan)
            .where(TreatmentPlan.child_id == child.id)
            .order_by(TreatmentPlan.created_at.desc())
            .limit(1)
        ).first()

        activity_times = [p.created_at for p in profiles] + [
            s.created_at for s in sessions
        ]

        rows.append(
            {
                "child_id": child.id,
                "dob": child.dob,
                "sex": child.sex,
                "dialect": child.dialect,
                "attempts": len(profiles),
                "adherence": round(adherence, 2),
                "gop_mean": gop_mean,
                "gop_delta_30d": gop_delta,
                "plan_status": latest_plan.status if latest_plan else None,
                "last_activity_at": max(activity_times) if activity_times else None,
            }
        )
    return rows


def build_heatmap(db: Session, child_id: uuid.UUID) -> dict:
    profiles = list(
        db.scalars(
            select(PhonemeProfile).where(PhonemeProfile.child_id == child_id)
        )
    )
    latest, _ = _latest_and_earliest_per_cell(profiles)
    return {
        "child_id": child_id,
        "cells": [
            {
                "phoneme": row.phoneme,
                "position": row.position,
                "gop_score": row.gop_score,
                "error_type": row.error_type,
                "created_at": row.created_at,
            }
            for row in latest.values()
        ],
    }
