"""Canonical dataset contracts for Excel/CSV import.

Each hospital names its columns differently -- and in a Saudi tertiary
centre the same extract may carry English headers, Arabic headers, or the
HIS vendor's internal codes. Rather than force one naming convention on
the customer, every canonical field declares the aliases seen in the
field, and ``mapper.py`` resolves whatever the file actually contains.

Adding support for a new HIS export is normally an aliases-only change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

FieldType = Literal["string", "integer", "number", "boolean", "datetime", "date"]


@dataclass(frozen=True)
class FieldSpec:
    name: str
    dtype: FieldType
    required: bool = False
    aliases: tuple[str, ...] = ()
    domain: tuple[str, ...] | None = None
    minimum: float | None = None
    maximum: float | None = None
    description: str = ""
    #: Marks the field as a direct patient identifier. Values are hashed at
    #: load time and the raw value is dropped before staging is persisted.
    is_identifier: bool = False


@dataclass(frozen=True)
class ChronologyRule:
    """``earlier`` must not occur after ``later`` when both are present."""

    earlier: str
    later: str
    #: Tolerance for clock skew between source systems.
    tolerance_minutes: int = 0


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    title_en: str
    title_ar: str
    fields: tuple[FieldSpec, ...]
    natural_key: tuple[str, ...]
    chronology: tuple[ChronologyRule, ...] = ()
    #: Fields that must reference an encounter already loaded (or present in
    #: the same batch) before the rows can be promoted.
    references_encounter: bool = False
    notes: str = ""

    @property
    def field_map(self) -> dict[str, FieldSpec]:
        return {f.name: f for f in self.fields}

    @property
    def required_fields(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields if f.required)


_YES_NO = ("Y", "N", "YES", "NO", "TRUE", "FALSE", "1", "0")


# ---------------------------------------------------------------------
# encounters -- the spine every other dataset hangs off
# ---------------------------------------------------------------------
ENCOUNTERS = DatasetSpec(
    key="encounters",
    title_en="Encounters (admissions & discharges)",
    title_ar="الزيارات (الدخول والخروج)",
    natural_key=("encounter_no",),
    fields=(
        FieldSpec(
            "encounter_no", "string", required=True,
            aliases=("encounter", "visit_no", "visit_id", "episode_no", "admission_no",
                     "case_no", "account_no", "رقم الزيارة", "رقم الدخول"),
            description="Unique visit/episode number from the HIS.",
        ),
        FieldSpec(
            "mrn", "string", required=True, is_identifier=True,
            aliases=("medical_record_no", "medical_record_number", "patient_id", "file_no",
                     "patient_no", "الرقم الطبي", "رقم الملف"),
            description="Medical record number. Hashed on ingest; never stored raw.",
        ),
        FieldSpec("birth_year", "integer", aliases=("year_of_birth", "yob", "سنة الميلاد"),
                  minimum=1900, maximum=2200),
        FieldSpec("age", "integer", aliases=("patient_age", "العمر"), minimum=0, maximum=130,
                  description="Used to derive birth_year when it is absent."),
        FieldSpec("sex", "string", aliases=("gender", "الجنس"), domain=("M", "F", "U")),
        FieldSpec("nationality_group", "string", aliases=("nationality", "الجنسية")),
        FieldSpec(
            "encounter_class", "string", required=True,
            aliases=("visit_type", "patient_type", "encounter_type", "class", "نوع الزيارة"),
            domain=("EMERGENCY", "INPATIENT", "OUTPATIENT", "DAYCASE", "OBSERVATION"),
        ),
        FieldSpec("admitting_unit_code", "string",
                  aliases=("unit", "ward", "admitting_ward", "nursing_unit", "unit_code",
                           "القسم", "الجناح")),
        FieldSpec("discharge_unit_code", "string",
                  aliases=("discharge_ward", "final_ward", "قسم الخروج")),
        FieldSpec("specialty", "string", aliases=("service", "department", "clinical_service",
                                                  "التخصص")),
        FieldSpec("primary_diagnosis_code", "string",
                  aliases=("icd10", "icd_10", "diagnosis_code", "principal_diagnosis",
                           "التشخيص")),
        FieldSpec("drg_code", "string", aliases=("drg", "drg_group")),
        FieldSpec("is_elective", "boolean", aliases=("elective", "planned_admission"),
                  domain=_YES_NO),
        FieldSpec("registration_at", "datetime",
                  aliases=("registration_time", "registration_datetime", "reg_time",
                           "وقت التسجيل")),
        FieldSpec("admission_at", "datetime",
                  aliases=("admission_time", "admit_datetime", "admission_date_time",
                           "admit_date", "وقت الدخول", "تاريخ الدخول")),
        FieldSpec("admission_decision_at", "datetime",
                  aliases=("decision_to_admit", "dta", "admit_decision_time",
                           "قرار التنويم")),
        FieldSpec("bed_requested_at", "datetime",
                  aliases=("bed_request_time", "bed_requested", "طلب السرير")),
        FieldSpec("bed_assigned_at", "datetime",
                  aliases=("bed_assignment_time", "bed_allocated", "تخصيص السرير")),
        FieldSpec("ward_arrival_at", "datetime",
                  aliases=("ward_arrival_time", "arrival_on_ward", "الوصول للقسم")),
        FieldSpec("discharge_order_at", "datetime",
                  aliases=("discharge_order_time", "discharge_decision", "أمر الخروج")),
        FieldSpec("discharge_ready_at", "datetime",
                  aliases=("medically_fit_time", "ready_for_discharge", "جاهز للخروج")),
        FieldSpec("discharge_at", "datetime",
                  aliases=("discharge_time", "discharge_datetime", "discharge_date",
                           "وقت الخروج", "تاريخ الخروج")),
        FieldSpec("disposition", "string",
                  aliases=("discharge_disposition", "discharge_status", "outcome",
                           "حالة الخروج"),
                  domain=("HOME", "TRANSFER_OUT", "DAMA", "LAMA", "LWBS", "DECEASED",
                          "ABSCONDED", "REFERRED")),
    ),
    chronology=(
        ChronologyRule("registration_at", "admission_at"),
        ChronologyRule("admission_decision_at", "bed_requested_at"),
        ChronologyRule("bed_requested_at", "bed_assigned_at"),
        ChronologyRule("bed_assigned_at", "ward_arrival_at"),
        ChronologyRule("admission_at", "discharge_order_at"),
        ChronologyRule("discharge_order_at", "discharge_at"),
        ChronologyRule("admission_at", "discharge_at"),
    ),
    notes="One row per hospital visit. Outpatient rows may omit admission/discharge.",
)


# ---------------------------------------------------------------------
# ed_visits
# ---------------------------------------------------------------------
ED_VISITS = DatasetSpec(
    key="ed_visits",
    title_en="Emergency department visits",
    title_ar="زيارات قسم الطوارئ",
    natural_key=("encounter_no",),
    references_encounter=True,
    fields=(
        FieldSpec("encounter_no", "string", required=True,
                  aliases=("visit_no", "ed_visit_no", "episode_no", "رقم الزيارة")),
        FieldSpec("arrival_at", "datetime", required=True,
                  aliases=("arrival_time", "ed_arrival", "door_time", "وقت الوصول")),
        FieldSpec("arrival_mode", "string",
                  aliases=("mode_of_arrival", "transport", "وسيلة الوصول"),
                  domain=("WALK_IN", "AMBULANCE", "REFERRAL", "TRANSFER", "POLICE", "OTHER")),
        FieldSpec("triage_at", "datetime",
                  aliases=("triage_time", "triage_datetime", "وقت الفرز")),
        FieldSpec("ctas_level", "integer",
                  aliases=("ctas", "triage_level", "acuity", "esi", "مستوى الفرز"),
                  minimum=1, maximum=5),
        FieldSpec("room_at", "datetime",
                  aliases=("room_time", "bed_time", "treatment_space_time", "وقت دخول الغرفة")),
        FieldSpec("physician_at", "datetime",
                  aliases=("physician_time", "doctor_time", "first_provider_contact",
                           "seen_by_doctor", "وقت رؤية الطبيب")),
        FieldSpec("disposition_at", "datetime",
                  aliases=("disposition_time", "decision_time", "وقت القرار")),
        FieldSpec("departure_at", "datetime",
                  aliases=("departure_time", "ed_exit_time", "left_ed", "وقت المغادرة")),
        FieldSpec("ed_disposition", "string",
                  aliases=("disposition", "ed_outcome", "نتيجة الزيارة"),
                  domain=("ADMIT", "DISCHARGE", "TRANSFER", "LWBS", "LAMA", "DEATH", "OTHER")),
        FieldSpec("on_ventilator", "boolean", aliases=("ventilated", "on_vent"), domain=_YES_NO),
    ),
    chronology=(
        ChronologyRule("arrival_at", "triage_at"),
        ChronologyRule("triage_at", "physician_at"),
        ChronologyRule("arrival_at", "room_at"),
        ChronologyRule("physician_at", "disposition_at"),
        ChronologyRule("disposition_at", "departure_at"),
        ChronologyRule("arrival_at", "departure_at"),
    ),
)


# ---------------------------------------------------------------------
# bed_movements (ADT trail)
# ---------------------------------------------------------------------
BED_MOVEMENTS = DatasetSpec(
    key="bed_movements",
    title_en="Bed movements / ADT trail",
    title_ar="حركة الأسرة",
    natural_key=("encounter_no", "seq_no"),
    references_encounter=True,
    fields=(
        FieldSpec("encounter_no", "string", required=True, aliases=("visit_no", "رقم الزيارة")),
        FieldSpec("seq_no", "integer", required=True,
                  aliases=("sequence", "movement_no", "line_no", "التسلسل"), minimum=1),
        FieldSpec("unit_code", "string", required=True,
                  aliases=("unit", "ward", "nursing_unit", "location", "القسم")),
        FieldSpec("bed_code", "string", aliases=("bed", "bed_no", "bed_number", "رقم السرير")),
        FieldSpec("in_at", "datetime", required=True,
                  aliases=("in_time", "from_time", "start_time", "transfer_in", "وقت الدخول")),
        FieldSpec("out_at", "datetime",
                  aliases=("out_time", "to_time", "end_time", "transfer_out", "وقت الخروج")),
        FieldSpec("movement_reason", "string",
                  aliases=("reason", "movement_type", "transfer_reason", "سبب النقل"),
                  domain=("ADMISSION", "TRANSFER", "ESCALATION", "STEPDOWN", "DISCHARGE",
                          "OUTLIER", "OTHER")),
    ),
    chronology=(ChronologyRule("in_at", "out_at"),),
    notes="Consecutive rows per encounter must be contiguous; gaps are flagged.",
)


# ---------------------------------------------------------------------
# orders (lab / radiology / consults)
# ---------------------------------------------------------------------
ORDERS = DatasetSpec(
    key="orders",
    title_en="Diagnostic orders & consultations",
    title_ar="الطلبات التشخيصية والاستشارات",
    natural_key=("encounter_no", "order_ref"),
    references_encounter=True,
    fields=(
        FieldSpec("encounter_no", "string", required=True, aliases=("visit_no", "رقم الزيارة")),
        FieldSpec("order_ref", "string", required=True,
                  aliases=("order_no", "order_id", "accession", "accession_no", "رقم الطلب")),
        FieldSpec("domain", "string", required=True,
                  aliases=("order_type", "category", "service_type", "نوع الطلب"),
                  domain=("LAB", "RADIOLOGY", "CONSULT", "PROCEDURE")),
        FieldSpec("order_code", "string", aliases=("test_code", "procedure_code", "loinc")),
        FieldSpec("order_name", "string", aliases=("test_name", "description", "اسم الفحص")),
        FieldSpec("modality", "string", aliases=("imaging_modality", "exam_type"),
                  domain=("CT", "MRI", "XR", "US", "NM", "MG", "FL", "OTHER")),
        FieldSpec("is_stat", "boolean", aliases=("stat", "urgent", "priority"), domain=_YES_NO),
        FieldSpec("ordered_at", "datetime", required=True,
                  aliases=("order_time", "requested_at", "وقت الطلب")),
        FieldSpec("collected_at", "datetime",
                  aliases=("collection_time", "specimen_collected", "وقت السحب")),
        FieldSpec("performed_at", "datetime", aliases=("exam_time", "performed_time")),
        FieldSpec("resulted_at", "datetime",
                  aliases=("result_time", "verified_at", "report_time", "وقت النتيجة")),
        FieldSpec("acknowledged_at", "datetime", aliases=("ack_time", "reviewed_at")),
        FieldSpec("responding_specialty", "string", aliases=("consultant_specialty", "التخصص")),
    ),
    chronology=(
        ChronologyRule("ordered_at", "collected_at"),
        ChronologyRule("collected_at", "resulted_at"),
        ChronologyRule("ordered_at", "resulted_at"),
        ChronologyRule("resulted_at", "acknowledged_at"),
    ),
)


# ---------------------------------------------------------------------
# safety_events
# ---------------------------------------------------------------------
SAFETY_EVENTS = DatasetSpec(
    key="safety_events",
    title_en="Patient safety & quality events",
    title_ar="حوادث سلامة المرضى",
    natural_key=("event_ref",),
    fields=(
        FieldSpec("event_ref", "string", required=True,
                  aliases=("event_no", "incident_no", "occurrence_id", "رقم الحادثة")),
        FieldSpec("encounter_no", "string", aliases=("visit_no", "رقم الزيارة")),
        FieldSpec("unit_code", "string", aliases=("unit", "ward", "location", "القسم")),
        FieldSpec("kind", "string", required=True,
                  aliases=("event_type", "incident_type", "category", "نوع الحادثة"),
                  domain=("FALL", "PRESSURE_INJURY", "MEDICATION_ERROR", "HAI_CLABSI",
                          "HAI_CAUTI", "HAI_VAP", "HAI_SSI", "CODE_BLUE", "RRT_ACTIVATION",
                          "SEPSIS_ALERT", "RETURN_TO_OR", "WRONG_SITE",
                          "TRANSFUSION_REACTION", "OTHER")),
        FieldSpec("occurred_at", "datetime", required=True,
                  aliases=("event_time", "incident_date", "occurrence_time", "وقت الحادثة")),
        FieldSpec("harm", "string", aliases=("harm_level", "severity", "درجة الضرر"),
                  domain=("NO_HARM", "MILD", "MODERATE", "SEVERE", "DEATH")),
        FieldSpec("present_on_admission", "boolean",
                  aliases=("poa", "on_admission", "community_acquired"), domain=_YES_NO,
                  description="Separates hospital-acquired harm from imported harm."),
        FieldSpec("pressure_injury_stage", "string", aliases=("stage", "pi_stage"),
                  domain=("I", "II", "III", "IV", "UNSTAGEABLE", "DTI")),
        FieldSpec("medication_error_stage", "string", aliases=("error_stage", "process_step"),
                  domain=("PRESCRIBING", "TRANSCRIBING", "DISPENSING", "ADMINISTRATION",
                          "MONITORING")),
        FieldSpec("is_sentinel", "boolean", aliases=("sentinel", "sentinel_event"), domain=_YES_NO),
    ),
)


# ---------------------------------------------------------------------
# staffing
# ---------------------------------------------------------------------
STAFFING = DatasetSpec(
    key="staffing",
    title_en="Nursing staffing & workforce",
    title_ar="التوظيف التمريضي",
    natural_key=("unit_code", "service_date", "shift"),
    fields=(
        FieldSpec("unit_code", "string", required=True, aliases=("unit", "ward", "cost_centre",
                                                                 "القسم")),
        FieldSpec("service_date", "date", required=True,
                  aliases=("date", "roster_date", "shift_date", "التاريخ")),
        FieldSpec("shift", "string", aliases=("shift_name", "الوردية"),
                  domain=("DAY", "NIGHT", "EVENING", "ALL")),
        FieldSpec("rn_productive_hours", "number", required=True,
                  aliases=("rn_hours", "registered_nurse_hours", "ساعات التمريض"), minimum=0),
        FieldSpec("lpn_productive_hours", "number", aliases=("lpn_hours", "en_hours"), minimum=0),
        FieldSpec("na_productive_hours", "number",
                  aliases=("na_hours", "nursing_assistant_hours", "hca_hours"), minimum=0),
        FieldSpec("non_productive_hours", "number",
                  aliases=("non_productive", "training_hours", "meeting_hours"), minimum=0),
        FieldSpec("overtime_hours", "number", aliases=("ot_hours", "overtime", "ساعات إضافية"),
                  minimum=0),
        FieldSpec("agency_hours", "number", aliases=("agency", "contract_hours"), minimum=0),
        FieldSpec("sick_leave_hours", "number", aliases=("sick_hours", "sick_leave",
                                                         "إجازة مرضية"), minimum=0),
        FieldSpec("scheduled_hours", "number", aliases=("rostered_hours", "planned_hours"),
                  minimum=0),
        FieldSpec("budgeted_fte", "number", aliases=("budget_fte", "approved_fte"), minimum=0),
        FieldSpec("filled_fte", "number", aliases=("actual_fte", "current_fte"), minimum=0),
        FieldSpec("separations", "integer", aliases=("leavers", "terminations", "resignations"),
                  minimum=0),
        FieldSpec("headcount", "integer", aliases=("staff_count", "total_staff"), minimum=0),
        FieldSpec("patient_days", "number", aliases=("census", "midnight_census"), minimum=0,
                  description="Optional; derived from bed movements when omitted."),
    ),
)


# ---------------------------------------------------------------------
# units (reference data)
# ---------------------------------------------------------------------
UNITS = DatasetSpec(
    key="units",
    title_en="Units & bed capacity (reference)",
    title_ar="الأقسام وسعة الأسرة",
    natural_key=("unit_code",),
    fields=(
        FieldSpec("unit_code", "string", required=True, aliases=("code", "unit", "ward_code",
                                                                 "رمز القسم")),
        FieldSpec("name_en", "string", required=True, aliases=("unit_name", "name", "ward_name")),
        FieldSpec("name_ar", "string", aliases=("arabic_name", "الاسم العربي")),
        FieldSpec("kind", "string", required=True, aliases=("unit_type", "type", "category"),
                  domain=("ED", "ICU", "HDU", "WARD", "OR", "PACU", "OPD", "DAYCASE", "LDR",
                          "NICU", "DIALYSIS")),
        FieldSpec("specialty", "string", aliases=("service", "التخصص")),
        FieldSpec("physical_beds", "integer", aliases=("beds", "total_beds", "عدد الأسرة"),
                  minimum=0),
        FieldSpec("staffed_beds", "integer", required=True,
                  aliases=("open_beds", "operational_beds", "funded_beds", "الأسرة المشغلة"),
                  minimum=0,
                  description="Capacity denominator for occupancy. Not the licensed count."),
        FieldSpec("target_occupancy", "number", aliases=("occupancy_target",),
                  minimum=0, maximum=100),
    ),
)


# ---------------------------------------------------------------------
# vitals (feeds NEWS2 early warning)
# ---------------------------------------------------------------------
VITALS = DatasetSpec(
    key="vitals",
    title_en="Vital signs (early warning score input)",
    title_ar="العلامات الحيوية",
    natural_key=("encounter_no", "recorded_at"),
    references_encounter=True,
    fields=(
        FieldSpec("encounter_no", "string", required=True, aliases=("visit_no",)),
        FieldSpec("recorded_at", "datetime", required=True,
                  aliases=("observation_time", "vitals_time", "وقت القياس")),
        FieldSpec("respiratory_rate", "integer", aliases=("rr", "resp_rate"), minimum=0, maximum=80),
        FieldSpec("spo2", "integer", aliases=("oxygen_saturation", "sat", "o2_sat"),
                  minimum=0, maximum=100),
        FieldSpec("on_oxygen", "boolean", aliases=("supplemental_oxygen", "o2"), domain=_YES_NO),
        FieldSpec("systolic_bp", "integer", aliases=("sbp", "systolic"), minimum=0, maximum=300),
        FieldSpec("heart_rate", "integer", aliases=("hr", "pulse"), minimum=0, maximum=300),
        FieldSpec("temperature_c", "number", aliases=("temp", "temperature"),
                  minimum=25, maximum=45),
        FieldSpec("consciousness", "string", aliases=("acvpu", "avpu", "loc"),
                  domain=("A", "C", "V", "P", "U")),
    ),
)


# ---------------------------------------------------------------------
# or_cases
# ---------------------------------------------------------------------
OR_CASES = DatasetSpec(
    key="or_cases",
    title_en="Operating room cases",
    title_ar="عمليات غرف العمليات",
    natural_key=("encounter_no", "case_ref"),
    references_encounter=True,
    fields=(
        FieldSpec("encounter_no", "string", required=True, aliases=("visit_no",)),
        FieldSpec("case_ref", "string", required=True, aliases=("case_no", "surgery_no",
                                                                "رقم العملية")),
        FieldSpec("theatre_code", "string", aliases=("theatre", "or_room", "room", "غرفة العمليات")),
        FieldSpec("procedure_code", "string", aliases=("cpt", "procedure")),
        FieldSpec("specialty", "string", aliases=("surgical_specialty", "service")),
        FieldSpec("is_emergency", "boolean", aliases=("emergency", "urgent"), domain=_YES_NO),
        FieldSpec("scheduled_start_at", "datetime", aliases=("scheduled_time", "booked_time")),
        FieldSpec("holding_at", "datetime", aliases=("holding_time", "pre_op_time")),
        FieldSpec("wheels_in_at", "datetime", aliases=("wheels_in", "in_room_time")),
        FieldSpec("anesthesia_start_at", "datetime", aliases=("anesthesia_start", "anes_start")),
        FieldSpec("incision_at", "datetime", aliases=("incision_time", "knife_to_skin",
                                                      "surgery_start")),
        FieldSpec("closure_at", "datetime", aliases=("closure_time", "surgery_end")),
        FieldSpec("wheels_out_at", "datetime", aliases=("wheels_out", "out_room_time")),
        FieldSpec("pacu_in_at", "datetime", aliases=("pacu_in", "recovery_in")),
        FieldSpec("pacu_out_at", "datetime", aliases=("pacu_out", "recovery_out")),
        FieldSpec("is_cancelled", "boolean", aliases=("cancelled", "case_cancelled"), domain=_YES_NO),
        FieldSpec("cancellation_reason", "string", aliases=("cancel_reason", "سبب الإلغاء")),
    ),
    chronology=(
        ChronologyRule("wheels_in_at", "anesthesia_start_at"),
        ChronologyRule("anesthesia_start_at", "incision_at"),
        ChronologyRule("incision_at", "closure_at"),
        ChronologyRule("closure_at", "wheels_out_at"),
        ChronologyRule("wheels_out_at", "pacu_in_at"),
        ChronologyRule("pacu_in_at", "pacu_out_at"),
    ),
)


# ---------------------------------------------------------------------
# icu_stays
# ---------------------------------------------------------------------
ICU_STAYS = DatasetSpec(
    key="icu_stays",
    title_en="Intensive care stays",
    title_ar="إقامات العناية المركزة",
    natural_key=("encounter_no", "admit_at"),
    references_encounter=True,
    fields=(
        FieldSpec("encounter_no", "string", required=True, aliases=("visit_no",)),
        FieldSpec("unit_code", "string", required=True, aliases=("icu_unit", "unit", "ward")),
        FieldSpec("admit_at", "datetime", required=True,
                  aliases=("icu_admission", "icu_admit_time", "دخول العناية")),
        FieldSpec("discharge_at", "datetime",
                  aliases=("icu_discharge", "icu_discharge_time", "خروج العناية")),
        FieldSpec("apache_ii", "integer", aliases=("apache", "apache_score"), minimum=0, maximum=71),
        FieldSpec("ventilated_hours", "number", aliases=("vent_hours", "mv_hours"), minimum=0),
        FieldSpec("outcome", "string", aliases=("icu_outcome", "result"),
                  domain=("SURVIVED", "DIED", "TRANSFERRED")),
    ),
    chronology=(ChronologyRule("admit_at", "discharge_at"),),
)


# ---------------------------------------------------------------------
# patient_experience
# ---------------------------------------------------------------------
PATIENT_EXPERIENCE = DatasetSpec(
    key="patient_experience",
    title_en="Patient experience surveys",
    title_ar="استبيانات تجربة المريض",
    natural_key=("survey_ref",),
    fields=(
        FieldSpec("survey_ref", "string", required=True, aliases=("survey_no", "response_id")),
        FieldSpec("encounter_no", "string", aliases=("visit_no",)),
        FieldSpec("unit_code", "string", aliases=("unit", "ward")),
        FieldSpec("surveyed_at", "datetime", required=True,
                  aliases=("survey_date", "response_date", "تاريخ الاستبيان")),
        FieldSpec("overall_rating", "integer", aliases=("rating", "overall_score"),
                  minimum=0, maximum=10),
        FieldSpec("would_recommend", "integer", aliases=("nps", "recommend_score"),
                  minimum=0, maximum=10),
    ),
)


DATASETS: dict[str, DatasetSpec] = {
    spec.key: spec
    for spec in (
        UNITS, ENCOUNTERS, ED_VISITS, BED_MOVEMENTS, ORDERS, SAFETY_EVENTS,
        STAFFING, VITALS, OR_CASES, ICU_STAYS, PATIENT_EXPERIENCE,
    )
}

#: Load order matters: reference data first, then the encounter spine, then
#: everything that points at an encounter.
LOAD_ORDER: tuple[str, ...] = (
    "units", "encounters", "ed_visits", "bed_movements", "orders",
    "icu_stays", "or_cases", "vitals", "safety_events", "staffing",
    "patient_experience",
)


def get_dataset(key: str) -> DatasetSpec:
    try:
        return DATASETS[key]
    except KeyError:
        raise KeyError(
            f"Unknown dataset '{key}'. Known datasets: {', '.join(sorted(DATASETS))}"
        ) from None
