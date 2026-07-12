import '../models/score_result.dart';

/// Seam between screens and the scoring backend. The API implementation
/// lives in api_scoring_client.dart; tests inject fakes.
abstract class ScoringClient {
  Future<ScoreResult> scoreUtterance({
    required String audioPath,
    required String targetPhoneme,
    required String position,
  });

  /// Log a completed practice attempt (duration + score) as a session row —
  /// feeds the parent dashboard's weekly minutes. Best-effort: failures are
  /// swallowed by implementations, never surfaced to the child.
  Future<void> logPractice({
    required String stimulusId,
    required int durationSec,
    required ScoreResult result,
  });
}
