"""Automatic column detection, type inference and value coercion.

Two problems this module solves that a naive ``pd.read_excel`` does not:

1. **Header drift.** The same HIS exports "Arrival Time", "ARRIVAL_DTTM"
   and "وقت الوصول" depending on who ran the report. Matching is done on a
   normalised form, then by alias, then by fuzzy similarity, and only a
   confident match is accepted -- an unconfident one is reported to the
   user for manual mapping rather than guessed at silently.

2. **Timestamp chaos.** A single hospital extract routinely mixes Excel
   serial numbers, ``dd/mm/yyyy``, ``mm/dd/yyyy``, ISO strings and
   Arabic-Indic digits. Day/month order is resolved per column using the
   whole column as evidence rather than row by row, because deciding
   ``03/04`` in isolation is a coin flip.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher

import numpy as np
import pandas as pd

from app.ingest.datasets import DatasetSpec, FieldSpec

# Accept a fuzzy match only above this ratio; below it the column is left
# unmapped so a human decides.
FUZZY_ACCEPT = 0.86

#: Arabic-Indic and Eastern Arabic-Indic digits -> ASCII.
_DIGIT_TRANSLATION = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
    "01234567890123456789",
)

_TRUE_TOKENS = {"y", "yes", "true", "t", "1", "1.0", "نعم", "صحيح"}
_FALSE_TOKENS = {"n", "no", "false", "f", "0", "0.0", "لا", "خطأ"}

_NULL_TOKENS = {
    "", "na", "n/a", "#n/a", "null", "none", "nil", "-", "--", "unknown", "unk",
    "not recorded", "nr", "#value!", "#ref!", "#div/0!", ".", "؟", "غير معروف",
}

# Excel's day zero. The 1900 leap-year bug means serials below 61 are
# ambiguous, so those are treated as unparseable rather than silently shifted.
_EXCEL_EPOCH = datetime(1899, 12, 30)


def normalise_header(raw: str) -> str:
    """Fold a spreadsheet header down to a comparable token string."""
    text = unicodedata.normalize("NFKC", str(raw)).strip().lower()
    text = text.translate(_DIGIT_TRANSLATION)
    # Arabic diacritics and tatweel carry no meaning in a column name.
    text = re.sub(r"[ؗ-ًؚ-ْـ]", "", text)
    text = re.sub(r"[\(\[\{].*?[\)\]\}]", " ", text)     # drop "(dd/mm/yyyy)" hints
    text = re.sub(r"[^0-9a-z؀-ۿ]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    # Common noise words that never distinguish two fields.
    for noise in ("_dttm", "_dt", "_ts", "_col", "_field"):
        if text.endswith(noise):
            text = text[: -len(noise)]
    return text


def _declared_forms(spec: FieldSpec) -> set[str]:
    """Names the field explicitly answers to: its own name and its aliases."""
    return {normalise_header(spec.name)} | {normalise_header(a) for a in spec.aliases}


def _derived_forms(spec: FieldSpec) -> set[str]:
    """Names inferred from a suffix convention rather than declared.

    A field called ``arrival_at`` plausibly answers to ``arrival`` and
    ``arrival_time``. These are guesses, so they are matched only after
    every declared name has had its chance -- otherwise a column headed
    "Disposition" would be captured by ``disposition_at``'s derived stem
    instead of by ``ed_disposition``, which actually declares that alias.
    """
    derived: set[str] = set()
    for form in _declared_forms(spec):
        if form.endswith("_at"):
            stem = form[:-3]
            derived.update({stem, f"{stem}_time", f"{stem}_date", f"{stem}_datetime"})
        if form.endswith("_no"):
            stem = form[:-3]
            derived.update({f"{stem}_number", f"{stem}_id", stem})
    return derived - _declared_forms(spec)


def _alias_forms(spec: FieldSpec) -> set[str]:
    return _declared_forms(spec) | _derived_forms(spec)


@dataclass
class ColumnProfile:
    """What the profiler observed about one source column."""

    source_name: str
    normalised: str
    non_null: int
    null_count: int
    null_rate: float
    distinct: int
    inferred_type: str
    samples: list[str] = field(default_factory=list)
    mapped_to: str | None = None
    match_kind: str = "unmapped"      # exact | alias | fuzzy | unmapped
    match_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "source_name": self.source_name,
            "normalised": self.normalised,
            "non_null": self.non_null,
            "null_count": self.null_count,
            "null_rate": round(self.null_rate, 4),
            "distinct": self.distinct,
            "inferred_type": self.inferred_type,
            "samples": self.samples,
            "mapped_to": self.mapped_to,
            "match_kind": self.match_kind,
            "match_score": round(self.match_score, 3),
        }


def _is_null(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and np.isnan(value):
        return True
    if value is pd.NaT:
        return True
    text = str(value).strip().lower()
    return text in _NULL_TOKENS


def infer_type(series: pd.Series) -> str:
    """Best-effort semantic type for a raw column."""
    values = [v for v in series.tolist() if not _is_null(v)]
    if not values:
        return "empty"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_bool_dtype(series):
        return "boolean"

    sample = values[:500]
    lowered = {str(v).strip().lower() for v in sample}
    if lowered <= (_TRUE_TOKENS | _FALSE_TOKENS):
        return "boolean"

    parsed_dt = sum(1 for v in sample if _coerce_datetime_scalar(v) is not None)
    if parsed_dt / len(sample) >= 0.9:
        # Distinguish a pure date column from a timestamp column.
        has_time = any(
            (dt := _coerce_datetime_scalar(v)) is not None
            and (dt.hour or dt.minute or dt.second)
            for v in sample
        )
        return "datetime" if has_time else "date"

    numeric = pd.to_numeric(pd.Series(sample).astype(str).str.translate(_DIGIT_TRANSLATION),
                            errors="coerce")
    if numeric.notna().mean() >= 0.95:
        finite = numeric.dropna()
        if (finite % 1 == 0).all():
            return "integer"
        return "number"
    return "string"


def profile_columns(df: pd.DataFrame) -> list[ColumnProfile]:
    total = len(df)
    profiles: list[ColumnProfile] = []
    for column in df.columns:
        series = df[column]
        null_mask = series.map(_is_null)
        non_null = int((~null_mask).sum())
        samples = [
            str(v) for v in series[~null_mask].head(3).tolist()
        ]
        profiles.append(
            ColumnProfile(
                source_name=str(column),
                normalised=normalise_header(column),
                non_null=non_null,
                null_count=total - non_null,
                null_rate=(total - non_null) / total if total else 0.0,
                distinct=int(series[~null_mask].astype(str).nunique()),
                inferred_type=infer_type(series),
                samples=samples,
            )
        )
    return profiles


def map_columns(profiles: list[ColumnProfile], spec: DatasetSpec) -> dict[str, str]:
    """Resolve source columns onto canonical field names.

    Returns ``{canonical_field: source_column}``. Profiles are annotated in
    place with how each match was made so the UI can show its reasoning and
    let the user override it.
    """
    declared_index: dict[str, list[str]] = {}
    derived_index: dict[str, list[str]] = {}
    for field_spec in spec.fields:
        for form in _declared_forms(field_spec):
            declared_index.setdefault(form, []).append(field_spec.name)
        for form in _derived_forms(field_spec):
            derived_index.setdefault(form, []).append(field_spec.name)

    mapping: dict[str, str] = {}
    claimed: set[str] = set()

    # Passes 1 and 2 -- declared names first, then suffix-derived guesses.
    # Both are deterministic; only the confidence label differs.
    for index, kind in ((declared_index, "declared"), (derived_index, "derived")):
        for profile in profiles:
            if profile.mapped_to or profile.normalised not in index:
                continue
            candidates = [c for c in index[profile.normalised] if c not in claimed]
            if not candidates:
                continue
            # Prefer the field whose own name matches the header exactly.
            target = next(
                (c for c in candidates if normalise_header(c) == profile.normalised),
                candidates[0],
            )
            mapping[target] = profile.source_name
            claimed.add(target)
            profile.mapped_to = target
            if normalise_header(target) == profile.normalised:
                profile.match_kind = "exact"
            else:
                profile.match_kind = "alias" if kind == "declared" else "derived"
            profile.match_score = 1.0 if kind == "declared" else 0.9

    # Pass 2 -- fuzzy, only for what is still unclaimed on both sides.
    remaining_fields = [f for f in spec.fields if f.name not in claimed]
    for profile in profiles:
        if profile.mapped_to or not remaining_fields:
            continue
        best_name, best_score = None, 0.0
        for field_spec in remaining_fields:
            for form in _alias_forms(field_spec):
                score = SequenceMatcher(None, profile.normalised, form).ratio()
                if score > best_score:
                    best_name, best_score = field_spec.name, score
        if best_name and best_score >= FUZZY_ACCEPT:
            mapping[best_name] = profile.source_name
            claimed.add(best_name)
            profile.mapped_to = best_name
            profile.match_kind = "fuzzy"
            profile.match_score = best_score
            remaining_fields = [f for f in remaining_fields if f.name != best_name]

    return mapping


# ---------------------------------------------------------------------
# Value coercion
# ---------------------------------------------------------------------
def _coerce_datetime_scalar(value) -> datetime | None:
    if _is_null(value):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, (int, float, np.integer, np.floating)):
        serial = float(value)
        # Excel serials for real hospital dates land well above 20000
        # (year 1954+); anything smaller is a number, not a date.
        if 20000 <= serial <= 80000:
            return _EXCEL_EPOCH + timedelta(days=serial)
        return None

    text = unicodedata.normalize("NFKC", str(value)).strip().translate(_DIGIT_TRANSLATION)
    if not text or text.lower() in _NULL_TOKENS:
        return None
    # Arabic AM/PM markers appear in locale-formatted exports.
    text = text.replace("ص", "AM").replace("م", "PM")
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        parsed = pd.to_datetime(text, errors="coerce")
    except (ValueError, TypeError):
        return None
    return None if pd.isna(parsed) else parsed.to_pydatetime()


def detect_column_format(series: pd.Series, *, sample_size: int = 300,
                         threshold: float = 0.9) -> str | None:
    """Find one strptime format that parses most of a column.

    Hospital extracts are almost always internally consistent, so finding
    the column's format once lets the whole column go through pandas'
    vectorised parser instead of a per-value format search. On a 60,000-row
    file with five timestamp columns that is the difference between
    seconds and minutes.
    """
    values = [
        unicodedata.normalize("NFKC", str(v)).strip().translate(_DIGIT_TRANSLATION)
        for v in series.dropna().head(sample_size).tolist()
    ]
    values = [v for v in values if v and v.lower() not in _NULL_TOKENS]
    if not values:
        return None

    for fmt in _DATETIME_FORMATS:
        parsed = 0
        for value in values:
            try:
                datetime.strptime(value, fmt)
                parsed += 1
            except ValueError:
                continue
        if parsed / len(values) >= threshold:
            return fmt
    return None


_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d",
    "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
    "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y",
    "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y",
    "%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y",
    "%d %b %Y %H:%M", "%b %d, %Y %I:%M %p", "%Y%m%d%H%M%S", "%Y%m%d",
)


def detect_dayfirst(series: pd.Series) -> bool:
    """Decide day/month order from the whole column.

    Any value whose first component exceeds 12 proves day-first; any value
    whose second component exceeds 12 proves month-first. Whichever
    evidence is stronger wins, defaulting to day-first because that is the
    convention across the Gulf.
    """
    day_first_evidence = month_first_evidence = 0
    pattern = re.compile(r"^\s*(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})")
    for value in series.dropna().astype(str).head(2000):
        match = pattern.match(value.translate(_DIGIT_TRANSLATION))
        if not match:
            continue
        first, second = int(match.group(1)), int(match.group(2))
        if first > 12 >= second:
            day_first_evidence += 1
        elif second > 12 >= first:
            month_first_evidence += 1
    if month_first_evidence > day_first_evidence:
        return False
    return True


def coerce_series(series: pd.Series, spec: FieldSpec) -> tuple[pd.Series, pd.Series]:
    """Coerce one column to its declared type.

    Returns ``(coerced, failed_mask)`` where ``failed_mask`` marks values
    that were present in the source but could not be converted -- those are
    the rows the data-quality report has to talk about.
    """
    present = ~series.map(_is_null)

    if spec.dtype in ("datetime", "date"):
        dayfirst = detect_dayfirst(series)

        if pd.api.types.is_datetime64_any_dtype(series):
            coerced = pd.to_datetime(series, errors="coerce")
        else:
            # Fast path: one detected format for the whole column.
            column_format = detect_column_format(series)
            if column_format is not None:
                text = (series.astype(str).str.strip()
                        .str.translate(_DIGIT_TRANSLATION))
                coerced = pd.to_datetime(text, format=column_format, errors="coerce")
            else:
                coerced = pd.to_datetime(pd.Series(
                    [None] * len(series), index=series.index), errors="coerce")

        # Anything the fast path missed -- a stray format, an Excel serial,
        # a locale-formatted stamp -- is retried value by value.
        unresolved = present & coerced.isna()
        if unresolved.any():
            coerced = coerced.astype(object)
            coerced.loc[unresolved] = series[unresolved].map(_coerce_datetime_scalar)
            coerced = pd.to_datetime(coerced, errors="coerce")

        unresolved = present & coerced.isna()
        if unresolved.any():
            fallback = pd.to_datetime(
                series[unresolved].astype(str).str.translate(_DIGIT_TRANSLATION),
                errors="coerce", dayfirst=dayfirst,
            )
            coerced.loc[unresolved] = fallback
        coerced = pd.to_datetime(coerced, errors="coerce")
        if spec.dtype == "date":
            coerced = coerced.dt.date
        return coerced, present & pd.isna(coerced)

    if spec.dtype == "boolean":
        def to_bool(value):
            if _is_null(value):
                return None
            if isinstance(value, (bool, np.bool_)):
                return bool(value)
            token = str(value).strip().lower()
            if token in _TRUE_TOKENS:
                return True
            if token in _FALSE_TOKENS:
                return False
            return None
        coerced = series.map(to_bool)
        return coerced, present & coerced.isna()

    if spec.dtype in ("integer", "number"):
        cleaned = (
            series.astype(str)
            .str.translate(_DIGIT_TRANSLATION)
            .str.replace(",", "", regex=False)
            .str.replace("%", "", regex=False)
            .str.strip()
        )
        coerced = pd.to_numeric(cleaned, errors="coerce")
        if spec.dtype == "integer":
            coerced = coerced.round()
        coerced = coerced.where(present)
        return coerced, present & coerced.isna()

    # string
    coerced = series.map(lambda v: None if _is_null(v) else str(v).strip())
    if spec.domain:
        # Domain values are compared case- and separator-insensitively, so
        # "walk in", "Walk-In" and "WALK_IN" all land on the same code.
        lookup = {re.sub(r"[^a-z0-9]", "", d.lower()): d for d in spec.domain}

        def normalise(value):
            # An all-empty column comes back from map() as float NaN rather
            # than None, and NaN is truthy -- hence the explicit type check.
            if not isinstance(value, str) or not value:
                return None if _is_null(value) else value
            return lookup.get(re.sub(r"[^a-z0-9]", "", value.lower()), value)

        coerced = coerced.map(normalise)
    return coerced, pd.Series(False, index=series.index)


def apply_mapping(df: pd.DataFrame, mapping: dict[str, str], spec: DatasetSpec
                  ) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    """Project a raw frame onto canonical fields and coerce every column."""
    out = pd.DataFrame(index=df.index)
    failures: dict[str, pd.Series] = {}
    for field_spec in spec.fields:
        source = mapping.get(field_spec.name)
        if source is None or source not in df.columns:
            out[field_spec.name] = None
            continue
        coerced, failed = coerce_series(df[source], field_spec)
        out[field_spec.name] = coerced
        if failed.any():
            failures[field_spec.name] = failed
    return out, failures
