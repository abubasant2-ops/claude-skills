def test_create_and_get_assessment(client, child_id):
    resp = client.post(
        "/api/v1/assessments",
        json={
            "child_id": child_id,
            "type": "screening",
            "raw_json": {"answers": [1, 0, 1]},
            "severity": 2,
            "red_flags": ["no_two_word_combos_by_24m"],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["type"] == "screening"
    assert body["severity"] == 2
    assert body["red_flags"] == ["no_two_word_combos_by_24m"]

    resp = client.get(f"/api/v1/assessments/{body['id']}")
    assert resp.status_code == 200
    assert resp.json()["child_id"] == child_id


def test_severity_out_of_range_rejected(client, child_id):
    resp = client.post(
        "/api/v1/assessments",
        json={"child_id": child_id, "type": "articulation", "severity": 7},
    )
    assert resp.status_code == 422
