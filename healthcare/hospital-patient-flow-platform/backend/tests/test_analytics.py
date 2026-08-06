"""Metric definitions verified against hand-computed expectations."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from app.analytics import capacity, ed, nursing, quality, service
from app.analytics.common import expand_to_days, rag_status, safe_div


# ---------------------------------------------------------------------
# Fractional patient days
# ---------------------------------------------------------------------
def test_expand_to_days_splits_a_stay_across_calendar_days():
    """22:00 Monday to 06:00 Wednesday is 2h + 24h + 6h, not 'two midnights'."""
    intervals = pd.DataFrame({
        "unit_id": [1],
        "in_at": [datetime(2026, 3, 2, 22, 0)],
        "out_at": [datetime(2026, 3, 4, 6, 0)],
    })
    result = expand_to_days(intervals, window_start=date(2026, 3, 1), window_end=date(2026, 3, 31))
    by_day = dict(zip(result["service_date"], result["patient_days"]))

    assert by_day[date(2026, 3, 2)] == pytest.approx(2 / 24, abs=1e-6)
    assert by_day[date(2026, 3, 3)] == pytest.approx(1.0, abs=1e-6)
    assert by_day[date(2026, 3, 4)] == pytest.approx(6 / 24, abs=1e-6)
    assert result["patient_days"].sum() == pytest.approx(32 / 24, abs=1e-6)


def test_expand_to_days_counts_same_day_admission_and_discharge():
    """A six-hour day case contributes 0.25 patient days, not zero."""
    intervals = pd.DataFrame({
        "unit_id": [1],
        "in_at": [datetime(2026, 3, 2, 9, 0)],
        "out_at": [datetime(2026, 3, 2, 15, 0)],
    })
    result = expand_to_days(intervals, window_start=date(2026, 3, 1), window_end=date(2026, 3, 3))
    assert result["patient_days"].sum() == pytest.approx(0.25, abs=1e-6)


def test_expand_to_days_clips_to_the_reporting_window():
    intervals = pd.DataFrame({
        "unit_id": [1],
        "in_at": [datetime(2026, 2, 20, 0, 0)],
        "out_at": [datetime(2026, 3, 5, 0, 0)],
    })
    result = expand_to_days(intervals, window_start=date(2026, 3, 1), window_end=date(2026, 3, 3))
    # Only 1-3 March fall inside the window: three full days.
    assert result["patient_days"].sum() == pytest.approx(3.0, abs=1e-6)


def test_open_stay_is_capped_at_the_supplied_now():
    intervals = pd.DataFrame({
        "unit_id": [1],
        "in_at": [datetime(2026, 3, 1, 0, 0)],
        "out_at": [None],
    })
    result = expand_to_days(
        intervals, window_start=date(2026, 3, 1), window_end=date(2026, 3, 31),
        open_interval_end=datetime(2026, 3, 3, 12, 0),
    )
    assert result["patient_days"].sum() == pytest.approx(2.5, abs=1e-6)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def test_safe_div_returns_none_rather_than_zero_or_infinity():
    assert safe_div(5, 0) is None
    assert safe_div(None, 10) is None
    assert safe_div(1, 4, scale=100) == 25.0


@pytest.mark.parametrize("value,higher_better,expected", [
    (95, False, "red"),        # occupancy above the red line of 94
    (92, False, "amber"),      # past amber (90), short of red
    (88, False, "green"),      # still inside the amber threshold
    (40, True, "red"),         # satisfaction below the red line of 60
    (70, True, "amber"),
    (95, True, "green"),
    (None, False, "unknown"),
])
def test_rag_status_flips_with_direction(value, higher_better, expected):
    assert rag_status(value, target=85, amber=90 if not higher_better else 80,
                      red=94 if not higher_better else 60,
                      higher_is_better=higher_better) == expected


# ---------------------------------------------------------------------
# NEDOCS
# ---------------------------------------------------------------------
def test_nedocs_matches_the_published_formula():
    score, band, _ = ed.nedocs(
        ed_patients=20, ed_beds=30, admitted_in_ed=3, hospital_beds=300,
        longest_admit_wait_hours=1, longest_waiting_room_minutes=20, ventilated_patients=0,
    )
    # -20 + 85.8*(20/30) + 600*(3/300) + 13.4*1 + 0.93*20 = 75.2
    assert score == pytest.approx(75.2, abs=0.1)
    assert band == "EXTREMELY_BUSY"


def test_nedocs_is_clipped_to_the_instrument_range():
    score, band, _ = ed.nedocs(
        ed_patients=90, ed_beds=30, admitted_in_ed=40, hospital_beds=300,
        longest_admit_wait_hours=14, longest_waiting_room_minutes=400, ventilated_patients=5,
    )
    assert score == 200.0
    assert band == "DANGEROUSLY_OVERCROWDED"


def test_nedocs_without_beds_is_unknown_not_a_number():
    score, band, _ = ed.nedocs(
        ed_patients=10, ed_beds=0, admitted_in_ed=0, hospital_beds=0,
        longest_admit_wait_hours=0, longest_waiting_room_minutes=0,
    )
    assert band == "UNKNOWN"
    assert score == 0.0


def test_hourly_state_never_produces_a_negative_wait():
    """A patient arriving mid-hour is not present at the top of that hour."""
    visits = pd.DataFrame({
        "arrival_at": [pd.Timestamp("2026-03-01 08:55")],
        "departure_at": [pd.Timestamp("2026-03-01 11:30")],
        "disposition_at": [pd.Timestamp("2026-03-01 11:00")],
        "admission_decision_at": [pd.NaT],
        "ed_disposition": ["DISCHARGE"],
        "on_ventilator": [False],
        "room_at": [pd.NaT],
        "physician_at": [pd.NaT],
    })
    hourly = ed.hourly_state(visits, date(2026, 3, 1), date(2026, 3, 1),
                             ed_beds=10, hospital_beds=100)
    assert (hourly["longest_wait_minutes"] >= 0).all()
    # Present at 09:00 and 10:00 and 11:00, but not at 08:00.
    assert hourly.set_index("bucket_start").loc["2026-03-01 08:00", "census"] == 0
    assert hourly.set_index("bucket_start").loc["2026-03-01 09:00", "census"] == 1


# ---------------------------------------------------------------------
# NEWS2
# ---------------------------------------------------------------------
def test_news2_normal_observations_score_zero():
    score, band = quality.news2_score(
        respiratory_rate=16, spo2=98, on_oxygen=False, systolic_bp=120,
        heart_rate=70, temperature_c=36.8, consciousness="A",
    )
    assert score == 0
    assert band == "LOW"


def test_news2_deteriorating_patient_scores_high():
    # RR 22 (2) + SpO2 93 (2) + oxygen (2) + SBP 95 (2) + HR 105 (1) + 38.5C (1) + A (0)
    score, band = quality.news2_score(
        respiratory_rate=22, spo2=93, on_oxygen=True, systolic_bp=95,
        heart_rate=105, temperature_c=38.5, consciousness="A",
    )
    assert score == 10
    assert band == "HIGH"


def test_news2_single_extreme_parameter_escalates_the_band():
    """One parameter scoring 3 warrants review even when the total is low."""
    score, band = quality.news2_score(
        respiratory_rate=26, spo2=98, on_oxygen=False, systolic_bp=120,
        heart_rate=70, temperature_c=36.8, consciousness="A",
    )
    assert score == 3
    assert band == "LOW_MEDIUM"


def test_news2_is_withheld_when_too_few_parameters_are_present():
    """A partial NEWS2 reads falsely reassuring, so none is returned."""
    score, band = quality.news2_score(respiratory_rate=16, spo2=98)
    assert score is None
    assert band is None


# ---------------------------------------------------------------------
# Readmission
# ---------------------------------------------------------------------
def test_readmission_counts_only_unplanned_returns_within_the_window():
    encounters = pd.DataFrame({
        "encounter_id": [1, 2, 3, 4],
        "patient_id": [100, 100, 200, 200],
        "encounter_class": ["INPATIENT"] * 4,
        "admission_at": [
            pd.Timestamp("2026-03-01"), pd.Timestamp("2026-03-10"),   # 9 days -> counts
            pd.Timestamp("2026-03-01"), pd.Timestamp("2026-04-20"),   # 45 days -> does not
        ],
        "discharge_at": [
            pd.Timestamp("2026-03-05"), pd.Timestamp("2026-03-12"),
            pd.Timestamp("2026-03-06"), pd.Timestamp("2026-04-25"),
        ],
        "disposition": ["HOME"] * 4,
        "is_death": [False] * 4,
        "is_elective": [False] * 4,
    })
    rate, readmitted, index_count = quality.readmission_rate(
        encounters, date(2026, 3, 1), date(2026, 3, 8)
    )
    # Index discharges inside the window: encounters 1 and 3. Only 1 is readmitted.
    assert index_count == 2
    assert readmitted == 1
    assert rate == pytest.approx(50.0)


def test_deaths_are_excluded_from_the_readmission_denominator():
    encounters = pd.DataFrame({
        "encounter_id": [1],
        "patient_id": [100],
        "encounter_class": ["INPATIENT"],
        "admission_at": [pd.Timestamp("2026-03-01")],
        "discharge_at": [pd.Timestamp("2026-03-05")],
        "disposition": ["DECEASED"],
        "is_death": [True],
        "is_elective": [False],
    })
    rate, _, index_count = quality.readmission_rate(encounters, date(2026, 3, 1), date(2026, 3, 8))
    assert index_count == 0
    assert rate is None


def test_elective_return_is_not_a_readmission():
    encounters = pd.DataFrame({
        "encounter_id": [1, 2],
        "patient_id": [100, 100],
        "encounter_class": ["INPATIENT", "INPATIENT"],
        "admission_at": [pd.Timestamp("2026-03-01"), pd.Timestamp("2026-03-10")],
        "discharge_at": [pd.Timestamp("2026-03-05"), pd.Timestamp("2026-03-12")],
        "disposition": ["HOME", "HOME"],
        "is_death": [False, False],
        "is_elective": [False, True],
    })
    rate, readmitted, _ = quality.readmission_rate(encounters, date(2026, 3, 1), date(2026, 3, 8))
    assert readmitted == 0
    assert rate == pytest.approx(0.0)


# ---------------------------------------------------------------------
# End-to-end against the fixture hospital
# ---------------------------------------------------------------------
def test_occupancy_and_alos_against_the_fixture(session, hospital):
    result = service.analyse(session, facility_id=hospital["facility"].facility_id,
                             start=hospital["start"], end=hospital["end"],
                             include_previous=False)
    metrics = result.metrics

    # Ten 48-hour stays admitted 08:00 on 1-10 March. Eight complete inside
    # the window and contribute 2.0 patient days each. The 9 March stay is
    # clipped at the window edge (0.667 + 1.0) and the 10 March stay
    # contributes only its first 16 hours (0.667):
    #     8 x 2.0 + 1.667 + 0.667 = 18.334 patient days.
    # The denominator is every inpatient bed -- the 10-bed ward plus the
    # empty 4-bed ICU -- across 10 days, so 140 staffed bed days. The ED's
    # 10 spaces are excluded because they are not inpatient capacity.
    occupancy = metrics["occupancy_rate"].value
    assert occupancy == pytest.approx(100 * 18.334 / 140, abs=0.1)

    # Every completed stay is exactly 48 hours.
    assert metrics["alos_days"].value == pytest.approx(2.0, abs=0.01)

    # One death among the discharges that fall inside the window.
    assert metrics["mortality_rate"].value is not None
    assert metrics["mortality_rate"].value > 0


def test_hospital_acquired_rate_excludes_present_on_admission(session, hospital):
    result = service.analyse(session, facility_id=hospital["facility"].facility_id,
                             start=hospital["start"], end=hospital["end"],
                             include_previous=False)
    # The only HAI in the fixture is flagged present-on-admission.
    assert result.metrics["hai_rate"].value == pytest.approx(0.0)
    # The fall is hospital-acquired and must be counted.
    assert result.metrics["fall_rate"].value > 0


def test_nursing_hours_use_derived_patient_days(session, hospital):
    result = service.analyse(session, facility_id=hospital["facility"].facility_id,
                             start=hospital["start"], end=hospital["end"],
                             include_previous=False)
    # 10 days x 90 productive hours (60 RN + 10 LPN + 20 NA) = 900 hours over
    # the 18.334 ward patient days derived above.
    assert result.metrics["nchpd"].value == pytest.approx(900 / 18.334, rel=0.01)


def test_role_dashboard_returns_only_that_role_tiles(session, hospital):
    result = service.analyse(session, facility_id=hospital["facility"].facility_id,
                             start=hospital["start"], end=hospital["end"],
                             include_previous=False)
    payload = service.dashboard(result, "CNO")
    keys = {tile["key"] for tile in payload["tiles"]}
    assert "nchpd" in keys
    assert "nedocs_score" not in keys
    assert payload["role"] == "CNO"


def test_unknown_role_is_rejected(session, hospital):
    result = service.analyse(session, facility_id=hospital["facility"].facility_id,
                             start=hospital["start"], end=hospital["end"],
                             include_previous=False)
    with pytest.raises(ValueError, match="Unknown role"):
        service.dashboard(result, "JANITOR")


def test_metrics_carry_bilingual_labels_and_targets(session, hospital):
    result = service.analyse(session, facility_id=hospital["facility"].facility_id,
                             start=hospital["start"], end=hospital["end"],
                             include_previous=False)
    occupancy = result.metrics["occupancy_rate"].to_dict()
    assert occupancy["label_ar"]
    assert occupancy["label_en"]
    assert occupancy["target"] is not None
    assert occupancy["status"] in ("green", "amber", "red", "unknown")
