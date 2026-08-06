"""Test fixtures: an in-memory hospital small enough to reason about by hand.

Every expected value in the test suite is derived from these fixtures on
paper first, so a failing test means the code is wrong -- not that a
golden file drifted.
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

# Point the app at a throwaway database before anything imports the engine.
os.environ["HPF_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["HPF_ENVIRONMENT"] = "test"
os.environ["HPF_MRN_SALT"] = "test-salt"

from app.core.db import Base, SessionLocal, engine           # noqa: E402
from app.models import (                                      # noqa: E402
    BedMovement,
    EdVisit,
    Encounter,
    Facility,
    Patient,
    SafetyEvent,
    StaffingDay,
    Unit,
)

START = date(2026, 3, 1)
END = date(2026, 3, 10)


@pytest.fixture(scope="function")
def session():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def hospital(session):
    """A two-ward, one-ED facility with ten days of hand-checkable activity."""
    facility = Facility(code="TEST-01", name_en="Test Hospital", name_ar="مستشفى الاختبار",
                        licensed_beds=30, ed_treatment_spaces=10, timezone="Asia/Riyadh")
    session.add(facility)
    session.flush()

    ward = Unit(facility_id=facility.facility_id, code="W1", name_en="Ward One",
                kind="WARD", physical_beds=10, staffed_beds=10)
    icu = Unit(facility_id=facility.facility_id, code="ICU1", name_en="ICU One",
               kind="ICU", physical_beds=4, staffed_beds=4)
    emergency = Unit(facility_id=facility.facility_id, code="ED", name_en="Emergency",
                     kind="ED", physical_beds=10, staffed_beds=10)
    session.add_all([ward, icu, emergency])
    session.flush()

    # Ten encounters, one admitted each day at 08:00 for exactly 48 hours.
    # Ward patient days therefore total 20 across the window, but the first
    # and last stays are clipped by the window edges.
    for index in range(10):
        patient = Patient(mrn_hash=f"hash-{index}", birth_year=1980, sex="M")
        session.add(patient)
        session.flush()

        admitted = datetime(2026, 3, 1 + index, 8, 0)
        discharged = admitted + timedelta(hours=48)
        encounter = Encounter(
            facility_id=facility.facility_id,
            patient_id=patient.patient_id,
            source_encounter_no=f"E{index:03d}",
            encounter_class="INPATIENT",
            admitting_unit_id=ward.unit_id,
            discharge_unit_id=ward.unit_id,
            specialty="Internal Medicine",
            registration_at=admitted - timedelta(hours=2),
            admission_at=admitted,
            admission_decision_at=admitted - timedelta(hours=1),
            bed_requested_at=admitted - timedelta(minutes=50),
            bed_assigned_at=admitted - timedelta(minutes=20),
            ward_arrival_at=admitted,
            discharge_order_at=discharged - timedelta(hours=3),
            discharge_ready_at=discharged - timedelta(hours=1),
            discharge_at=discharged,
            disposition="DECEASED" if index == 0 else "HOME",
            is_death=index == 0,
            los_hours=48.0,
        )
        session.add(encounter)
        session.flush()

        session.add(BedMovement(encounter_id=encounter.encounter_id, unit_id=ward.unit_id,
                                seq_no=1, in_at=admitted, out_at=discharged,
                                movement_reason="ADMISSION"))
        session.add(EdVisit(
            encounter_id=encounter.encounter_id, facility_id=facility.facility_id,
            arrival_at=admitted - timedelta(hours=3),
            triage_at=admitted - timedelta(hours=3) + timedelta(minutes=10),
            ctas_level=3,
            room_at=admitted - timedelta(hours=3) + timedelta(minutes=30),
            physician_at=admitted - timedelta(hours=3) + timedelta(minutes=45),
            disposition_at=admitted - timedelta(hours=1),
            departure_at=admitted,
            ed_disposition="ADMIT",
        ))

    # Two safety events, one present on admission so it must be excluded
    # from the hospital-acquired rate.
    session.add(SafetyEvent(facility_id=facility.facility_id, unit_id=ward.unit_id,
                            kind="FALL", occurred_at=datetime(2026, 3, 5, 14, 0),
                            harm="MODERATE", present_on_admission=False))
    session.add(SafetyEvent(facility_id=facility.facility_id, unit_id=ward.unit_id,
                            kind="HAI_CAUTI", occurred_at=datetime(2026, 3, 6, 9, 0),
                            harm="MILD", present_on_admission=True))

    # Ward staffing: a flat 60 RN hours per day for ten days.
    for index in range(10):
        session.add(StaffingDay(
            unit_id=ward.unit_id, service_date=date(2026, 3, 1 + index), shift="ALL",
            rn_productive_hours=60.0, lpn_productive_hours=10.0, na_productive_hours=20.0,
            non_productive_hours=10.0, overtime_hours=6.0, agency_hours=3.0,
            sick_leave_hours=4.0, scheduled_hours=100.0,
            budgeted_fte=20.0, filled_fte=18.0, separations=0, headcount=25,
        ))

    session.commit()
    return {"facility": facility, "ward": ward, "icu": icu, "ed": emergency,
            "start": START, "end": END}
