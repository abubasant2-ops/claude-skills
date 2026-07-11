import uuid
from datetime import datetime, timedelta, timezone

from app.models import PhonemeProfile, TherapySession

NOW = datetime.now(timezone.utc)


def _at(days_ago: int) -> datetime:
    # +1 minute keeps boundary rows (exactly N days old) inside the window
    # computed against the slightly-later request-time "now".
    return NOW - timedelta(days=days_ago) + timedelta(minutes=1)


def _seed(db, child_id, *, days_ago, phoneme="ر", gop=41, error="lateralization"):
    db.add(
        PhonemeProfile(
            child_id=uuid.UUID(child_id),
            phoneme=phoneme,
            position="initial",
            gop_score=gop,
            error_type=error,
            created_at=_at(days_ago),
        )
    )


def _seed_session(db, child_id, *, days_ago, duration_sec):
    db.add(
        TherapySession(
            child_id=uuid.UUID(child_id),
            activity_ids=[],
            scores_json={},
            duration_sec=duration_sec,
            created_at=_at(days_ago),
        )
    )


def test_parent_summary_streak_minutes_and_report(client, child_id, db):
    # Practice on today, yesterday, and 2 days ago → streak of 3;
    # a gap at day 3, activity at day 4 must not count.
    for days_ago in [0, 1, 2, 4]:
        _seed(db, child_id, days_ago=days_ago)
    # ر improved within the week: first 38 → latest 41.
    _seed(db, child_id, days_ago=6, gop=38)
    # ش scored once, above ر → sorted after ر (weakest first).
    _seed(db, child_id, days_ago=0, phoneme="ش", gop=64, error="substitution")
    # Practice sessions: 300s two days ago + 120s today; an old one outside
    # the window must be excluded.
    _seed_session(db, child_id, days_ago=2, duration_sec=300)
    _seed_session(db, child_id, days_ago=0, duration_sec=120)
    _seed_session(db, child_id, days_ago=10, duration_sec=999)
    db.commit()

    resp = client.get(f"/api/v1/children/{child_id}/parent-summary")
    assert resp.status_code == 200
    body = resp.json()

    assert body["streak_days"] == 3
    assert body["week_practice_seconds"] == 420
    assert body["week_attempts"] == 6  # 5×ر (days 0,1,2,4,6) + 1×ش
    assert len(body["daily"]) == 7
    assert body["daily"][-1]["seconds"] == 120  # today is last
    assert sum(d["seconds"] for d in body["daily"]) == 420

    phonemes = body["phonemes"]
    assert [row["phoneme"] for row in phonemes] == ["ر", "ش"]  # weakest first
    ra = phonemes[0]
    assert ra["attempts"] == 5
    assert ra["first_gop"] == 38
    assert ra["latest_gop"] == 41
    assert ra["latest_error_type"] == "lateralization"

    assert body["plan"] is None  # no plan generated yet


def test_parent_summary_includes_latest_plan(client, child_id, db):
    _seed(db, child_id, days_ago=0, phoneme="ق", gop=58, error="substitution")
    db.commit()
    generated = client.post(f"/api/v1/children/{child_id}/plans/generate")
    assert generated.status_code == 201

    resp = client.get(f"/api/v1/children/{child_id}/parent-summary")
    body = resp.json()
    assert body["plan"] == {"target_phonemes": ["ق"], "status": "draft"}


def test_parent_summary_unknown_child(client):
    resp = client.get(
        "/api/v1/children/00000000-0000-0000-0000-000000000000/parent-summary"
    )
    assert resp.status_code == 404


def test_create_session_with_duration_and_scores(client, child_id):
    resp = client.post(
        "/api/v1/sessions",
        json={
            "child_id": child_id,
            "duration_sec": 95,
            "activity_ids": ["stimulus-sun"],
            "scores_json": {"phoneme": "ش", "gop_score": 64},
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["duration_sec"] == 95
    assert body["scores_json"] == {"phoneme": "ش", "gop_score": 64}