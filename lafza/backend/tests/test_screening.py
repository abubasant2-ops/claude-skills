import uuid

from app.models import Assessment
from app.services.screening import evaluate_screening, get_questionnaire


# ---------- unit: instrument age gating ----------

def test_questionnaire_age_gating():
    infant = get_questionnaire(18)  # 1.5y
    ids = {q["id"] for q in infant["red_flag_questions"]}
    assert "no_single_words" in ids
    assert "under_50_words" not in ids  # 24m+ only
    assert "unintelligible_to_strangers" not in ids  # 48m+ only
    assert infant["vocabulary_words"]  # 12–48m window
    assert infant["intelligibility_options"] == []  # 30m+

    schooler = get_questionnaire(78)  # 6.5y
    ids = {q["id"] for q in schooler["red_flag_questions"]}
    assert "unintelligible_to_strangers" in ids
    assert schooler["vocabulary_words"] == []  # window passed
    assert schooler["intelligibility_options"]


# ---------- unit: deterministic evaluation ----------

def test_healthy_child_scores_green():
    result = evaluate_screening(
        age_months=30,
        red_flag_answers={
            "no_single_words": True,
            "under_50_words": True,
            "no_two_word_combos": True,
            "regression": False,
            "hearing_concern": False,
        },
        vocabulary_checked=["ماما", "بابا", "ماء", "حليب", "قطة", "كرة"],
        intelligibility=3,
    )
    assert result["severity"] == 0
    assert result["traffic_light"] == "green"
    assert result["red_flags"] == []
    assert result["refer_immediately"] is False


def test_two_language_flags_score_red():
    result = evaluate_screening(
        age_months=26,
        red_flag_answers={
            "no_single_words": True,
            "under_50_words": False,  # flag
            "no_two_word_combos": False,  # flag
            "regression": False,
            "hearing_concern": False,
        },
        vocabulary_checked=["ماما", "بابا", "ماء", "حليب", "قطة"],
        intelligibility=None,
    )
    assert result["severity"] == 4  # 2 flags × 2
    assert result["traffic_light"] == "red"
    assert set(result["red_flags"]) == {
        "under_50_words_by_24m",
        "no_two_word_combos_by_24m",
    }


def test_regression_forces_immediate_referral():
    result = evaluate_screening(
        age_months=20,
        red_flag_answers={"no_single_words": True, "regression": True},
        vocabulary_checked=["ماما", "بابا", "ماء", "حليب", "قطة"],
        intelligibility=None,
    )
    assert result["severity"] == 4
    assert result["refer_immediately"] is True
    assert "regression" in result["red_flags"]
    assert "إحالة عاجلة" in result["recommendation_ar"]


def test_soft_signals_only_score_amber():
    # No red flags, but tiny vocabulary + low intelligibility → 2 → amber.
    result = evaluate_screening(
        age_months=36,
        red_flag_answers={
            "no_single_words": True,
            "under_50_words": True,
            "no_two_word_combos": True,
            "regression": False,
            "hearing_concern": False,
        },
        vocabulary_checked=["ماما", "بابا"],  # 2/16 < 25%
        intelligibility=2,
    )
    assert result["severity"] == 2
    assert result["traffic_light"] == "amber"
    assert result["red_flags"] == []


def test_questions_below_age_are_ignored():
    # A 20-month-old answering "no 50 words" must NOT be flagged (24m rule).
    result = evaluate_screening(
        age_months=20,
        red_flag_answers={"no_single_words": True, "under_50_words": False},
        vocabulary_checked=["ماما", "بابا", "ماء", "حليب", "قطة"],
        intelligibility=None,
    )
    assert result["red_flags"] == []


# ---------- endpoint: persistence ----------

def test_screening_endpoint_persists_assessment(client, child_id, db):
    q = client.get(f"/api/v1/children/{child_id}/screening/questionnaire")
    assert q.status_code == 200
    assert q.json()["instrument_version"] == "screening-v1"

    resp = client.post(
        f"/api/v1/children/{child_id}/screening",
        json={
            "red_flag_answers": {
                "no_single_words": True,
                "under_50_words": True,
                "no_two_word_combos": True,
                "unintelligible_to_strangers": False,
                "regression": False,
                "hearing_concern": False,
            },
            "vocabulary_checked": [],
            "intelligibility": 2,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    # dob 2022-05-01 (conftest) → ~4y+: unintelligible flag (2) + low
    # intelligibility (1) = 3 → red.
    assert body["red_flags"] == ["unintelligible_at_4y"]
    assert body["severity"] == 3
    assert body["traffic_light"] == "red"

    assessment = db.get(Assessment, uuid.UUID(body["assessment_id"]))
    assert assessment is not None
    assert assessment.type == "screening"
    assert assessment.severity == 3
    assert assessment.red_flags == ["unintelligible_at_4y"]
    assert assessment.raw_json["answers"]["intelligibility"] == 2


def test_screening_unknown_child(client):
    resp = client.post(
        "/api/v1/children/00000000-0000-0000-0000-000000000000/screening",
        json={},
    )
    assert resp.status_code == 404
