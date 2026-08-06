#!/usr/bin/env python3
"""Generate a synthetic tertiary-hospital dataset.

The point is not random noise -- it is data with the *structure* real
hospital data has, so the platform can be demonstrated and tested against
something that behaves like the real thing:

* ED arrivals follow a diurnal curve with a Friday-Saturday weekend dip.
* Occupancy drifts up over the period and spikes in a deliberate winter
  surge, so forecasting and anomaly detection have something to find.
* Boarding time degrades as occupancy rises -- the actual causal
  relationship that makes flow dashboards worth building.
* A configurable share of rows carry realistic defects (blank timestamps,
  duplicated visit numbers, mixed date formats, Arabic-Indic digits) so
  the data-quality engine has something to catch.

Everything is synthetic. No real patient data is used or reproduced.

Usage:
    python scripts/generate_sample_data.py --days 180 --out data/samples
"""

from __future__ import annotations

import argparse
import math
import random
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
random.seed(42)

# ---------------------------------------------------------------------
# Facility definition
# ---------------------------------------------------------------------
UNITS = [
    # code,      name_en,                     name_ar,                  kind,  beds, specialty
    ("ED",       "Emergency Department",      "قسم الطوارئ",            "ED",     56, "Emergency"),
    ("MICU",     "Medical ICU",               "العناية الطبية",          "ICU",    20, "Critical Care"),
    ("SICU",     "Surgical ICU",              "العناية الجراحية",        "ICU",    16, "Critical Care"),
    ("CICU",     "Cardiac ICU",               "عناية القلب",             "ICU",    12, "Cardiology"),
    ("NICU",     "Neonatal ICU",              "عناية الأطفال حديثي الولادة", "NICU", 24, "Neonatology"),
    ("HDU",      "High Dependency Unit",      "وحدة الرعاية المتوسطة",   "HDU",    18, "Critical Care"),
    ("MED1",     "Medical Ward 1",            "الباطنة ١",               "WARD",   40, "Internal Medicine"),
    ("MED2",     "Medical Ward 2",            "الباطنة ٢",               "WARD",   38, "Internal Medicine"),
    ("SURG1",    "Surgical Ward 1",           "الجراحة ١",               "WARD",   36, "General Surgery"),
    ("SURG2",    "Surgical Ward 2",           "الجراحة ٢",               "WARD",   32, "Orthopaedics"),
    ("CARD",     "Cardiology Ward",           "قسم القلب",               "WARD",   30, "Cardiology"),
    ("ONC",      "Oncology Ward",             "قسم الأورام",             "WARD",   28, "Oncology"),
    ("PED",      "Paediatric Ward",           "قسم الأطفال",             "WARD",   34, "Paediatrics"),
    ("OBGY",     "Obstetrics & Gynaecology",  "النساء والولادة",         "WARD",   36, "Obstetrics"),
    ("OR",       "Operating Theatres",        "غرف العمليات",            "OR",     14, "Surgery"),
    ("PACU",     "Post-Anaesthesia Care",     "الإفاقة",                 "PACU",   16, "Anaesthesia"),
]

WARD_CODES = [u[0] for u in UNITS if u[3] == "WARD"]
ICU_CODES = [u[0] for u in UNITS if u[3] in ("ICU", "HDU")]

SPECIALTIES = ["Internal Medicine", "General Surgery", "Cardiology", "Orthopaedics",
               "Paediatrics", "Obstetrics", "Oncology", "Neurology", "Pulmonology"]

SPECIALTY_TO_WARD = {
    "Internal Medicine": ["MED1", "MED2"], "General Surgery": ["SURG1"],
    "Orthopaedics": ["SURG2"], "Cardiology": ["CARD"], "Oncology": ["ONC"],
    "Paediatrics": ["PED"], "Obstetrics": ["OBGY"], "Neurology": ["MED1"],
    "Pulmonology": ["MED2"],
}

# Relative ED arrival intensity by hour. Real EDs peak late morning and
# again in the evening, and empty out between 03:00 and 06:00.
HOUR_WEIGHTS = np.array([
    0.45, 0.35, 0.28, 0.24, 0.24, 0.30, 0.45, 0.70, 1.00, 1.30, 1.45, 1.42,
    1.30, 1.22, 1.18, 1.20, 1.30, 1.42, 1.50, 1.45, 1.25, 1.00, 0.78, 0.58,
])
HOUR_WEIGHTS = HOUR_WEIGHTS / HOUR_WEIGHTS.sum()

CTAS_PROBABILITIES = [0.02, 0.13, 0.38, 0.34, 0.13]
CTAS_ADMIT_RATE = {1: 0.88, 2: 0.62, 3: 0.28, 4: 0.07, 5: 0.02}

ICD10 = ["J18.9", "I50.9", "N39.0", "K35.80", "I21.4", "J44.1", "E11.65",
         "A41.9", "S72.00", "O80", "C34.90", "I63.9", "K92.2", "R07.9"]


def _lognormal(mean_hours: float, sigma: float = 0.7) -> float:
    """Draw a positive duration whose median is ``mean_hours``."""
    return float(rng.lognormal(mean=math.log(mean_hours), sigma=sigma))


def _seasonal_multiplier(day_index: int, total_days: int) -> float:
    """Slow upward drift plus a deliberate mid-period surge.

    The surge gives the anomaly detector and the forecaster a genuine
    signal to find instead of pure noise.
    """
    drift = 1.0 + 0.10 * (day_index / max(total_days, 1))
    surge_centre = int(total_days * 0.62)
    surge = 1.0 + 0.28 * math.exp(-((day_index - surge_centre) ** 2) / (2 * 9 ** 2))
    return drift * surge


def _weekday_multiplier(day: date) -> float:
    # Friday/Saturday is the weekend in Saudi Arabia: fewer elective cases,
    # slightly more emergency presentations.
    return {0: 1.08, 1: 1.05, 2: 1.02, 3: 1.00, 4: 0.88, 5: 0.90, 6: 1.06}[day.weekday()]


def generate(days: int, start: date, base_ed_arrivals: int = 210) -> dict[str, pd.DataFrame]:
    units_rows = [
        {
            "unit_code": code, "name_en": name_en, "name_ar": name_ar, "kind": kind,
            "specialty": specialty, "physical_beds": beds,
            "staffed_beds": max(int(beds * 0.94), 1),
            "target_occupancy": 80 if kind in ("ICU", "NICU", "HDU") else 85,
        }
        for code, name_en, name_ar, kind, beds, specialty in UNITS
    ]

    encounters, ed_visits, movements, orders = [], [], [], []
    safety_events, staffing, icu_stays, or_cases, vitals, surveys = [], [], [], [], [], []

    encounter_seq = 0
    event_seq = 0
    order_seq = 0
    patient_pool = [f"MRN{i:07d}" for i in range(1, 45000)]

    # Tracks how full the hospital is, which drives boarding delays.
    occupancy_pressure = 0.78

    # Seed the wards with patients who were already admitted before the
    # extract begins. Without them the first fortnight is a ramp from an
    # empty hospital, which is not something a real extract ever shows --
    # and it swamps anomaly detection with warm-up artefacts.
    encounter_seq = _seed_existing_inpatients(
        encounters, movements, icu_stays, patient_pool, start, encounter_seq
    )

    for day_index in range(days):
        service_day = start + timedelta(days=day_index)
        seasonal = _seasonal_multiplier(day_index, days)
        weekday = _weekday_multiplier(service_day)

        occupancy_pressure = float(np.clip(
            0.80 * seasonal * weekday + rng.normal(0, 0.03), 0.55, 1.02
        ))

        arrivals_today = int(rng.poisson(base_ed_arrivals * seasonal * weekday))
        hourly_counts = rng.multinomial(arrivals_today, HOUR_WEIGHTS)

        for hour, count in enumerate(hourly_counts):
            for _ in range(int(count)):
                encounter_seq += 1
                encounter_no = f"E{service_day.year}{encounter_seq:07d}"
                mrn = random.choice(patient_pool)

                arrival = datetime.combine(service_day, datetime.min.time()) + timedelta(
                    hours=hour, minutes=float(rng.uniform(0, 60))
                )
                ctas = int(rng.choice([1, 2, 3, 4, 5], p=CTAS_PROBABILITIES))

                # Crowding lengthens every downstream wait.
                crowding = 1.0 + 1.9 * max(occupancy_pressure - 0.80, 0)

                triage = arrival + timedelta(minutes=_lognormal(6 * crowding, 0.5))
                room_delay = {1: 1, 2: 7, 3: 24, 4: 36, 5: 44}[ctas] * crowding
                room = triage + timedelta(minutes=_lognormal(max(room_delay, 1), 0.65))
                physician = room + timedelta(minutes=_lognormal(12 * crowding, 0.6))

                # 2% of visits leave before being seen, concentrated in low acuity
                # and worsening sharply when the department is crowded.
                lwbs_risk = {1: 0.000, 2: 0.002, 3: 0.012, 4: 0.035, 5: 0.055}[ctas] * crowding
                is_lwbs = rng.random() < lwbs_risk

                admitted = (not is_lwbs) and rng.random() < CTAS_ADMIT_RATE[ctas]
                is_lama = (not is_lwbs) and (not admitted) and rng.random() < 0.012

                if is_lwbs:
                    departure = arrival + timedelta(minutes=_lognormal(150 * crowding, 0.5))
                    ed_visits.append(_ed_row(encounter_no, arrival, triage, ctas, None, None,
                                             None, departure, "LWBS", False))
                    encounters.append(_encounter_row(
                        encounter_no, mrn, "EMERGENCY", None, None, arrival, None, None,
                        departure, "LWBS", ctas))
                    movements.append(_movement(encounter_no, 1, "ED", arrival, departure,
                                               "ADMISSION"))
                    continue

                workup = _lognormal(75 if ctas <= 2 else 55, 0.55)
                disposition = physician + timedelta(minutes=workup)

                if not admitted:
                    departure = disposition + timedelta(minutes=_lognormal(28, 0.5))
                    ed_disposition = "LAMA" if is_lama else "DISCHARGE"
                    ed_visits.append(_ed_row(encounter_no, arrival, triage, ctas, room, physician,
                                             disposition, departure, ed_disposition, False))
                    encounters.append(_encounter_row(
                        encounter_no, mrn, "EMERGENCY", None, None, arrival, None, None,
                        departure, "LAMA" if is_lama else "HOME", ctas))
                    movements.append(_movement(encounter_no, 1, "ED", arrival, departure,
                                               "ADMISSION"))
                    _add_orders(orders, encounter_no, arrival, physician, ctas, order_seq)
                    order_seq += 3
                    continue

                # --- Admitted patient -------------------------------------
                specialty = _pick_specialty(ctas)
                needs_icu = (ctas <= 2 and rng.random() < 0.58) or (ctas == 3 and rng.random() < 0.05)
                if needs_icu:
                    unit_code = random.choice(ICU_CODES)
                elif specialty == "Paediatrics" and rng.random() < 0.22:
                    unit_code = "NICU"
                else:
                    unit_code = random.choice(SPECIALTY_TO_WARD.get(specialty, WARD_CODES))

                decision = disposition
                bed_requested = decision + timedelta(minutes=_lognormal(12, 0.5))
                # Bed-finding is where crowding bites hardest.
                allocation = _lognormal(45 * (crowding ** 2.1), 0.8)
                bed_assigned = bed_requested + timedelta(minutes=allocation)
                ward_arrival = bed_assigned + timedelta(minutes=_lognormal(38, 0.7))
                departure = ward_arrival

                los_hours = _lognormal(112 if needs_icu else 78, 0.85)
                los_hours = min(los_hours, 24 * 120)
                discharge = ward_arrival + timedelta(hours=los_hours)

                # Discharges cluster late morning; nights are rare.
                discharge = discharge.replace(
                    hour=int(np.clip(rng.normal(13, 3), 7, 22)),
                    minute=int(rng.uniform(0, 60)),
                )
                if discharge <= ward_arrival:
                    discharge = ward_arrival + timedelta(hours=6)

                discharge_order = discharge - timedelta(minutes=_lognormal(165, 0.7))
                discharge_ready = discharge - timedelta(minutes=_lognormal(95, 0.8))
                if discharge_order > discharge_ready:
                    discharge_order, discharge_ready = discharge_ready, discharge_order

                died = rng.random() < (0.055 if needs_icu else 0.012)
                disposition_code = "DECEASED" if died else "HOME"

                ed_visits.append(_ed_row(encounter_no, arrival, triage, ctas, room, physician,
                                         disposition, departure, "ADMIT",
                                         needs_icu and rng.random() < 0.3))
                encounters.append(_encounter_row(
                    encounter_no, mrn, "INPATIENT", unit_code, specialty, arrival,
                    ward_arrival, decision, discharge, disposition_code, ctas,
                    bed_requested=bed_requested, bed_assigned=bed_assigned,
                    ward_arrival=ward_arrival, discharge_order=discharge_order,
                    discharge_ready=discharge_ready,
                ))

                # Bed movement trail. The ED segment is included because the
                # ADT trail is what gives emergency nursing hours a patient-day
                # denominator; without it the ED's NCHPD is undefined.
                movements.append(_movement(encounter_no, 1, "ED", arrival, departure, "ADMISSION"))
                seq = 2
                if needs_icu:
                    icu_hours = min(los_hours * float(rng.uniform(0.35, 0.8)), los_hours - 2)
                    icu_out = ward_arrival + timedelta(hours=max(icu_hours, 4))
                    movements.append(_movement(encounter_no, seq, unit_code, ward_arrival,
                                               icu_out, "ADMISSION"))
                    icu_stays.append({
                        "encounter_no": encounter_no, "unit_code": unit_code,
                        "admit_at": ward_arrival, "discharge_at": icu_out,
                        "apache_ii": int(np.clip(rng.normal(16, 6), 0, 50)),
                        "ventilated_hours": round(max(0, rng.normal(icu_hours * 0.55, 12)), 1),
                        "outcome": "DIED" if died else "TRANSFERRED",
                    })
                    seq += 1
                    step_down = random.choice(SPECIALTY_TO_WARD.get(specialty, WARD_CODES))
                    movements.append(_movement(encounter_no, seq, step_down, icu_out,
                                               discharge, "STEPDOWN"))
                else:
                    movements.append(_movement(encounter_no, seq, unit_code, ward_arrival,
                                               discharge, "ADMISSION"))

                _add_orders(orders, encounter_no, arrival, physician, ctas, order_seq)
                order_seq += 4

                # Vitals: three observations per admitted patient.
                for offset in (2, 24, 48):
                    if offset > los_hours:
                        break
                    vitals.append(_vitals(encounter_no, ward_arrival + timedelta(hours=offset),
                                          severe=needs_icu))

                # Surgical patients get a theatre case.
                if specialty in ("General Surgery", "Orthopaedics") and rng.random() < 0.72:
                    or_cases.append(_or_case(encounter_no, ward_arrival, specialty))

                if rng.random() < 0.28:
                    surveys.append({
                        "survey_ref": f"S{encounter_seq:08d}",
                        "encounter_no": encounter_no,
                        "unit_code": unit_code,
                        "surveyed_at": discharge + timedelta(days=int(rng.integers(1, 7))),
                        "overall_rating": int(np.clip(rng.normal(8.4, 1.6), 0, 10)),
                        "would_recommend": int(np.clip(rng.normal(8.6, 1.8), 0, 10)),
                    })

        # ---- Daily safety events -------------------------------------
        # Rates rise with occupancy: an over-full ward is a less safe ward.
        pressure_factor = 1.0 + 1.6 * max(occupancy_pressure - 0.85, 0)
        for kind, daily_lambda in (
            ("FALL", 0.55), ("PRESSURE_INJURY", 0.30), ("MEDICATION_ERROR", 1.10),
            ("HAI_CLABSI", 0.08), ("HAI_CAUTI", 0.10), ("HAI_VAP", 0.06),
            ("HAI_SSI", 0.09), ("CODE_BLUE", 0.22), ("RRT_ACTIVATION", 0.85),
            ("SEPSIS_ALERT", 0.40),
        ):
            for _ in range(int(rng.poisson(daily_lambda * pressure_factor))):
                event_seq += 1
                harm = str(rng.choice(
                    ["NO_HARM", "MILD", "MODERATE", "SEVERE", "DEATH"],
                    p=[0.55, 0.26, 0.13, 0.05, 0.01],
                ))
                safety_events.append({
                    "event_ref": f"EV{event_seq:07d}",
                    "encounter_no": None,
                    "unit_code": random.choice(WARD_CODES + ICU_CODES),
                    "kind": kind,
                    "occurred_at": datetime.combine(service_day, datetime.min.time())
                    + timedelta(hours=float(rng.uniform(0, 24))),
                    "harm": harm,
                    # A quarter of infections and pressure injuries arrive with the patient.
                    "present_on_admission": kind.startswith("HAI_") and rng.random() < 0.25,
                    "pressure_injury_stage": (
                        str(rng.choice(["I", "II", "III", "IV"], p=[0.35, 0.45, 0.15, 0.05]))
                        if kind == "PRESSURE_INJURY" else None
                    ),
                    "medication_error_stage": (
                        str(rng.choice(["PRESCRIBING", "TRANSCRIBING", "DISPENSING",
                                        "ADMINISTRATION"], p=[0.3, 0.15, 0.2, 0.35]))
                        if kind == "MEDICATION_ERROR" else None
                    ),
                    "is_sentinel": harm == "DEATH" and rng.random() < 0.3,
                })

    # Staffing is derived from the census the movements actually produce
    # rather than from an assumed occupancy. Rostering against a number the
    # rest of the dataset contradicts is exactly how a demo ends up
    # reporting 60 nursing hours per patient day on a half-empty ICU.
    staffing = _build_staffing(pd.DataFrame(movements), start, days)

    return {
        "units": pd.DataFrame(units_rows),
        "encounters": pd.DataFrame(encounters),
        "ed_visits": pd.DataFrame(ed_visits),
        "bed_movements": pd.DataFrame(movements),
        "orders": pd.DataFrame(orders),
        "safety_events": pd.DataFrame(safety_events),
        "staffing": pd.DataFrame(staffing),
        "icu_stays": pd.DataFrame(icu_stays),
        "or_cases": pd.DataFrame(or_cases),
        "vitals": pd.DataFrame(vitals),
        "patient_experience": pd.DataFrame(surveys),
    }


def _seed_existing_inpatients(encounters: list, movements: list, icu_stays: list,
                              patient_pool: list[str], start: date,
                              encounter_seq: int) -> int:
    """Populate the wards as they would already be on day one of the extract."""
    for code, _, _, kind, beds, specialty in UNITS:
        if kind in ("ED", "OR", "PACU", "OPD"):
            continue
        staffed = max(int(beds * 0.94), 1)
        occupied = int(staffed * float(rng.uniform(0.70, 0.88)))

        for _ in range(occupied):
            encounter_seq += 1
            encounter_no = f"E{start.year}P{encounter_seq:07d}"
            # Admitted somewhere in the fortnight before the window opens,
            # discharging on a staggered schedule after it.
            admitted = (datetime.combine(start, datetime.min.time())
                        - timedelta(hours=float(rng.uniform(6, 14 * 24))))
            remaining = _lognormal(60 if kind in ("ICU", "NICU", "HDU") else 48, 0.8)
            discharged = datetime.combine(start, datetime.min.time()) + timedelta(hours=remaining)
            died = rng.random() < (0.05 if kind in ("ICU", "NICU", "HDU") else 0.012)

            encounters.append(_encounter_row(
                encounter_no, random.choice(patient_pool), "INPATIENT", code, specialty,
                admitted, admitted, admitted, discharged,
                "DECEASED" if died else "HOME", 3,
                bed_requested=admitted, bed_assigned=admitted, ward_arrival=admitted,
                discharge_order=discharged - timedelta(hours=3),
                discharge_ready=discharged - timedelta(hours=1),
            ))
            movements.append(_movement(encounter_no, 1, code, admitted, discharged, "ADMISSION"))

            if kind in ("ICU", "NICU", "HDU"):
                icu_stays.append({
                    "encounter_no": encounter_no, "unit_code": code,
                    "admit_at": admitted, "discharge_at": discharged,
                    "apache_ii": int(np.clip(rng.normal(16, 6), 0, 50)),
                    "ventilated_hours": round(max(0, rng.normal(remaining * 0.5, 10)), 1),
                    "outcome": "DIED" if died else "TRANSFERRED",
                })
    return encounter_seq


#: Target productive RN hours per patient day by unit type. These are the
#: ratios a Magnet-aspiring tertiary centre rosters to.
RN_HOURS_PER_PATIENT_DAY = {"ICU": 16.0, "NICU": 14.0, "HDU": 9.0, "ED": 4.6, "WARD": 5.0}


def _build_staffing(movements: pd.DataFrame, start: date, days: int) -> list[dict]:
    """Roster each unit against the census its own movements produce."""
    unit_lookup = {code: (kind, beds) for code, _, _, kind, beds, _ in UNITS}

    census: dict[tuple[str, date], float] = {}
    if not movements.empty:
        frame = movements.copy()
        frame["in_at"] = pd.to_datetime(frame["in_at"])
        frame["out_at"] = pd.to_datetime(frame["out_at"])
        for row in frame.itertuples(index=False):
            if pd.isna(row.in_at) or pd.isna(row.out_at):
                continue
            cursor = row.in_at.normalize()
            while cursor <= row.out_at:
                day_start = cursor
                day_end = cursor + pd.Timedelta(days=1)
                overlap = (min(row.out_at, day_end) - max(row.in_at, day_start)).total_seconds()
                if overlap > 0:
                    key = (row.unit_code, cursor.date())
                    census[key] = census.get(key, 0.0) + overlap / 86400.0
                cursor = day_end

    rows = []
    for day_index in range(days):
        service_day = start + timedelta(days=day_index)
        for code, (kind, beds) in unit_lookup.items():
            if kind in ("OR", "PACU", "OPD"):
                continue
            staffed = max(int(beds * 0.94), 1)
            patient_days = census.get((code, service_day), 0.0)
            occupancy = patient_days / staffed if staffed else 0

            rn_target = RN_HOURS_PER_PATIENT_DAY.get(kind, 5.0)
            # Even an empty unit keeps a safety minimum on shift; nursing
            # hours do not fall to zero just because the beds do.
            minimum_hours = staffed * 0.9
            rn_hours = max(patient_days * rn_target * float(rng.uniform(0.9, 1.1)), minimum_hours)
            # Overtime and agency use rise when a unit runs hot.
            pressure = 1.0 + 1.8 * max(occupancy - 0.85, 0)

            rows.append({
                "unit_code": code,
                "service_date": service_day,
                "shift": "ALL",
                "rn_productive_hours": round(rn_hours, 1),
                "lpn_productive_hours": round(rn_hours * 0.18, 1),
                "na_productive_hours": round(rn_hours * 0.30, 1),
                "non_productive_hours": round(rn_hours * 0.09, 1),
                "overtime_hours": round(rn_hours * float(rng.uniform(0.03, 0.06)) * pressure, 1),
                "agency_hours": round(rn_hours * float(rng.uniform(0.0, 0.07)), 1),
                "sick_leave_hours": round(rn_hours * float(rng.uniform(0.01, 0.05)), 1),
                "scheduled_hours": round(rn_hours * 1.14, 1),
                "budgeted_fte": round(staffed * 1.45, 1),
                "filled_fte": round(staffed * 1.45 * float(rng.uniform(0.85, 0.97)), 1),
                # ~14% annual turnover spread across the period.
                "separations": int(rng.random() < 0.0045 * staffed / 20),
                "headcount": int(staffed * 1.4),
                "patient_days": round(patient_days, 2),
            })
    return rows


def _pick_specialty(ctas: int) -> str:
    if ctas <= 2:
        return str(rng.choice(["Internal Medicine", "Cardiology", "Neurology", "Pulmonology"],
                              p=[0.4, 0.25, 0.2, 0.15]))
    return str(rng.choice(SPECIALTIES))


def _ed_row(encounter_no, arrival, triage, ctas, room, physician, disposition,
            departure, ed_disposition, ventilated) -> dict:
    return {
        "encounter_no": encounter_no,
        "arrival_at": arrival,
        "arrival_mode": str(rng.choice(["WALK_IN", "AMBULANCE", "REFERRAL"], p=[0.68, 0.24, 0.08])),
        "triage_at": triage,
        "ctas_level": ctas,
        "room_at": room,
        "physician_at": physician,
        "disposition_at": disposition,
        "departure_at": departure,
        "ed_disposition": ed_disposition,
        "on_ventilator": ventilated,
    }


def _encounter_row(encounter_no, mrn, encounter_class, unit_code, specialty, registration,
                   admission, decision, discharge, disposition, ctas, *,
                   bed_requested=None, bed_assigned=None, ward_arrival=None,
                   discharge_order=None, discharge_ready=None) -> dict:
    return {
        "encounter_no": encounter_no,
        "mrn": mrn,
        "birth_year": int(rng.integers(1935, 2023)),
        "sex": str(rng.choice(["M", "F"], p=[0.52, 0.48])),
        "nationality_group": str(rng.choice(["Saudi", "Non-Saudi"], p=[0.68, 0.32])),
        "encounter_class": encounter_class,
        "admitting_unit_code": unit_code,
        "discharge_unit_code": unit_code,
        "specialty": specialty,
        "primary_diagnosis_code": random.choice(ICD10),
        "is_elective": False,
        "registration_at": registration,
        "admission_at": admission,
        "admission_decision_at": decision,
        "bed_requested_at": bed_requested,
        "bed_assigned_at": bed_assigned,
        "ward_arrival_at": ward_arrival,
        "discharge_order_at": discharge_order,
        "discharge_ready_at": discharge_ready,
        "discharge_at": discharge,
        "disposition": disposition,
    }


def _movement(encounter_no, seq, unit_code, in_at, out_at, reason) -> dict:
    return {
        "encounter_no": encounter_no, "seq_no": seq, "unit_code": unit_code,
        "bed_code": f"{unit_code}-{int(rng.integers(1, 40)):02d}",
        "in_at": in_at, "out_at": out_at, "movement_reason": reason,
    }


def _add_orders(orders: list, encounter_no: str, arrival: datetime,
                physician: datetime, ctas: int, seq: int) -> None:
    order_count = 4 if ctas <= 2 else 2
    for i in range(order_count):
        domain = str(rng.choice(["LAB", "RADIOLOGY", "CONSULT"], p=[0.62, 0.28, 0.10]))
        ordered = physician + timedelta(minutes=float(rng.uniform(2, 40)))
        is_stat = ctas <= 2 and rng.random() < 0.6

        if domain == "LAB":
            collected = ordered + timedelta(minutes=_lognormal(14, 0.6))
            tat = _lognormal(28 if is_stat else 62, 0.5)
            resulted = collected + timedelta(minutes=tat)
            modality = None
        elif domain == "RADIOLOGY":
            collected = None
            modality = str(rng.choice(["XR", "CT", "US", "MRI"], p=[0.5, 0.28, 0.16, 0.06]))
            base = {"XR": 55, "CT": 95, "US": 80, "MRI": 190}[modality]
            resulted = ordered + timedelta(minutes=_lognormal(base * (0.6 if is_stat else 1.0), 0.55))
        else:
            collected = None
            modality = None
            resulted = ordered + timedelta(minutes=_lognormal(75, 0.8))

        orders.append({
            "encounter_no": encounter_no,
            "order_ref": f"O{seq + i:09d}",
            "domain": domain,
            "order_code": f"{domain[:2]}{int(rng.integers(100, 999))}",
            "order_name": {"LAB": "Complete blood count", "RADIOLOGY": "Diagnostic imaging",
                           "CONSULT": "Specialty consultation"}[domain],
            "modality": modality,
            "is_stat": is_stat,
            "ordered_at": ordered,
            "collected_at": collected,
            "performed_at": None,
            "resulted_at": resulted,
            "acknowledged_at": resulted + timedelta(minutes=_lognormal(18, 0.7)),
            "responding_specialty": random.choice(SPECIALTIES) if domain == "CONSULT" else None,
        })


def _vitals(encounter_no: str, recorded_at: datetime, *, severe: bool) -> dict:
    shift = 1.6 if severe else 1.0
    return {
        "encounter_no": encounter_no,
        "recorded_at": recorded_at,
        "respiratory_rate": int(np.clip(rng.normal(16 + 4 * (shift - 1), 3.5), 6, 45)),
        "spo2": int(np.clip(rng.normal(97 - 4 * (shift - 1), 2.5), 78, 100)),
        "on_oxygen": bool(severe and rng.random() < 0.6),
        "systolic_bp": int(np.clip(rng.normal(126 - 14 * (shift - 1), 20), 70, 210)),
        "heart_rate": int(np.clip(rng.normal(82 + 16 * (shift - 1), 15), 40, 165)),
        "temperature_c": round(float(np.clip(rng.normal(36.9, 0.65), 34.5, 41.0)), 1),
        "consciousness": str(rng.choice(["A", "C", "V"], p=[0.94, 0.045, 0.015])),
    }


def _or_case(encounter_no: str, admitted_at: datetime, specialty: str) -> dict:
    scheduled = (admitted_at + timedelta(hours=float(rng.uniform(4, 30)))).replace(
        hour=int(rng.integers(7, 17)), minute=int(rng.choice([0, 15, 30, 45]))
    )
    delay = _lognormal(14, 0.9)
    wheels_in = scheduled + timedelta(minutes=delay)
    anesthesia = wheels_in + timedelta(minutes=float(rng.uniform(5, 15)))
    incision = anesthesia + timedelta(minutes=float(rng.uniform(10, 25)))
    closure = incision + timedelta(minutes=_lognormal(85, 0.6))
    wheels_out = closure + timedelta(minutes=float(rng.uniform(8, 25)))
    pacu_in = wheels_out + timedelta(minutes=float(rng.uniform(3, 12)))
    cancelled = rng.random() < 0.045
    return {
        "encounter_no": encounter_no,
        "case_ref": f"OR{int(rng.integers(1, 999999)):06d}",
        "theatre_code": f"OR-{int(rng.integers(1, 15)):02d}",
        "procedure_code": f"CPT{int(rng.integers(10000, 69999))}",
        "specialty": specialty,
        "is_emergency": bool(rng.random() < 0.35),
        "scheduled_start_at": scheduled,
        "holding_at": wheels_in - timedelta(minutes=float(rng.uniform(20, 60))),
        "wheels_in_at": None if cancelled else wheels_in,
        "anesthesia_start_at": None if cancelled else anesthesia,
        "incision_at": None if cancelled else incision,
        "closure_at": None if cancelled else closure,
        "wheels_out_at": None if cancelled else wheels_out,
        "pacu_in_at": None if cancelled else pacu_in,
        "pacu_out_at": None if cancelled else pacu_in + timedelta(minutes=_lognormal(95, 0.5)),
        "is_cancelled": cancelled,
        "cancellation_reason": str(rng.choice(
            ["Patient not fit", "No ICU bed", "Equipment unavailable", "Surgeon unavailable"]
        )) if cancelled else None,
    }


# ---------------------------------------------------------------------
# Realistic defects, so the data-quality engine has work to do
# ---------------------------------------------------------------------
ARABIC_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def inject_defects(frames: dict[str, pd.DataFrame], rate: float = 0.02) -> dict[str, pd.DataFrame]:
    """Introduce the defects real hospital extracts actually contain."""
    if rate <= 0:
        return frames

    out = {key: frame.copy() for key, frame in frames.items()}

    ed = out.get("ed_visits")
    if ed is not None and not ed.empty:
        # Missing triage timestamps -- the single most common ED data gap.
        blank = rng.random(len(ed)) < rate * 1.5
        ed.loc[blank, "triage_at"] = None

        # A handful of rows where physician time precedes arrival (clock skew
        # between the triage tablet and the EMR).
        skewed = rng.random(len(ed)) < rate * 0.3
        ed.loc[skewed, "physician_at"] = ed.loc[skewed, "arrival_at"] - pd.Timedelta(minutes=25)

    encounters = out.get("encounters")
    if encounters is not None and not encounters.empty:
        # Duplicated export block: the same rows appended twice.
        duplicate_count = max(int(len(encounters) * rate * 0.4), 1)
        duplicates = encounters.sample(duplicate_count, random_state=7)
        out["encounters"] = pd.concat([encounters, duplicates], ignore_index=True)

        # Arabic-Indic digits in the MRN column, which a naive loader mangles.
        frame = out["encounters"]
        arabic = rng.random(len(frame)) < rate * 0.5
        frame.loc[arabic, "mrn"] = frame.loc[arabic, "mrn"].astype(str).str.translate(ARABIC_DIGITS)

        # Some discharges recorded as plain dd/mm/yyyy dates rather than
        # timestamps. The column is cast to object first, otherwise pandas
        # re-parses the strings as month-first and silently swaps the day.
        date_only = rng.random(len(frame)) < rate
        frame["discharge_at"] = frame["discharge_at"].astype(object)
        frame.loc[date_only, "discharge_at"] = pd.to_datetime(
            frame.loc[date_only, "discharge_at"], errors="coerce"
        ).dt.strftime("%d/%m/%Y")

    staffing = out.get("staffing")
    if staffing is not None and not staffing.empty:
        # Blank RN hours for a few unit-days.
        blank = rng.random(len(staffing)) < rate
        staffing.loc[blank, "rn_productive_hours"] = None

    return out


# ---------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------
def write(frames: dict[str, pd.DataFrame], out_dir: Path, *, excel: bool = True) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []

    for key, frame in frames.items():
        csv_path = out_dir / f"{key}.csv"
        frame.to_csv(csv_path, index=False)
        written.append(csv_path)

    if excel:
        workbook_path = out_dir / "hospital_sample_data.xlsx"
        with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
            for key, frame in frames.items():
                # Excel caps sheet names at 31 characters.
                frame.to_excel(writer, sheet_name=key[:31], index=False)
        written.append(workbook_path)

    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=180, help="Days of history to generate")
    parser.add_argument("--start", type=str, default=None,
                        help="Start date YYYY-MM-DD (default: today minus --days)")
    parser.add_argument("--arrivals", type=int, default=210,
                        help="Baseline ED arrivals per day")
    parser.add_argument("--defect-rate", type=float, default=0.02,
                        help="Share of rows given realistic defects (0 disables)")
    parser.add_argument("--out", type=str, default="data/samples", help="Output directory")
    parser.add_argument("--no-excel", action="store_true", help="Write CSV only")
    args = parser.parse_args()

    start = (date.fromisoformat(args.start) if args.start
             else date.today() - timedelta(days=args.days))

    print(f"Generating {args.days} days from {start} ...")
    frames = generate(args.days, start, base_ed_arrivals=args.arrivals)
    frames = inject_defects(frames, args.defect_rate)

    written = write(frames, Path(args.out), excel=not args.no_excel)

    print("\nDataset summary")
    print("-" * 52)
    for key, frame in frames.items():
        print(f"  {key:22s} {len(frame):>8,} rows")
    print("-" * 52)
    print(f"Files written to {Path(args.out).resolve()}:")
    for path in written:
        print(f"  {path.name}")


if __name__ == "__main__":
    main()
