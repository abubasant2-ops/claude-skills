import os

# Must be set before any app import so the cached Settings binds to the test DB.
os.environ["LAFZA_POSTGRES_DB"] = "lafza_test"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.main import app
from app.models import Base

engine = create_engine(get_settings().database_url)


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture()
def db():
    """Session bound to an outer transaction that is rolled back after each test,
    so endpoint commits become savepoints and the test DB stays empty."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def parent_id(client) -> str:
    resp = client.post(
        "/api/v1/users",
        json={"role": "parent", "email": "parent@example.com", "password": "secret123"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.fixture()
def child_id(client, parent_id) -> str:
    resp = client.post(
        "/api/v1/children",
        json={
            "guardian_id": parent_id,
            "dob": "2022-05-01",
            "sex": "male",
            "dialect": "gulf",
            "consent_flags": {"audio_capture": True},
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]
