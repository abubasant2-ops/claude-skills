"""Constrained value sets for model columns and API schemas.

Stored as strings in the DB with CHECK constraints (see base.enum_check);
these enums are the single source of truth for the allowed values.
"""

import enum


class UserRole(enum.StrEnum):
    PARENT = "parent"
    SLP = "slp"
    ADMIN = "admin"


class Sex(enum.StrEnum):
    MALE = "male"
    FEMALE = "female"


class AssessmentType(enum.StrEnum):
    SCREENING = "screening"
    ARTICULATION = "articulation"


class PhonemePosition(enum.StrEnum):
    INITIAL = "initial"
    MEDIAL = "medial"
    FINAL = "final"


class PlanAuthor(enum.StrEnum):
    AI = "ai"
    SLP = "slp"


class PlanStatus(enum.StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    ACTIVE = "active"


class ActivityLevel(enum.StrEnum):
    WORD = "word"
    PHRASE = "phrase"
    SENTENCE = "sentence"
    STORY = "story"
