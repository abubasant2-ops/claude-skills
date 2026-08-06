"""HTTP contract tests against the fixture hospital."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.core.db import SessionLocal, get_session
from app.main import create_app


@pytest.fixture
def client(session, hospital):
    app = create_app()

    # Route the API at the same in-memory database the fixture populated.
    def override_session():
        db = SessionLocal()
        try:
            yield db
            db.commit()
        finally:
            db.close()

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client


def test_health_reports_database_state(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "up"


def test_metric_catalogue_is_bilingual(client):
    body = client.get("/api/v1/metrics/catalogue").json()
    assert body["count"] > 40
    for metric in body["metrics"]:
        assert metric["label_en"]
        assert metric["label_ar"]
        assert metric["definition_en"]


def test_metrics_endpoint_returns_values_for_the_window(client, hospital):
    response = client.get("/api/v1/metrics", params={
        "facility_id": hospital["facility"].facility_id,
        "start": hospital["start"].isoformat(),
        "end": hospital["end"].isoformat(),
    })
    assert response.status_code == 200
    body = response.json()
    keys = {m["key"] for m in body["metrics"]}
    assert {"occupancy_rate", "alos_days", "nchpd"} <= keys
    assert body["coverage"]["encounters"] == 10


@pytest.mark.parametrize("role", ["CEO", "COO", "CNO", "ED_DIRECTOR", "QUALITY", "BED_MANAGER"])
def test_every_role_dashboard_renders(client, hospital, role):
    response = client.get(f"/api/v1/dashboards/{role}", params={
        "facility_id": hospital["facility"].facility_id,
        "start": hospital["start"].isoformat(),
        "end": hospital["end"].isoformat(),
    })
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == role
    assert len(body["tiles"]) == 8
    assert "sections" in body


def test_unknown_role_returns_404(client):
    assert client.get("/api/v1/dashboards/JANITOR").status_code == 404


def test_period_preset_is_accepted(client, hospital):
    response = client.get("/api/v1/metrics", params={
        "facility_id": hospital["facility"].facility_id, "preset": "last_30d",
    })
    assert response.status_code == 200


def test_invalid_preset_is_rejected_with_a_useful_message(client):
    response = client.get("/api/v1/metrics", params={"preset": "last_fortnight"})
    assert response.status_code == 400
    assert "Unknown preset" in response.json()["detail"]


def test_reversed_date_range_is_rejected(client):
    response = client.get("/api/v1/metrics", params={"start": "2026-03-10", "end": "2026-03-01"})
    assert response.status_code == 400


def test_missing_facility_returns_404(client):
    response = client.get("/api/v1/metrics", params={
        "facility_id": 999, "start": "2026-03-01", "end": "2026-03-10",
    })
    assert response.status_code == 404


def test_trend_rejects_unknown_metric_keys(client):
    response = client.get("/api/v1/trends", params={
        "metric_keys": ["not_a_real_metric"], "start": "2026-03-01", "end": "2026-03-05",
    })
    assert response.status_code == 400
    assert "Unknown metric key" in response.json()["detail"]


def test_trend_returns_one_point_per_bucket(client, hospital):
    response = client.get("/api/v1/trends", params={
        "metric_keys": ["occupancy_rate"],
        "facility_id": hospital["facility"].facility_id,
        "start": "2026-03-01", "end": "2026-03-05", "grain": "day",
    })
    body = response.json()
    assert len(body["labels"]) == 5
    assert len(body["series"]["occupancy_rate"]) == 5


def test_csv_export_carries_a_bom_for_excel(client, hospital):
    response = client.get("/api/v1/export", params={
        "facility_id": hospital["facility"].facility_id,
        "start": hospital["start"].isoformat(), "end": hospital["end"].isoformat(),
        "fmt": "csv", "scope": "metrics",
    })
    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert "attachment" in response.headers["content-disposition"]


def test_import_dataset_contract_is_published(client):
    body = client.get("/api/v1/import/datasets").json()
    keys = {d["key"] for d in body["datasets"]}
    assert {"encounters", "ed_visits", "bed_movements", "staffing"} <= keys
    assert body["load_order"][0] == "units"


def test_upload_rejects_an_unsupported_file_type(client):
    response = client.post(
        "/api/v1/import/upload",
        data={"dataset": "ed_visits", "facility_id": "1"},
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert response.status_code == 415


def test_upload_rejects_an_unknown_dataset(client):
    response = client.post(
        "/api/v1/import/upload",
        data={"dataset": "not_a_dataset", "facility_id": "1"},
        files={"file": ("x.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
    )
    assert response.status_code == 404


def test_upload_round_trip_produces_a_quality_report(client, hospital):
    csv = (
        "Visit No,Arrival Time,Triage Time,Acuity,Disposition\n"
        "E000,2026-03-01 05:00:00,2026-03-01 05:10:00,3,ADMIT\n"
        "E001,2026-03-02 05:00:00,2026-03-02 05:12:00,4,DISCHARGE\n"
    ).encode()

    response = client.post(
        "/api/v1/import/upload",
        data={"dataset": "ed_visits", "facility_id": str(hospital["facility"].facility_id),
              "dry_run": "true"},
        files={"file": ("ed.csv", io.BytesIO(csv), "text/csv")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["row_count"] == 2
    assert body["state"] == "VALIDATED"
    # The vendor headers must have been resolved onto canonical fields.
    assert body["column_mapping"]["encounter_no"] == "Visit No"
    assert body["column_mapping"]["arrival_at"] == "Arrival Time"
    assert body["quality_score"] > 80

    detail = client.get(f"/api/v1/import/batches/{body['batch_id']}").json()
    assert detail["dataset"] == "ed_visits"
    assert "findings" in detail


def test_admin_can_override_a_benchmark(client):
    response = client.put("/api/v1/admin/benchmarks", json={
        "metric_key": "occupancy_rate", "target_value": 78.0,
        "amber_threshold": 85.0, "red_threshold": 92.0, "source": "INTERNAL",
    })
    assert response.status_code == 200

    body = client.get("/api/v1/admin/benchmarks").json()
    configured = {b["metric_key"]: b for b in body["configured"]}
    assert configured["occupancy_rate"]["target"] == 78.0


def test_benchmark_override_rejects_unknown_metrics(client):
    response = client.put("/api/v1/admin/benchmarks", json={"metric_key": "made_up"})
    assert response.status_code == 400


def test_predictions_endpoint_degrades_gracefully_on_thin_history(client, hospital):
    """Ten days of data cannot train a forecaster; the API must say so
    rather than return a confident-looking number."""
    response = client.get("/api/v1/predictions", params={
        "facility_id": hospital["facility"].facility_id,
        "as_of": hospital["end"].isoformat(), "horizon_days": 7,
    })
    assert response.status_code == 200
    body = response.json()
    model = body["occupancy_forecast"]["model"]
    assert model["fallback_reason"]
    assert "SeasonalNaive" in model["algorithm"] or model["algorithm"] == "unavailable"
