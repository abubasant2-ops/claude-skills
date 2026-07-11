import '../models/score_result.dart';

/// Seam between screens and the scoring backend. The API implementation
/// lives in api_scoring_client.dart; tests inject fakes.
abstract class ScoringClient {
  Future<ScoreResult> scoreUtterance({
    required String audioPath,
    required String targetPhoneme,
    required String position,
  });
}
