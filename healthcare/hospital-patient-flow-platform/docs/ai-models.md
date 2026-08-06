# Predictive models

Six models, all deliberately modest: regularised linear models, gradient
boosting and isolation forests. They train in seconds on one hospital's
history, run without a GPU, and can be explained to a clinical governance
committee. A model nobody trusts changes no decision, and an unexplainable
bed forecast does not survive its first disagreement with a charge nurse.

Every model is trained **per facility**. Case mix, bed counts and
discharge culture differ enough that a model fitted on one hospital
transfers badly to another, and training is cheap enough to do on demand.

## Validation approach

All models use **forward-chaining** splits: train on the past, test on the
future, never the reverse. Random k-fold on a time series leaks tomorrow
into today and inflates scores badly — a bed occupancy model can look
excellent under k-fold and be useless in production.

Two guardrails are built in:

* **Below 60 observations, no model is fitted.** The platform returns a
  weekly seasonal-naive baseline and says so in `fallback_reason`. That
  baseline is genuinely competitive for hospital occupancy, so falling
  back is not a failure — but the caller is told, so the UI can label it
  honestly instead of implying a trained model.
* **Skill against persistence is always reported**, including when it is
  negative. `skill_vs_baseline_pct` compares the model's backtest MAE
  against carrying the last value forward. A negative number means the
  model is not earning its place, and hiding that would be the single most
  misleading thing this platform could do.

## 1. Bed occupancy forecast

| | |
|---|---|
| **Algorithm** | `GradientBoostingRegressor` (200 trees, depth 3, lr 0.05) |
| **Target** | Facility occupancy rate, 1–14 days ahead |
| **Features** | Lags 1/2/3/7/14 · rolling 3/7/14 mean and std · same-weekday expanding mean · cyclical day-of-week and month · Friday–Saturday weekend flag |
| **Validation** | 4-fold forward chaining, MAE vs carry-forward |
| **Reference result** | 120 training days, MAE 6.1 occupancy points |

Multi-step forecasting is **recursive**: each predicted day is fed back as
the lag for the next, which is what lets a 14-day horizon respond to its
own trajectory rather than flattening to the mean.

The uncertainty band is derived from the **backtest MAE**, not from
in-sample residuals. A boosted tree's in-sample residuals are a fraction
of the error it makes on unseen days; using them produced a band of ±0.3
points on a 14-day forecast, which looks authoritative and is worse than
useless for capacity planning. Sigma is taken as `MAE × 1.2533` (the
normal-error conversion) and the band widens with `√horizon`, capped at 3×
so day 14 stays readable.

## 2. ICU utilisation forecast

Same architecture, restricted to units of kind `ICU`, `NICU` and `HDU`.
Reported separately because critical-care capacity fails differently from
ward capacity: there is no corridor, and a full ICU cancels theatre lists.

## 3. Discharge demand forecast

Same architecture, target = discharges per day, horizon 7 days. Feeds
discharge-lounge and transport planning. On the reference dataset this one
barely beats persistence (+8% skill), which is reported plainly.

## 4. Emergency department crowding

| | |
|---|---|
| **Algorithm** | `GradientBoostingClassifier` |
| **Target** | Will NEDOCS exceed 100 four hours from now? |
| **Features** | Current census, boarders, arrivals · lags 1/2/3/6/12/24/168 h · rolling 6 h and 24 h means · same hour on each of the previous 3 days · hour-of-day cyclical encoding · night flag |
| **Validation** | Forward-chaining ROC AUC |
| **Reference result** | AUC 0.83 on 60 days of hourly history |

Framed as **classification, not regression**, because the decision it
supports is binary: open the surge area and call in staff, or don't. A
predicted NEDOCS of 97 versus 103 is a distinction without a difference;
"probably overcrowded by 18:00" is actionable.

The hourly ED state is reconstructed from a flat visit extract, so
retrospective crowding analysis needs no live feed. NEDOCS is an
*instantaneous* instrument — census is counted as `arrival ≤ t < departure`
at the top of each hour, not as anyone who passed through it.

## 5. Anomaly detection

| | |
|---|---|
| **Algorithm** | `IsolationForest` (200 trees, 5% contamination) + robust z-score attribution |
| **Input** | Daily matrix: occupancy, census, admissions, discharges, deaths, ED arrivals, LWBS |

Isolation Forest supplies the multivariate view — a day where nothing is
individually extreme but the combination is unusual. A **median/MAD**
z-score then names which indicator drove the flag, because "day 12 is
anomalous" is not actionable on its own. Median and MAD rather than mean
and standard deviation: one extreme day would otherwise inflate the spread
and hide its neighbours.

Days at the edges of the loaded history are trimmed before detection. A
hospital that loads two years of movements but six months of ED visits
would otherwise have its entire contamination budget spent on the
ramp-up, and the real surge in the middle of the period would never
surface.

## 6. Patient risk scoring

| | |
|---|---|
| **Algorithm** | `LogisticRegression`, balanced class weights |
| **Target** | Prolonged length of stay (above this hospital's own 75th percentile) or 30-day readmission |
| **Features** | Admission hour and weekday · weekend flag · elective flag · CTAS · ED boarding hours · arrival by ambulance · units visited · ICU exposure · prior admissions |

Logistic regression on purpose: coefficients are inspectable, the output
is a calibrated probability, and a governance committee can be shown
exactly what drives a flag. The API returns the top contributing features
with each score.

"Prolonged" is defined against **this hospital's own distribution** rather
than an imported constant, so it stays meaningful across very different
case mixes.

> **This is an operational prioritisation aid for the patient-flow team.
> It is not a clinical decision support tool, is not validated for
> individual treatment decisions, and must not be presented as either.**
> The disclaimer is returned in the API payload and rendered in the UI.

On the reference synthetic dataset this model achieves AUC 0.56 — barely
better than chance, because synthetic length of stay is close to pure
lognormal noise. It is reported rather than hidden. On real data with real
comorbidity signal the figure would be expected to be materially higher,
and the honest thing is to let each hospital see its own number.

## 7. Bottleneck anticipation

Not a model — a rules layer over the forecasts that turns predictions into
dated, actionable warnings:

* Forecast occupancy ≥ 92% → escalate discharge planning, review electives
* Forecast ICU ≥ 90% → confirm step-down capacity and surge staffing
* Occupancy ≥ 85% **combined with** expected discharges below 70% of
  typical → flow gridlock warning

The third rule is the one that matters. High occupancy alone is survivable;
high occupancy on a day with unusually few expected discharges is what
produces corridor care. A forecast nobody translates into "Thursday will
be tight, start the discharge round early" changes nothing, so the
threshold and the recommended action ship attached to the number.

## Model governance

`ml_model` records every training run — algorithm, feature names, row
count, backtest metrics, timestamp. `ml_prediction` stores each forecast
with its horizon, and `backfill_actuals()` fills in what actually happened
once the horizon elapses.

`GET /api/v1/predictions/accuracy` reports realised MAE per target. Without
that endpoint the platform could claim accuracy but never demonstrate it;
with it, the model-performance page is real rather than decorative.

## Deliberate omissions

* **No deep learning.** On single-hospital datasets of a few hundred days
  it would overfit, and it would forfeit the explainability that gets a
  model adopted.
* **No external data** (weather, public holidays, epidemic feeds). Each
  would add signal, and each adds an integration dependency that must be
  maintained. They are the obvious next increment once the platform has
  earned its place.
* **No cross-hospital pooling.** Attractive for cluster-level deployment,
  but it raises data-sharing questions that belong to the customer, not to
  the platform's defaults.
