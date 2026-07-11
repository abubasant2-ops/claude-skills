import 'dart:math';

/// Client-side mirror of the backend ScoringService stub (CLAUDE.md §6).
/// Same shape, same bias rules, so Phase C can swap in the real API client
/// without changing any caller.
class MockScoringService {
  MockScoringService();

  static const List<String> _hardLetters = ['ر', 'ص', 'ض', 'ط', 'ق'];

  static const Map<String, String> _typicalErrors = {
    'ر': 'lateralization', // ر→ل
    'س': 'interdentalization', // س→ث
    'ك': 'substitution', // ك→ت fronting
    'ق': 'substitution', // ق→ك fronting
    'ص': 'distortion', // de-emphasis ص→س
    'ط': 'distortion', // de-emphasis ط→ت
  };

  int _attempt = 0;

  /// Random-but-consistent per phoneme+position, biased lower for hard
  /// letters — matches the backend stub behaviour.
  ScoreResult scoreUtterance({
    required String targetPhoneme,
    required String position,
    String? audioPath,
  }) {
    final int seed =
        targetPhoneme.hashCode ^ position.hashCode ^ _attempt++;
    final Random random = Random(seed);

    int base = 55 + (targetPhoneme.hashCode + position.hashCode).abs() % 36;
    if (_hardLetters.contains(targetPhoneme)) {
      base -= 20;
    }
    final int score = (base + random.nextInt(9) - 4).clamp(0, 100);

    return ScoreResult(
      phoneme: targetPhoneme,
      position: position,
      gopScore: score,
      errorType:
          score < 60 ? (_typicalErrors[targetPhoneme] ?? 'distortion') : null,
      confidence: 0.78 + random.nextDouble() * 0.19,
    );
  }
}

class ScoreResult {
  const ScoreResult({
    required this.phoneme,
    required this.position,
    required this.gopScore,
    required this.errorType,
    required this.confidence,
  });

  final String phoneme;
  final String position;
  final int gopScore; // 0–100
  final String? errorType;
  final double confidence;

  bool get isGood => gopScore >= 70;
}
