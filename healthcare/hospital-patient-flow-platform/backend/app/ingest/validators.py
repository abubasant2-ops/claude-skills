"""Validation rules and the data-quality scorecard.

Findings are graded on four levels. Only ``CRITICAL`` stops a load
outright; ``ERROR`` quarantines the offending rows and lets the rest
through, because a hospital that cannot import 40,000 good rows because of
12 bad ones will simply stop using the platform.

The composite score follows the DAMA dimensions -- completeness,
validity, uniqueness, consistency and timeliness -- so the number can be
defended in a CBAHI or JCI data-integrity review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from app.ingest.datasets import DatasetSpec

SEVERITY_ORDER = {"INFO": 0, "WARNING": 1, "ERROR": 2, "CRITICAL": 3}

# How each dimension contributes to the headline score.
DIMENSION_WEIGHTS = {
    "completeness": 0.30,
    "validity": 0.25,
    "uniqueness": 0.15,
    "consistency": 0.20,
    "timeliness": 0.10,
}


@dataclass
class Finding:
    rule_code: str
    severity: str
    message_en: str
    message_ar: str = ""
    column_name: str | None = None
    affected_rows: int = 0
    sample_rows: list[int] = field(default_factory=list)
    dimension: str = "validity"

    def to_dict(self) -> dict:
        return {
            "rule_code": self.rule_code,
            "severity": self.severity,
            "column_name": self.column_name,
            "affected_rows": self.affected_rows,
            "sample_rows": self.sample_rows[:10],
            "message_en": self.message_en,
            "message_ar": self.message_ar,
            "dimension": self.dimension,
        }


@dataclass
class ValidationResult:
    findings: list[Finding]
    rejected_index: pd.Index
    scores: dict[str, float]
    quality_score: float

    @property
    def blocking(self) -> bool:
        return any(f.severity == "CRITICAL" for f in self.findings)

    def to_dict(self) -> dict:
        return {
            "quality_score": round(self.quality_score, 2),
            "dimension_scores": {k: round(v, 2) for k, v in self.scores.items()},
            "rejected_rows": int(len(self.rejected_index)),
            "findings": [f.to_dict() for f in self.findings],
        }


def _sample(index: pd.Index, limit: int = 10) -> list[int]:
    return [int(i) for i in list(index)[:limit]]


def validate(
    frame: pd.DataFrame,
    spec: DatasetSpec,
    coercion_failures: dict[str, pd.Series],
    mapping: dict[str, str],
    *,
    now: datetime | None = None,
    known_encounter_nos: set[str] | None = None,
) -> ValidationResult:
    """Run every rule for ``spec`` over an already-coerced frame."""
    now = now or datetime.now()
    findings: list[Finding] = []
    reject = pd.Series(False, index=frame.index)
    total = len(frame)
    if total == 0:
        return ValidationResult([], frame.index[:0], {k: 100.0 for k in DIMENSION_WEIGHTS}, 100.0)

    # -- Schema: required fields that the file never supplied at all -----
    for name in spec.required_fields:
        if name not in mapping:
            findings.append(Finding(
                rule_code="MISSING_REQUIRED_COLUMN",
                severity="CRITICAL",
                column_name=name,
                affected_rows=total,
                message_en=f"Required column '{name}' was not found in the file.",
                message_ar=f"العمود المطلوب '{name}' غير موجود في الملف.",
                dimension="completeness",
            ))

    # -- Completeness ---------------------------------------------------
    completeness_penalty = 0.0
    for field_spec in spec.fields:
        if field_spec.name not in frame.columns:
            continue
        missing = frame[field_spec.name].isna()
        if not missing.any():
            continue
        rate = missing.mean()
        if field_spec.required:
            reject |= missing
            findings.append(Finding(
                rule_code="REQUIRED_VALUE_MISSING",
                severity="ERROR",
                column_name=field_spec.name,
                affected_rows=int(missing.sum()),
                sample_rows=_sample(frame.index[missing]),
                message_en=(
                    f"{int(missing.sum())} row(s) have no value for required field "
                    f"'{field_spec.name}'. These rows were quarantined."
                ),
                message_ar=f"{int(missing.sum())} صف بدون قيمة للحقل الإلزامي '{field_spec.name}'.",
                dimension="completeness",
            ))
            completeness_penalty += rate * 2
        elif rate >= 0.5 and field_spec.name in mapping:
            findings.append(Finding(
                rule_code="SPARSE_COLUMN",
                severity="WARNING",
                column_name=field_spec.name,
                affected_rows=int(missing.sum()),
                message_en=(
                    f"'{field_spec.name}' is {rate:.0%} empty. Metrics that depend on it "
                    "will be computed on a reduced denominator."
                ),
                message_ar=f"الحقل '{field_spec.name}' فارغ بنسبة {rate:.0%}.",
                dimension="completeness",
            ))
            completeness_penalty += rate * 0.3

    # -- Validity: type coercion ----------------------------------------
    for column, failed in coercion_failures.items():
        if not failed.any():
            continue
        findings.append(Finding(
            rule_code="TYPE_COERCION_FAILED",
            severity="ERROR" if column in spec.required_fields else "WARNING",
            column_name=column,
            affected_rows=int(failed.sum()),
            sample_rows=_sample(frame.index[failed]),
            message_en=(
                f"{int(failed.sum())} value(s) in '{column}' could not be read as "
                f"{spec.field_map[column].dtype}."
            ),
            message_ar=f"تعذر تحويل {int(failed.sum())} قيمة في العمود '{column}'.",
            dimension="validity",
        ))
        if column in spec.required_fields:
            reject |= failed

    # -- Validity: domains and ranges -----------------------------------
    for field_spec in spec.fields:
        if field_spec.name not in frame.columns:
            continue
        series = frame[field_spec.name]
        present = series.notna()
        if not present.any():
            continue

        if field_spec.domain and field_spec.dtype == "string":
            allowed = set(field_spec.domain)
            offending = present & ~series.isin(allowed)
            if offending.any():
                unexpected = sorted({str(v) for v in series[offending].unique()})[:5]
                findings.append(Finding(
                    rule_code="VALUE_OUT_OF_DOMAIN",
                    severity="WARNING",
                    column_name=field_spec.name,
                    affected_rows=int(offending.sum()),
                    sample_rows=_sample(frame.index[offending]),
                    message_en=(
                        f"'{field_spec.name}' contains {int(offending.sum())} value(s) outside the "
                        f"expected code set (e.g. {', '.join(unexpected)}). "
                        "Map them in the code-set editor or they will be grouped as OTHER."
                    ),
                    message_ar=f"قيم غير معرفة في العمود '{field_spec.name}'.",
                    dimension="validity",
                ))

        if field_spec.minimum is not None or field_spec.maximum is not None:
            numeric = pd.to_numeric(series, errors="coerce")
            low = field_spec.minimum if field_spec.minimum is not None else -np.inf
            high = field_spec.maximum if field_spec.maximum is not None else np.inf
            offending = numeric.notna() & ((numeric < low) | (numeric > high))
            if offending.any():
                findings.append(Finding(
                    rule_code="VALUE_OUT_OF_RANGE",
                    severity="WARNING",
                    column_name=field_spec.name,
                    affected_rows=int(offending.sum()),
                    sample_rows=_sample(frame.index[offending]),
                    message_en=(
                        f"{int(offending.sum())} value(s) in '{field_spec.name}' fall outside the "
                        f"plausible range [{field_spec.minimum}, {field_spec.maximum}]."
                    ),
                    message_ar=f"قيم خارج النطاق المتوقع في '{field_spec.name}'.",
                    dimension="validity",
                ))

    # -- Uniqueness ------------------------------------------------------
    key_columns = [c for c in spec.natural_key if c in frame.columns]
    duplicate_rate = 0.0
    if key_columns:
        key_present = frame[key_columns].notna().all(axis=1)
        dup_mask = key_present & frame.duplicated(subset=key_columns, keep="first")
        if dup_mask.any():
            duplicate_rate = dup_mask.mean()
            reject |= dup_mask
            findings.append(Finding(
                rule_code="DUPLICATE_NATURAL_KEY",
                severity="ERROR",
                column_name=", ".join(key_columns),
                affected_rows=int(dup_mask.sum()),
                sample_rows=_sample(frame.index[dup_mask]),
                message_en=(
                    f"{int(dup_mask.sum())} row(s) repeat an existing {'+'.join(key_columns)}. "
                    "The first occurrence was kept and the rest quarantined."
                ),
                message_ar=f"{int(dup_mask.sum())} صف مكرر حسب المفتاح {'+'.join(key_columns)}.",
                dimension="uniqueness",
            ))

    exact_dups = frame.duplicated(keep="first")
    if exact_dups.any():
        findings.append(Finding(
            rule_code="EXACT_DUPLICATE_ROW",
            severity="WARNING",
            affected_rows=int(exact_dups.sum()),
            sample_rows=_sample(frame.index[exact_dups]),
            message_en=(
                f"{int(exact_dups.sum())} row(s) are byte-for-byte duplicates, which usually "
                "means the export was run twice and concatenated."
            ),
            message_ar=f"{int(exact_dups.sum())} صف مطابق تماماً لصف آخر.",
            dimension="uniqueness",
        ))

    # -- Consistency: chronology ----------------------------------------
    chronology_violations = 0
    for rule in spec.chronology:
        if rule.earlier not in frame.columns or rule.later not in frame.columns:
            continue
        earlier = pd.to_datetime(frame[rule.earlier], errors="coerce")
        later = pd.to_datetime(frame[rule.later], errors="coerce")
        both = earlier.notna() & later.notna()
        offending = both & (later < earlier - timedelta(minutes=rule.tolerance_minutes))
        if offending.any():
            chronology_violations += int(offending.sum())
            # Quarantined rather than merely flagged: a negative interval
            # produces a negative length of stay, which would corrupt every
            # average it touches and is rejected by the warehouse anyway.
            reject |= offending
            findings.append(Finding(
                rule_code="CHRONOLOGY_VIOLATION",
                severity="ERROR",
                column_name=f"{rule.earlier} -> {rule.later}",
                affected_rows=int(offending.sum()),
                sample_rows=_sample(frame.index[offending]),
                message_en=(
                    f"{int(offending.sum())} row(s) have '{rule.later}' before '{rule.earlier}'. "
                    "Intervals derived from these rows would be negative, so the rows were "
                    "quarantined. Check the source system's date format and timezone handling."
                ),
                message_ar=f"{int(offending.sum())} صف فيه '{rule.later}' قبل '{rule.earlier}'.",
                dimension="consistency",
            ))

    # -- Timeliness: future and stale timestamps -------------------------
    horizon = now + timedelta(hours=12)          # tolerate modest clock skew
    stale_floor = now - timedelta(days=365 * 10)
    future_rows = 0
    for field_spec in spec.fields:
        if field_spec.dtype not in ("datetime", "date") or field_spec.name not in frame.columns:
            continue
        values = pd.to_datetime(frame[field_spec.name], errors="coerce")
        future = values.notna() & (values > horizon)
        if future.any():
            future_rows += int(future.sum())
            findings.append(Finding(
                rule_code="FUTURE_TIMESTAMP",
                severity="WARNING",
                column_name=field_spec.name,
                affected_rows=int(future.sum()),
                sample_rows=_sample(frame.index[future]),
                message_en=(
                    f"{int(future.sum())} value(s) in '{field_spec.name}' are dated in the future. "
                    "Check the source system's timezone and date format."
                ),
                message_ar=f"{int(future.sum())} قيمة مستقبلية في '{field_spec.name}'.",
                dimension="timeliness",
            ))
        ancient = values.notna() & (values < stale_floor)
        if ancient.any():
            findings.append(Finding(
                rule_code="IMPLAUSIBLE_HISTORIC_DATE",
                severity="WARNING",
                column_name=field_spec.name,
                affected_rows=int(ancient.sum()),
                sample_rows=_sample(frame.index[ancient]),
                message_en=(
                    f"{int(ancient.sum())} value(s) in '{field_spec.name}' predate the last decade, "
                    "which usually indicates a misread Excel serial number."
                ),
                message_ar=f"{int(ancient.sum())} تاريخ قديم بشكل غير منطقي في '{field_spec.name}'.",
                dimension="timeliness",
            ))

    # -- Referential integrity ------------------------------------------
    if spec.references_encounter and known_encounter_nos is not None \
            and "encounter_no" in frame.columns:
        present = frame["encounter_no"].notna()
        orphan = present & ~frame["encounter_no"].astype(str).isin(known_encounter_nos)
        if orphan.any():
            reject |= orphan
            findings.append(Finding(
                rule_code="ORPHAN_ENCOUNTER_REFERENCE",
                severity="ERROR",
                column_name="encounter_no",
                affected_rows=int(orphan.sum()),
                sample_rows=_sample(frame.index[orphan]),
                message_en=(
                    f"{int(orphan.sum())} row(s) reference an encounter number that is not in the "
                    "warehouse. Load the encounters file for this period first."
                ),
                message_ar=f"{int(orphan.sum())} صف يشير إلى زيارة غير موجودة.",
                dimension="consistency",
            ))

    findings.extend(_dataset_specific_rules(frame, spec))

    scores = _score(
        frame=frame,
        spec=spec,
        mapping=mapping,
        completeness_penalty=completeness_penalty,
        duplicate_rate=duplicate_rate,
        chronology_violations=chronology_violations,
        future_rows=future_rows,
        coercion_failures=coercion_failures,
    )
    quality = sum(scores[dim] * weight for dim, weight in DIMENSION_WEIGHTS.items())
    if any(f.severity == "CRITICAL" for f in findings):
        quality = min(quality, 40.0)

    return ValidationResult(
        findings=findings,
        rejected_index=frame.index[reject],
        scores=scores,
        quality_score=quality,
    )


def _dataset_specific_rules(frame: pd.DataFrame, spec: DatasetSpec) -> list[Finding]:
    """Clinical plausibility checks that only make sense per dataset."""
    findings: list[Finding] = []

    if spec.key == "encounters" and {"admission_at", "discharge_at"} <= set(frame.columns):
        admit = pd.to_datetime(frame["admission_at"], errors="coerce")
        discharge = pd.to_datetime(frame["discharge_at"], errors="coerce")
        los_days = (discharge - admit).dt.total_seconds() / 86400
        extreme = los_days.notna() & (los_days > 365)
        if extreme.any():
            findings.append(Finding(
                rule_code="IMPLAUSIBLE_LENGTH_OF_STAY",
                severity="WARNING",
                column_name="admission_at -> discharge_at",
                affected_rows=int(extreme.sum()),
                sample_rows=_sample(frame.index[extreme]),
                message_en=(
                    f"{int(extreme.sum())} encounter(s) show a stay longer than one year. "
                    "These are usually unclosed episodes rather than real long-stay patients "
                    "and will distort ALOS if left in."
                ),
                message_ar=f"{int(extreme.sum())} زيارة بمدة إقامة تتجاوز سنة.",
                dimension="consistency",
            ))
        # An open episode is legitimate for current inpatients but suspicious
        # in a historic extract.
        open_old = admit.notna() & discharge.isna() & (admit < datetime.now() - timedelta(days=90))
        if open_old.any():
            findings.append(Finding(
                rule_code="STALE_OPEN_ENCOUNTER",
                severity="WARNING",
                column_name="discharge_at",
                affected_rows=int(open_old.sum()),
                sample_rows=_sample(frame.index[open_old]),
                message_en=(
                    f"{int(open_old.sum())} encounter(s) admitted more than 90 days ago have no "
                    "discharge timestamp. They inflate occupancy until they are closed."
                ),
                message_ar=f"{int(open_old.sum())} زيارة قديمة بدون تاريخ خروج.",
                dimension="consistency",
            ))

    if spec.key == "ed_visits":
        if {"is_lwbs", "physician_at"} <= set(frame.columns):
            contradiction = frame["is_lwbs"].fillna(False).astype(bool) & frame["physician_at"].notna()
            if contradiction.any():
                findings.append(Finding(
                    rule_code="LWBS_WITH_PHYSICIAN_CONTACT",
                    severity="ERROR",
                    column_name="is_lwbs",
                    affected_rows=int(contradiction.sum()),
                    sample_rows=_sample(frame.index[contradiction]),
                    message_en=(
                        f"{int(contradiction.sum())} visit(s) are flagged left-without-being-seen "
                        "yet carry a physician contact time. One of the two fields is wrong and "
                        "the LWBS rate cannot be trusted until it is resolved."
                    ),
                    message_ar=f"{int(contradiction.sum())} زيارة مصنفة مغادرة قبل الفحص رغم وجود وقت طبيب.",
                    dimension="consistency",
                ))
        if {"ctas_level", "ed_disposition"} <= set(frame.columns):
            ctas = pd.to_numeric(frame["ctas_level"], errors="coerce")
            odd = (ctas == 1) & (frame["ed_disposition"] == "LWBS")
            if odd.any():
                findings.append(Finding(
                    rule_code="CRITICAL_ACUITY_LWBS",
                    severity="WARNING",
                    column_name="ctas_level",
                    affected_rows=int(odd.sum()),
                    sample_rows=_sample(frame.index[odd]),
                    message_en=(
                        f"{int(odd.sum())} CTAS-1 visit(s) are recorded as left-without-being-seen. "
                        "A resuscitation-level patient leaving unseen is either a coding error or "
                        "a serious safety event worth reviewing."
                    ),
                    message_ar=f"{int(odd.sum())} حالة حرجة (CTAS 1) غادرت قبل الفحص.",
                    dimension="consistency",
                ))

    if spec.key == "bed_movements" and {"encounter_no", "seq_no", "in_at", "out_at"} <= set(frame.columns):
        ordered = frame.sort_values(["encounter_no", "seq_no"])
        previous_out = pd.to_datetime(ordered.groupby("encounter_no")["out_at"].shift(), errors="coerce")
        current_in = pd.to_datetime(ordered["in_at"], errors="coerce")
        overlap = previous_out.notna() & current_in.notna() & (current_in < previous_out - timedelta(minutes=5))
        if overlap.any():
            findings.append(Finding(
                rule_code="OVERLAPPING_BED_OCCUPANCY",
                severity="ERROR",
                column_name="in_at",
                affected_rows=int(overlap.sum()),
                sample_rows=_sample(ordered.index[overlap]),
                message_en=(
                    f"{int(overlap.sum())} movement(s) start before the previous movement for the "
                    "same encounter ended. Overlapping segments double-count patient days."
                ),
                message_ar=f"{int(overlap.sum())} حركة سرير متداخلة زمنياً.",
                dimension="consistency",
            ))

    if spec.key == "staffing" and {"rn_productive_hours", "patient_days"} <= set(frame.columns):
        hours = pd.to_numeric(frame["rn_productive_hours"], errors="coerce")
        days = pd.to_numeric(frame["patient_days"], errors="coerce")
        ratio = hours / days.replace(0, np.nan)
        implausible = ratio.notna() & ((ratio < 0.5) | (ratio > 48))
        if implausible.any():
            findings.append(Finding(
                rule_code="IMPLAUSIBLE_NURSING_HOURS",
                severity="WARNING",
                column_name="rn_productive_hours",
                affected_rows=int(implausible.sum()),
                sample_rows=_sample(frame.index[implausible]),
                message_en=(
                    f"{int(implausible.sum())} row(s) imply fewer than 0.5 or more than 48 RN hours "
                    "per patient day. Check whether hours were reported per shift but census per day."
                ),
                message_ar=f"{int(implausible.sum())} صف بساعات تمريض غير منطقية لكل يوم مريض.",
                dimension="consistency",
            ))

    return findings


def _score(*, frame: pd.DataFrame, spec: DatasetSpec, mapping: dict[str, str],
           completeness_penalty: float, duplicate_rate: float,
           chronology_violations: int, future_rows: int,
           coercion_failures: dict[str, pd.Series]) -> dict[str, float]:
    total = max(len(frame), 1)

    mapped_fields = [f for f in spec.fields if f.name in mapping]
    if mapped_fields:
        filled = np.mean([frame[f.name].notna().mean() for f in mapped_fields])
    else:
        filled = 0.0
    # Missing required fields hurt more than missing optional ones.
    completeness = max(0.0, 100.0 * filled - 100.0 * completeness_penalty)

    failed_cells = sum(int(mask.sum()) for mask in coercion_failures.values())
    total_cells = total * max(len(mapped_fields), 1)
    validity = 100.0 * (1 - failed_cells / total_cells)

    uniqueness = 100.0 * (1 - duplicate_rate)

    consistency = 100.0 * (1 - min(chronology_violations / total, 1.0))

    timeliness = 100.0 * (1 - min(future_rows / total, 1.0))

    return {
        "completeness": float(np.clip(completeness, 0, 100)),
        "validity": float(np.clip(validity, 0, 100)),
        "uniqueness": float(np.clip(uniqueness, 0, 100)),
        "consistency": float(np.clip(consistency, 0, 100)),
        "timeliness": float(np.clip(timeliness, 0, 100)),
    }
