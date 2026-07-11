"""AI scoring interface (CLAUDE.md §6) — stub implementation for the MVP.

The interface is stable: callers MUST NOT change when the stub body is later
replaced by the real model (fine-tuned Whisper/wav2vec2 + GOP scoring).
"""

import hashlib

#: Letters that typically develop late and score lower (§6/§7).
HARD_LETTERS = frozenset({"ر", "ص", "ض", "ط", "ق"})

#: Allowed error_type values, fixed by the §6 interface contract.
ERROR_TYPES = frozenset(
    {"lateralization", "substitution", "omission", "distortion"}
)

#: Typical Arabic error pattern per letter (§7), folded into the §6 value set:
#: fronting/substitution processes → substitution; de-emphasis → distortion.
_ERROR_BY_LETTER = {
    "ر": "lateralization",  # ر→ل
    "س": "substitution",  # س→ث interdentalization
    "ش": "substitution",
    "ك": "substitution",  # ك→ت fronting
    "ق": "substitution",  # ق→ك fronting
    "غ": "substitution",  # غ→خ
    "ث": "substitution",  # stopping
    "ذ": "substitution",  # stopping
    "ج": "substitution",
    "ص": "distortion",  # de-emphasis ص→س
    "ط": "distortion",  # de-emphasis ط→ت
    "ض": "distortion",
    "ظ": "distortion",
}

_GOOD_THRESHOLD = 70


class ScoringService:
    def score_utterance(
        self, audio_path: str, target_phoneme: str, position: str
    ) -> dict:
        """Score one recorded utterance for a target phoneme.

        Returns:
        {
          "phoneme": "ر",
          "position": "initial",
          "gop_score": 0-100,        # goodness of pronunciation
          "error_type": None | "lateralization" | "substitution" | "omission" | "distortion",
          "confidence": 0.0-1.0
        }

        Stub behaviour: plausible and deterministic per (phoneme, position) —
        derived from a sha256 digest, NOT Python's per-process-salted hash() —
        with hard letters (ر ص ض ط ق) biased lower. audio_path is accepted for
        interface stability and ignored until the real model lands.
        """
        digest = hashlib.sha256(
            f"{target_phoneme}:{position}".encode()
        ).digest()

        base = 62 + digest[0] % 31  # easy letters: 62–92
        if target_phoneme in HARD_LETTERS:
            base -= 25  # hard letters: 37–67, always below threshold

        gop_score = max(0, min(100, base))

        error_type = None
        if gop_score < _GOOD_THRESHOLD:
            if position == "final" and digest[1] % 3 == 0:
                error_type = "omission"  # final-consonant deletion (§7)
            else:
                error_type = _ERROR_BY_LETTER.get(target_phoneme, "distortion")

        confidence = round(0.75 + (digest[2] / 255) * 0.23, 2)

        return {
            "phoneme": target_phoneme,
            "position": position,
            "gop_score": gop_score,
            "error_type": error_type,
            "confidence": confidence,
        }
