def test_create_and_get_user(client):
    resp = client.post(
        "/api/v1/users",
        json={"role": "slp", "email": "slp@example.com", "password": "secret123"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["role"] == "slp"
    assert body["email"] == "slp@example.com"
    assert "password" not in body
    assert "password_hash" not in body

    resp = client.get(f"/api/v1/users/{body['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == body["id"]


def test_create_user_requires_contact(client):
    resp = client.post(
        "/api/v1/users", json={"role": "parent", "password": "secret123"}
    )
    assert resp.status_code == 422


def test_duplicate_email_conflict(client):
    payload = {"role": "parent", "email": "dup@example.com", "password": "secret123"}
    assert client.post("/api/v1/users", json=payload).status_code == 201
    assert client.post("/api/v1/users", json=payload).status_code == 409
