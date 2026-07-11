def test_create_and_list_children(client, parent_id):
    resp = client.post(
        "/api/v1/children",
        json={
            "guardian_id": parent_id,
            "dob": "2023-01-15",
            "sex": "female",
            "consent_flags": {"audio_capture": True},
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["guardian_id"] == parent_id
    assert body["dialect"] == "gulf"  # default
    assert body["consent_flags"] == {"audio_capture": True}

    resp = client.get("/api/v1/children", params={"guardian_id": parent_id})
    assert resp.status_code == 200
    assert [c["id"] for c in resp.json()] == [body["id"]]


def test_create_child_unknown_guardian(client):
    resp = client.post(
        "/api/v1/children",
        json={
            "guardian_id": "00000000-0000-0000-0000-000000000000",
            "dob": "2023-01-15",
            "sex": "male",
        },
    )
    assert resp.status_code == 404
