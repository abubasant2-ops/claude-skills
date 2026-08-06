"""Column mapping, type coercion and validation rules."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from app.ingest import mapper
from app.ingest.datasets import ED_VISITS, ENCOUNTERS, get_dataset
from app.ingest.validators import validate


# ---------------------------------------------------------------------
# Header normalisation and mapping
# ---------------------------------------------------------------------
@pytest.mark.parametrize("raw,expected", [
    ("Arrival Time", "arrival_time"),
    ("ARRIVAL_DTTM", "arrival"),
    ("  Encounter No.  ", "encounter_no"),
    ("Triage Time (dd/mm/yyyy hh:mm)", "triage_time"),
    ("CTAS-Level", "ctas_level"),
])
def test_normalise_header(raw, expected):
    assert mapper.normalise_header(raw) == expected


def test_map_columns_resolves_aliases_and_arabic():
    frame = pd.DataFrame({
        "Visit No": ["V1"],
        "وقت الوصول": [datetime(2026, 3, 1, 8, 0)],
        "Triage Time": [datetime(2026, 3, 1, 8, 10)],
        "Acuity": [3],
        "Seen By Doctor": [datetime(2026, 3, 1, 8, 40)],
    })
    profiles = mapper.profile_columns(frame)
    mapping = mapper.map_columns(profiles, ED_VISITS)

    assert mapping["encounter_no"] == "Visit No"
    assert mapping["arrival_at"] == "وقت الوصول"
    assert mapping["triage_at"] == "Triage Time"
    assert mapping["ctas_level"] == "Acuity"
    assert mapping["physician_at"] == "Seen By Doctor"


def test_map_columns_does_not_claim_one_field_twice():
    frame = pd.DataFrame({"Arrival Time": [1], "Arrival Date": [2], "Visit No": ["V1"]})
    profiles = mapper.profile_columns(frame)
    mapping = mapper.map_columns(profiles, ED_VISITS)
    assert len(set(mapping.values())) == len(mapping)


def test_unrecognised_column_is_left_unmapped_not_guessed():
    frame = pd.DataFrame({"Visit No": ["V1"], "Zzz Random Vendor Field": ["x"]})
    profiles = mapper.profile_columns(frame)
    mapper.map_columns(profiles, ED_VISITS)
    unmapped = [p.source_name for p in profiles if p.mapped_to is None]
    assert "Zzz Random Vendor Field" in unmapped


# ---------------------------------------------------------------------
# Datetime coercion
# ---------------------------------------------------------------------
def test_excel_serial_number_is_decoded():
    # Excel serial 45000 is 2023-03-15 under the 1900 date system.
    assert mapper._coerce_datetime_scalar(45000) == datetime(2023, 3, 15)


def test_small_numbers_are_not_treated_as_dates():
    """A CTAS level of 3 must never become a date in 1900."""
    assert mapper._coerce_datetime_scalar(3) is None
    assert mapper._coerce_datetime_scalar(1500) is None


def test_arabic_indic_digits_are_parsed():
    assert mapper._coerce_datetime_scalar("٢٠٢٦-٠٣-٠١ ٠٨:٣٠") == datetime(2026, 3, 1, 8, 30)


def test_dayfirst_is_decided_from_the_whole_column():
    day_first = pd.Series(["01/02/2026", "15/02/2026", "28/02/2026"])
    month_first = pd.Series(["01/02/2026", "02/15/2026", "02/28/2026"])
    assert mapper.detect_dayfirst(day_first) is True
    assert mapper.detect_dayfirst(month_first) is False


def test_column_format_detection_picks_a_single_format():
    series = pd.Series(["2026-03-01 08:00:00", "2026-03-02 09:30:00", "2026-03-03 10:15:00"])
    assert mapper.detect_column_format(series) == "%Y-%m-%d %H:%M:%S"


def test_coerce_series_reports_unparseable_values():
    spec = ENCOUNTERS.field_map["admission_at"]
    series = pd.Series(["2026-03-01 08:00:00", "not a date", None])
    coerced, failed = mapper.coerce_series(series, spec)
    assert coerced.iloc[0] == pd.Timestamp("2026-03-01 08:00:00")
    assert failed.iloc[1]            # present but unparseable
    assert not failed.iloc[2]        # absent is missing, not invalid


def test_domain_values_are_normalised_case_and_separator_insensitively():
    spec = ED_VISITS.field_map["arrival_mode"]
    coerced, _ = mapper.coerce_series(pd.Series(["walk in", "Walk-In", "AMBULANCE"]), spec)
    assert list(coerced) == ["WALK_IN", "WALK_IN", "AMBULANCE"]


def test_empty_column_does_not_crash_domain_normalisation():
    """An all-blank column comes back from pandas as float NaN, which is truthy."""
    spec = ED_VISITS.field_map["arrival_mode"]
    coerced, _ = mapper.coerce_series(pd.Series([None, None, None]), spec)
    assert coerced.isna().all()


# ---------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------
def _validate(frame: pd.DataFrame, spec, mapping=None):
    mapping = mapping or {c: c for c in frame.columns}
    coerced, failures = mapper.apply_mapping(frame, mapping, spec)
    return coerced, validate(coerced, spec, failures, mapping)


def test_missing_required_column_is_critical():
    spec = get_dataset("ed_visits")
    frame = pd.DataFrame({"encounter_no": ["V1"]})
    _, result = _validate(frame, spec, {"encounter_no": "encounter_no"})
    codes = {f.rule_code for f in result.findings}
    assert "MISSING_REQUIRED_COLUMN" in codes
    assert result.blocking


def test_duplicate_natural_key_quarantines_later_rows():
    spec = get_dataset("ed_visits")
    frame = pd.DataFrame({
        "encounter_no": ["V1", "V1", "V2"],
        "arrival_at": ["2026-03-01 08:00:00"] * 3,
    })
    _, result = _validate(frame, spec)
    assert "DUPLICATE_NATURAL_KEY" in {f.rule_code for f in result.findings}
    assert len(result.rejected_index) == 1


def test_chronology_violation_quarantines_the_row():
    """A departure before arrival would yield a negative length of stay."""
    spec = get_dataset("ed_visits")
    frame = pd.DataFrame({
        "encounter_no": ["V1", "V2"],
        "arrival_at": ["2026-03-01 08:00:00", "2026-03-01 08:00:00"],
        "departure_at": ["2026-03-01 12:00:00", "2026-03-01 04:00:00"],
    })
    coerced, result = _validate(frame, spec)
    assert "CHRONOLOGY_VIOLATION" in {f.rule_code for f in result.findings}
    assert list(result.rejected_index) == [1]


def test_required_value_missing_is_rejected_but_optional_is_only_flagged():
    spec = get_dataset("ed_visits")
    frame = pd.DataFrame({
        "encounter_no": ["V1", None],
        "arrival_at": ["2026-03-01 08:00:00", "2026-03-01 09:00:00"],
        "ctas_level": [None, None],
    })
    _, result = _validate(frame, spec)
    codes = {f.rule_code for f in result.findings}
    assert "REQUIRED_VALUE_MISSING" in codes
    assert "SPARSE_COLUMN" in codes
    assert len(result.rejected_index) == 1


def test_out_of_range_value_is_flagged_not_rejected():
    spec = get_dataset("ed_visits")
    frame = pd.DataFrame({
        "encounter_no": ["V1"],
        "arrival_at": ["2026-03-01 08:00:00"],
        "ctas_level": [9],
    })
    _, result = _validate(frame, spec)
    assert "VALUE_OUT_OF_RANGE" in {f.rule_code for f in result.findings}
    assert len(result.rejected_index) == 0


def test_lwbs_with_physician_contact_is_contradictory():
    spec = get_dataset("ed_visits")
    frame = pd.DataFrame({
        "encounter_no": ["V1"],
        "arrival_at": ["2026-03-01 08:00:00"],
        "physician_at": ["2026-03-01 08:30:00"],
        "ed_disposition": ["LWBS"],
    })
    coerced, _ = mapper.apply_mapping(frame, {c: c for c in frame.columns}, spec)
    coerced["is_lwbs"] = True
    result = validate(coerced, spec, {}, {c: c for c in frame.columns})
    assert "LWBS_WITH_PHYSICIAN_CONTACT" in {f.rule_code for f in result.findings}


def test_clean_data_scores_near_100():
    spec = get_dataset("ed_visits")
    frame = pd.DataFrame({
        "encounter_no": [f"V{i}" for i in range(20)],
        "arrival_at": [f"2026-03-01 {8 + i % 12:02d}:00:00" for i in range(20)],
        "triage_at": [f"2026-03-01 {8 + i % 12:02d}:10:00" for i in range(20)],
        "ctas_level": [3] * 20,
        "ed_disposition": ["DISCHARGE"] * 20,
    })
    _, result = _validate(frame, spec)
    assert result.quality_score > 95
    assert not result.blocking


def test_quality_score_falls_with_dirty_data():
    spec = get_dataset("ed_visits")
    frame = pd.DataFrame({
        "encounter_no": ["V1", "V1", None, "V4"],
        "arrival_at": ["2026-03-01 08:00:00", "2026-03-01 08:00:00", "junk", None],
        "ctas_level": [None, None, None, None],
    })
    _, result = _validate(frame, spec)
    assert result.quality_score < 70
