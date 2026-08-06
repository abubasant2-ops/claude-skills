"""Metric catalogue: labels, definitions and benchmark thresholds.

Every indicator the platform can compute is declared once here. The
catalogue drives the bilingual tile labels, the red/amber/green banding
and the data dictionary that ships in ``docs/data-dictionary.md``, so a
new metric is added in one place rather than four.

Thresholds are defaults drawn from the standards named in ``source``.
They are starting points for a national tertiary centre, not law -- each
facility overrides them in ``ref_benchmark`` during implementation, which
is why the API always returns the target alongside the value.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    label_en: str
    label_ar: str
    unit: str
    domain: str                       # capacity | ed | journey | quality | nursing | flow
    definition_en: str
    higher_is_better: bool = False
    target: float | None = None
    amber: float | None = None
    red: float | None = None
    source: str = "INTERNAL"
    numerator_en: str = ""
    denominator_en: str = ""


def _m(*args, **kwargs) -> MetricDefinition:
    return MetricDefinition(*args, **kwargs)


CATALOGUE: dict[str, MetricDefinition] = {m.key: m for m in (
    # ---------------- Capacity ----------------
    _m("occupancy_rate", "Bed occupancy rate", "معدل إشغال الأسرة", "%", "capacity",
       "Occupancy-weighted patient days divided by staffed bed days.",
       target=85, amber=90, red=95, source="CBAHI",
       numerator_en="Patient days (fractional)", denominator_en="Staffed bed days"),
    _m("average_daily_census", "Average daily census", "متوسط التعداد اليومي", "patients", "capacity",
       "Total patient days in the period divided by the number of days.",
       higher_is_better=False, source="INTERNAL",
       numerator_en="Patient days", denominator_en="Days in period"),
    _m("alos_days", "Average length of stay", "متوسط مدة الإقامة", "days", "capacity",
       "Inpatient days divided by discharges. Deaths are included; day cases are not.",
       target=4.0, amber=5.0, red=6.0, source="HSTP",
       numerator_en="Inpatient days", denominator_en="Discharges"),
    _m("bed_turnover_rate", "Bed turnover rate", "معدل دوران السرير", "discharges/bed", "capacity",
       "Discharges per staffed bed in the period. Higher means each bed served more patients.",
       higher_is_better=True, source="INTERNAL",
       numerator_en="Discharges", denominator_en="Staffed beds"),
    _m("bed_turnover_interval_hours", "Bed turnover interval", "فترة دوران السرير", "hours", "capacity",
       "Idle hours a bed sits empty between one discharge and the next admission. "
       "A negative value means the unit ran beyond its staffed capacity.",
       target=6, amber=12, red=24, source="INTERNAL",
       numerator_en="Unoccupied bed days x 24", denominator_en="Discharges"),
    _m("admission_rate", "Admission rate", "معدل الدخول", "%", "capacity",
       "Emergency visits ending in admission, as a share of all ED visits.",
       source="INTERNAL", numerator_en="ED admissions", denominator_en="ED visits"),
    _m("discharge_rate", "Discharges per day", "معدل الخروج اليومي", "patients/day", "capacity",
       "Mean discharges per day across the period.", higher_is_better=True),
    _m("transfer_rate", "Internal transfer rate", "معدل النقل الداخلي", "%", "capacity",
       "Encounters with at least one inter-unit transfer, as a share of admissions.",
       target=15, amber=25, red=35),
    _m("mortality_rate", "Hospital mortality rate", "معدل الوفيات", "%", "quality",
       "In-hospital deaths divided by discharges (deaths included in the denominator).",
       target=2.0, amber=3.0, red=4.0, source="CBAHI",
       numerator_en="Deaths", denominator_en="Discharges"),
    _m("icu_mortality_rate", "ICU mortality rate", "معدل وفيات العناية المركزة", "%", "quality",
       "Deaths among ICU stays divided by completed ICU stays.",
       target=12.0, amber=18.0, red=25.0, source="JCI"),
    _m("icu_utilization", "ICU utilisation", "إشغال العناية المركزة", "%", "capacity",
       "Occupancy across all critical-care units.",
       target=80, amber=88, red=95, source="INTERNAL"),

    # ---------------- Emergency department ----------------
    _m("ed_visits", "ED visits", "زيارات الطوارئ", "visits", "ed",
       "Count of emergency department arrivals.", higher_is_better=False),
    _m("door_to_triage_min", "Door-to-triage", "من الوصول إلى الفرز", "min", "ed",
       "Median minutes from ED arrival to completed triage assessment.",
       target=10, amber=15, red=30, source="CBAHI"),
    _m("door_to_physician_min", "Door-to-physician", "من الوصول إلى الطبيب", "min", "ed",
       "Median minutes from ED arrival to first physician contact.",
       target=30, amber=60, red=90, source="CBAHI"),
    _m("door_to_disposition_min", "Door-to-disposition", "من الوصول إلى القرار", "min", "ed",
       "Median minutes from arrival to the documented disposition decision.",
       target=120, amber=180, red=240, source="JCI"),
    _m("ed_los_min", "ED length of stay", "مدة البقاء في الطوارئ", "min", "ed",
       "Median minutes from arrival to physical departure from the ED, "
       "excluding patients who left without being seen.",
       target=240, amber=300, red=360, source="CBAHI"),
    _m("ed_boarding_min", "ED boarding time", "مدة الانتظار للتنويم", "min", "ed",
       "Median minutes from decision-to-admit to leaving the ED for an inpatient bed. "
       "The single most sensitive indicator of hospital-wide flow failure.",
       target=120, amber=240, red=360, source="JCI"),
    _m("lwbs_rate", "Left without being seen", "غادر قبل الفحص", "%", "ed",
       "Visits ending in LWBS as a share of all ED visits.",
       target=1.0, amber=2.0, red=3.0, source="CBAHI"),
    _m("lama_rate", "Left against medical advice", "غادر ضد النصيحة الطبية", "%", "ed",
       "Visits ending in LAMA/DAMA as a share of all ED visits.",
       target=1.0, amber=2.0, red=3.0, source="CBAHI"),
    _m("ed_revisit_72h_rate", "72-hour ED revisits", "العودة خلال 72 ساعة", "%", "ed",
       "Unplanned returns to the ED within 72 hours of a previous ED departure.",
       target=2.0, amber=3.5, red=5.0, source="CBAHI"),
    _m("nedocs_score", "NEDOCS crowding score", "مؤشر ازدحام الطوارئ", "score", "ed",
       "National Emergency Department Overcrowding Scale. Above 100 the department "
       "is overcrowded; above 140 it is severely overcrowded.",
       target=60, amber=100, red=140, source="INTERNAL"),
    _m("ctas_1_2_share", "High-acuity share (CTAS 1-2)", "نسبة الحالات الحرجة", "%", "ed",
       "Share of ED visits triaged CTAS 1 or 2. Context for every timing metric.",
       higher_is_better=False),

    # ---------------- Journey ----------------
    _m("bed_allocation_min", "Bed allocation time", "زمن تخصيص السرير", "min", "journey",
       "Median minutes from bed request to bed assignment.",
       target=60, amber=120, red=180),
    _m("assignment_to_arrival_min", "Assignment to ward arrival", "من التخصيص إلى الوصول", "min", "journey",
       "Median minutes from bed assignment to the patient physically arriving on the ward. "
       "Isolates portering and ward-readiness delays from bed-finding delays.",
       target=45, amber=90, red=150),
    _m("discharge_process_min", "Discharge process duration", "مدة إجراءات الخروج", "min", "journey",
       "Median minutes from discharge order to the patient leaving the bed.",
       target=120, amber=180, red=240),
    _m("discharge_delay_min", "Avoidable discharge delay", "التأخير القابل للتجنب", "min", "journey",
       "Median minutes between being medically ready and actually leaving. Pure waste.",
       target=60, amber=120, red=240),
    _m("lab_tat_min", "Laboratory turnaround", "زمن نتائج المختبر", "min", "journey",
       "Median minutes from specimen collection to verified result.",
       target=60, amber=90, red=120, source="CBAHI"),
    _m("lab_stat_tat_min", "STAT laboratory turnaround", "زمن النتائج العاجلة", "min", "journey",
       "Median minutes from collection to verified result for STAT orders.",
       target=30, amber=45, red=60, source="CBAHI"),
    _m("radiology_tat_min", "Radiology turnaround", "زمن تقارير الأشعة", "min", "journey",
       "Median minutes from order to verified report.",
       target=120, amber=180, red=240, source="CBAHI"),
    _m("consult_response_min", "Consultation response", "زمن الاستجابة للاستشارة", "min", "journey",
       "Median minutes from consult request to the consultant's documented response.",
       target=60, amber=120, red=240, source="JCI"),
    _m("or_first_case_delay_min", "First-case on-time start", "تأخير أول عملية", "min", "journey",
       "Median minutes the day's first theatre case starts after its scheduled time.",
       target=0, amber=15, red=30),
    _m("or_turnover_min", "Theatre turnover", "زمن تجهيز غرفة العمليات", "min", "journey",
       "Median minutes between one case leaving the theatre and the next entering.",
       target=30, amber=45, red=60),

    # ---------------- Quality & safety ----------------
    _m("readmission_30d_rate", "30-day readmission rate", "معدل إعادة الدخول خلال ٣٠ يوم", "%", "quality",
       "Unplanned readmissions within 30 days of a live discharge.",
       target=8.0, amber=11.0, red=14.0, source="CBAHI"),
    _m("hai_rate", "Hospital-acquired infections", "العدوى المكتسبة", "per 1000 patient days", "quality",
       "CLABSI, CAUTI, VAP and SSI events not present on admission, per 1,000 patient days.",
       target=1.0, amber=2.0, red=3.0, source="JCI"),
    _m("fall_rate", "Patient falls", "معدل السقوط", "per 1000 patient days", "quality",
       "All inpatient falls per 1,000 patient days.",
       target=2.0, amber=3.0, red=4.0, source="MAGNET"),
    _m("fall_with_injury_rate", "Falls with injury", "السقوط مع إصابة", "per 1000 patient days", "quality",
       "Falls causing moderate or greater harm, per 1,000 patient days.",
       target=0.5, amber=0.8, red=1.2, source="MAGNET"),
    _m("pressure_injury_rate", "Hospital-acquired pressure injuries", "تقرحات الفراش", "per 1000 patient days", "quality",
       "Stage II and above pressure injuries not present on admission, per 1,000 patient days.",
       target=0.5, amber=1.0, red=2.0, source="MAGNET"),
    _m("medication_error_rate", "Medication errors", "أخطاء الدواء", "per 1000 patient days", "quality",
       "Reported medication errors at any stage, per 1,000 patient days. "
       "A rising rate often signals better reporting culture, not worse safety -- "
       "read it against the harm-weighted rate.",
       target=4.0, amber=8.0, red=12.0, source="JCI"),
    _m("code_blue_rate", "Code blue events", "بلاغات الإنعاش", "per 1000 discharges", "quality",
       "Cardiac arrest team activations per 1,000 discharges.",
       target=1.5, amber=2.5, red=4.0, source="JCI"),
    _m("rrt_activation_rate", "Rapid response activations", "تفعيل فريق الاستجابة السريعة", "per 1000 discharges", "quality",
       "RRT calls per 1,000 discharges. A high RRT-to-code-blue ratio is a good sign: "
       "deterioration is being caught before arrest.",
       higher_is_better=True, source="JCI"),
    _m("sepsis_bundle_1h_rate", "Sepsis 1-hour bundle compliance", "الالتزام بحزمة الإنتان", "%", "quality",
       "Share of recognised sepsis cases with the full 1-hour bundle delivered.",
       higher_is_better=True, target=90, amber=80, red=70, source="JCI"),
    _m("news2_high_rate", "High early-warning scores", "درجات الإنذار المبكر المرتفعة", "%", "quality",
       "Share of vital-sign observations scoring NEWS2 7 or above.",
       target=3.0, amber=5.0, red=8.0),
    _m("patient_satisfaction", "Patient satisfaction", "رضا المرضى", "%", "quality",
       "Mean overall rating converted to a percentage.",
       higher_is_better=True, target=85, amber=80, red=75, source="HSTP"),
    _m("net_promoter_score", "Net promoter score", "مؤشر الترشيح", "NPS", "quality",
       "Promoters (9-10) minus detractors (0-6) as a percentage of respondents.",
       higher_is_better=True, target=50, amber=30, red=10, source="HSTP"),

    # ---------------- Nursing ----------------
    _m("nchpd", "Nursing care hours per patient day", "ساعات الرعاية التمريضية", "hours", "nursing",
       "All productive nursing hours (RN + LPN + NA) divided by patient days.",
       higher_is_better=True, target=6.0, amber=5.0, red=4.0, source="MAGNET"),
    _m("rn_hppd", "RN hours per patient day", "ساعات الممرض المسجل", "hours", "nursing",
       "Registered nurse productive hours divided by patient days.",
       higher_is_better=True, target=4.0, amber=3.2, red=2.5, source="MAGNET"),
    _m("rn_skill_mix", "RN skill mix", "نسبة الممرضين المسجلين", "%", "nursing",
       "RN hours as a share of all nursing hours.",
       higher_is_better=True, target=65, amber=55, red=45, source="MAGNET"),
    _m("nurse_to_patient_ratio", "Patients per nurse", "نسبة المريض للممرض", "patients/RN", "nursing",
       "Mean patients per RN, derived from patient days and RN hours.",
       target=4.0, amber=5.0, red=6.0, source="MAGNET"),
    _m("staffing_utilization", "Staffing utilisation", "معدل استغلال الكادر", "%", "nursing",
       "Productive hours as a share of all paid hours.",
       higher_is_better=True, target=90, amber=85, red=80),
    _m("overtime_rate", "Overtime rate", "معدل العمل الإضافي", "%", "nursing",
       "Overtime hours as a share of productive nursing hours.",
       target=5.0, amber=8.0, red=12.0, source="HSTP"),
    _m("agency_rate", "Agency reliance", "الاعتماد على التعاقد", "%", "nursing",
       "Agency hours as a share of productive nursing hours.",
       target=3.0, amber=6.0, red=10.0),
    _m("sick_leave_rate", "Sick leave rate", "معدل الإجازات المرضية", "%", "nursing",
       "Sick leave hours as a share of scheduled hours.",
       target=2.5, amber=4.0, red=6.0, source="HSTP"),
    _m("vacancy_rate", "Vacancy rate", "معدل الشواغر", "%", "nursing",
       "Unfilled FTE as a share of budgeted FTE.",
       target=5.0, amber=10.0, red=15.0, source="HSTP"),
    _m("turnover_rate", "Turnover rate", "معدل دوران الموظفين", "%", "nursing",
       "Separations as a share of average headcount, annualised.",
       target=10.0, amber=15.0, red=20.0, source="MAGNET"),
)}


def get_definition(key: str) -> MetricDefinition | None:
    return CATALOGUE.get(key)


def make_metric(
    key: str,
    value: float | None,
    *,
    numerator: float | None = None,
    denominator: float | None = None,
    previous: float | None = None,
    overrides: dict[str, dict] | None = None,
    context: dict | None = None,
) -> "MetricValue":
    """Wrap a raw number in its catalogue metadata and RAG status.

    ``overrides`` carries facility-specific thresholds loaded from
    ``ref_benchmark`` so a hospital can retune a target without a code change.
    """
    from app.analytics.common import MetricValue, percent_change, rag_status

    definition = CATALOGUE.get(key)
    if definition is None:
        return MetricValue(key=key, label_en=key, label_ar=key, value=value,
                           numerator=numerator, denominator=denominator,
                           context=context or {})

    target, amber, red = definition.target, definition.amber, definition.red
    higher_is_better = definition.higher_is_better
    if overrides and key in overrides:
        override = overrides[key]
        target = override.get("target_value", target)
        amber = override.get("amber_threshold", amber)
        red = override.get("red_threshold", red)
        higher_is_better = override.get("higher_is_better", higher_is_better)

    return MetricValue(
        key=key,
        label_en=definition.label_en,
        label_ar=definition.label_ar,
        value=value,
        unit=definition.unit,
        numerator=numerator,
        denominator=denominator,
        target=target,
        status=rag_status(value, target=target, amber=amber, red=red,
                          higher_is_better=higher_is_better),
        trend_pct=percent_change(value, previous),
        higher_is_better=higher_is_better,
        context=context or {},
    )


def thresholds(key: str) -> tuple[float | None, float | None, float | None, bool]:
    """``(target, amber, red, higher_is_better)`` for a metric key."""
    definition = CATALOGUE.get(key)
    if definition is None:
        return None, None, None, False
    return definition.target, definition.amber, definition.red, definition.higher_is_better


def catalogue_by_domain(domain: str) -> list[MetricDefinition]:
    return [d for d in CATALOGUE.values() if d.domain == domain]


def seed_rows() -> list[dict]:
    """Rows for ``ref_benchmark``, used by the database seeder."""
    return [
        {
            "metric_key": d.key,
            "scope": "FACILITY",
            "scope_value": None,
            "target_value": d.target,
            "amber_threshold": d.amber,
            "red_threshold": d.red,
            "higher_is_better": d.higher_is_better,
            "source": d.source,
        }
        for d in CATALOGUE.values()
        if d.target is not None or d.amber is not None
    ]
