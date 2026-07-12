import uuid

from pydantic import BaseModel, Field


class RedFlagQuestionOut(BaseModel):
    id: str
    text_ar: str


class IntelligibilityOptionOut(BaseModel):
    value: int
    text_ar: str


class QuestionnaireOut(BaseModel):
    """Age-relevant slice of the screening instrument."""

    instrument_version: str
    age_months: int
    red_flag_questions: list[RedFlagQuestionOut]
    vocabulary_words: list[str]
    intelligibility_options: list[IntelligibilityOptionOut]


class ScreeningSubmission(BaseModel):
    """Parent answers. red_flag_answers values: true = نعم, false = لا."""

    red_flag_answers: dict[str, bool] = Field(default_factory=dict)
    vocabulary_checked: list[str] = Field(default_factory=list)
    intelligibility: int | None = Field(default=None, ge=1, le=4)


class ScreeningResultOut(BaseModel):
    assessment_id: uuid.UUID
    instrument_version: str
    age_months: int
    severity: int = Field(ge=0, le=4)
    red_flags: list[str]
    traffic_light: str  # green | amber | red
    refer_immediately: bool
    recommendation_ar: str
