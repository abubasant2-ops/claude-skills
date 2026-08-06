# API reference

Interactive documentation is served at `/docs` (Swagger UI) and the
machine-readable spec at `/openapi.json`. This page covers the shapes and
conventions that the generated spec does not explain.

Base path: `/api/v1`

## Conventions

**Period selection.** Every analytics endpoint accepts either a preset or
an explicit range:

```
?preset=last_30d              today, yesterday, last_7d, last_30d,
                              last_90d, mtd, qtd, ytd
?start=2026-07-01&end=2026-07-31
```

Windows longer than 400 days are rejected. Daily-grain trends are capped
at 120 days — beyond that the endpoint asks for `grain=week` or
`grain=month` rather than timing out.

**Facility scoping.** `?facility_id=1` on every endpoint. A missing
facility returns 404, not an empty result.

**Null means "no data", never zero.** A rate over an empty denominator
returns `null`. A closed unit reports no data rather than 0%, because 0%
occupancy and "this unit was shut" are different facts.

**Errors.** `{"detail": "..."}` with a message written for the person who
made the request:

| Status | Meaning |
|---|---|
| 400 | Bad period, unknown metric key, unknown preset, window too wide |
| 404 | Unknown facility, role, dataset or batch |
| 413 | Upload exceeds `HPF_MAX_UPLOAD_MB` |
| 415 | File is not `.xlsx`, `.xlsm` or `.csv` |
| 409 | The same file has already been loaded into this dataset |

Every response carries `X-Response-Time-ms`.

---

## Import

| Endpoint | Purpose |
|---|---|
| `GET /import/datasets` | Every importable dataset, its fields, types, required flags, code sets and recognised header aliases |
| `POST /import/preview` | Profile a file and return the proposed column mapping. **No database writes** |
| `POST /import/upload` | Validate and load. `dry_run=true` stops after validation |
| `GET /import/batches` | Import history |
| `GET /import/batches/{id}` | Full data quality report for one batch |
| `POST /import/batches/{id}/reverse` | Delete exactly the rows that batch created |

`POST /import/upload` is `multipart/form-data`:

| Field | Required | Notes |
|---|---|---|
| `dataset` | yes | One of the keys from `/import/datasets` |
| `file` | yes | `.xlsx`, `.xlsm` or `.csv` |
| `facility_id` | no | Default 1 |
| `sheet` | no | Auto-selected by header match when omitted |
| `dry_run` | no | Default false |
| `uploaded_by` | no | Recorded in the audit trail |

Response:

```json
{
  "batch_id": 47,
  "dataset": "ed_visits",
  "row_count": 27648,
  "accepted_rows": 27352,
  "rejected_rows": 296,
  "loaded_rows": 27352,
  "quality_score": 99.6,
  "state": "LOADED",
  "column_mapping": { "encounter_no": "Visit No", "arrival_at": "Arrival Time" },
  "unmapped_columns": ["Vendor Internal Ref"],
  "missing_optional_fields": ["arrival_mode"],
  "validation": {
    "quality_score": 99.6,
    "dimension_scores": {
      "completeness": 98.4, "validity": 100.0, "uniqueness": 99.8,
      "consistency": 99.0, "timeliness": 100.0
    },
    "rejected_rows": 296,
    "findings": [
      {
        "rule_code": "CHRONOLOGY_VIOLATION",
        "severity": "ERROR",
        "column_name": "arrival_at -> departure_at",
        "affected_rows": 296,
        "sample_rows": [12, 88, 401],
        "message_en": "296 row(s) have 'departure_at' before 'arrival_at' …",
        "message_ar": "…",
        "dimension": "consistency"
      }
    ]
  }
}
```

**Batch states:** `RECEIVED` → `PROFILED` → `VALIDATED` → `LOADED`, or
`REJECTED` (a `CRITICAL` finding), or `REVERSED`. A batch that validates
below `HPF_MIN_QUALITY_SCORE_TO_LOAD` stops at `VALIDATED` and is held for
human review.

**Severity levels:** `CRITICAL` stops the batch (a required *column* is
missing). `ERROR` quarantines the offending rows and loads the rest.
`WARNING` and `INFO` are reported only. A hospital that cannot import
40,000 good rows because of 12 bad ones simply stops using the platform.

---

## Analytics

| Endpoint | Purpose |
|---|---|
| `GET /facilities` | Facilities available to the caller |
| `GET /metrics/catalogue` | All 54 metric definitions with defaults. `?domain=` filters |
| `GET /metrics` | Every computed indicator for a period. `?domain=` filters |
| `GET /dashboards/{role}` | Role command centre: tiles, alerts, sections, coverage |
| `GET /trends` | Time series. Repeat `metric_keys` for several series |
| `GET /drilldown/units` | Per-unit capacity table plus the occupancy heat map |
| `GET /drilldown/journey` | Journey segments, bottleneck ranking, turnaround, theatre |
| `GET /drilldown/emergency` | Hourly ED state, CTAS mix, arrival profile, disposition mix |
| `GET /drilldown/quality` | Safety events by kind, harm and unit |
| `GET /drilldown/nursing` | Per-unit nursing indicators and census reconciliation |
| `GET /export` | CSV or JSON. `scope` = metrics, units, journey, nursing |

Roles: `CEO`, `COO`, `CNO`, `ED_DIRECTOR`, `QUALITY`, `BED_MANAGER`.

### Metric shape

Every metric everywhere uses this shape:

```json
{
  "key": "ed_boarding_min",
  "label_en": "ED boarding time",
  "label_ar": "مدة الانتظار للتنويم",
  "value": 126.74,
  "unit": "min",
  "numerator": null,
  "denominator": 417,
  "target": 120.0,
  "status": "amber",
  "trend_pct": -3.4,
  "higher_is_better": false,
  "context": { "p90": 402.1, "boarded_over_4h": 68 }
}
```

`status` is the red/amber/green band against the facility's benchmark.
`trend_pct` compares the equivalent preceding window. `context` carries
the supporting detail a tile shows on expansion — the 90th percentile for
timing metrics, the per-type breakdown for composite rates.

**Timing metrics report the median.** ED and journey distributions have
long right tails; one 30-hour boarder moves a mean far more than it moves
the typical patient's experience. The p90 in `context` keeps the tail
visible.

CSV exports are UTF-8 with a BOM so Excel renders the Arabic labels rather
than mojibake.

---

## Predictions

| Endpoint | Purpose |
|---|---|
| `GET /predictions` | Everything: forecasts, crowding, risk, anomalies, warnings |
| `GET /predictions/occupancy` | Occupancy, ICU and discharge forecasts plus warnings |
| `GET /predictions/ed-crowding` | Overcrowding probability 4 hours ahead |
| `GET /predictions/high-risk-patients` | Currently-admitted patients ranked by risk |
| `GET /predictions/anomalies` | Stored anomaly detections |
| `GET /predictions/accuracy` | Realised error against elapsed forecasts |
| `GET /predictions/models` | Model registry |

Every forecast carries its model card:

```json
{
  "target_key": "occupancy_rate",
  "points": [
    { "date": "2026-08-07", "predicted": 81.2, "lower": 59.8,
      "upper": 102.5, "horizon_days": 2 }
  ],
  "model": {
    "algorithm": "GradientBoostingRegressor",
    "training_rows": 120,
    "mae": 6.145,
    "baseline_mae": 5.858,
    "skill_vs_baseline_pct": -4.8,
    "folds": 4
  },
  "drivers": [{ "feature": "occupancy_rate_lag1", "weight": 0.41 }]
}
```

**`skill_vs_baseline_pct` can be negative, and is shown when it is.** It
compares backtest MAE against carrying the last value forward. A bed plan
should not rest on a model that has not beaten "assume tomorrow looks like
today", so the number is surfaced rather than buried.

When history is too thin to train, the response falls back to a weekly
seasonal-naive baseline and states why in `model.fallback_reason`. The UI
labels it as a baseline rather than implying a trained model.

`/predictions/high-risk-patients` returns a `disclaimer` field. It is an
operational prioritisation aid for the flow team — not a clinical decision
support tool, and not validated for individual treatment decisions.

---

## Admin

| Endpoint | Purpose |
|---|---|
| `POST /admin/facilities` | Create a facility |
| `GET /admin/units` | List units |
| `POST /admin/units` | Create or update a unit (upsert by code) |
| `GET /admin/benchmarks` | Configured overrides plus which metrics use defaults |
| `PUT /admin/benchmarks` | Override a metric's target and thresholds |

```http
PUT /api/v1/admin/benchmarks
{ "metric_key": "occupancy_rate", "target_value": 78,
  "amber_threshold": 85, "red_threshold": 92, "source": "INTERNAL" }
```

Overrides apply immediately to every dashboard. Unknown metric keys are
rejected rather than silently stored.

---

## System

`GET /health` returns liveness plus a real database round-trip:

```json
{ "status": "ok", "database": "up",
  "environment": "production", "version": "1.0.0" }
```

`status` degrades to `degraded` when the database check fails, which is
what the Kubernetes readiness probe watches.

---

## Direct SQL access

BI tools can read the warehouse directly. `db/views.sql` expresses the
same metric definitions the API serves — `v_patient_journey`,
`v_unit_day_occupancy`, `v_capacity_month`, `v_ed_day`,
`v_diagnostic_turnaround`, `v_safety_rate_month`, `v_nursing_month`,
`v_readmission`, and the materialised `mv_executive_daily`.

The duplication between SQL and Python is deliberate: a Power BI user who
bypasses the API gets identical numbers rather than a second, quietly
different version of the truth.
`backend/tests/test_sql_parity.py` compares the two on a live PostgreSQL
warehouse and fails if they drift.

**Set the database timezone before relying on these views.** They bucket
`TIMESTAMPTZ` values into days using the session timezone; at the UTC
default a Riyadh hospital's days start at 03:00 local. `db/00_timezone.sql`
pins it, and it must match `HPF_FACILITY_TIMEZONE`.
