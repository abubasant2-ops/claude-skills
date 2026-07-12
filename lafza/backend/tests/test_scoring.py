from statistics import mean

from app.services.scoring import ERROR_TYPES, HARD_LETTERS, ScoringService

MVP_LETTERS = ["ر", "س", "ش", "ك", "ق", "ص", "ط", "ث", "ذ", "ج", "غ", "ل"]
POSITIONS = ["initial", "medial", "final"]


def test_contract_shape_for_all_mvp_letters_and_positions():
    service = ScoringService()
    for letter in MVP_LETTERS:
        for position in POSITIONS:
            result = service.score_utterance("dummy.wav", letter, position)
            assert set(result) == {
                "phoneme", "position", "gop_score", "error_type", "confidence",
            }
            assert result["phoneme"] == letter
            assert result["position"] == position
            assert 0 <= result["gop_score"] <= 100
            assert result["error_type"] is None or result["error_type"] in ERROR_TYPES
            assert 0.0 <= result["confidence"] <= 1.0


def test_output_is_consistent_across_calls_and_instances():
    first = ScoringService()
    second = ScoringService()
    for letter in MVP_LETTERS:
        for position in POSITIONS:
            a = first.score_utterance("a.wav", letter, position)
            b = first.score_utterance("b.wav", letter, position)  # repeat call
            c = second.score_utterance("c.wav", letter, position)  # new instance
            assert a == b == c, f"inconsistent output for {letter}/{position}"


def test_hard_letters_score_lower_than_easy_letters():
    service = ScoringService()
    hard = [l for l in MVP_LETTERS if l in HARD_LETTERS]
    easy = [l for l in MVP_LETTERS if l not in HARD_LETTERS]

    def avg(letters):
        return mean(
            service.score_utterance("x.wav", letter, position)["gop_score"]
            for letter in letters
            for position in POSITIONS
        )

    assert avg(hard) < avg(easy)
    # Hard letters are always below the good threshold in the stub.
    for letter in hard:
        for position in POSITIONS:
            assert service.score_utterance("x.wav", letter, position)["gop_score"] < 70


def test_error_type_present_only_when_score_is_low():
    service = ScoringService()
    for letter in MVP_LETTERS:
        for position in POSITIONS:
            result = service.score_utterance("x.wav", letter, position)
            if result["gop_score"] >= 70:
                assert result["error_type"] is None
            else:
                assert result["error_type"] in ERROR_TYPES


def test_typical_arabic_error_patterns():
    service = ScoringService()
    # ر→ل lateralization; de-emphasis distortion for emphatics (§7).
    assert (
        service.score_utterance("x.wav", "ر", "initial")["error_type"]
        == "lateralization"
    )
    for letter in ["ص", "ط"]:
        result = service.score_utterance("x.wav", letter, "initial")
        assert result["error_type"] == "distortion"
    # ق fronting maps to substitution (unless final-position omission fires).
    assert (
        service.score_utterance("x.wav", "ق", "initial")["error_type"]
        == "substitution"
    )
