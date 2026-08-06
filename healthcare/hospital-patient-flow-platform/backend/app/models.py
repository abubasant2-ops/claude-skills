"""SQLAlchemy mappings for the warehouse defined in ``db/schema.sql``.

Enum columns are declared with ``native_enum=False`` so the same models
create valid DDL on both PostgreSQL and SQLite; on PostgreSQL the hand
written ``schema.sql`` installs the real native enum types and these
mappings bind to them transparently.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

UNIT_KINDS = ("ED", "ICU", "HDU", "WARD", "OR", "PACU", "OPD", "DAYCASE", "LDR", "NICU", "DIALYSIS")
ENCOUNTER_CLASSES = ("EMERGENCY", "INPATIENT", "OUTPATIENT", "DAYCASE", "OBSERVATION")
DISPOSITIONS = (
    "HOME", "TRANSFER_OUT", "DAMA", "LAMA", "LWBS", "DECEASED", "ABSCONDED", "REFERRED",
)
ORDER_DOMAINS = ("LAB", "RADIOLOGY", "CONSULT", "PROCEDURE")
SAFETY_EVENT_KINDS = (
    "FALL", "PRESSURE_INJURY", "MEDICATION_ERROR", "HAI_CLABSI", "HAI_CAUTI", "HAI_VAP",
    "HAI_SSI", "CODE_BLUE", "RRT_ACTIVATION", "SEPSIS_ALERT", "RETURN_TO_OR",
    "WRONG_SITE", "TRANSFUSION_REACTION", "OTHER",
)
HARM_LEVELS = ("NO_HARM", "MILD", "MODERATE", "SEVERE", "DEATH")
IMPORT_STATES = ("RECEIVED", "PROFILED", "VALIDATED", "REJECTED", "LOADED", "REVERSED")
DQ_SEVERITIES = ("INFO", "WARNING", "ERROR", "CRITICAL")

# Every hospital-acquired infection subtype, kept together so the quality
# module can aggregate them without repeating the list.
HAI_KINDS = ("HAI_CLABSI", "HAI_CAUTI", "HAI_VAP", "HAI_SSI")


def _enum(*values: str, name: str) -> Enum:
    return Enum(*values, name=name, native_enum=False, validate_strings=True)


TS = DateTime(timezone=True)


# ---------------------------------------------------------------------
# Reference layer
# ---------------------------------------------------------------------
class Facility(Base):
    __tablename__ = "ref_facility"

    facility_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Riyadh", nullable=False)
    licensed_beds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ed_treatment_spaces: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cluster_name: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())

    units: Mapped[list["Unit"]] = relationship(back_populates="facility", cascade="all, delete-orphan")


class Unit(Base):
    __tablename__ = "ref_unit"
    __table_args__ = (UniqueConstraint("facility_id", "code", name="uq_unit_code"),)

    unit_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    facility_id: Mapped[int] = mapped_column(
        ForeignKey("ref_facility.facility_id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(_enum(*UNIT_KINDS, name="unit_kind"), nullable=False)
    specialty: Mapped[str | None] = mapped_column(String(120))
    physical_beds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    staffed_beds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    target_occupancy: Mapped[float | None] = mapped_column(Numeric(5, 2), default=85.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    facility: Mapped[Facility] = relationship(back_populates="units")
    beds: Mapped[list["Bed"]] = relationship(back_populates="unit", cascade="all, delete-orphan")


class Bed(Base):
    __tablename__ = "ref_bed"
    __table_args__ = (UniqueConstraint("unit_id", "code", name="uq_bed_code"),)

    bed_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("ref_unit.unit_id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    room: Mapped[str | None] = mapped_column(String(32))
    is_isolation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_negative_pressure: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    gender_restriction: Mapped[str | None] = mapped_column(String(1))
    current_status: Mapped[str] = mapped_column(
        _enum("AVAILABLE", "OCCUPIED", "CLEANING", "BLOCKED", "RESERVED", "CLOSED", name="bed_status"),
        default="AVAILABLE",
        nullable=False,
    )

    unit: Mapped[Unit] = relationship(back_populates="beds")


class Patient(Base):
    """Patients are stored pseudonymised: the natural key is a salted hash
    of the MRN, so the warehouse never holds a directly identifying number."""

    __tablename__ = "ref_patient"

    patient_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mrn_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    birth_year: Mapped[int | None] = mapped_column(SmallInteger)
    sex: Mapped[str | None] = mapped_column(String(1))
    nationality_group: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class Benchmark(Base):
    __tablename__ = "ref_benchmark"
    __table_args__ = (
        UniqueConstraint("metric_key", "scope", "scope_value", name="uq_benchmark"),
    )

    benchmark_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    metric_key: Mapped[str] = mapped_column(String(80), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), default="FACILITY", nullable=False)
    scope_value: Mapped[str | None] = mapped_column(String(64))
    target_value: Mapped[float | None] = mapped_column(Numeric(12, 4))
    amber_threshold: Mapped[float | None] = mapped_column(Numeric(12, 4))
    red_threshold: Mapped[float | None] = mapped_column(Numeric(12, 4))
    higher_is_better: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[str | None] = mapped_column(String(32))


# ---------------------------------------------------------------------
# Staging + data quality
# ---------------------------------------------------------------------
class ImportBatch(Base):
    __tablename__ = "stg_import_batch"

    batch_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("ref_facility.facility_id"), nullable=False)
    dataset: Mapped[str] = mapped_column(String(40), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(400), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    sheet_name: Mapped[str | None] = mapped_column(String(120))
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    accepted_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quality_score: Mapped[float | None] = mapped_column(Float)
    state: Mapped[str] = mapped_column(
        _enum(*IMPORT_STATES, name="import_state"), default="RECEIVED", nullable=False
    )
    column_mapping: Mapped[dict | None] = mapped_column(JSON)
    profile: Mapped[dict | None] = mapped_column(JSON)
    uploaded_by: Mapped[str | None] = mapped_column(String(200))
    uploaded_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    loaded_at: Mapped[datetime | None] = mapped_column(TS)

    findings: Mapped[list["DataQualityFinding"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )


class DataQualityFinding(Base):
    __tablename__ = "dq_finding"

    finding_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("stg_import_batch.batch_id", ondelete="CASCADE"), nullable=False
    )
    rule_code: Mapped[str] = mapped_column(String(60), nullable=False)
    severity: Mapped[str] = mapped_column(_enum(*DQ_SEVERITIES, name="dq_severity"), nullable=False)
    column_name: Mapped[str | None] = mapped_column(String(120))
    affected_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sample_rows: Mapped[list | None] = mapped_column(JSON, default=list)
    message_en: Mapped[str] = mapped_column(Text, nullable=False)
    message_ar: Mapped[str | None] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())

    batch: Mapped[ImportBatch] = relationship(back_populates="findings")


# ---------------------------------------------------------------------
# Encounter spine
# ---------------------------------------------------------------------
class Encounter(Base):
    __tablename__ = "enc_encounter"
    __table_args__ = (
        UniqueConstraint("facility_id", "source_encounter_no", name="uq_encounter_no"),
        CheckConstraint(
            "discharge_at IS NULL OR admission_at IS NULL OR discharge_at >= admission_at",
            name="chk_discharge_after_admit",
        ),
        Index("idx_enc_admission", "facility_id", "admission_at"),
        Index("idx_enc_discharge", "facility_id", "discharge_at"),
        Index("idx_enc_patient", "patient_id", "discharge_at"),
    )

    encounter_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("stg_import_batch.batch_id", ondelete="SET NULL")
    )
    facility_id: Mapped[int] = mapped_column(ForeignKey("ref_facility.facility_id"), nullable=False)
    patient_id: Mapped[int] = mapped_column(ForeignKey("ref_patient.patient_id"), nullable=False)
    source_encounter_no: Mapped[str] = mapped_column(String(64), nullable=False)
    encounter_class: Mapped[str] = mapped_column(
        "class", _enum(*ENCOUNTER_CLASSES, name="encounter_class"), nullable=False
    )
    admitting_unit_id: Mapped[int | None] = mapped_column(ForeignKey("ref_unit.unit_id"))
    discharge_unit_id: Mapped[int | None] = mapped_column(ForeignKey("ref_unit.unit_id"))
    specialty: Mapped[str | None] = mapped_column(String(120))
    primary_diagnosis_code: Mapped[str | None] = mapped_column(String(20))
    drg_code: Mapped[str | None] = mapped_column(String(20))
    is_elective: Mapped[bool | None] = mapped_column(Boolean)

    registration_at: Mapped[datetime | None] = mapped_column(TS)
    admission_at: Mapped[datetime | None] = mapped_column(TS)
    admission_decision_at: Mapped[datetime | None] = mapped_column(TS)
    bed_requested_at: Mapped[datetime | None] = mapped_column(TS)
    bed_assigned_at: Mapped[datetime | None] = mapped_column(TS)
    ward_arrival_at: Mapped[datetime | None] = mapped_column(TS)
    discharge_order_at: Mapped[datetime | None] = mapped_column(TS)
    discharge_ready_at: Mapped[datetime | None] = mapped_column(TS)
    discharge_at: Mapped[datetime | None] = mapped_column(TS)

    disposition: Mapped[str | None] = mapped_column(_enum(*DISPOSITIONS, name="discharge_disposition"))
    is_death: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    los_hours: Mapped[float | None] = mapped_column(Float)
    is_readmission_30d: Mapped[bool | None] = mapped_column(Boolean)
    index_encounter_id: Mapped[int | None] = mapped_column(ForeignKey("enc_encounter.encounter_id"))
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())

    ed_visit: Mapped["EdVisit | None"] = relationship(
        back_populates="encounter", cascade="all, delete-orphan", uselist=False
    )
    movements: Mapped[list["BedMovement"]] = relationship(
        back_populates="encounter", cascade="all, delete-orphan"
    )


class EdVisit(Base):
    __tablename__ = "enc_ed_visit"
    __table_args__ = (Index("idx_ed_arrival", "facility_id", "arrival_at"),)

    ed_visit_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("stg_import_batch.batch_id", ondelete="SET NULL")
    )
    encounter_id: Mapped[int] = mapped_column(
        ForeignKey("enc_encounter.encounter_id", ondelete="CASCADE"), unique=True, nullable=False
    )
    facility_id: Mapped[int] = mapped_column(ForeignKey("ref_facility.facility_id"), nullable=False)

    arrival_at: Mapped[datetime] = mapped_column(TS, nullable=False)
    arrival_mode: Mapped[str | None] = mapped_column(String(32))
    triage_at: Mapped[datetime | None] = mapped_column(TS)
    ctas_level: Mapped[int | None] = mapped_column(SmallInteger)
    room_at: Mapped[datetime | None] = mapped_column(TS)
    physician_at: Mapped[datetime | None] = mapped_column(TS)
    disposition_at: Mapped[datetime | None] = mapped_column(TS)
    departure_at: Mapped[datetime | None] = mapped_column(TS)
    ed_disposition: Mapped[str | None] = mapped_column(String(32))
    is_lwbs: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_lama: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_72h_revisit: Mapped[bool | None] = mapped_column(Boolean)
    on_ventilator: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    encounter: Mapped[Encounter] = relationship(back_populates="ed_visit")


# ---------------------------------------------------------------------
# Operational facts
# ---------------------------------------------------------------------
class BedMovement(Base):
    __tablename__ = "ops_bed_movement"
    __table_args__ = (
        UniqueConstraint("encounter_id", "seq_no", name="uq_movement_seq"),
        Index("idx_move_unit_window", "unit_id", "in_at", "out_at"),
    )

    movement_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("stg_import_batch.batch_id", ondelete="SET NULL")
    )
    encounter_id: Mapped[int] = mapped_column(
        ForeignKey("enc_encounter.encounter_id", ondelete="CASCADE"), nullable=False
    )
    unit_id: Mapped[int] = mapped_column(ForeignKey("ref_unit.unit_id"), nullable=False)
    bed_id: Mapped[int | None] = mapped_column(ForeignKey("ref_bed.bed_id"))
    seq_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    in_at: Mapped[datetime] = mapped_column(TS, nullable=False)
    out_at: Mapped[datetime | None] = mapped_column(TS)
    movement_reason: Mapped[str | None] = mapped_column(String(32))
    is_outlier_placement: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    encounter: Mapped[Encounter] = relationship(back_populates="movements")


class DiagnosticOrder(Base):
    __tablename__ = "ops_order"
    __table_args__ = (Index("idx_order_domain_time", "domain", "ordered_at"),)

    order_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("stg_import_batch.batch_id", ondelete="SET NULL")
    )
    encounter_id: Mapped[int] = mapped_column(
        ForeignKey("enc_encounter.encounter_id", ondelete="CASCADE"), nullable=False
    )
    domain: Mapped[str] = mapped_column(_enum(*ORDER_DOMAINS, name="order_domain"), nullable=False)
    order_code: Mapped[str | None] = mapped_column(String(40))
    order_name: Mapped[str | None] = mapped_column(String(200))
    modality: Mapped[str | None] = mapped_column(String(20))
    is_stat: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ordered_at: Mapped[datetime] = mapped_column(TS, nullable=False)
    collected_at: Mapped[datetime | None] = mapped_column(TS)
    performed_at: Mapped[datetime | None] = mapped_column(TS)
    resulted_at: Mapped[datetime | None] = mapped_column(TS)
    acknowledged_at: Mapped[datetime | None] = mapped_column(TS)
    responding_specialty: Mapped[str | None] = mapped_column(String(120))


class OrCase(Base):
    __tablename__ = "ops_or_case"

    or_case_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("stg_import_batch.batch_id", ondelete="SET NULL")
    )
    encounter_id: Mapped[int] = mapped_column(
        ForeignKey("enc_encounter.encounter_id", ondelete="CASCADE"), nullable=False
    )
    theatre_unit_id: Mapped[int | None] = mapped_column(ForeignKey("ref_unit.unit_id"))
    theatre_code: Mapped[str | None] = mapped_column(String(32))
    procedure_code: Mapped[str | None] = mapped_column(String(40))
    specialty: Mapped[str | None] = mapped_column(String(120))
    is_emergency: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    scheduled_start_at: Mapped[datetime | None] = mapped_column(TS)
    holding_at: Mapped[datetime | None] = mapped_column(TS)
    wheels_in_at: Mapped[datetime | None] = mapped_column(TS)
    anesthesia_start_at: Mapped[datetime | None] = mapped_column(TS)
    incision_at: Mapped[datetime | None] = mapped_column(TS)
    closure_at: Mapped[datetime | None] = mapped_column(TS)
    wheels_out_at: Mapped[datetime | None] = mapped_column(TS)
    pacu_in_at: Mapped[datetime | None] = mapped_column(TS)
    pacu_out_at: Mapped[datetime | None] = mapped_column(TS)
    is_cancelled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cancellation_reason: Mapped[str | None] = mapped_column(String(200))


class IcuStay(Base):
    __tablename__ = "ops_icu_stay"

    icu_stay_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("stg_import_batch.batch_id", ondelete="SET NULL")
    )
    encounter_id: Mapped[int] = mapped_column(
        ForeignKey("enc_encounter.encounter_id", ondelete="CASCADE"), nullable=False
    )
    unit_id: Mapped[int] = mapped_column(ForeignKey("ref_unit.unit_id"), nullable=False)
    admit_at: Mapped[datetime] = mapped_column(TS, nullable=False)
    discharge_at: Mapped[datetime | None] = mapped_column(TS)
    apache_ii: Mapped[int | None] = mapped_column(SmallInteger)
    ventilated_hours: Mapped[float | None] = mapped_column(Float)
    is_readmission_48h: Mapped[bool | None] = mapped_column(Boolean)
    outcome: Mapped[str | None] = mapped_column(String(20))


class VitalsEws(Base):
    __tablename__ = "ops_vitals_ews"
    __table_args__ = (Index("idx_vitals_enc_time", "encounter_id", "recorded_at"),)

    vitals_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("stg_import_batch.batch_id", ondelete="SET NULL")
    )
    encounter_id: Mapped[int] = mapped_column(
        ForeignKey("enc_encounter.encounter_id", ondelete="CASCADE"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(TS, nullable=False)
    respiratory_rate: Mapped[int | None] = mapped_column(SmallInteger)
    spo2: Mapped[int | None] = mapped_column(SmallInteger)
    on_oxygen: Mapped[bool | None] = mapped_column(Boolean)
    systolic_bp: Mapped[int | None] = mapped_column(SmallInteger)
    heart_rate: Mapped[int | None] = mapped_column(SmallInteger)
    temperature_c: Mapped[float | None] = mapped_column(Float)
    consciousness: Mapped[str | None] = mapped_column(String(1))
    news2_score: Mapped[int | None] = mapped_column(SmallInteger)
    news2_band: Mapped[str | None] = mapped_column(String(16))


# ---------------------------------------------------------------------
# Quality and safety
# ---------------------------------------------------------------------
class SafetyEvent(Base):
    __tablename__ = "qly_safety_event"
    __table_args__ = (Index("idx_safety_kind_time", "facility_id", "kind", "occurred_at"),)

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("stg_import_batch.batch_id", ondelete="SET NULL")
    )
    facility_id: Mapped[int] = mapped_column(ForeignKey("ref_facility.facility_id"), nullable=False)
    encounter_id: Mapped[int | None] = mapped_column(
        ForeignKey("enc_encounter.encounter_id", ondelete="SET NULL")
    )
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("ref_unit.unit_id"))
    kind: Mapped[str] = mapped_column(_enum(*SAFETY_EVENT_KINDS, name="safety_event_kind"), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(TS, nullable=False)
    harm: Mapped[str] = mapped_column(_enum(*HARM_LEVELS, name="harm_level"), default="NO_HARM", nullable=False)
    present_on_admission: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pressure_injury_stage: Mapped[str | None] = mapped_column(String(20))
    medication_error_stage: Mapped[str | None] = mapped_column(String(32))
    detail: Mapped[dict | None] = mapped_column(JSON)
    is_sentinel: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class SepsisBundle(Base):
    __tablename__ = "qly_sepsis_bundle"

    sepsis_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("stg_import_batch.batch_id", ondelete="SET NULL")
    )
    encounter_id: Mapped[int] = mapped_column(
        ForeignKey("enc_encounter.encounter_id", ondelete="CASCADE"), nullable=False
    )
    recognition_at: Mapped[datetime] = mapped_column(TS, nullable=False)
    lactate_at: Mapped[datetime | None] = mapped_column(TS)
    cultures_at: Mapped[datetime | None] = mapped_column(TS)
    antibiotics_at: Mapped[datetime | None] = mapped_column(TS)
    fluids_at: Mapped[datetime | None] = mapped_column(TS)
    bundle_complete_1h: Mapped[bool | None] = mapped_column(Boolean)
    bundle_complete_3h: Mapped[bool | None] = mapped_column(Boolean)
    outcome: Mapped[str | None] = mapped_column(String(20))


class PatientExperience(Base):
    __tablename__ = "qly_patient_experience"

    survey_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("stg_import_batch.batch_id", ondelete="SET NULL")
    )
    facility_id: Mapped[int] = mapped_column(ForeignKey("ref_facility.facility_id"), nullable=False)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("ref_unit.unit_id"))
    encounter_id: Mapped[int | None] = mapped_column(
        ForeignKey("enc_encounter.encounter_id", ondelete="SET NULL")
    )
    surveyed_at: Mapped[datetime] = mapped_column(TS, nullable=False)
    overall_rating: Mapped[int | None] = mapped_column(SmallInteger)
    would_recommend: Mapped[int | None] = mapped_column(SmallInteger)
    domain_scores: Mapped[dict | None] = mapped_column(JSON)


# ---------------------------------------------------------------------
# Workforce
# ---------------------------------------------------------------------
class StaffingDay(Base):
    __tablename__ = "wf_staffing_day"
    __table_args__ = (
        UniqueConstraint("unit_id", "service_date", "shift", name="uq_staffing_day"),
    )

    staffing_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("stg_import_batch.batch_id", ondelete="SET NULL")
    )
    unit_id: Mapped[int] = mapped_column(ForeignKey("ref_unit.unit_id"), nullable=False)
    service_date: Mapped[date] = mapped_column(Date, nullable=False)
    shift: Mapped[str] = mapped_column(String(10), default="ALL", nullable=False)

    rn_productive_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    lpn_productive_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    na_productive_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    non_productive_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    overtime_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    agency_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    sick_leave_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    scheduled_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    budgeted_fte: Mapped[float | None] = mapped_column(Float)
    filled_fte: Mapped[float | None] = mapped_column(Float)
    separations: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    headcount: Mapped[int | None] = mapped_column(SmallInteger)
    patient_days: Mapped[float | None] = mapped_column(Float)


# ---------------------------------------------------------------------
# Derived aggregates
# ---------------------------------------------------------------------
class CensusDay(Base):
    __tablename__ = "agg_census_day"

    unit_id: Mapped[int] = mapped_column(ForeignKey("ref_unit.unit_id"), primary_key=True)
    service_date: Mapped[date] = mapped_column(Date, primary_key=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("ref_facility.facility_id"), nullable=False)
    midnight_census: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    patient_days: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    available_bed_days: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    admissions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    discharges: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    transfers_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    transfers_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deaths: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    occupancy_rate: Mapped[float | None] = mapped_column(Float)
    peak_census: Mapped[int | None] = mapped_column(Integer)


class EdHour(Base):
    __tablename__ = "agg_ed_hour"

    facility_id: Mapped[int] = mapped_column(ForeignKey("ref_facility.facility_id"), primary_key=True)
    bucket_start: Mapped[datetime] = mapped_column(TS, primary_key=True)
    arrivals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    departures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    census: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    boarders: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    longest_boarding_hours: Mapped[float | None] = mapped_column(Float)
    longest_wait_minutes: Mapped[float | None] = mapped_column(Float)
    ventilated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    nedocs_score: Mapped[float | None] = mapped_column(Float)
    nedocs_band: Mapped[str | None] = mapped_column(String(32))


class MetricDay(Base):
    """Long-format metric store. One row per facility/unit/date/metric so
    new indicators never require a schema migration."""

    __tablename__ = "agg_metric_day"

    facility_id: Mapped[int] = mapped_column(ForeignKey("ref_facility.facility_id"), primary_key=True)
    service_date: Mapped[date] = mapped_column(Date, primary_key=True)
    metric_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    # 0 stands for "whole facility" so the column can stay in the primary key.
    unit_id: Mapped[int] = mapped_column(Integer, primary_key=True, default=0)
    value: Mapped[float | None] = mapped_column(Float)
    numerator: Mapped[float | None] = mapped_column(Float)
    denominator: Mapped[float | None] = mapped_column(Float)
    computed_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


# ---------------------------------------------------------------------
# ML registry
# ---------------------------------------------------------------------
class MlModel(Base):
    __tablename__ = "ml_model"
    __table_args__ = (UniqueConstraint("model_key", "version", name="uq_model_version"),)

    model_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_key: Mapped[str] = mapped_column(String(60), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(80), nullable=False)
    trained_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    training_rows: Mapped[int | None] = mapped_column(Integer)
    feature_names: Mapped[list | None] = mapped_column(JSON)
    metrics: Mapped[dict | None] = mapped_column(JSON)
    artifact_path: Mapped[str | None] = mapped_column(String(400))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Prediction(Base):
    __tablename__ = "ml_prediction"
    __table_args__ = (Index("idx_pred_lookup", "facility_id", "target_key", "horizon_at"),)

    prediction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("ml_model.model_id", ondelete="CASCADE"))
    facility_id: Mapped[int] = mapped_column(ForeignKey("ref_facility.facility_id"), nullable=False)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("ref_unit.unit_id"))
    target_key: Mapped[str] = mapped_column(String(60), nullable=False)
    horizon_at: Mapped[datetime] = mapped_column(TS, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    predicted_value: Mapped[float | None] = mapped_column(Float)
    lower_bound: Mapped[float | None] = mapped_column(Float)
    upper_bound: Mapped[float | None] = mapped_column(Float)
    predicted_class: Mapped[str | None] = mapped_column(String(40))
    probability: Mapped[float | None] = mapped_column(Float)
    actual_value: Mapped[float | None] = mapped_column(Float)
    drivers: Mapped[dict | None] = mapped_column(JSON)


class Anomaly(Base):
    __tablename__ = "ml_anomaly"

    anomaly_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("ref_facility.facility_id"), nullable=False)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("ref_unit.unit_id"))
    service_date: Mapped[date] = mapped_column(Date, nullable=False)
    metric_key: Mapped[str] = mapped_column(String(80), nullable=False)
    observed_value: Mapped[float | None] = mapped_column(Float)
    expected_value: Mapped[float | None] = mapped_column(Float)
    deviation_score: Mapped[float | None] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(_enum(*DQ_SEVERITIES, name="dq_severity"), default="WARNING")
    explanation_en: Mapped[str | None] = mapped_column(Text)
    explanation_ar: Mapped[str | None] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class AppUser(Base):
    __tablename__ = "app_user"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    facility_id: Mapped[int | None] = mapped_column(ForeignKey("ref_facility.facility_id"))
    locale: Mapped[str] = mapped_column(String(5), default="en", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"

    audit_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.user_id"))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    object_type: Mapped[str | None] = mapped_column(String(60))
    object_id: Mapped[str | None] = mapped_column(String(80))
    detail: Mapped[dict | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
