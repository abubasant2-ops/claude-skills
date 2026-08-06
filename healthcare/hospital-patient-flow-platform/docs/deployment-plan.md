# Deployment plan

A phased rollout for a large tertiary hospital. The sequencing is the
important part: the platform is only as credible as its first number, so
data quality is settled before any dashboard is shown to an executive.

## Phase 0 — Prerequisites (before week 1)

| Item | Owner | Why it blocks |
|---|---|---|
| Named data owner per source system | Hospital IT | Someone must be accountable when an extract stops arriving |
| Facility timezone agreed and applied to the database | Hospital IT | Day boundaries in the SQL views resolve against it; UTC silently shifts every daily total |
| Extract capability confirmed for each dataset | HIS / LIS / HR vendors | Determines which command centres can launch |
| PostgreSQL 16 instance with backup and PITR | Hospital IT | The platform does not deploy its own database |
| `HPF_MRN_SALT` generated and stored in the secret manager | Security | Rotating it later re-pseudonymises every patient and breaks longitudinal linkage — treat it as permanent |
| Data-sharing and privacy sign-off (PDPL) | Compliance | Confirms no direct identifiers leave the source systems |
| Bed inventory: staffed beds per unit, not licensed | Bed management | The single most common cause of a wrong occupancy figure |

**On staffed vs licensed beds.** Occupancy is only meaningful against the
beds that are actually open and staffed. Hospitals routinely supply the
licensed count, which understates occupancy by 10–20 points and makes a
department in crisis look comfortable. Settle this in Phase 0, in writing.

## Phase 1 — Foundation (weeks 1–3)

1. Deploy the API and database to a non-production environment.
2. Load `units` with the agreed staffed-bed inventory.
3. Import 12 months of `encounters` and `bed_movements` history.
4. Review the data quality report with the data owners. Iterate on the
   extract until the quality score is stable above 85.
5. Reconcile occupancy and ALOS against the hospital's existing monthly
   returns.

**Exit criterion:** finance and bed management both agree the occupancy
and ALOS figures are correct. Do not proceed until they do. A platform
that argues with the monthly return loses that argument permanently.

## Phase 2 — Emergency and journey (weeks 4–6)

1. Add `ed_visits` and `orders`.
2. Validate door-to-physician and ED LOS against any existing ED report.
3. Calibrate NEDOCS inputs — ED treatment spaces and total hospital beds
   drive the score and are frequently mis-stated.
4. Launch the **Emergency** and **Operations** command centres to their
   directors only.

**Exit criterion:** the ED director recognises their department in the
numbers. If NEDOCS reads "dangerously overcrowded" at 04:00 on a Tuesday,
the inputs are wrong, not the department.

## Phase 3 — Quality, nursing and executive (weeks 7–10)

1. Add `safety_events`, `staffing`, `vitals`, `icu_stays`, `or_cases`.
2. Reconcile harm rates against the incident reporting system's own
   figures. Confirm the `present_on_admission` flag is populated —
   without it, community-acquired infections are counted as the
   hospital's.
3. Review the census reconciliation panel: where the roster's census and
   the ADT trail disagree by more than 10%, one of the two feeds is wrong.
4. Override default benchmarks with the hospital's own targets through
   `PUT /api/v1/admin/benchmarks`.
5. Launch **Nursing**, **Quality**, **Bed Management** and **Executive**.

## Phase 4 — Prediction (weeks 11–14)

Only after at least 6 months of clean history is loaded.

1. Train the forecast and crowding models; review backtest metrics.
2. Run forecasts in shadow mode for four weeks — generated and stored,
   not shown.
3. Review `GET /api/v1/predictions/accuracy` with the operations team.
4. Release forecasts only for targets where skill against carry-forward is
   positive. A model that does not beat "assume tomorrow looks like today"
   should not be driving a staffing decision.

**This phase can legitimately end with some models withheld.** That is a
successful outcome, not a failed one.

## Phase 5 — Scheduled operation (week 15 onward)

Automate the daily extract-and-load, monitor quality scores, and review
the trend of the quality score itself: a slow decline usually means a
source system changed and nobody said so.

## Environments

| Environment | Purpose | Data |
|---|---|---|
| Development | Feature work | Synthetic (`scripts/generate_sample_data.py`) |
| Staging | Extract validation, UAT | De-identified copy of one month |
| Production | Live | Real extracts |

## Deploying

### Local / demo

```bash
docker compose up -d --build
docker compose exec api python scripts/generate_sample_data.py --days 180
docker compose exec api python scripts/load_demo.py --data data/samples
# API   http://localhost:8000/docs
# Web   http://localhost:3000
```

### Kubernetes

```bash
kubectl apply -f deploy/k8s/manifests.yaml
kubectl -n hpf create secret generic hpf-secrets \
  --from-literal=HPF_DATABASE_URL='postgresql+psycopg://...' \
  --from-literal=HPF_MRN_SALT="$(openssl rand -hex 32)" \
  --dry-run=client -o yaml | kubectl apply -f -
```

The manifests deploy the API (3 replicas, HPA to 12), the web tier
(2 replicas), a PDB, a NetworkPolicy limiting API ingress to the web tier
and the ingress controller, and an Ingress with a 200 MB body limit for
uploads. **The database is intentionally not included** — a hospital's
PostgreSQL should be a managed instance with backup, PITR and its own DR
plan, not a StatefulSet nobody owns.

### Schema

`db/00_timezone.sql`, then `db/schema.sql`, then `db/views.sql`, in that
order. Compose mounts all three as init scripts. For an existing database,
apply through Alembic so the change is recorded.

**The timezone step is not optional.** The analytical views bucket
`TIMESTAMPTZ` values into days using the session timezone. At the
PostgreSQL default of UTC, a hospital in Asia/Riyadh gets day boundaries
at 03:00 local: a patient discharged at 01:00 Tuesday counts against
Monday, and SQL totals diverge from the API's by roughly three hours of
census at each window edge. It is small enough to go unnoticed and large
enough to be wrong. Set it on the database so psql and Power BI sessions
inherit it too, and keep it equal to `HPF_FACILITY_TIMEZONE`:

```sql
ALTER DATABASE hpf SET timezone TO 'Asia/Riyadh';
```

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `HPF_DATABASE_URL` | SQLite file | PostgreSQL in every real deployment |
| `HPF_MRN_SALT` | dev placeholder | **The API refuses to start in production while this is unchanged** |
| `HPF_ENVIRONMENT` | `development` | `production` enables the salt check |
| `HPF_MIN_QUALITY_SCORE_TO_LOAD` | 60 | Batches below this are staged for review |
| `HPF_MAX_UPLOAD_MB` | 100 | Match the ingress body limit |
| `HPF_FACILITY_TIMEZONE` | `Asia/Riyadh` | Naive timestamps are localised to this |
| `HPF_CORS_ORIGINS` | `localhost:3000` | The web tier's public origin |
| `NEXT_PUBLIC_API_BASE` | `localhost:8000` | Inlined at frontend **build** time |

## Operating

**Daily.** Scheduled extract → `POST /api/v1/import/upload` per dataset in
load order. Alert if any batch state is not `LOADED`, or if a quality
score drops more than 10 points against its trailing average.

**Weekly.** Review quarantined rows with the data owner. Persistent
quarantine of the same rule means the extract needs fixing at source, not
tolerating.

**Monthly.** Re-run forecast accuracy. Review benchmark overrides against
current targets.

**Backups.** Database on the hospital's standard schedule. The uploads
volume holds the original source files and is part of the audit trail —
it must be backed up too. Losing it does not lose the data, but it does
lose the ability to prove where a number came from.

**Rollback.** Application: redeploy the previous image tag; the schema is
additive within a minor version. A bad import:
`POST /api/v1/import/batches/{id}/reverse` deletes exactly the rows that
batch created.

## Monitoring

| Signal | Where | Alert on |
|---|---|---|
| API liveness | `GET /health` | Non-200, or `database: down` |
| Request latency | `X-Response-Time-ms` header; >3 s is logged | p95 above 5 s |
| Import success | `GET /api/v1/import/batches` | Any state ≠ `LOADED` |
| Data quality | `quality_score` per batch | Below 70, or a 10-point drop |
| Freshness | `loaded_at` of the newest batch | Older than 36 hours |
| Forecast accuracy | `GET /api/v1/predictions/accuracy` | MAE drift beyond 1.5× baseline |

## Risks

| Risk | Mitigation |
|---|---|
| Extract silently changes shape | Column mapping is recorded per batch and diffed; unmapped columns are reported on every upload |
| Staffed-bed inventory goes stale | Occupancy above 100% for a unit is a strong signal the inventory is wrong; surfaced as an alert |
| Executives act on a metric they misread | Every tile carries its target, its definition is in the data dictionary, and every rate returns `null` rather than 0 on an empty denominator |
| Forecasts trusted beyond their accuracy | Skill against persistence is displayed with every forecast, including when negative |
| Risk score used clinically | Disclaimer in the API payload and the UI; scoring is deliberately restricted to operational features |
