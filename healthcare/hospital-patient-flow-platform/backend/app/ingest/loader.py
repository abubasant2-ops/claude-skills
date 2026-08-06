"""File reading and the import pipeline.

    read  ->  profile  ->  map  ->  coerce  ->  validate  ->  stage  ->  promote

Every stage is recorded against an ``ImportBatch`` so a load can be
explained after the fact and reversed by batch id. Nothing reaches the
fact tables until validation has passed the configured quality gate.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.ingest import mapper
from app.ingest.datasets import DatasetSpec, get_dataset
from app.ingest.validators import ValidationResult, validate
from app.models import (
    Bed,
    BedMovement,
    DataQualityFinding,
    DiagnosticOrder,
    EdVisit,
    Encounter,
    Facility,
    IcuStay,
    ImportBatch,
    OrCase,
    Patient,
    PatientExperience,
    SafetyEvent,
    StaffingDay,
    Unit,
    VitalsEws,
)

log = logging.getLogger(__name__)

# A hospital report often has a title block above the real header. Scan
# this many rows looking for the row that best matches the expected fields.
HEADER_SCAN_DEPTH = 12


@dataclass
class IngestReport:
    batch_id: int
    dataset: str
    filename: str
    row_count: int
    accepted_rows: int
    rejected_rows: int
    loaded_rows: int
    quality_score: float
    state: str
    column_mapping: dict[str, str]
    unmapped_columns: list[str]
    missing_optional_fields: list[str]
    validation: dict

    def to_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "dataset": self.dataset,
            "filename": self.filename,
            "row_count": self.row_count,
            "accepted_rows": self.accepted_rows,
            "rejected_rows": self.rejected_rows,
            "loaded_rows": self.loaded_rows,
            "quality_score": round(self.quality_score, 2),
            "state": self.state,
            "column_mapping": self.column_mapping,
            "unmapped_columns": self.unmapped_columns,
            "missing_optional_fields": self.missing_optional_fields,
            "validation": self.validation,
        }


# ---------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _score_header_row(values: list, spec: DatasetSpec) -> int:
    """How many cells in a candidate header row look like known fields."""
    known: set[str] = set()
    for field_spec in spec.fields:
        known.add(mapper.normalise_header(field_spec.name))
        known.update(mapper.normalise_header(a) for a in field_spec.aliases)
    hits = 0
    for value in values:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            continue
        normalised = mapper.normalise_header(value)
        if not normalised:
            continue
        if normalised in known:
            hits += 2
        elif any(normalised in k or k in normalised for k in known if len(k) > 4):
            hits += 1
    return hits


def read_table(path: Path, spec: DatasetSpec, sheet: str | int | None = None) -> tuple[pd.DataFrame, str | None]:
    """Read an .xlsx/.csv into a frame, locating the real header row."""
    suffix = path.suffix.lower()

    if suffix in (".csv", ".txt", ".tsv"):
        separator = "\t" if suffix == ".tsv" else None
        raw = pd.read_csv(path, header=None, dtype=object, sep=separator,
                          engine="python", keep_default_na=False, na_values=[""])
        sheet_name = None
    elif suffix in (".xlsx", ".xlsm"):
        book = pd.ExcelFile(path)
        sheet_name = sheet if sheet is not None else _pick_sheet(book, spec)
        raw = book.parse(sheet_name, header=None, dtype=object)
        sheet_name = str(sheet_name)
    else:
        raise ValueError(f"Unsupported file type '{suffix}'. Use .xlsx, .xlsm or .csv.")

    if raw.empty:
        return pd.DataFrame(), sheet_name

    best_row, best_score = 0, -1
    for candidate in range(min(HEADER_SCAN_DEPTH, len(raw))):
        score = _score_header_row(raw.iloc[candidate].tolist(), spec)
        if score > best_score:
            best_row, best_score = candidate, score

    header = raw.iloc[best_row].tolist()
    body = raw.iloc[best_row + 1:].reset_index(drop=True)
    # Anonymous trailing columns from merged title cells become col_N.
    columns, seen = [], {}
    for position, value in enumerate(header):
        name = str(value).strip() if value is not None and not pd.isna(value) else f"column_{position + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        columns.append(name)
    body.columns = columns

    # Drop fully-blank rows and the all-blank spacer columns Excel loves.
    body = body.dropna(how="all").reset_index(drop=True)
    body = body.loc[:, ~body.isna().all()]
    return body, sheet_name


def _pick_sheet(book: pd.ExcelFile, spec: DatasetSpec) -> str:
    """Choose the sheet whose header best matches the dataset."""
    if len(book.sheet_names) == 1:
        return book.sheet_names[0]
    # A sheet literally named after the dataset wins outright.
    for name in book.sheet_names:
        if mapper.normalise_header(name) == mapper.normalise_header(spec.key):
            return name
    best_name, best_score = book.sheet_names[0], -1
    for name in book.sheet_names:
        preview = book.parse(name, header=None, nrows=HEADER_SCAN_DEPTH, dtype=object)
        if preview.empty:
            continue
        score = max(
            _score_header_row(preview.iloc[row].tolist(), spec) for row in range(len(preview))
        )
        if score > best_score:
            best_name, best_score = name, score
    return best_name


# ---------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------
def hash_identifier(raw: str) -> str:
    salt = get_settings().mrn_salt
    return hashlib.sha256(f"{salt}|{str(raw).strip()}".encode()).hexdigest()


def ingest_file(
    session: Session,
    *,
    facility_id: int,
    dataset: str,
    path: Path,
    sheet: str | int | None = None,
    uploaded_by: str | None = None,
    dry_run: bool = False,
) -> IngestReport:
    """Run one file end to end. ``dry_run`` stops after validation."""
    spec = get_dataset(dataset)
    settings = get_settings()

    facility = session.get(Facility, facility_id)
    if facility is None:
        raise ValueError(f"Facility {facility_id} does not exist")

    frame_raw, sheet_name = read_table(path, spec, sheet)
    checksum = sha256_file(path)

    batch = ImportBatch(
        facility_id=facility_id,
        dataset=dataset,
        source_filename=path.name,
        source_sha256=checksum,
        sheet_name=sheet_name,
        row_count=len(frame_raw),
        uploaded_by=uploaded_by,
        state="RECEIVED",
    )
    session.add(batch)
    session.flush()

    if frame_raw.empty:
        batch.state = "REJECTED"
        session.add(DataQualityFinding(
            batch_id=batch.batch_id, rule_code="EMPTY_FILE", severity="CRITICAL",
            affected_rows=0,
            message_en="The file contains no data rows below its header.",
            message_ar="الملف لا يحتوي على أي صفوف بيانات.",
        ))
        session.flush()
        return IngestReport(batch.batch_id, dataset, path.name, 0, 0, 0, 0, 0.0,
                            "REJECTED", {}, [], [], {"findings": []})

    profiles = mapper.profile_columns(frame_raw)
    mapping = mapper.map_columns(profiles, spec)
    frame, coercion_failures = mapper.apply_mapping(frame_raw, mapping, spec)

    batch.column_mapping = mapping
    batch.profile = {"columns": [p.to_dict() for p in profiles]}
    batch.state = "PROFILED"
    session.flush()

    known_encounters = None
    if spec.references_encounter:
        known_encounters = {
            row[0] for row in session.execute(
                select(Encounter.source_encounter_no).where(Encounter.facility_id == facility_id)
            )
        }

    result = validate(
        frame, spec, coercion_failures, mapping,
        known_encounter_nos=known_encounters,
    )

    for finding in result.findings:
        session.add(DataQualityFinding(
            batch_id=batch.batch_id,
            rule_code=finding.rule_code,
            severity=finding.severity,
            column_name=finding.column_name,
            affected_rows=finding.affected_rows,
            sample_rows=finding.sample_rows[:10],
            message_en=finding.message_en,
            message_ar=finding.message_ar or None,
        ))

    accepted = frame.drop(index=result.rejected_index)
    batch.accepted_rows = len(accepted)
    batch.rejected_rows = len(result.rejected_index)
    batch.quality_score = result.quality_score

    unmapped = [p.source_name for p in profiles if p.mapped_to is None]
    missing_optional = [
        f.name for f in spec.fields if f.name not in mapping and not f.required
    ]

    loaded = 0
    if dry_run:
        batch.state = "VALIDATED"
    elif result.blocking:
        batch.state = "REJECTED"
    elif result.quality_score < settings.min_quality_score_to_load:
        batch.state = "VALIDATED"          # held for human review
        session.add(DataQualityFinding(
            batch_id=batch.batch_id, rule_code="QUALITY_GATE_HELD", severity="ERROR",
            affected_rows=len(frame),
            message_en=(
                f"Quality score {result.quality_score:.1f} is below the load threshold of "
                f"{settings.min_quality_score_to_load:.0f}. The batch is staged for review; "
                "resolve the findings above and re-submit, or force the load explicitly."
            ),
            message_ar=(
                f"درجة الجودة {result.quality_score:.1f} أقل من الحد المطلوب "
                f"{settings.min_quality_score_to_load:.0f}."
            ),
        ))
    else:
        loaded = promote(session, batch, accepted, spec, facility_id)
        batch.state = "LOADED"
        batch.loaded_at = datetime.now(timezone.utc)

    session.flush()

    return IngestReport(
        batch_id=batch.batch_id,
        dataset=dataset,
        filename=path.name,
        row_count=len(frame_raw),
        accepted_rows=len(accepted),
        rejected_rows=len(result.rejected_index),
        loaded_rows=loaded,
        quality_score=result.quality_score,
        state=batch.state,
        column_mapping=mapping,
        unmapped_columns=unmapped,
        missing_optional_fields=missing_optional,
        validation=result.to_dict(),
    )


# ---------------------------------------------------------------------
# Promotion into the warehouse
# ---------------------------------------------------------------------
def _value(row, name):
    value = row.get(name)
    if value is None or pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    return value


def _bool(row, name, default=False):
    value = _value(row, name)
    return default if value is None else bool(value)


def _int(row, name):
    value = _value(row, name)
    return None if value is None else int(value)


def _float(row, name, default=None):
    value = _value(row, name)
    return default if value is None else float(value)


def promote(session: Session, batch: ImportBatch, frame: pd.DataFrame,
            spec: DatasetSpec, facility_id: int) -> int:
    handler = _PROMOTERS.get(spec.key)
    if handler is None:
        raise NotImplementedError(f"No promoter registered for dataset '{spec.key}'")
    return handler(session, batch, frame, facility_id)


def _unit_index(session: Session, facility_id: int) -> dict[str, int]:
    return {
        code: unit_id
        for code, unit_id in session.execute(
            select(Unit.code, Unit.unit_id).where(Unit.facility_id == facility_id)
        )
    }


def _encounter_index(session: Session, facility_id: int) -> dict[str, int]:
    return {
        no: enc_id
        for no, enc_id in session.execute(
            select(Encounter.source_encounter_no, Encounter.encounter_id)
            .where(Encounter.facility_id == facility_id)
        )
    }


def _promote_units(session, batch, frame, facility_id) -> int:
    existing = {
        unit.code: unit
        for unit in session.scalars(select(Unit).where(Unit.facility_id == facility_id))
    }
    count = 0
    for _, row in frame.iterrows():
        code = _value(row, "unit_code")
        if not code:
            continue
        unit = existing.get(str(code))
        if unit is None:
            unit = Unit(facility_id=facility_id, code=str(code), name_en="", kind="WARD")
            session.add(unit)
            existing[str(code)] = unit
        unit.name_en = _value(row, "name_en") or unit.name_en or str(code)
        unit.name_ar = _value(row, "name_ar") or unit.name_ar
        unit.kind = _value(row, "kind") or unit.kind
        unit.specialty = _value(row, "specialty") or unit.specialty
        unit.physical_beds = _int(row, "physical_beds") or unit.physical_beds or 0
        unit.staffed_beds = _int(row, "staffed_beds") or unit.staffed_beds or 0
        unit.target_occupancy = _float(row, "target_occupancy", unit.target_occupancy)
        count += 1
    session.flush()
    return count


def _promote_encounters(session, batch, frame, facility_id) -> int:
    units = _unit_index(session, facility_id)
    existing = _encounter_index(session, facility_id)
    patients = {
        mrn_hash: patient_id
        for mrn_hash, patient_id in session.execute(select(Patient.mrn_hash, Patient.patient_id))
    }

    # Patients are created in one pass and flushed once. Flushing per row
    # turns a 30,000-row load into 30,000 round trips.
    frame = frame.copy()
    frame["_mrn_hash"] = frame["mrn"].map(
        lambda v: hash_identifier(v) if v is not None and not pd.isna(v) else None
    )
    new_patients: dict[str, Patient] = {}
    for _, row in frame.iterrows():
        mrn_hash = row["_mrn_hash"]
        if not mrn_hash or mrn_hash in patients or mrn_hash in new_patients:
            continue
        birth_year = _int(row, "birth_year")
        if birth_year is None and (age := _int(row, "age")) is not None:
            birth_year = datetime.now().year - age
        new_patients[mrn_hash] = Patient(
            mrn_hash=mrn_hash,
            birth_year=birth_year,
            sex=(_value(row, "sex") or "U")[:1].upper(),
            nationality_group=_value(row, "nationality_group"),
        )
    if new_patients:
        session.add_all(list(new_patients.values()))
        session.flush()
        patients.update({h: p.patient_id for h, p in new_patients.items()})

    count = 0
    pending: dict[str, Encounter] = {}

    for _, row in frame.iterrows():
        encounter_no = _value(row, "encounter_no")
        mrn_hash = row["_mrn_hash"]
        if not encounter_no or not mrn_hash:
            continue
        patient_id = patients.get(mrn_hash)
        if patient_id is None:
            continue

        admission_at = _value(row, "admission_at")
        discharge_at = _value(row, "discharge_at")
        # Defence in depth: validation already quarantines these, but a
        # forced load must not be able to violate the warehouse constraint.
        if admission_at and discharge_at and discharge_at < admission_at:
            continue

        encounter = pending.get(str(encounter_no))
        if encounter is None:
            encounter_id = existing.get(str(encounter_no))
            encounter = session.get(Encounter, encounter_id) if encounter_id else None
        if encounter is None:
            encounter = Encounter(
                facility_id=facility_id,
                source_encounter_no=str(encounter_no),
                patient_id=patient_id,
                encounter_class=_value(row, "encounter_class") or "INPATIENT",
            )
            session.add(encounter)
            pending[str(encounter_no)] = encounter

        encounter.batch_id = batch.batch_id
        encounter.patient_id = patient_id
        encounter.encounter_class = _value(row, "encounter_class") or encounter.encounter_class
        encounter.admitting_unit_id = units.get(str(_value(row, "admitting_unit_code") or ""))
        encounter.discharge_unit_id = (
            units.get(str(_value(row, "discharge_unit_code") or "")) or encounter.admitting_unit_id
        )
        encounter.specialty = _value(row, "specialty")
        encounter.primary_diagnosis_code = _value(row, "primary_diagnosis_code")
        encounter.drg_code = _value(row, "drg_code")
        encounter.is_elective = _value(row, "is_elective")
        for stamp in (
            "registration_at", "admission_at", "admission_decision_at", "bed_requested_at",
            "bed_assigned_at", "ward_arrival_at", "discharge_order_at", "discharge_ready_at",
            "discharge_at",
        ):
            setattr(encounter, stamp, _value(row, stamp))
        disposition = _value(row, "disposition")
        encounter.disposition = disposition
        encounter.is_death = disposition == "DECEASED"
        if encounter.admission_at and encounter.discharge_at:
            encounter.los_hours = round(
                (encounter.discharge_at - encounter.admission_at).total_seconds() / 3600, 2
            )
        count += 1

    session.flush()
    existing.update({no: enc.encounter_id for no, enc in pending.items()})
    return count


def _promote_ed_visits(session, batch, frame, facility_id) -> int:
    encounters = _encounter_index(session, facility_id)
    existing = {
        enc_id: visit
        for enc_id, visit in session.execute(
            select(EdVisit.encounter_id, EdVisit).where(EdVisit.facility_id == facility_id)
        )
    }
    count = 0
    for _, row in frame.iterrows():
        encounter_id = encounters.get(str(_value(row, "encounter_no") or ""))
        arrival = _value(row, "arrival_at")
        if not encounter_id or arrival is None:
            continue
        visit = existing.get(encounter_id)
        if visit is None:
            visit = EdVisit(encounter_id=encounter_id, facility_id=facility_id, arrival_at=arrival)
            session.add(visit)
            existing[encounter_id] = visit

        visit.batch_id = batch.batch_id
        visit.arrival_at = arrival
        visit.arrival_mode = _value(row, "arrival_mode")
        visit.triage_at = _value(row, "triage_at")
        visit.ctas_level = _int(row, "ctas_level")
        visit.room_at = _value(row, "room_at")
        visit.physician_at = _value(row, "physician_at")
        visit.disposition_at = _value(row, "disposition_at")
        visit.departure_at = _value(row, "departure_at")
        disposition = _value(row, "ed_disposition")
        visit.ed_disposition = disposition
        visit.is_lwbs = disposition == "LWBS"
        visit.is_lama = disposition == "LAMA"
        visit.on_ventilator = _bool(row, "on_ventilator")
        count += 1
    session.flush()
    _flag_ed_revisits(session, facility_id)
    return count


def _flag_ed_revisits(session: Session, facility_id: int) -> None:
    """Mark unplanned returns to the ED within 72 hours of a discharge.

    Computed after each ED load rather than at read time so the dashboard
    query stays a simple aggregate.
    """
    rows = session.execute(
        select(EdVisit, Encounter.patient_id)
        .join(Encounter, Encounter.encounter_id == EdVisit.encounter_id)
        .where(EdVisit.facility_id == facility_id)
        .order_by(Encounter.patient_id, EdVisit.arrival_at)
    ).all()

    previous_patient, previous_departure = None, None
    for visit, patient_id in rows:
        if patient_id == previous_patient and previous_departure and visit.arrival_at:
            delta = (visit.arrival_at - previous_departure).total_seconds() / 3600
            visit.is_72h_revisit = 0 < delta <= 72
        else:
            visit.is_72h_revisit = False
        previous_patient = patient_id
        previous_departure = visit.departure_at or visit.arrival_at


def _promote_bed_movements(session, batch, frame, facility_id) -> int:
    encounters = _encounter_index(session, facility_id)
    units = _unit_index(session, facility_id)
    beds = {
        (unit_id, code): bed_id
        for unit_id, code, bed_id in session.execute(
            select(Bed.unit_id, Bed.code, Bed.bed_id)
            .join(Unit, Unit.unit_id == Bed.unit_id)
            .where(Unit.facility_id == facility_id)
        )
    }
    existing = {
        (enc_id, seq): movement
        for enc_id, seq, movement in session.execute(
            select(BedMovement.encounter_id, BedMovement.seq_no, BedMovement)
        )
    }
    count = 0
    for _, row in frame.iterrows():
        encounter_id = encounters.get(str(_value(row, "encounter_no") or ""))
        unit_id = units.get(str(_value(row, "unit_code") or ""))
        seq_no = _int(row, "seq_no")
        in_at = _value(row, "in_at")
        if not encounter_id or not unit_id or seq_no is None or in_at is None:
            continue

        bed_code = _value(row, "bed_code")
        bed_id = beds.get((unit_id, str(bed_code))) if bed_code else None
        if bed_code and bed_id is None:
            bed = Bed(unit_id=unit_id, code=str(bed_code))
            session.add(bed)
            session.flush()
            bed_id = bed.bed_id
            beds[(unit_id, str(bed_code))] = bed_id

        movement = existing.get((encounter_id, seq_no))
        if movement is None:
            movement = BedMovement(encounter_id=encounter_id, seq_no=seq_no,
                                   unit_id=unit_id, in_at=in_at)
            session.add(movement)
            existing[(encounter_id, seq_no)] = movement
        movement.batch_id = batch.batch_id
        movement.unit_id = unit_id
        movement.bed_id = bed_id
        movement.in_at = in_at
        movement.out_at = _value(row, "out_at")
        movement.movement_reason = _value(row, "movement_reason")
        count += 1
    session.flush()
    return count


def _promote_orders(session, batch, frame, facility_id) -> int:
    encounters = _encounter_index(session, facility_id)
    count = 0
    for _, row in frame.iterrows():
        encounter_id = encounters.get(str(_value(row, "encounter_no") or ""))
        ordered_at = _value(row, "ordered_at")
        if not encounter_id or ordered_at is None:
            continue
        session.add(DiagnosticOrder(
            batch_id=batch.batch_id,
            encounter_id=encounter_id,
            domain=_value(row, "domain") or "LAB",
            order_code=_value(row, "order_code"),
            order_name=_value(row, "order_name"),
            modality=_value(row, "modality"),
            is_stat=_bool(row, "is_stat"),
            ordered_at=ordered_at,
            collected_at=_value(row, "collected_at"),
            performed_at=_value(row, "performed_at"),
            resulted_at=_value(row, "resulted_at"),
            acknowledged_at=_value(row, "acknowledged_at"),
            responding_specialty=_value(row, "responding_specialty"),
        ))
        count += 1
    session.flush()
    return count


def _promote_safety_events(session, batch, frame, facility_id) -> int:
    encounters = _encounter_index(session, facility_id)
    units = _unit_index(session, facility_id)
    count = 0
    for _, row in frame.iterrows():
        occurred_at = _value(row, "occurred_at")
        kind = _value(row, "kind")
        if occurred_at is None or not kind:
            continue
        session.add(SafetyEvent(
            batch_id=batch.batch_id,
            facility_id=facility_id,
            encounter_id=encounters.get(str(_value(row, "encounter_no") or "")),
            unit_id=units.get(str(_value(row, "unit_code") or "")),
            kind=kind,
            occurred_at=occurred_at,
            harm=_value(row, "harm") or "NO_HARM",
            present_on_admission=_bool(row, "present_on_admission"),
            pressure_injury_stage=_value(row, "pressure_injury_stage"),
            medication_error_stage=_value(row, "medication_error_stage"),
            is_sentinel=_bool(row, "is_sentinel"),
        ))
        count += 1
    session.flush()
    return count


def _promote_staffing(session, batch, frame, facility_id) -> int:
    units = _unit_index(session, facility_id)
    existing = {
        (unit_id, service_date, shift): record
        for unit_id, service_date, shift, record in session.execute(
            select(StaffingDay.unit_id, StaffingDay.service_date, StaffingDay.shift, StaffingDay)
        )
    }
    count = 0
    for _, row in frame.iterrows():
        unit_id = units.get(str(_value(row, "unit_code") or ""))
        service_date = _value(row, "service_date")
        if not unit_id or service_date is None:
            continue
        if isinstance(service_date, datetime):
            service_date = service_date.date()
        shift = _value(row, "shift") or "ALL"
        record = existing.get((unit_id, service_date, shift))
        if record is None:
            record = StaffingDay(unit_id=unit_id, service_date=service_date, shift=shift)
            session.add(record)
            existing[(unit_id, service_date, shift)] = record
        record.batch_id = batch.batch_id
        record.rn_productive_hours = _float(row, "rn_productive_hours", 0.0)
        record.lpn_productive_hours = _float(row, "lpn_productive_hours", 0.0)
        record.na_productive_hours = _float(row, "na_productive_hours", 0.0)
        record.non_productive_hours = _float(row, "non_productive_hours", 0.0)
        record.overtime_hours = _float(row, "overtime_hours", 0.0)
        record.agency_hours = _float(row, "agency_hours", 0.0)
        record.sick_leave_hours = _float(row, "sick_leave_hours", 0.0)
        record.scheduled_hours = _float(row, "scheduled_hours", 0.0)
        record.budgeted_fte = _float(row, "budgeted_fte")
        record.filled_fte = _float(row, "filled_fte")
        record.separations = _int(row, "separations") or 0
        record.headcount = _int(row, "headcount")
        record.patient_days = _float(row, "patient_days")
        count += 1
    session.flush()
    return count


def _promote_vitals(session, batch, frame, facility_id) -> int:
    from app.analytics.quality import news2_score

    encounters = _encounter_index(session, facility_id)
    count = 0
    for _, row in frame.iterrows():
        encounter_id = encounters.get(str(_value(row, "encounter_no") or ""))
        recorded_at = _value(row, "recorded_at")
        if not encounter_id or recorded_at is None:
            continue
        score, band = news2_score(
            respiratory_rate=_int(row, "respiratory_rate"),
            spo2=_int(row, "spo2"),
            on_oxygen=_bool(row, "on_oxygen"),
            systolic_bp=_int(row, "systolic_bp"),
            heart_rate=_int(row, "heart_rate"),
            temperature_c=_float(row, "temperature_c"),
            consciousness=_value(row, "consciousness"),
        )
        session.add(VitalsEws(
            batch_id=batch.batch_id,
            encounter_id=encounter_id,
            recorded_at=recorded_at,
            respiratory_rate=_int(row, "respiratory_rate"),
            spo2=_int(row, "spo2"),
            on_oxygen=_bool(row, "on_oxygen"),
            systolic_bp=_int(row, "systolic_bp"),
            heart_rate=_int(row, "heart_rate"),
            temperature_c=_float(row, "temperature_c"),
            consciousness=_value(row, "consciousness"),
            news2_score=score,
            news2_band=band,
        ))
        count += 1
    session.flush()
    return count


def _promote_or_cases(session, batch, frame, facility_id) -> int:
    encounters = _encounter_index(session, facility_id)
    units = _unit_index(session, facility_id)
    count = 0
    for _, row in frame.iterrows():
        encounter_id = encounters.get(str(_value(row, "encounter_no") or ""))
        if not encounter_id:
            continue
        session.add(OrCase(
            batch_id=batch.batch_id,
            encounter_id=encounter_id,
            theatre_unit_id=units.get(str(_value(row, "theatre_code") or "")),
            theatre_code=_value(row, "theatre_code"),
            procedure_code=_value(row, "procedure_code"),
            specialty=_value(row, "specialty"),
            is_emergency=_bool(row, "is_emergency"),
            scheduled_start_at=_value(row, "scheduled_start_at"),
            holding_at=_value(row, "holding_at"),
            wheels_in_at=_value(row, "wheels_in_at"),
            anesthesia_start_at=_value(row, "anesthesia_start_at"),
            incision_at=_value(row, "incision_at"),
            closure_at=_value(row, "closure_at"),
            wheels_out_at=_value(row, "wheels_out_at"),
            pacu_in_at=_value(row, "pacu_in_at"),
            pacu_out_at=_value(row, "pacu_out_at"),
            is_cancelled=_bool(row, "is_cancelled"),
            cancellation_reason=_value(row, "cancellation_reason"),
        ))
        count += 1
    session.flush()
    return count


def _promote_icu_stays(session, batch, frame, facility_id) -> int:
    encounters = _encounter_index(session, facility_id)
    units = _unit_index(session, facility_id)
    count = 0
    for _, row in frame.iterrows():
        encounter_id = encounters.get(str(_value(row, "encounter_no") or ""))
        unit_id = units.get(str(_value(row, "unit_code") or ""))
        admit_at = _value(row, "admit_at")
        if not encounter_id or not unit_id or admit_at is None:
            continue
        session.add(IcuStay(
            batch_id=batch.batch_id,
            encounter_id=encounter_id,
            unit_id=unit_id,
            admit_at=admit_at,
            discharge_at=_value(row, "discharge_at"),
            apache_ii=_int(row, "apache_ii"),
            ventilated_hours=_float(row, "ventilated_hours"),
            outcome=_value(row, "outcome"),
        ))
        count += 1
    session.flush()
    return count


def _promote_patient_experience(session, batch, frame, facility_id) -> int:
    encounters = _encounter_index(session, facility_id)
    units = _unit_index(session, facility_id)
    count = 0
    for _, row in frame.iterrows():
        surveyed_at = _value(row, "surveyed_at")
        if surveyed_at is None:
            continue
        session.add(PatientExperience(
            batch_id=batch.batch_id,
            facility_id=facility_id,
            unit_id=units.get(str(_value(row, "unit_code") or "")),
            encounter_id=encounters.get(str(_value(row, "encounter_no") or "")),
            surveyed_at=surveyed_at,
            overall_rating=_int(row, "overall_rating"),
            would_recommend=_int(row, "would_recommend"),
        ))
        count += 1
    session.flush()
    return count


_PROMOTERS = {
    "units": _promote_units,
    "encounters": _promote_encounters,
    "ed_visits": _promote_ed_visits,
    "bed_movements": _promote_bed_movements,
    "orders": _promote_orders,
    "safety_events": _promote_safety_events,
    "staffing": _promote_staffing,
    "vitals": _promote_vitals,
    "or_cases": _promote_or_cases,
    "icu_stays": _promote_icu_stays,
    "patient_experience": _promote_patient_experience,
}


def reverse_batch(session: Session, batch_id: int) -> int:
    """Undo a load. Rows are deleted by batch id, which is why every fact
    table carries one."""
    from app.models import Anomaly  # noqa: F401  (kept out of the hot import path)

    batch = session.get(ImportBatch, batch_id)
    if batch is None:
        raise ValueError(f"Batch {batch_id} not found")
    if batch.state != "LOADED":
        raise ValueError(f"Batch {batch_id} is in state {batch.state}; only LOADED can be reversed")

    removed = 0
    for model in (VitalsEws, DiagnosticOrder, OrCase, IcuStay, SafetyEvent,
                  PatientExperience, StaffingDay, BedMovement, EdVisit, Encounter):
        rows = session.scalars(select(model).where(model.batch_id == batch_id)).all()
        for row in rows:
            session.delete(row)
        removed += len(rows)
    batch.state = "REVERSED"
    session.flush()
    return removed
