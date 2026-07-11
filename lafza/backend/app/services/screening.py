"""Parent screening instrument (MVP): red flags + vocabulary checklist +
intelligibility rating (blueprint §11.1–§11.2).

Deterministic scoring — algorithm over AI. The instrument is versioned so
stored assessments stay interpretable when questions evolve.
"""

from datetime import date

INSTRUMENT_VERSION = "screening-v1"

#: Red-flag rules per §11.1. flag_on: which answer raises the flag.
#: immediate=True → refer immediately regardless of anything else.
RED_FLAG_QUESTIONS: list[dict] = [
    {
        "id": "no_single_words",
        "text_ar": "هل ينطق طفلك كلمات مفردة مفهومة (مثل: ماما، بابا)؟",
        "min_age_months": 18,
        "flag_on": "no",
        "flag": "no_words_by_18m",
        "immediate": False,
    },
    {
        "id": "under_50_words",
        "text_ar": "هل يقول طفلك خمسين كلمة مختلفة على الأقل؟",
        "min_age_months": 24,
        "flag_on": "no",
        "flag": "under_50_words_by_24m",
        "immediate": False,
    },
    {
        "id": "no_two_word_combos",
        "text_ar": "هل يجمع طفلك كلمتين في جملة (مثل: أبغى ماء)؟",
        "min_age_months": 24,
        "flag_on": "no",
        "flag": "no_two_word_combos_by_24m",
        "immediate": False,
    },
    {
        "id": "unintelligible_to_strangers",
        "text_ar": "هل يفهم الغرباءُ كلامَ طفلك في أغلب الأحيان؟",
        "min_age_months": 48,
        "flag_on": "no",
        "flag": "unintelligible_at_4y",
        "immediate": False,
    },
    {
        "id": "regression",
        "text_ar": "هل فقد طفلك كلمات أو مهارات تواصل كان يتقنها سابقًا؟",
        "min_age_months": 0,
        "flag_on": "yes",
        "flag": "regression",
        "immediate": True,
    },
    {
        "id": "hearing_concern",
        "text_ar": "هل لديكم شك في سمع طفلك (لا يلتفت للنداء أو الأصوات)؟",
        "min_age_months": 0,
        "flag_on": "yes",
        "flag": "suspected_hearing_loss",
        "immediate": True,
    },
]

#: Early-vocabulary checklist (ages 12–48 months).
VOCABULARY_WORDS: list[str] = [
    "ماما", "بابا", "ماء", "حليب", "خبز", "تمر", "قطة", "سيارة",
    "كرة", "عين", "يد", "رأس", "فوق", "تحت", "لا", "باي",
]
VOCABULARY_MIN_AGE = 12
VOCABULARY_MAX_AGE = 48
LOW_VOCABULARY_RATIO = 0.25

#: Intelligibility self-rating (from 30 months).
INTELLIGIBILITY_MIN_AGE = 30
INTELLIGIBILITY_OPTIONS = [
    {"value": 4, "text_ar": "كل كلامه تقريبًا"},
    {"value": 3, "text_ar": "معظمه"},
    {"value": 2, "text_ar": "نصفه تقريبًا"},
    {"value": 1, "text_ar": "القليل منه"},
]
LOW_INTELLIGIBILITY = 2

_RECOMMENDATIONS_AR = {
    "green": "لا مؤشرات مقلقة حاليًا. تابعوا التحدث واللعب اللغوي مع طفلكم، وأعيدوا الفحص بعد ستة أشهر.",
    "amber": "توجد مؤشرات تستدعي المتابعة. ابدؤوا البرنامج المنزلي اليومي في التطبيق وأعيدوا الفحص بعد ثلاثة أشهر.",
    "red": "ننصح بتقييم كامل لدى أخصائي نطق ولغة في أقرب وقت. يمكن البدء بالبرنامج المنزلي فورًا إلى حين الموعد.",
}
_REFERRAL_NOTE_AR = "بعض الإجابات تستدعي إحالة عاجلة (سمع/نكوص) — يُرجى مراجعة طبيب الأطفال دون تأخير."


def age_in_months(dob: date, today: date | None = None) -> int:
    today = today or date.today()
    return (today.year - dob.year) * 12 + (today.month - dob.month)


def get_questionnaire(age_months: int) -> dict:
    """The age-relevant slice of the instrument, for the client to render."""
    return {
        "instrument_version": INSTRUMENT_VERSION,
        "age_months": age_months,
        "red_flag_questions": [
            {"id": q["id"], "text_ar": q["text_ar"]}
            for q in RED_FLAG_QUESTIONS
            if age_months >= q["min_age_months"]
        ],
        "vocabulary_words": (
            VOCABULARY_WORDS
            if VOCABULARY_MIN_AGE <= age_months <= VOCABULARY_MAX_AGE
            else []
        ),
        "intelligibility_options": (
            INTELLIGIBILITY_OPTIONS
            if age_months >= INTELLIGIBILITY_MIN_AGE
            else []
        ),
    }


def evaluate_screening(
    age_months: int,
    red_flag_answers: dict[str, bool],
    vocabulary_checked: list[str],
    intelligibility: int | None,
) -> dict:
    """Deterministic severity 0–4 + red flags + traffic light.

    Each raised red flag adds 2; low vocabulary or low intelligibility adds
    1 each; capped at 4. Immediate flags (hearing, regression) force 4.
    """
    flags: list[str] = []
    immediate = False
    for question in RED_FLAG_QUESTIONS:
        if age_months < question["min_age_months"]:
            continue
        answer = red_flag_answers.get(question["id"])
        if answer is None:
            continue
        raised = (not answer) if question["flag_on"] == "no" else answer
        if raised:
            flags.append(question["flag"])
            immediate = immediate or question["immediate"]

    severity = 2 * len(flags)

    vocabulary_ratio = None
    if VOCABULARY_MIN_AGE <= age_months <= VOCABULARY_MAX_AGE:
        vocabulary_ratio = len(vocabulary_checked) / len(VOCABULARY_WORDS)
        if vocabulary_ratio < LOW_VOCABULARY_RATIO:
            severity += 1

    if (
        age_months >= INTELLIGIBILITY_MIN_AGE
        and intelligibility is not None
        and intelligibility <= LOW_INTELLIGIBILITY
    ):
        severity += 1

    severity = min(4, severity)
    if immediate:
        severity = 4

    traffic_light = (
        "green" if severity == 0 else "amber" if severity <= 2 else "red"
    )
    recommendation = _RECOMMENDATIONS_AR[traffic_light]
    if immediate:
        recommendation = f"{_REFERRAL_NOTE_AR} {recommendation}"

    return {
        "instrument_version": INSTRUMENT_VERSION,
        "age_months": age_months,
        "severity": severity,
        "red_flags": flags,
        "traffic_light": traffic_light,
        "refer_immediately": immediate,
        "vocabulary_ratio": vocabulary_ratio,
        "recommendation_ar": recommendation,
    }
