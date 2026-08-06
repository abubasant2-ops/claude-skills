---
name: hospital-patient-flow-platform
description: "Hospital patient flow and operational intelligence platform. Use when analysing hospital operational data, building capacity or bed management dashboards, measuring emergency department performance, calculating occupancy, ALOS, bed turnover, NEDOCS crowding, door-to-doctor or boarding times, computing quality and patient safety indicators (readmissions, HAI, falls, pressure injuries, medication errors, NEWS2), nursing indicators (NCHPD, skill mix, turnover, vacancy), forecasting bed demand or ED crowding, importing hospital Excel extracts, or preparing evidence for CBAHI, JCI, Magnet or Saudi HSTP accreditation."
---

# Hospital Patient Flow & Operational Intelligence Platform

A working platform, not a template. It ingests hospital Excel/CSV
extracts, validates and scores them, computes 54 operational, clinical
and quality indicators with explicit numerators and denominators, forecasts
capacity pressure, and serves six role-specific command centres in Arabic
and English.

## When to use this skill

Use it when the task involves:

- Analysing hospital operational data (occupancy, length of stay, patient flow)
- Building or reviewing bed management, ED, quality or nursing dashboards
- Defining or auditing a hospital indicator's numerator and denominator
- Importing messy hospital extracts and reporting their data quality
- Forecasting bed occupancy, ICU demand or ED crowding
- Preparing indicator evidence for CBAHI, JCI, Magnet or Saudi HSTP

Do **not** use it for clinical decision support, individual patient
treatment decisions, billing, or as a source of truth for the medical
record.

## Getting started

```bash
python scripts/generate_sample_data.py --days 120 --out data/samples
python scripts/load_demo.py --data data/samples
cd backend && uvicorn app.main:app --reload      # http://localhost:8000/docs
cd frontend && npm install && npm run dev        # http://localhost:3000
```

`docker compose up -d --build` runs the same stack on PostgreSQL.

## Structure

```
backend/app/ingest/      dataset contracts, column mapper, validators, loader
backend/app/analytics/   capacity, ed, journey, quality, nursing, benchmarks
backend/app/ml/          forecasting, crowding, anomalies, patient risk
backend/app/api/         FastAPI routers
db/                      PostgreSQL schema and analytical views
frontend/                Next.js command centres (AR/EN, RTL)
scripts/                 sample data, loader, Excel templates, doc generator
docs/                    architecture, API, data dictionary, wireframes,
                         AI models, deployment, compliance mapping
```

## Metric definitions that differ from the naive version

These are the decisions that determine whether the numbers survive contact
with a hospital's finance department. If you are adapting this skill,
carry them across.

**Patient days are occupancy-weighted.** `analytics/common.expand_to_days`
splits every bed occupancy interval across the calendar days it touches.
A 22:00 Monday → 06:00 Wednesday stay gives 0.083 / 1.0 / 0.25, not "two
midnights". Midnight census makes short-stay and observation activity
disappear.

**ED treatment spaces are excluded from inpatient occupancy.** Including a
56-bay ED in a 500-bed hospital understates ward occupancy by ~10 points.
Nursing indicators *do* include the ED, because emergency nursing hours
need a real denominator — so the service computes two occupancy frames.

**Harm rates count hospital-acquired events only**, per 1,000 patient
days. `present_on_admission = true` is excluded from the numerator.

**Timing metrics report medians**, with p90 in each tile's `context`.

**NEDOCS is instantaneous.** Census at the top of each hour is
`arrival ≤ t < departure`, not interval overlap — overlap inflates census
and produces negative waiting times.

**Readmission looks past the reporting window.** The denominator is index
discharges inside the period; the numerator searches the following 30
days, so the repository loads a deliberately wider slice.

**Rates return `null`, not zero, on an empty denominator.**

**Timestamps are localised to the facility timezone on load.** The
warehouse stores `TIMESTAMPTZ`; PostgreSQL returns timezone-aware values
and SQLite naive ones. `analytics/repository._localise` converts to
facility-local wall time so "hour of day" means the hour the ward
experienced. The SQL views need the matching database timezone —
`db/00_timezone.sql` — or they disagree with the API by the UTC offset.

**Nursing turnover annualises**: separations are summed but headcount is a
stock, averaged within each unit and then summed across units. Averaging
across the whole frame divides a hospital-wide count by one unit's
headcount and inflates turnover several-fold.

## Ingestion behaviour worth reusing

- **Header detection** scans the first 12 rows and scores each against the
  dataset's known fields — hospital reports carry title blocks.
- **Column mapping runs in three passes**: declared names and aliases,
  then suffix-derived forms, then fuzzy match above 0.86. Derived forms
  must rank below declared ones, or a column headed "Disposition" is
  captured by `disposition_at`'s stem instead of `ed_disposition`.
- **Date format is detected once per column** and applied vectorised.
  Deciding `03/04/2026` row by row is a coin flip; deciding it from the
  whole column is evidence-based and ~5× faster.
- **Rows are quarantined, not batches.** Only a missing required *column*
  is fatal.
- **Quality scoring** uses the five DAMA dimensions so the number is
  defensible in a data-integrity review.

## Predictive layer

Modest algorithms on purpose — gradient boosting, logistic regression,
isolation forest. All validated with forward-chaining splits.

The single most important convention: **`skill_vs_baseline_pct` is
reported even when negative.** It compares backtest MAE against carrying
the last value forward. Below 60 observations no model is fitted at all —
a weekly seasonal-naive baseline is returned with `fallback_reason` set,
so the UI can label it honestly.

Prediction intervals derive from backtest MAE, not in-sample residuals. A
boosted tree's in-sample residuals produced a ±0.3-point band on a 14-day
occupancy forecast: authoritative-looking and useless.

## Standards

Indicator definitions follow CBAHI, JCI, Magnet/NDNQI and Saudi HSTP
conventions. `docs/compliance-mapping.md` maps each requirement to the
indicator that evidences it, and states the limitations honestly — no
case-mix adjustment, coverage depends on the extract, and the platform
evidences compliance rather than conferring it.

## Verification

```bash
python -m pytest backend/tests -q        # 77 tests, no database needed
cd frontend && npx tsc --noEmit && npm run build

# SQL/Python parity, needs a loaded PostgreSQL warehouse (skips without one)
HPF_TEST_POSTGRES_URL=postgresql+psycopg://... \
  python -m pytest backend/tests/test_sql_parity.py -v
```

Tests check metric definitions against hand-computed expectations, not
golden files: fractional patient days, NEDOCS against the published
formula, NEWS2 against the RCP scoring table, readmission inclusion rules,
and the ingestion edge cases (Excel serials, Arabic-Indic digits,
day/month ambiguity, chronology violations).

## Reference documents

| Document | Contents |
|---|---|
| `docs/architecture.md` | System and pipeline diagrams, component boundaries, scaling, security |
| `docs/data-dictionary.md` | All 11 datasets, 127 fields, 54 metrics — generated from code |
| `docs/api-reference.md` | Endpoint contracts, metric shape, error semantics |
| `docs/wireframes.md` | Layout grammar, per-role composition, accessibility, RTL |
| `docs/ai-models.md` | Model cards, validation approach, deliberate omissions |
| `docs/deployment-plan.md` | Five-phase rollout with exit criteria, ops runbook, risks |
| `docs/compliance-mapping.md` | CBAHI / JCI / Magnet / HSTP / PDPL mapping |

All sample data is synthetic. No real patient data is used or reproduced.
