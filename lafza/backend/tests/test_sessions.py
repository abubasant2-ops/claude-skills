import uuid

from sqlalchemy import select

from app.models import PhonemeProfile


def _create_session(client, child_id) -> str:
    resp = client.post("/api/v1/sessions", json={"child_id": child_id})
    assert resp.status_code == 201
    return resp.json()["id"]


def test_create_and_get_session(client, child_id):
    session_id = _create_session(client, child_id)
    resp = client.get(f"/api/v1/sessions/{session_id}")
    assert resp.status_code == 200
    assert resp.json()["child_id"] == child_id


def test_create_session_unknown_child(client):
    resp = client.post(
        "/api/v1/sessions",
        json={"child_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 404


def test_utterance_scored_and_persisted_to_phoneme_profiles(client, child_id, db):
    session_id = _create_session(client, child_id)

    resp = client.post(
        f"/api/v1/sessions/{session_id}/utterances",
        data={"target_phoneme": "ر", "position": "initial"},
        files={"audio": ("utterance.webm", b"fake-audio-bytes", "audio/webm")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["phoneme"] == "ر"
    assert body["position"] == "initial"
    assert 0 <= body["gop_score"] <= 100
    assert body["error_type"] == "lateralization"  # ر is hard → always below 70
    assert body["child_id"] == child_id

    # The row really landed in phoneme_profiles.
    profile = db.get(PhonemeProfile, uuid.UUID(body["phoneme_profile_id"]))
    assert profile is not None
    assert str(profile.child_id) == child_id
    assert profile.phoneme == "ر"
    assert profile.gop_score == body["gop_score"]
    assert profile.error_type == "lateralization"


def test_utterance_scoring_is_deterministic_per_phoneme(client, child_id, db):
    session_id = _create_session(client, child_id)

    def post():
        return client.post(
            f"/api/v1/sessions/{session_id}/utterances",
            data={"target_phoneme": "ش", "position": "initial"},
            files={"audio": ("u.webm", b"bytes-vary-\x00\x01", "audio/webm")},
        ).json()

    first, second = post(), post()
    assert first["gop_score"] == second["gop_score"]
    assert first["error_type"] == second["error_type"]
    # Two separate profile rows were written (time-series).
    rows = db.scalars(
        select(PhonemeProfile).where(PhonemeProfile.phoneme == "ش")
    ).all()
    assert len(rows) == 2


def test_utterance_validation_errors(client, child_id):
    session_id = _create_session(client, child_id)

    # Unknown session.
    resp = client.post(
        "/api/v1/sessions/00000000-0000-0000-0000-000000000000/utterances",
        data={"target_phoneme": "ر", "position": "initial"},
        files={"audio": ("u.webm", b"x", "audio/webm")},
    )
    assert resp.status_code == 404

    # Invalid position.
    resp = client.post(
        f"/api/v1/sessions/{session_id}/utterances",
        data={"target_phoneme": "ر", "position": "sideways"},
        files={"audio": ("u.webm", b"x", "audio/webm")},
    )
    assert resp.status_code == 422

    # Empty audio.
    resp = client.post(
        f"/api/v1/sessions/{session_id}/utterances",
        data={"target_phoneme": "ر", "position": "initial"},
        files={"audio": ("u.webm", b"", "audio/webm")},
    )
    assert resp.status_code == 422
