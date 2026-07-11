"""Auto-generated therapy plans (CLAUDE.md Phase C, ranking rules from §7).

Takes a child's phoneme_profiles time-series, picks the 3 best therapy
targets, and persists a draft treatment plan authored by "ai" for SLP review.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PhonemeProfile, TreatmentPlan
from app.models.enums import PlanAuthor, PlanStatus

GOOD_THRESHOLD = 70
TARGET_GOP = 85  # discharge criterion (blueprint §11.3)
PLAN_SIZE = 3
BLOCK_WEEKS = 12  # standard therapy block (blueprint §11.3)

#: §7 developmental order — earlier tier = easier = preferred first target.
#: In-tier order is kept for tie-breaking. ق is absent from the §7 line;
#: it sits in the middle tier per the §11.1 acquisition bands (emerging
#: 3.5–5y alongside ش س ز).
DEVELOPMENTAL_TIERS: list[list[str]] = [
    ["ك", "ل", "ج"],
    ["ش", "س", "ز", "ق"],
    ["ر", "ص", "ض", "ط", "ظ", "ذ", "ث", "غ"],
]

_POSITION_ORDER = {"initial": 0, "medial": 1, "final": 2}

_POSITION_AR = {
    "initial": "بداية الكلمة",
    "medial": "وسط الكلمة",
    "final": "نهاية الكلمة",
}

_ARABIC_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def _to_arabic_digits(value: int) -> str:
    return str(value).translate(_ARABIC_DIGITS)


def _tier_and_index(phoneme: str) -> tuple[int, int]:
    for tier_idx, tier in enumerate(DEVELOPMENTAL_TIERS):
        if phoneme in tier:
            return tier_idx, tier.index(phoneme)
    return len(DEVELOPMENTAL_TIERS), 0  # unknown letters rank last


class NoTherapyTargetsError(Exception):
    """Child has no phoneme profiles, or none below the therapy threshold."""


@dataclass
class TargetSelection:
    phoneme: str
    positions: list[str]  # failing positions, initial→medial→final
    baseline_gop: int  # mean of latest failing scores (stimulability proxy)
    error_types: list[str]


class PlanGeneratorService:
    def select_targets(
        self, profiles: list[PhonemeProfile]
    ) -> list[TargetSelection]:
        """Rank failing phonemes per §7 and return the top PLAN_SIZE.

        Ordering: developmental tier first (earlier = easier), then higher
        baseline GOP within the tier (closer to correct = more stimulable),
        then the §7 in-tier sequence as a stable tie-break.
        """
        # Latest row wins per (phoneme, position) — profiles are a time-series.
        latest: dict[tuple[str, str], PhonemeProfile] = {}
        for row in sorted(profiles, key=lambda r: r.created_at):
            latest[(row.phoneme, row.position)] = row

        by_phoneme: dict[str, list[PhonemeProfile]] = defaultdict(list)
        for row in latest.values():
            by_phoneme[row.phoneme].append(row)

        candidates: list[tuple[tuple, TargetSelection]] = []
        for phoneme, rows in by_phoneme.items():
            failing = [r for r in rows if r.gop_score < GOOD_THRESHOLD]
            if not failing:
                continue
            baseline = round(sum(r.gop_score for r in failing) / len(failing))
            tier, in_tier = _tier_and_index(phoneme)
            selection = TargetSelection(
                phoneme=phoneme,
                positions=sorted(
                    {r.position for r in failing},
                    key=lambda p: _POSITION_ORDER.get(p, 9),
                ),
                baseline_gop=baseline,
                error_types=sorted(
                    {r.error_type for r in failing if r.error_type}
                ),
            )
            candidates.append(((tier, -baseline, in_tier), selection))

        candidates.sort(key=lambda item: item[0])
        return [selection for _, selection in candidates[:PLAN_SIZE]]

    def generate_for_child(
        self, db: Session, child_id: uuid.UUID
    ) -> TreatmentPlan:
        """Select targets from the child's profiles and persist a draft plan."""
        profiles = list(
            db.scalars(
                select(PhonemeProfile).where(PhonemeProfile.child_id == child_id)
            )
        )
        if not profiles:
            raise NoTherapyTargetsError(
                "child has no phoneme profiles — run an articulation assessment first"
            )
        targets = self.select_targets(profiles)
        if not targets:
            raise NoTherapyTargetsError(
                f"all phonemes score at or above {GOOD_THRESHOLD} — no therapy targets"
            )

        plan = TreatmentPlan(
            child_id=child_id,
            author=PlanAuthor.AI.value,
            status=PlanStatus.DRAFT.value,  # SLP must review/approve
            target_phonemes=[t.phoneme for t in targets],
            goals=[self._goal_for(t) for t in targets],
        )
        db.add(plan)
        db.commit()
        return plan

    @staticmethod
    def _goal_for(target: TargetSelection) -> dict:
        positions_ar = " و".join(_POSITION_AR[p] for p in target.positions)
        return {
            "phoneme": target.phoneme,
            "positions": target.positions,
            "baseline_gop": target.baseline_gop,
            "target_gop": TARGET_GOP,
            "duration_weeks": BLOCK_WEEKS,
            "error_types": target.error_types,
            "description_ar": (
                f"تحسين نطق صوت «{target.phoneme}» في {positions_ar} "
                f"من {_to_arabic_digits(target.baseline_gop)} "
                f"إلى {_to_arabic_digits(TARGET_GOP)} نقطة "
                f"خلال {_to_arabic_digits(BLOCK_WEEKS)} أسبوعًا"
            ),
        }
