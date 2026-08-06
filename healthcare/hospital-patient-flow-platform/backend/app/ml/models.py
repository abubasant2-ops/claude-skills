"""Predictive models.

Deliberately modest algorithms -- regularised linear models, gradient
boosting and isolation forests -- chosen because they train in seconds on
a single hospital's history, run without a GPU, and can be explained to a
clinical governance committee. A model nobody trusts does not change a
decision, and unexplainable bed forecasts do not survive their first
disagreement with a charge nurse.

Every model is validated with a *forward-chaining* split: train on the
past, test on the future, never the reverse. Random k-fold on time series
leaks tomorrow into today and inflates scores badly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor, IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import mean_absolute_error, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.ml import features as feat

log = logging.getLogger(__name__)

#: Below this many observations a learned model is worse than a seasonal
#: baseline, so the platform returns the baseline and says so.
MIN_TRAIN_ROWS = 60


@dataclass
class ModelResult:
    """A trained model plus everything needed to explain and audit it."""

    model_key: str
    algorithm: str
    feature_names: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    training_rows: int = 0
    estimator: object | None = None
    fallback_reason: str | None = None

    @property
    def is_fitted(self) -> bool:
        return self.estimator is not None

    def to_dict(self) -> dict:
        return {
            "model_key": self.model_key,
            "algorithm": self.algorithm,
            "training_rows": self.training_rows,
            "feature_count": len(self.feature_names),
            "metrics": self.metrics,
            "fallback_reason": self.fallback_reason,
        }


@dataclass
class Forecast:
    target_key: str
    points: list[dict] = field(default_factory=list)
    model: dict = field(default_factory=dict)
    drivers: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"target_key": self.target_key, "points": self.points,
                "model": self.model, "drivers": self.drivers}


def _regression_pipeline(kind: str = "gbr") -> Pipeline:
    estimator = (
        GradientBoostingRegressor(
            n_estimators=200, learning_rate=0.05, max_depth=3,
            subsample=0.9, random_state=42,
        )
        if kind == "gbr"
        else Ridge(alpha=1.0, random_state=None)
    )
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("model", estimator),
    ])


def _backtest_regression(pipeline: Pipeline, X: pd.DataFrame, y: pd.Series,
                         splits: int = 4) -> dict:
    """Forward-chaining backtest. Returns MAE and a naive-baseline comparison."""
    if len(X) < MIN_TRAIN_ROWS:
        return {}
    n_splits = min(splits, max(2, len(X) // 30))
    splitter = TimeSeriesSplit(n_splits=n_splits)

    errors, baseline_errors = [], []
    for train_idx, test_idx in splitter.split(X):
        pipeline.fit(X.iloc[train_idx], y.iloc[train_idx])
        predicted = pipeline.predict(X.iloc[test_idx])
        errors.append(mean_absolute_error(y.iloc[test_idx], predicted))
        # Baseline: carry the last observed value forward.
        baseline = np.full(len(test_idx), y.iloc[train_idx].iloc[-1])
        baseline_errors.append(mean_absolute_error(y.iloc[test_idx], baseline))

    mae = float(np.mean(errors))
    baseline_mae = float(np.mean(baseline_errors))
    return {
        "mae": round(mae, 3),
        "baseline_mae": round(baseline_mae, 3),
        # Positive means the model beats persistence; negative means it does not,
        # which is worth knowing before anyone staffs a ward from its output.
        "skill_vs_baseline_pct": round(100 * (1 - mae / baseline_mae), 1)
        if baseline_mae > 0 else None,
        "folds": n_splits,
    }


def _forecast_sigma(metrics: dict, in_sample_residual_std: float) -> float:
    """Error scale for the prediction interval.

    In-sample residuals of a boosted tree are far smaller than the error it
    makes on unseen days -- using them produces a band of a fraction of a
    percentage point around a 14-day occupancy forecast, which is worse than
    useless for capacity planning because it looks authoritative.

    The backtest MAE is the honest estimate. For roughly normal errors
    sigma is about 1.2533 x MAE, so that conversion is applied and the
    in-sample figure is kept only as a last-resort fallback.
    """
    mae = metrics.get("mae")
    if mae:
        return float(mae) * 1.2533
    return max(in_sample_residual_std, 1e-6)


def _feature_importance(pipeline: Pipeline, feature_names: list[str],
                        top: int = 8) -> list[dict]:
    model = pipeline.named_steps.get("model")
    if hasattr(model, "feature_importances_"):
        weights = model.feature_importances_
    elif hasattr(model, "coef_"):
        weights = np.abs(np.ravel(model.coef_))
    else:
        return []
    order = np.argsort(weights)[::-1][:top]
    total = float(np.sum(weights)) or 1.0
    return [
        {"feature": feature_names[i], "weight": round(float(weights[i]) / total, 4)}
        for i in order if i < len(feature_names)
    ]


# ---------------------------------------------------------------------
# 1. Bed occupancy forecast
# ---------------------------------------------------------------------
def forecast_occupancy(
    occupancy_daily: pd.DataFrame,
    encounters: pd.DataFrame,
    *,
    start: date,
    end: date,
    horizon_days: int = 14,
    target: str = "occupancy_rate",
) -> Forecast:
    """Recursive multi-step daily forecast with an empirical interval.

    Each predicted day is fed back as the lag for the next, which is what
    lets a 14-day horizon respond to its own trajectory. The uncertainty
    band widens with the square root of the horizon -- errors accumulate,
    and a flat band would understate day-14 risk.
    """
    frame = feat.daily_occupancy_features(occupancy_daily, encounters, start=start, end=end)
    frame = frame.dropna(subset=[target])
    columns = feat.select_feature_columns(frame, target)

    usable = frame.dropna(subset=columns[:5]) if columns else frame
    if len(usable) < MIN_TRAIN_ROWS or not columns:
        return _seasonal_naive_forecast(frame, target, horizon_days,
                                        reason=f"only {len(usable)} usable days of history")

    X, y = usable[columns], usable[target]
    pipeline = _regression_pipeline("gbr")
    metrics = _backtest_regression(pipeline, X, y)
    pipeline.fit(X, y)
    sigma = _forecast_sigma(metrics, float(np.std(y - pipeline.predict(X))))

    history = frame.copy()
    points = []
    last_date = history.index.max()
    for step in range(1, horizon_days + 1):
        next_date = last_date + pd.Timedelta(days=step)
        row = _next_row(history, next_date, target)
        prediction = float(pipeline.predict(row[columns].to_frame().T)[0])
        prediction = float(np.clip(prediction, 0, 130))

        # Error growth with horizon, capped so day 14 stays interpretable.
        spread = 1.96 * sigma * min(np.sqrt(step), 3.0)
        points.append({
            "date": next_date.date().isoformat(),
            "predicted": round(prediction, 1),
            "lower": round(max(prediction - spread, 0), 1),
            "upper": round(min(prediction + spread, 130), 1),
            "horizon_days": step,
        })

        row[target] = prediction
        history = pd.concat([history, row.to_frame().T])
        history.index = pd.DatetimeIndex(history.index)

    return Forecast(
        target_key=target,
        points=points,
        model={"algorithm": "GradientBoostingRegressor", "training_rows": len(usable), **metrics},
        drivers=_feature_importance(pipeline, columns),
    )


def _next_row(history: pd.DataFrame, next_date: pd.Timestamp, target: str) -> pd.Series:
    """Build the feature row for a future date from the history so far."""
    row = pd.Series(index=history.columns, dtype=float, name=next_date)

    row["dayofweek"] = next_date.dayofweek
    row["is_weekend"] = int(next_date.dayofweek in feat.WEEKEND_DAYS)
    row["day_of_month"] = next_date.day
    row["month"] = next_date.month
    row["dow_sin"] = np.sin(2 * np.pi * next_date.dayofweek / 7)
    row["dow_cos"] = np.cos(2 * np.pi * next_date.dayofweek / 7)
    row["month_sin"] = np.sin(2 * np.pi * next_date.month / 12)
    row["month_cos"] = np.cos(2 * np.pi * next_date.month / 12)

    for column in ("occupancy_rate", "admissions", "discharges"):
        if column not in history.columns:
            continue
        series = history[column].dropna()
        if series.empty:
            continue
        for lag in feat.DAILY_LAGS:
            name = f"{column}_lag{lag}"
            if name in row.index:
                row[name] = series.iloc[-lag] if len(series) >= lag else series.iloc[-1]
        for window in feat.ROLLING_WINDOWS:
            tail = series.iloc[-window:]
            if f"{column}_roll{window}_mean" in row.index:
                row[f"{column}_roll{window}_mean"] = float(tail.mean())
            if f"{column}_roll{window}_std" in row.index:
                row[f"{column}_roll{window}_std"] = float(tail.std()) if len(tail) > 1 else 0.0
        if f"{column}_dow_mean" in row.index:
            same_dow = history[history.index.dayofweek == next_date.dayofweek][column].dropna()
            row[f"{column}_dow_mean"] = float(same_dow.mean()) if len(same_dow) else float(series.mean())

    for column in ("admissions", "discharges", "patient_days", "available_bed_days"):
        if column in row.index and pd.isna(row[column]):
            series = history[column].dropna()
            row[column] = float(series.iloc[-7:].mean()) if len(series) else 0.0

    return row.fillna(0.0)


def _seasonal_naive_forecast(frame: pd.DataFrame, target: str, horizon_days: int,
                             *, reason: str) -> Forecast:
    """Weekly seasonal naive: repeat the value from the same weekday.

    Used whenever there is too little history to learn from. It is a
    genuinely competitive baseline for hospital occupancy, so falling back
    to it is not a failure -- but the caller is told, so the UI can label
    the forecast honestly instead of implying a trained model.
    """
    if frame.empty or target not in frame.columns:
        return Forecast(target_key=target, points=[],
                        model={"algorithm": "unavailable", "fallback_reason": reason})

    series = frame[target].dropna()
    if series.empty:
        return Forecast(target_key=target, points=[],
                        model={"algorithm": "unavailable", "fallback_reason": reason})

    # Day-to-day variation is the natural error scale for a naive forecast.
    sigma = float(series.diff().std() or series.std() or 1.0)
    last_date = series.index.max()
    points = []
    for step in range(1, horizon_days + 1):
        next_date = last_date + pd.Timedelta(days=step)
        same_dow = series[series.index.dayofweek == next_date.dayofweek]
        value = float(same_dow.iloc[-4:].mean()) if len(same_dow) else float(series.iloc[-7:].mean())
        spread = 1.96 * sigma * min(np.sqrt(step), 3.0)
        points.append({
            "date": next_date.date().isoformat(),
            "predicted": round(value, 1),
            "lower": round(max(value - spread, 0), 1),
            "upper": round(value + spread, 1),
            "horizon_days": step,
        })

    return Forecast(
        target_key=target,
        points=points,
        model={"algorithm": "SeasonalNaive(weekly)", "training_rows": int(len(series)),
               "fallback_reason": reason},
    )


# ---------------------------------------------------------------------
# 2. ED crowding classifier
# ---------------------------------------------------------------------
def train_ed_crowding(hourly: pd.DataFrame, *, horizon_hours: int = 4,
                      threshold: float = 100.0) -> ModelResult:
    """Predict whether NEDOCS will exceed ``threshold`` ``horizon_hours`` ahead.

    Framed as classification rather than regression because the decision it
    supports is binary -- open the surge area and call in staff, or don't.
    """
    if hourly.empty:
        return ModelResult("ed_crowding", "unavailable", fallback_reason="no ED history")

    frame = feat.hourly_ed_features(hourly)
    if frame.empty:
        return ModelResult("ed_crowding", "unavailable", fallback_reason="no ED history")

    frame["target"] = (frame["nedocs_score"].shift(-horizon_hours) > threshold).astype(float)
    frame = frame.dropna(subset=["target"])

    columns = feat.select_feature_columns(frame, "nedocs_score")
    columns = [c for c in columns if c != "target"]
    usable = frame.dropna(subset=columns[:6]) if columns else frame

    if len(usable) < MIN_TRAIN_ROWS * 4 or usable["target"].nunique() < 2:
        return ModelResult(
            "ed_crowding", "unavailable",
            fallback_reason=(
                "insufficient history or no crowding events observed; "
                "the classifier needs both crowded and uncrowded hours to learn"
            ),
        )

    X, y = usable[columns], usable["target"]
    pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("model", GradientBoostingClassifier(n_estimators=150, learning_rate=0.05,
                                             max_depth=3, random_state=42)),
    ])

    # Forward-chaining AUC; a fold with one class present is skipped rather
    # than scored, because AUC is undefined there.
    aucs = []
    splitter = TimeSeriesSplit(n_splits=4)
    for train_idx, test_idx in splitter.split(X):
        if y.iloc[train_idx].nunique() < 2 or y.iloc[test_idx].nunique() < 2:
            continue
        pipeline.fit(X.iloc[train_idx], y.iloc[train_idx])
        probability = pipeline.predict_proba(X.iloc[test_idx])[:, 1]
        aucs.append(roc_auc_score(y.iloc[test_idx], probability))

    pipeline.fit(X, y)
    return ModelResult(
        model_key="ed_crowding",
        algorithm="GradientBoostingClassifier",
        feature_names=columns,
        training_rows=len(usable),
        estimator=pipeline,
        metrics={
            "roc_auc": round(float(np.mean(aucs)), 3) if aucs else None,
            "positive_rate": round(float(y.mean()), 3),
            "horizon_hours": horizon_hours,
            "threshold": threshold,
        },
    )


def predict_ed_crowding(result: ModelResult, hourly: pd.DataFrame,
                        *, horizon_hours: int = 4) -> dict:
    if not result.is_fitted or hourly.empty:
        return {"available": False, "reason": result.fallback_reason or "model not trained"}

    frame = feat.hourly_ed_features(hourly)
    if frame.empty:
        return {"available": False, "reason": "no recent ED observations"}

    latest = frame.iloc[[-1]][result.feature_names]
    probability = float(result.estimator.predict_proba(latest)[0, 1])
    as_of = frame.index[-1]

    return {
        "available": True,
        "as_of": as_of.isoformat(),
        "horizon_at": (as_of + timedelta(hours=horizon_hours)).isoformat(),
        "probability_overcrowded": round(probability, 3),
        "risk_band": ("HIGH" if probability >= 0.6 else
                      "MODERATE" if probability >= 0.3 else "LOW"),
        "current_nedocs": round(float(frame["nedocs_score"].iloc[-1]), 1),
        "drivers": _feature_importance(result.estimator, result.feature_names, top=5),
        "model": result.to_dict(),
    }


# ---------------------------------------------------------------------
# 3. Discharge demand
# ---------------------------------------------------------------------
def forecast_discharges(occupancy_daily: pd.DataFrame, encounters: pd.DataFrame,
                        *, start: date, end: date, horizon_days: int = 7) -> Forecast:
    """Expected discharges per day -- the input to discharge-lounge planning."""
    forecast = forecast_occupancy(
        occupancy_daily, encounters, start=start, end=end,
        horizon_days=horizon_days, target="discharges",
    )
    forecast.target_key = "discharge_demand"
    for point in forecast.points:
        point["predicted"] = round(max(point["predicted"], 0), 1)
        point["lower"] = round(max(point["lower"], 0), 1)
    return forecast


def forecast_icu(occupancy_daily: pd.DataFrame, icu_unit_ids: list[int],
                 *, start: date, end: date, horizon_days: int = 14) -> Forecast:
    frame = feat.icu_features(occupancy_daily, icu_unit_ids, start=start, end=end)
    if frame.empty or "icu_occupancy" not in frame.columns:
        return Forecast(target_key="icu_utilization", points=[],
                        model={"algorithm": "unavailable",
                               "fallback_reason": "no critical-care occupancy history"})

    target = "icu_occupancy"
    columns = feat.select_feature_columns(frame, target)
    usable = frame.dropna(subset=[target] + columns[:5]) if columns else frame.dropna(subset=[target])

    if len(usable) < MIN_TRAIN_ROWS or not columns:
        forecast = _seasonal_naive_forecast(
            frame.dropna(subset=[target]), target, horizon_days,
            reason=f"only {len(usable)} usable days of critical-care history",
        )
        forecast.target_key = "icu_utilization"
        return forecast

    X, y = usable[columns], usable[target]
    pipeline = _regression_pipeline("gbr")
    metrics = _backtest_regression(pipeline, X, y)
    pipeline.fit(X, y)
    sigma = _forecast_sigma(metrics, float(np.std(y - pipeline.predict(X))))

    history = frame.copy()
    points = []
    last_date = history.index.max()
    for step in range(1, horizon_days + 1):
        next_date = last_date + pd.Timedelta(days=step)
        row = _next_row(history, next_date, target)
        # ICU lags are named for icu_occupancy; reuse the generic builder by
        # copying the occupancy lags across when present.
        for lag in feat.DAILY_LAGS:
            name = f"{target}_lag{lag}"
            if name in row.index:
                series = history[target].dropna()
                row[name] = series.iloc[-lag] if len(series) >= lag else series.iloc[-1]
        prediction = float(np.clip(pipeline.predict(row[columns].to_frame().T)[0], 0, 130))
        spread = 1.96 * sigma * min(np.sqrt(step), 3.0)
        points.append({
            "date": next_date.date().isoformat(),
            "predicted": round(prediction, 1),
            "lower": round(max(prediction - spread, 0), 1),
            "upper": round(min(prediction + spread, 130), 1),
            "horizon_days": step,
        })
        row[target] = prediction
        history = pd.concat([history, row.to_frame().T])
        history.index = pd.DatetimeIndex(history.index)

    return Forecast(
        target_key="icu_utilization",
        points=points,
        model={"algorithm": "GradientBoostingRegressor", "training_rows": len(usable), **metrics},
        drivers=_feature_importance(pipeline, columns),
    )


# ---------------------------------------------------------------------
# 4. Anomaly detection
# ---------------------------------------------------------------------
def detect_anomalies(daily_metrics: pd.DataFrame, *, contamination: float = 0.05) -> list[dict]:
    """Flag days whose KPI vector departs from the facility's own pattern.

    Isolation Forest supplies the multivariate view -- a day where nothing
    is individually extreme but the combination is unusual. A robust
    per-metric z-score then names *which* indicator drove the flag, because
    "day 12 is anomalous" is not actionable on its own.
    """
    if daily_metrics.empty or len(daily_metrics) < 21:
        return []

    numeric = daily_metrics.select_dtypes(include=[np.number]).copy()
    numeric = numeric.loc[:, numeric.notna().sum() >= max(10, len(numeric) * 0.5)]
    if numeric.shape[1] == 0:
        return []
    filled = numeric.fillna(numeric.median())

    forest = IsolationForest(contamination=contamination, random_state=42, n_estimators=200)
    forest.fit(filled)
    scores = forest.decision_function(filled)
    flagged = forest.predict(filled) == -1

    # Median and MAD rather than mean and standard deviation: a single
    # extreme day would otherwise inflate the spread and hide its neighbours.
    median = filled.median()
    mad = (filled - median).abs().median().replace(0, np.nan)
    robust_z = ((filled - median) / (1.4826 * mad)).abs()

    anomalies = []
    for position, is_flagged in enumerate(flagged):
        if not is_flagged:
            continue
        row_z = robust_z.iloc[position].dropna().sort_values(ascending=False)
        top = row_z.head(3)
        service_date = daily_metrics.index[position]
        drivers = [
            {
                "metric": str(metric),
                "observed": round(float(filled.iloc[position][metric]), 2),
                "typical": round(float(median[metric]), 2),
                "robust_z": round(float(value), 2),
            }
            for metric, value in top.items() if value >= 2.0
        ]
        if not drivers:
            continue
        anomalies.append({
            "service_date": service_date.date().isoformat()
            if hasattr(service_date, "date") else str(service_date),
            "anomaly_score": round(float(-scores[position]), 4),
            "severity": "CRITICAL" if -scores[position] > 0.15 else "WARNING",
            "drivers": drivers,
            "explanation_en": _explain_anomaly(drivers),
        })
    return sorted(anomalies, key=lambda a: a["anomaly_score"], reverse=True)


def _explain_anomaly(drivers: list[dict]) -> str:
    parts = []
    for driver in drivers:
        direction = "above" if driver["observed"] > driver["typical"] else "below"
        parts.append(
            f"{driver['metric'].replace('_', ' ')} was {driver['observed']}, "
            f"{direction} the usual {driver['typical']}"
        )
    return "; ".join(parts) + "."


# ---------------------------------------------------------------------
# 5. High-risk patient scoring
# ---------------------------------------------------------------------
def train_patient_risk(
    encounters: pd.DataFrame,
    ed_visits: pd.DataFrame,
    movements: pd.DataFrame,
    icu_stays: pd.DataFrame,
    *,
    target: str = "prolonged_los",
) -> ModelResult:
    """Score encounters for prolonged stay or 30-day readmission risk.

    Logistic regression is used on purpose: coefficients are inspectable,
    the score is a calibrated probability, and a clinical governance
    committee can be shown exactly what drives a flag. This is a
    *prioritisation* aid for the flow team, not a clinical decision tool,
    and it must not be presented as one.
    """
    frame = feat.patient_risk_features(encounters, ed_visits, movements, icu_stays)
    if frame.empty or encounters.empty:
        return ModelResult("patient_risk", "unavailable", fallback_reason="no encounter history")

    source = encounters.set_index(encounters.index)
    if target == "prolonged_los":
        los_hours = pd.to_numeric(source["los_hours"], errors="coerce")
        completed = los_hours.notna()
        if completed.sum() < MIN_TRAIN_ROWS:
            return ModelResult("patient_risk", "unavailable",
                               fallback_reason="too few completed stays to learn from")
        # "Prolonged" is defined against this hospital's own distribution
        # rather than an imported constant, so it stays meaningful across
        # very different case mixes.
        cutoff = float(los_hours[completed].quantile(0.75))
        labels = (los_hours > cutoff).astype(float)
    else:
        labels = source.get("is_readmission_30d")
        if labels is None:
            return ModelResult("patient_risk", "unavailable",
                               fallback_reason="readmission labels not computed")
        completed = labels.notna()
        labels = labels.fillna(False).astype(float)
        cutoff = None

    numeric_columns = [c for c in frame.columns
                       if c not in ("encounter_id", "specialty")
                       and pd.api.types.is_numeric_dtype(frame[c])]
    mask = completed.reindex(frame.index).fillna(False).astype(bool).values
    X = frame.loc[mask, numeric_columns]
    y = labels.reindex(frame.index)[mask]

    if len(X) < MIN_TRAIN_ROWS or y.nunique() < 2:
        return ModelResult("patient_risk", "unavailable",
                           fallback_reason="insufficient labelled encounters")

    pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("model", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)),
    ])

    aucs = []
    splitter = TimeSeriesSplit(n_splits=min(4, max(2, len(X) // 50)))
    for train_idx, test_idx in splitter.split(X):
        if y.iloc[train_idx].nunique() < 2 or y.iloc[test_idx].nunique() < 2:
            continue
        pipeline.fit(X.iloc[train_idx], y.iloc[train_idx])
        aucs.append(roc_auc_score(y.iloc[test_idx],
                                 pipeline.predict_proba(X.iloc[test_idx])[:, 1]))

    pipeline.fit(X, y)
    return ModelResult(
        model_key="patient_risk",
        algorithm="LogisticRegression",
        feature_names=numeric_columns,
        training_rows=int(len(X)),
        estimator=pipeline,
        metrics={
            "roc_auc": round(float(np.mean(aucs)), 3) if aucs else None,
            "positive_rate": round(float(y.mean()), 3),
            "target": target,
            "los_cutoff_hours": round(cutoff, 1) if cutoff else None,
        },
    )


def score_patients(result: ModelResult, encounters: pd.DataFrame, ed_visits: pd.DataFrame,
                   movements: pd.DataFrame, icu_stays: pd.DataFrame,
                   *, top: int = 20) -> list[dict]:
    """Rank currently-admitted patients by predicted risk."""
    if not result.is_fitted or encounters.empty:
        return []

    frame = feat.patient_risk_features(encounters, ed_visits, movements, icu_stays)
    if frame.empty:
        return []

    # Only patients still in the hospital can be acted on.
    current = encounters["discharge_at"].isna().reindex(frame.index).fillna(False)
    if not current.any():
        current = pd.Series(True, index=frame.index)

    subset = frame[current.values]
    if subset.empty:
        return []

    probabilities = result.estimator.predict_proba(subset[result.feature_names])[:, 1]
    model = result.estimator.named_steps["model"]
    coefficients = dict(zip(result.feature_names, np.ravel(model.coef_)))

    rows = []
    for position, (_, feature_row) in enumerate(subset.iterrows()):
        probability = float(probabilities[position])
        contributions = sorted(
            (
                {"feature": name, "value": round(float(feature_row[name]), 2),
                 "direction": "increases" if coefficients[name] > 0 else "decreases"}
                for name in result.feature_names
                if abs(coefficients.get(name, 0)) > 0.05
            ),
            key=lambda d: abs(coefficients[d["feature"]]), reverse=True,
        )[:3]
        rows.append({
            "encounter_id": int(feature_row["encounter_id"]),
            "risk_probability": round(probability, 3),
            "risk_band": ("HIGH" if probability >= 0.6 else
                          "MODERATE" if probability >= 0.35 else "LOW"),
            "drivers": contributions,
        })

    rows.sort(key=lambda r: r["risk_probability"], reverse=True)
    return rows[:top]


# ---------------------------------------------------------------------
# 6. Operational bottleneck anticipation
# ---------------------------------------------------------------------
def anticipate_bottlenecks(occupancy_forecast: Forecast, icu_forecast: Forecast,
                           discharge_forecast: Forecast,
                           *, occupancy_threshold: float = 92.0,
                           icu_threshold: float = 90.0) -> list[dict]:
    """Turn forecasts into dated, actionable warnings.

    A forecast that nobody translates into "Thursday will be tight, start
    the discharge round early" changes nothing, so the thresholds and the
    recommended action are attached here rather than left to the reader.
    """
    warnings = []

    for point in occupancy_forecast.points:
        if point["predicted"] >= occupancy_threshold:
            warnings.append({
                "date": point["date"],
                "kind": "BED_CAPACITY",
                "severity": "CRITICAL" if point["predicted"] >= 97 else "WARNING",
                "predicted_value": point["predicted"],
                "threshold": occupancy_threshold,
                "message_en": (
                    f"Forecast occupancy {point['predicted']:.0f}% on {point['date']} "
                    f"(range {point['lower']:.0f}-{point['upper']:.0f}%). Escalate discharge "
                    "planning and review elective admissions for that day."
                ),
                "message_ar": (
                    f"إشغال متوقع {point['predicted']:.0f}% بتاريخ {point['date']}. "
                    "يُنصح بتسريع خطط الخروج ومراجعة الحالات المجدولة."
                ),
            })

    for point in icu_forecast.points:
        if point["predicted"] >= icu_threshold:
            warnings.append({
                "date": point["date"],
                "kind": "ICU_CAPACITY",
                "severity": "CRITICAL" if point["predicted"] >= 95 else "WARNING",
                "predicted_value": point["predicted"],
                "threshold": icu_threshold,
                "message_en": (
                    f"Critical-care occupancy forecast at {point['predicted']:.0f}% on "
                    f"{point['date']}. Confirm step-down capacity and surge staffing."
                ),
                "message_ar": (
                    f"إشغال العناية المركزة المتوقع {point['predicted']:.0f}% بتاريخ {point['date']}."
                ),
            })

    # A day with high occupancy and unusually few expected discharges is the
    # combination that actually produces gridlock.
    discharge_by_date = {p["date"]: p["predicted"] for p in discharge_forecast.points}
    if discharge_by_date:
        typical = float(np.median(list(discharge_by_date.values())))
        for point in occupancy_forecast.points:
            expected = discharge_by_date.get(point["date"])
            if expected is None or point["predicted"] < 85:
                continue
            if expected < typical * 0.7:
                warnings.append({
                    "date": point["date"],
                    "kind": "FLOW_GRIDLOCK",
                    "severity": "WARNING",
                    "predicted_value": point["predicted"],
                    "threshold": None,
                    "message_en": (
                        f"{point['date']} combines high occupancy ({point['predicted']:.0f}%) with "
                        f"below-normal expected discharges ({expected:.0f} vs typical "
                        f"{typical:.0f}). Bring discharge decisions forward to the preceding day."
                    ),
                    "message_ar": (
                        f"{point['date']}: إشغال مرتفع مع خروج متوقع أقل من المعتاد."
                    ),
                })

    warnings.sort(key=lambda w: (w["date"], w["severity"] != "CRITICAL"))
    return warnings
