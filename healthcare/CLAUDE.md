# CLAUDE.md — Healthcare domain

Guidance for working in `healthcare/`. See the root
[CLAUDE.md](../CLAUDE.md) for repository-wide conventions.

## Contents

| Skill | Focus |
|---|---|
| [hospital-patient-flow-platform](hospital-patient-flow-platform/) | Hospital operational intelligence: Excel ingestion, 54 indicators, forecasting, six bilingual command centres |

## How this domain differs from the rest of the repository

Most skills in this library are documentation packages with small
stdlib-only helper scripts. The healthcare domain contains a **working
platform** — a FastAPI backend, a PostgreSQL schema, a Next.js frontend
and a test suite. That is a deliberate exception, not a drift from the
repo's conventions:

* Hospital indicators are only useful when their numerator, denominator
  and edge cases are pinned down exactly. Prose cannot do that; running
  code with tests can.
* The definitional decisions (occupancy-weighted patient days, excluding
  ED bays from inpatient capacity, hospital-acquired-only harm rates) are
  the actual value. They are worth nothing as advice and a great deal as
  an implementation someone can diff against their own.

Consequently this folder carries dependencies (`pandas`, `scikit-learn`,
`fastapi`, `next`) that the root CLAUDE.md discourages elsewhere. Keep new
healthcare skills that are *advisory* stdlib-only in the usual way; this
exception applies to the platform, not to the domain.

## Working on the platform

Read `hospital-patient-flow-platform/SKILL.md` first — it lists the metric
conventions that must survive any refactor.

**Before changing a metric**, check `docs/data-dictionary.md` for its
current definition and `backend/tests/test_analytics.py` for the
hand-computed expectation. Test expectations are derived on paper from the
fixtures, so a failing test means the code changed behaviour, not that a
golden file went stale.

**After changing dataset contracts or the metric catalogue**, regenerate
the dictionary:

```bash
python scripts/build_data_dictionary.py
```

**Keep SQL and Python in step.** `db/views.sql` expresses the same metric
definitions the Python layer computes, so BI users who bypass the API get
identical numbers. Changing one without the other reintroduces exactly the
"two versions of the truth" problem the platform exists to remove.

## Clinical safety rules

Non-negotiable for anything added here:

1. **No clinical decision support.** Operational prioritisation only. The
   patient risk score carries a disclaimer in the API payload and the UI;
   keep it there.
2. **No direct patient identifiers** in any dataset contract. MRNs are
   hashed at ingest; there is no field for a name, national ID, address or
   phone number, and none should be added.
3. **Never fabricate a metric on incomplete data.** A rate over an empty
   denominator returns `null`, not zero. If a hospital cannot supply
   `present_on_admission`, the HAI rate is unavailable — say so rather
   than computing something indefensible.
4. **Report model weakness.** Forecast skill against persistence is shown
   even when negative. Do not add a code path that hides it.
5. **Synthetic data only** in the repository. All sample data is
   generated; no real patient data is ever committed.

## Adding a new indicator

1. Add a `MetricDefinition` to `backend/app/analytics/benchmarks.py` with
   its label in both languages, unit, definition, numerator, denominator,
   thresholds and source standard.
2. Compute it in the relevant module (`capacity`, `ed`, `journey`,
   `quality`, `nursing`) using `make_metric`.
3. Add the equivalent SQL to `db/views.sql`.
4. Add a test with a hand-computed expectation.
5. Regenerate the data dictionary.
6. If a role should lead with it, add the key to `ROLE_TILES` in
   `backend/app/analytics/service.py`.

## Adding a new import dataset

1. Add a `DatasetSpec` to `backend/app/ingest/datasets.py` — fields,
   types, required flags, code sets, aliases (English, Arabic and vendor
   spellings), chronology rules.
2. Add it to `LOAD_ORDER` in dependency order.
3. Add a promoter function in `backend/app/ingest/loader.py` and register
   it in `_PROMOTERS`.
4. Add the tables to `db/schema.sql` and the ORM mappings to
   `backend/app/models.py`, both carrying `batch_id` so loads stay
   reversible.
5. Regenerate the dictionary and the Excel templates.
