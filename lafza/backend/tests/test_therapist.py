import uuid
from datetime import datetime, timedelta, timezone

from app.models import PhonemeProfile

NOW = datetime.now(timezone.utc)


def _profile(db, child_id, *, phoneme, position="initial", gop, error=None,
             days_ago=0):
    db.add(
        PhonemeProfile(
            child_id=uuid.UUID(child_id),
            phoneme=phoneme,
            position=position,
            gop_score=gop,
            error_type=error,
            created_at=NOW - timedelta(days=days_ago) + timedelta(minutes=1),
        )
    )


def test_caseload_adherence_and_gop_delta(client, child_id, db):
    # Practice on 2 of the last 7 days → adherence 2/7; ر improved 40→50
    # inside the 30-day window (old 20-score is outside and must not count).
    _profile(db, child_id, phoneme="ر", gop=20, days_ago=40)
    _profile(db, child_id, phoneme="ر", gop=40, days_ago=3)
    _profile(db, child_id, phoneme="ر", gop=50, days_ago=0)
    db.commit()

    resp = client.get("/api/v1/therapist/caseload")
    assert resp.status_code == 200
    rows = resp.json()
    row = next(r for r in rows if r["child_id"] == child_id)

    assert row["attempts"] == 3
    assert row["adherence"] == round(2 / 7, 2)
    assert row["gop_mean"] == 50  # latest per cell
    assert row["gop_delta_30d"] == 10  # 50 - 40 (day-40 excluded)
    assert row["plan_status"] is None
    assert row["last_activity_at"] is not None


def test_heatmap_returns_latest_score_per_cell(client, child_id, db):
    _profile(db, child_id, phoneme="ر", position="initial", gop=40,
             error="lateralization", days_ago=2)
    _profile(db, child_id, phoneme="ر", position="initial", gop=55,
             error="lateralization", days_ago=0)
    _profile(db, child_id, phoneme="ر", position="final", gop=35,
             error="omission", days_ago=0)
    _profile(db, child_id, phoneme="ك", position="initial", gop=88, days_ago=0)
    db.commit()

    resp = client.get(f"/api/v1/children/{child_id}/phoneme-heatmap")
    assert resp.status_code == 200
    cells = {
        (c["phoneme"], c["position"]): c for c in resp.json()["cells"]
    }
    assert len(cells) == 3
    assert cells[("ر", "initial")]["gop_score"] == 55  # latest wins
    assert cells[("ر", "final")]["error_type"] == "omission"
    assert cells[("ك", "initial")]["gop_score"] == 88


def test_heatmap_unknown_child(client):
    resp = client.get(
        "/api/v1/children/00000000-0000-0000-0000-000000000000/phoneme-heatmap"
    )
    assert resp.status_code == 404
