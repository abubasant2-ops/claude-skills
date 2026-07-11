def test_create_update_plan_lifecycle(client, child_id):
    resp = client.post(
        "/api/v1/treatment-plans",
        json={
            "child_id": child_id,
            "author": "ai",
            "goals": [{"goal": "produce /ر/ in initial position with 80% accuracy"}],
            "target_phonemes": ["ر", "س", "ك"],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "draft"  # default
    assert body["target_phonemes"] == ["ر", "س", "ك"]
    assert body["approved_by"] is None

    slp = client.post(
        "/api/v1/users",
        json={"role": "slp", "email": "approver@example.com", "password": "secret123"},
    ).json()
    resp = client.patch(
        f"/api/v1/treatment-plans/{body['id']}",
        json={"status": "approved", "approved_by": slp["id"]},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"
    assert resp.json()["approved_by"] == slp["id"]


def test_create_plan_unknown_child(client):
    resp = client.post(
        "/api/v1/treatment-plans",
        json={
            "child_id": "00000000-0000-0000-0000-000000000000",
            "author": "ai",
        },
    )
    assert resp.status_code == 404
