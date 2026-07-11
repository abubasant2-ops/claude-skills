/// §6 scoring contract as consumed by the app — same shape the backend
/// ScoringService returns.
class ScoreResult {
  const ScoreResult({
    required this.phoneme,
    required this.position,
    required this.gopScore,
    required this.errorType,
    required this.confidence,
  });

  factory ScoreResult.fromJson(Map<String, dynamic> json) => ScoreResult(
        phoneme: json['phoneme'] as String,
        position: json['position'] as String,
        gopScore: json['gop_score'] as int,
        errorType: json['error_type'] as String?,
        confidence: (json['confidence'] as num).toDouble(),
      );

  final String phoneme;
  final String position;
  final int gopScore; // 0–100
  final String? errorType;
  final double confidence;

  bool get isGood => gopScore >= 70;
}
