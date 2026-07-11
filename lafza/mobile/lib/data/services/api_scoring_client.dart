import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../core/api/utterance_bytes.dart';
import '../models/score_result.dart';
import 'scoring_client.dart';

/// Base URL of the FastAPI backend. Override at build time:
/// flutter build web --dart-define=LAFZA_API_BASE=https://api.example/api/v1
/// (Android emulator needs http://10.0.2.2:8000/api/v1.)
const String kApiBase = String.fromEnvironment(
  'LAFZA_API_BASE',
  defaultValue: 'http://127.0.0.1:8000/api/v1',
);

/// Real scoring path: POST the recorded utterance to the backend, which runs
/// ScoringService and persists the phoneme_profiles row.
class ApiScoringClient implements ScoringClient {
  ApiScoringClient({http.Client? httpClient, this._baseUrl = kApiBase})
      : _http = httpClient ?? http.Client();

  final http.Client _http;
  final String _baseUrl;

  /// DEV bootstrap: creates a throwaway parent → child → session on first
  /// use so the utterance endpoint has a session to hang off. Goes away when
  /// auth + child profiles land (Phase D); consent flag mirrors the in-app
  /// guardian-consent gate.
  String? _sessionId;

  Future<String> _ensureSession() async {
    if (_sessionId != null) return _sessionId!;

    final userResp = await _post('/users', {
      'role': 'parent',
      'phone': '+9665demo${DateTime.now().millisecondsSinceEpoch}',
      'password': 'demo-pass-123',
    });
    final childResp = await _post('/children', {
      'guardian_id': userResp['id'],
      'dob': '2020-01-01',
      'sex': 'male',
      'consent_flags': {'audio_capture': true},
    });
    final sessionResp = await _post('/sessions', {
      'child_id': childResp['id'],
    });
    return _sessionId = sessionResp['id'] as String;
  }

  Future<Map<String, dynamic>> _post(
      String path, Map<String, dynamic> body) async {
    final resp = await _http.post(
      Uri.parse('$_baseUrl$path'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );
    if (resp.statusCode != 201) {
      throw ScoringApiException('POST $path failed (${resp.statusCode})');
    }
    return jsonDecode(resp.body) as Map<String, dynamic>;
  }

  @override
  Future<ScoreResult> scoreUtterance({
    required String audioPath,
    required String targetPhoneme,
    required String position,
  }) async {
    final sessionId = await _ensureSession();
    final bytes = await readUtteranceBytes(audioPath);

    final request = http.MultipartRequest(
      'POST',
      Uri.parse('$_baseUrl/sessions/$sessionId/utterances'),
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
      throw ScoringApiException(
          'utterance scoring failed (${streamed.statusCode})');
    }
    return ScoreResult.fromJson(jsonDecode(body) as Map<String, dynamic>);
  }
}

class ScoringApiException implements Exception {
  ScoringApiException(this.message);

  final String message;

  @override
  String toString() => 'ScoringApiException: $message';
}
