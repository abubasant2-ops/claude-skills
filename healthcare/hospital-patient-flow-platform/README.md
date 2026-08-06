# Hospital Patient Flow & Operational Intelligence Platform

Turns hospital Excel and CSV extracts into operational, clinical and
quality intelligence: capacity, emergency department, patient journey,
safety and nursing indicators, with forecasting on top and bilingual
(Arabic/English) command centre dashboards.

Built for large tertiary hospitals. Metric definitions follow CBAHI, JCI,
Magnet/NDNQI and Saudi HSTP conventions.

---

## What it does

| Module | What you get |
|---|---|
| **Import & data quality** | 11 dataset contracts, automatic column detection across English/Arabic/vendor headers, type inference, 21 validation rules, a five-dimension quality score, row-level quarantine, and fully reversible loads |
| **Patient journey** | Registration → triage → physician → diagnostics → admission decision → bed allocation → ward → theatre → ICU → discharge, every interval measured and ranked by avoidable patient-hours |
| **Capacity** | Occupancy-weighted patient days, ADC, ALOS, bed turnover rate and interval, ICU utilisation, transfers, mortality |
| **Emergency** | CTAS mix, door-to-triage/physician/disposition, ED LOS, boarding, LWBS, LAMA, 72-hour revisits, and hourly NEDOCS crowding reconstructed from a flat visit extract |
| **Quality & safety** | Mortality, 30-day readmission, HAI, falls, pressure injuries, medication errors, code blue, RRT, sepsis bundle, NEWS2 early warning, patient experience |
| **Nursing** | NCHPD, RN HPPD, skill mix, nurse-to-patient ratio, utilisation, overtime, agency, sick leave, vacancy, turnover |
| **Prediction** | Occupancy / ICU / discharge forecasts, ED crowding classifier, anomaly detection, patient risk scoring, dated bottleneck warnings |
| **Dashboards** | Six role command centres — CEO, COO, CNO, ED Director, Quality, Bed Management — in Arabic and English |

54 indicators, each with a definition, a numerator, a denominator, a
benchmark and a source standard. See
[`docs/data-dictionary.md`](docs/data-dictionary.md).

---

## Quick start

```bash
# 1. Backend
cd backend && pip install -r requirements.txt && cd ..

# 2. Generate a realistic synthetic hospital (120 days, ~28k encounters)
python scripts/generate_sample_data.py --days 120 --out data/samples

# 3. Create the schema, seed a facility, run the full import pipeline
python scripts/load_demo.py --data data/samples

# 4. Serve the API
cd backend && uvicorn app.main:app --reload   # http://localhost:8000/docs

# 5. Serve the dashboards
cd frontend && npm install && npm run dev     # http://localhost:3000
```

Or the whole stack on PostgreSQL:

```bash
docker compose up -d --build
```

Build the Excel import templates for your data team:

```bash
python scripts/build_excel_templates.py --out data/templates
```

---

## Deliverables map

| Asked for | Where it is |
|---|---|
| Database schema | [`db/schema.sql`](db/schema.sql) — 25 tables, enums, indexes, constraints |
| SQL structure | [`db/views.sql`](db/views.sql) — 8 analytical views + a materialised rollup |
| System architecture diagram | [`docs/architecture.md`](docs/architecture.md) — Mermaid |
| UI wireframes | [`docs/wireframes.md`](docs/wireframes.md) |
| Dashboard designs | [`frontend/`](frontend/) — working Next.js app, 6 command centres |
| AI models | [`docs/ai-models.md`](docs/ai-models.md) · [`backend/app/ml/`](backend/app/ml/) |
| API architecture | [`docs/api-reference.md`](docs/api-reference.md) · OpenAPI at `/docs` |
| Data dictionary | [`docs/data-dictionary.md`](docs/data-dictionary.md) — generated from code |
| Excel templates | `python scripts/build_excel_templates.py` — 11 workbooks + combined |
| Deployment plan | [`docs/deployment-plan.md`](docs/deployment-plan.md) · [`deploy/k8s/`](deploy/k8s/) |
| Standards mapping | [`docs/compliance-mapping.md`](docs/compliance-mapping.md) |

---

## Design decisions worth knowing

**Occupancy is occupancy-weighted, not midnight census.** A stay from
22:00 Monday to 06:00 Wednesday contributes 0.083 / 1.0 / 0.25 patient
days, not "two midnights". Midnight counting makes short-stay and
observation activity vanish from occupancy reports.

**Emergency treatment spaces are not inpatient beds.** They are excluded
from the occupancy denominator — including a 56-bay ED in a 500-bed
hospital understates ward occupancy by roughly ten points. Nursing
indicators *do* include the ED, because emergency nurses care for real
patients whose hours need a real denominator.

**Timing indicators report medians, with p90 alongside.** One 30-hour
boarder moves a mean far more than it moves the typical patient's
experience.

**Harm rates count hospital-acquired events only**, per 1,000 patient
days. Events flagged `present_on_admission` are excluded. Mixing the two
is the most common reason an infection rate fails a survey.

**Rows are quarantined, not batches.** A file with 12 bad rows out of
40,000 loads the 39,988 and reports the 12. Only a missing required
*column* is fatal.

**Forecast skill is always shown, including when negative.** Every
forecast reports its improvement over carrying the last value forward. A
bed plan should not rest on a model that hasn't beaten "assume tomorrow
looks like today".

**One computation, many dashboards.** Role views are projections over a
single analysis run, so the CEO and the bed manager can never see
different values for the same indicator.

---

## Verification

```bash
python -m pytest backend/tests -q        # 77 tests, no database needed
cd frontend && npx tsc --noEmit && npm run build
```

The 77 tests check metric definitions against hand-computed expectations
(fractional patient days, NEDOCS against the published formula, NEWS2
against the RCP scoring table, readmission inclusion rules), the ingestion
rules (Excel serials, Arabic-Indic digits, day/month ambiguity, duplicate
keys, chronology violations), and the HTTP contract.

Three further tests compare the SQL views against the Python modules on a
real PostgreSQL warehouse. They skip unless one is configured:

```bash
HPF_TEST_POSTGRES_URL=postgresql+psycopg://... \
  python -m pytest backend/tests/test_sql_parity.py -v
```

Verified end to end on the reference dataset — 120 days, 28,138
encounters, 35,925 bed movements, 62,012 orders — on **both** SQLite and
PostgreSQL 16, with identical row counts and quality scores. Full import
takes ~100 seconds.

> **One configuration step matters more than it looks.** The analytical
> views bucket `TIMESTAMPTZ` values into days, and that bucketing resolves
> against the session timezone. Apply `db/00_timezone.sql` (or set
> `timezone` on the database) to the facility's timezone. Left at UTC, a
> Riyadh hospital's day boundaries fall at 03:00 local and SQL totals
> drift from the API's by about three hours of census per window edge —
> small enough to miss, large enough to be wrong.

---

## Repository layout

```
backend/
  app/
    core/        config, engine, session
    models.py    SQLAlchemy mappings for the warehouse
    ingest/      dataset contracts, column mapper, validators, loader
    analytics/   capacity, ed, journey, quality, nursing, benchmarks, service
    ml/          features, models, prediction service
    api/         FastAPI routers
  tests/         77 tests
db/              PostgreSQL schema and analytical views
frontend/        Next.js 15 + Tailwind + ECharts, AR/EN with RTL
scripts/         sample data, demo loader, Excel templates, doc generator
deploy/k8s/      Kubernetes manifests
docs/            architecture, API, data dictionary, wireframes, models,
                 deployment, compliance
data/            generated samples and templates (gitignored)
```

---

## Limitations

* **Batch, not real-time.** Freshness equals the last import. Every
  dashboard shows its period and generation time.
* **Not a clinical decision support tool.** The patient risk score
  prioritises the flow team's review list; it is not validated for
  individual treatment decisions.
* **Mortality and readmission are crude rates** with no case-mix
  adjustment. Comparing units or hospitals on them unadjusted is a misuse.
* **Indicator coverage depends on the extract.** A hospital that cannot
  supply `present_on_admission` cannot get a defensible HAI rate, and the
  platform says so rather than computing one anyway.
* **The platform evidences compliance; it does not confer it.**

---

## Licence

Part of the [claude-skills](../../) library. See [LICENSE](../../LICENSE).

All sample data is synthetic. No real patient data is used or reproduced.
