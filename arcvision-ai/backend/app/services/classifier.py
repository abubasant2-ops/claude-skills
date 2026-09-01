"""Initial document classification by extension + lightweight content sniff."""

from __future__ import annotations

import os
from typing import Literal

FileType = Literal["pdf", "ifc", "rvt", "dwg", "boq", "contract", "unknown"]
Discipline = Literal["arch", "struct", "elec", "mech", "plumb", "general", None]  # type: ignore[valid-type]


_EXT_MAP: dict[str, FileType] = {
    ".pdf": "pdf",
    ".ifc": "ifc",
    ".rvt": "rvt",
    ".dwg": "dwg",
    ".dxf": "dwg",
    ".xlsx": "boq",
    ".xls": "boq",
    ".csv": "boq",
}


def classify_filetype(filename: str) -> FileType:
    _, ext = os.path.splitext(filename.lower())
    return _EXT_MAP.get(ext, "unknown")


# Keyword heuristics for discipline detection — works for both AR and EN file names.
_DISCIPLINE_KEYWORDS: dict[str, list[str]] = {
    "arch": ["arch", "architectural", "معماري", "معمارية"],
    "struct": ["struct", "structural", "إنشائي", "انشائي", "إنشائية", "rebar", "concrete"],
    "elec": ["elec", "electrical", "كهرباء", "كهربائي"],
    "mech": ["mech", "mechanical", "hvac", "ميكانيكا", "ميكانيكي"],
    "plumb": ["plumb", "sanitary", "سباكة", "صحي"],
    "general": ["contract", "عقد", "boq", "حصر", "كميات"],
}


def classify_discipline(filename: str) -> str | None:
    name = filename.lower()
    for disc, kws in _DISCIPLINE_KEYWORDS.items():
        if any(kw in name for kw in kws):
            return disc
    return None
