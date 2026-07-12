import uuid
from datetime import datetime, timedelta, timezone

from app.models import PhonemeProfile, TreatmentPlan
from app.services.plan_generator import PlanGeneratorService

T0 = datetime(2026, 7, 1, tzinfo=timezone.utc)


def _profile(phoneme, position, gop, error=None, at=T0):
    return PhonemeProfile(
        id=uuid.uuid4(),
        child_id=uuid.uuid4(),
        phoneme=phoneme,
        position=position,
        gop_score=gop,
        error_type=error,
        created_at=at,
    )


def test_targets_ranked_by_tier_then_stimulability():
    service = PlanGeneratorService()
    profiles = [
        _profile("ر", "initial", 40, "lateralization"),  # tier 3
        _profile("ط", "initial", 45, "distortion"),  # tier 3
        _profile("ق", "initial", 58, "substitution"),  # tier 2
        _profile("س", "initial", 62, "substitution"),  # tier 2, more stimulable
        _profile("ك", "initial", 64, "substitution"),  # tier 1 → first
        _profile("ل", "initial", 85),  # passing → excluded
    ]
    targets = service.select_targets(profiles)
    assert [t.phoneme for t in targets] == ["ك", "س", "ق"]
    assert targets[0].baseline_gop == 64
    assert targets[1].error_types == ["substitution"]


def test_latest_score_wins_over_history():
    service = PlanGeneratorService()
    profiles = [
        # ك used to fail but the newest score passes → not a target.
        _profile("ك", "initial", 50, "substitution", at=T0),
        _profile("ك", "initial", 90, None, at=T0 + timedelta(days=7)),
        # ر regressed: newest score fails → targeted.
        _profile("ر", "initial", 80, None, at=T0),
        _profile("ر", "initial", 42, "lateralization", at=T0 + timedelta(days=7)),
    ]
    targets = service.select_targets(profiles)
    assert [t.phoneme for t in targets] == ["ر"]


def test_multi_position_failures_merge_into_one_target():
    service = PlanGeneratorService()
    profiles = [
        _profile("ر", "final", 38, "omission"),
        _profile("ر", "initial", 44, "lateralization"),
        _profile("ر", "medial", 41, "lateralization"),
    ]
    targets = service.select_targets(profiles)
    assert len(targets) == 1
    assert targets[0].positions == ["initial", "medial", "final"]
    assert targets[0].baseline_gop == 41  # mean of 44, 41, 38
    assert targets[0].error_types == ["lateralization", "omission"]


def test_generate_endpoint_persists_draft_plan(client, child_id, db):
    # Seed an error profile via the DB (assessment already covered elsewhere).
    for phoneme, gop, error in [
        ("ر", 41, "lateralization"),
        ("ص", 44, "distortion"),
        ("ق", 64, "substitution"),
        ("ش", 64, "substitution"),
        ("ك", 88, None),
    ]:
        db.add(
            PhonemeProfile(
                child_id=uuid.UUID(child_id),
                phoneme=phoneme,
                position="initial",
                gop_score=gop,
                error_type=error,
            )
        )
    db.commit()

    resp = client.post(f"/api/v1/children/{child_id}/plans/generate")
    assert resp.status_code == 201
    body = resp.json()
    assert body["author"] == "ai"
    assert body["status"] == "draft"
    assert body["approved_by"] is None
    # tier 2 pair first (ش before ق by §7 in-tier order on equal scores),
    # then the most stimulable tier-3 failure (ص 44 > ر 41).
    assert body["target_phonemes"] == ["ش", "ق", "ص"]
    goals = body["goals"]
    assert [g["phoneme"] for g in goals] == ["ش", "ق", "ص"]
    assert all(g["target_gop"] == 85 and g["duration_weeks"] == 12 for g in goals)
    assert "«ش»" in goals[0]["description_ar"]

    plan = db.get(TreatmentPlan, uuid.UUID(body["id"]))
    assert plan is not None
    assert plan.status == "draft"
    assert plan.target_phonemes == ["ش", "ق", "ص"]


def test_generate_endpoint_validation(client, child_id):
    # No profiles at all → 422.
    resp = client.post(f"/api/v1/children/{child_id}/plans/generate")
    assert resp.status_code == 422

    # Unknown child → 404.
    resp = client.post(
        "/api/v1/children/00000000-0000-0000-0000-000000000000/plans/generate"
    )
    assert resp.status_code == 404
