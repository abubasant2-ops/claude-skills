import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../core/api/api_config.dart';
import '../../core/api/utterance_bytes.dart';
import '../models/score_result.dart';
import 'demo_account.dart';
import 'scoring_client.dart';

/// Real scoring path: POST the recorded utterance to the backend, which runs
/// ScoringService and persists the phoneme_profiles row.
class ApiScoringClient implements ScoringClient {
  ApiScoringClient({
    required this._account,
    http.Client? httpClient,
    this.baseUrl = kApiBase,
  }) : _http = httpClient ?? http.Client();

  final DemoAccountRepository _account;
  final http.Client _http;
  final String baseUrl;

  @override
  Future<ScoreResult> scoreUtterance({
    required String audioPath,
    required String targetPhoneme,
    required String position,
  }) async {
    final sessionId = await _account.sessionId();
    final bytes = await readUtteranceBytes(audioPath);

    final request = http.MultipartRequest(
      'POST',
      Uri.parse('$baseUrl/sessions/$sessionId/utterances'),
    )
      ..fields['target_phoneme'] = targetPhoneme
      ..fields['position'] = position
      ..files.add(http.MultipartFile.fromBytes(
        'audio',
        bytes,
        filename: 'utterance.webm',
      ));

    final streamed = await _http.send(request);
    final body = await streamed.stream.bytesToString();
    if (streamed.statusCode != 201) {
      throw ApiException('utterance scoring failed (${streamed.statusCode})');
    }
    return ScoreResult.fromJson(jsonDecode(body) as Map<String, dynamic>);
  }

  @override
  Future<void> logPractice({
    required String stimulusId,
    required int durationSec,
    required ScoreResult result,
  }) async {
    try {
      final childId = await _account.childId();
      await _http.post(
        Uri.parse('$baseUrl/sessions'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'child_id': childId,
          'duration_sec': durationSec,
          'activity_ids': [stimulusId],
          'scores_json': {
            'phoneme': result.phoneme,
            'position': result.position,
            'gop_score': result.gopScore,
          },
        }),
      );
    } catch (_) {
      // Best-effort telemetry — never interrupt the child's flow.
    }
  }
}
