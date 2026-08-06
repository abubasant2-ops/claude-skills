"""Frame loaders sitting between SQLAlchemy and the metric modules.

Keeping I/O here means every metric function takes plain DataFrames, so
the whole analytics layer is unit-testable without a database and the
metric definitions can be read without SQL noise in the way.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    BedMovement,
    DiagnosticOrder,
    EdVisit,
    Encounter,
    IcuStay,
    OrCase,
    PatientExperience,
    SafetyEvent,
    StaffingDay,
    Unit,
    VitalsEws,
)


def _to_frame(rows, columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=columns) if rows else pd.DataFrame(columns=columns)


def _localise(series: pd.Series) -> pd.Series:
    """Convert a timestamp column to facility-local wall-clock time.

    The warehouse stores every clinical timestamp as ``TIMESTAMPTZ``, which
    is right: an ED arrival happened at one instant regardless of who reads
    it. PostgreSQL therefore hands back timezone-aware values, while SQLite
    hands back naive ones.

    The analytics layer works in facility-local wall time throughout --
    "hour of day" has to mean the hour the ward experienced, not the hour
    in UTC. Converting to the facility timezone and then dropping the
    offset gives one consistent representation on both backends. Without
    this, every comparison against a naive period boundary raises on
    PostgreSQL, and any that survived would shift the ED arrival profile by
    the UTC offset.
    """
    stamps = pd.to_datetime(series, errors="coerce")
    if getattr(stamps.dtype, "tz", None) is not None:
        stamps = stamps.dt.tz_convert(get_settings().facility_timezone).dt.tz_localize(None)
    return stamps


def _window(start: date, end: date) -> tuple[datetime, datetime]:
    """Half-open datetime window covering the inclusive date range."""
    return datetime.combine(start, time.min), datetime.combine(end + timedelta(days=1), time.min)


def load_units(session: Session, facility_id: int) -> pd.DataFrame:
    rows = session.execute(
        select(Unit.unit_id, Unit.code, Unit.name_en, Unit.name_ar, Unit.kind,
               Unit.specialty, Unit.physical_beds, Unit.staffed_beds,
               Unit.target_occupancy, Unit.is_active)
        .where(Unit.facility_id == facility_id)
    ).all()
    frame = _to_frame(rows, ["unit_id", "code", "name_en", "name_ar", "kind", "specialty",
                             "physical_beds", "staffed_beds", "target_occupancy", "is_active"])
    if not frame.empty:
        frame["staffed_beds"] = pd.to_numeric(frame["staffed_beds"], errors="coerce").fillna(0)
        frame["target_occupancy"] = pd.to_numeric(frame["target_occupancy"], errors="coerce")
    return frame


def load_encounters(session: Session, facility_id: int, start: date, end: date) -> pd.DataFrame:
    """Encounters that overlap the window in any way.

    The filter deliberately catches encounters admitted before the window
    and still open inside it -- excluding them would understate occupancy
    for every long-stay patient.
    """
    lower, upper = _window(start, end)
    rows = session.execute(
        select(Encounter.encounter_id, Encounter.patient_id, Encounter.source_encounter_no,
               Encounter.encounter_class, Encounter.admitting_unit_id, Encounter.discharge_unit_id,
               Encounter.specialty, Encounter.primary_diagnosis_code, Encounter.is_elective,
               Encounter.registration_at, Encounter.admission_at, Encounter.admission_decision_at,
               Encounter.bed_requested_at, Encounter.bed_assigned_at, Encounter.ward_arrival_at,
               Encounter.discharge_order_at, Encounter.discharge_ready_at, Encounter.discharge_at,
               Encounter.disposition, Encounter.is_death, Encounter.los_hours)
        .where(
            Encounter.facility_id == facility_id,
            Encounter.admission_at < upper,
            (Encounter.discharge_at.is_(None)) | (Encounter.discharge_at >= lower),
        )
    ).all()
    columns = ["encounter_id", "patient_id", "source_encounter_no", "encounter_class",
               "admitting_unit_id", "discharge_unit_id", "specialty", "primary_diagnosis_code",
               "is_elective", "registration_at", "admission_at", "admission_decision_at",
               "bed_requested_at", "bed_assigned_at", "ward_arrival_at", "discharge_order_at",
               "discharge_ready_at", "discharge_at", "disposition", "is_death", "los_hours"]
    frame = _to_frame(rows, columns)
    for column in columns:
        if column.endswith("_at"):
            frame[column] = _localise(frame[column])
    return frame


def load_all_encounters_for_readmission(session: Session, facility_id: int,
                                        start: date, end: date) -> pd.DataFrame:
    """Discharges in the window plus the following 30 days of admissions.

    Readmission needs a look-ahead the reporting window itself does not
    contain, so the lookup is widened rather than computed on truncated data.
    """
    lower, upper = _window(start, end + timedelta(days=31))
    rows = session.execute(
        select(Encounter.encounter_id, Encounter.patient_id, Encounter.encounter_class,
               Encounter.discharge_unit_id, Encounter.specialty, Encounter.admission_at,
               Encounter.discharge_at, Encounter.disposition, Encounter.is_death,
               Encounter.is_elective)
        .where(
            Encounter.facility_id == facility_id,
            Encounter.admission_at.is_not(None),
            Encounter.admission_at < upper,
            (Encounter.discharge_at.is_(None)) | (Encounter.discharge_at >= lower - timedelta(days=31)),
        )
    ).all()
    frame = _to_frame(rows, ["encounter_id", "patient_id", "encounter_class", "discharge_unit_id",
                             "specialty", "admission_at", "discharge_at", "disposition",
                             "is_death", "is_elective"])
    for column in ("admission_at", "discharge_at"):
        frame[column] = _localise(frame[column])
    return frame


def load_ed_visits(session: Session, facility_id: int, start: date, end: date) -> pd.DataFrame:
    lower, upper = _window(start, end)
    rows = session.execute(
        select(EdVisit.ed_visit_id, EdVisit.encounter_id, EdVisit.arrival_at, EdVisit.arrival_mode,
               EdVisit.triage_at, EdVisit.ctas_level, EdVisit.room_at, EdVisit.physician_at,
               EdVisit.disposition_at, EdVisit.departure_at, EdVisit.ed_disposition,
               EdVisit.is_lwbs, EdVisit.is_lama, EdVisit.is_72h_revisit, EdVisit.on_ventilator,
               Encounter.admission_decision_at)
        .join(Encounter, Encounter.encounter_id == EdVisit.encounter_id)
        .where(EdVisit.facility_id == facility_id,
               EdVisit.arrival_at >= lower, EdVisit.arrival_at < upper)
    ).all()
    frame = _to_frame(rows, ["ed_visit_id", "encounter_id", "arrival_at", "arrival_mode",
                             "triage_at", "ctas_level", "room_at", "physician_at",
                             "disposition_at", "departure_at", "ed_disposition", "is_lwbs",
                             "is_lama", "is_72h_revisit", "on_ventilator",
                             "admission_decision_at"])
    for column in ("arrival_at", "triage_at", "room_at", "physician_at", "disposition_at",
                   "departure_at", "admission_decision_at"):
        frame[column] = _localise(frame[column])
    if not frame.empty:
        frame["ctas_level"] = pd.to_numeric(frame["ctas_level"], errors="coerce")
    return frame


def load_bed_movements(session: Session, facility_id: int, start: date, end: date) -> pd.DataFrame:
    lower, upper = _window(start, end)
    rows = session.execute(
        select(BedMovement.movement_id, BedMovement.encounter_id, BedMovement.unit_id,
               BedMovement.bed_id, BedMovement.seq_no, BedMovement.in_at, BedMovement.out_at,
               BedMovement.movement_reason, Unit.kind, Unit.name_en, Unit.staffed_beds)
        .join(Unit, Unit.unit_id == BedMovement.unit_id)
        .where(Unit.facility_id == facility_id,
               BedMovement.in_at < upper,
               (BedMovement.out_at.is_(None)) | (BedMovement.out_at >= lower))
    ).all()
    frame = _to_frame(rows, ["movement_id", "encounter_id", "unit_id", "bed_id", "seq_no",
                             "in_at", "out_at", "movement_reason", "unit_kind", "unit_name",
                             "staffed_beds"])
    for column in ("in_at", "out_at"):
        frame[column] = _localise(frame[column])
    return frame


def load_orders(session: Session, facility_id: int, start: date, end: date) -> pd.DataFrame:
    lower, upper = _window(start, end)
    rows = session.execute(
        select(DiagnosticOrder.order_id, DiagnosticOrder.encounter_id, DiagnosticOrder.domain,
               DiagnosticOrder.order_name, DiagnosticOrder.modality, DiagnosticOrder.is_stat,
               DiagnosticOrder.ordered_at, DiagnosticOrder.collected_at,
               DiagnosticOrder.performed_at, DiagnosticOrder.resulted_at,
               DiagnosticOrder.acknowledged_at, DiagnosticOrder.responding_specialty)
        .join(Encounter, Encounter.encounter_id == DiagnosticOrder.encounter_id)
        .where(Encounter.facility_id == facility_id,
               DiagnosticOrder.ordered_at >= lower, DiagnosticOrder.ordered_at < upper)
    ).all()
    frame = _to_frame(rows, ["order_id", "encounter_id", "domain", "order_name", "modality",
                             "is_stat", "ordered_at", "collected_at", "performed_at",
                             "resulted_at", "acknowledged_at", "responding_specialty"])
    for column in ("ordered_at", "collected_at", "performed_at", "resulted_at", "acknowledged_at"):
        frame[column] = _localise(frame[column])
    return frame


def load_safety_events(session: Session, facility_id: int, start: date, end: date) -> pd.DataFrame:
    lower, upper = _window(start, end)
    rows = session.execute(
        select(SafetyEvent.event_id, SafetyEvent.encounter_id, SafetyEvent.unit_id,
               SafetyEvent.kind, SafetyEvent.occurred_at, SafetyEvent.harm,
               SafetyEvent.present_on_admission, SafetyEvent.pressure_injury_stage,
               SafetyEvent.medication_error_stage, SafetyEvent.is_sentinel)
        .where(SafetyEvent.facility_id == facility_id,
               SafetyEvent.occurred_at >= lower, SafetyEvent.occurred_at < upper)
    ).all()
    frame = _to_frame(rows, ["event_id", "encounter_id", "unit_id", "kind", "occurred_at",
                             "harm", "present_on_admission", "pressure_injury_stage",
                             "medication_error_stage", "is_sentinel"])
    frame["occurred_at"] = _localise(frame["occurred_at"])
    return frame


def load_staffing(session: Session, facility_id: int, start: date, end: date) -> pd.DataFrame:
    rows = session.execute(
        select(StaffingDay.staffing_id, StaffingDay.unit_id, StaffingDay.service_date,
               StaffingDay.shift, StaffingDay.rn_productive_hours,
               StaffingDay.lpn_productive_hours, StaffingDay.na_productive_hours,
               StaffingDay.non_productive_hours, StaffingDay.overtime_hours,
               StaffingDay.agency_hours, StaffingDay.sick_leave_hours,
               StaffingDay.scheduled_hours, StaffingDay.budgeted_fte, StaffingDay.filled_fte,
               StaffingDay.separations, StaffingDay.headcount, StaffingDay.patient_days,
               Unit.name_en, Unit.kind)
        .join(Unit, Unit.unit_id == StaffingDay.unit_id)
        .where(Unit.facility_id == facility_id,
               StaffingDay.service_date >= start, StaffingDay.service_date <= end)
    ).all()
    frame = _to_frame(rows, ["staffing_id", "unit_id", "service_date", "shift",
                             "rn_productive_hours", "lpn_productive_hours", "na_productive_hours",
                             "non_productive_hours", "overtime_hours", "agency_hours",
                             "sick_leave_hours", "scheduled_hours", "budgeted_fte", "filled_fte",
                             "separations", "headcount", "reported_patient_days", "unit_name",
                             "unit_kind"])
    if not frame.empty:
        frame["service_date"] = pd.to_datetime(frame["service_date"]).dt.date
    return frame


def load_icu_stays(session: Session, facility_id: int, start: date, end: date) -> pd.DataFrame:
    lower, upper = _window(start, end)
    rows = session.execute(
        select(IcuStay.icu_stay_id, IcuStay.encounter_id, IcuStay.unit_id, IcuStay.admit_at,
               IcuStay.discharge_at, IcuStay.apache_ii, IcuStay.ventilated_hours,
               IcuStay.outcome, Unit.name_en)
        .join(Unit, Unit.unit_id == IcuStay.unit_id)
        .where(Unit.facility_id == facility_id,
               IcuStay.admit_at < upper,
               (IcuStay.discharge_at.is_(None)) | (IcuStay.discharge_at >= lower))
    ).all()
    frame = _to_frame(rows, ["icu_stay_id", "encounter_id", "unit_id", "admit_at",
                             "discharge_at", "apache_ii", "ventilated_hours", "outcome",
                             "unit_name"])
    for column in ("admit_at", "discharge_at"):
        frame[column] = _localise(frame[column])
    return frame


def load_or_cases(session: Session, facility_id: int, start: date, end: date) -> pd.DataFrame:
    lower, upper = _window(start, end)
    rows = session.execute(
        select(OrCase.or_case_id, OrCase.encounter_id, OrCase.theatre_code, OrCase.specialty,
               OrCase.is_emergency, OrCase.scheduled_start_at, OrCase.wheels_in_at,
               OrCase.anesthesia_start_at, OrCase.incision_at, OrCase.closure_at,
               OrCase.wheels_out_at, OrCase.pacu_in_at, OrCase.pacu_out_at,
               OrCase.is_cancelled, OrCase.cancellation_reason)
        .join(Encounter, Encounter.encounter_id == OrCase.encounter_id)
        .where(Encounter.facility_id == facility_id,
               OrCase.scheduled_start_at >= lower, OrCase.scheduled_start_at < upper)
    ).all()
    frame = _to_frame(rows, ["or_case_id", "encounter_id", "theatre_code", "specialty",
                             "is_emergency", "scheduled_start_at", "wheels_in_at",
                             "anesthesia_start_at", "incision_at", "closure_at", "wheels_out_at",
                             "pacu_in_at", "pacu_out_at", "is_cancelled", "cancellation_reason"])
    for column in ("scheduled_start_at", "wheels_in_at", "anesthesia_start_at", "incision_at",
                   "closure_at", "wheels_out_at", "pacu_in_at", "pacu_out_at"):
        frame[column] = _localise(frame[column])
    return frame


def load_experience(session: Session, facility_id: int, start: date, end: date) -> pd.DataFrame:
    lower, upper = _window(start, end)
    rows = session.execute(
        select(PatientExperience.survey_id, PatientExperience.unit_id,
               PatientExperience.surveyed_at, PatientExperience.overall_rating,
               PatientExperience.would_recommend)
        .where(PatientExperience.facility_id == facility_id,
               PatientExperience.surveyed_at >= lower, PatientExperience.surveyed_at < upper)
    ).all()
    frame = _to_frame(rows, ["survey_id", "unit_id", "surveyed_at", "overall_rating",
                             "would_recommend"])
    frame["surveyed_at"] = _localise(frame["surveyed_at"])
    return frame


def load_vitals(session: Session, facility_id: int, start: date, end: date) -> pd.DataFrame:
    lower, upper = _window(start, end)
    rows = session.execute(
        select(VitalsEws.vitals_id, VitalsEws.encounter_id, VitalsEws.recorded_at,
               VitalsEws.news2_score, VitalsEws.news2_band)
        .join(Encounter, Encounter.encounter_id == VitalsEws.encounter_id)
        .where(Encounter.facility_id == facility_id,
               VitalsEws.recorded_at >= lower, VitalsEws.recorded_at < upper)
    ).all()
    frame = _to_frame(rows, ["vitals_id", "encounter_id", "recorded_at", "news2_score",
                             "news2_band"])
    frame["recorded_at"] = _localise(frame["recorded_at"])
    return frame
