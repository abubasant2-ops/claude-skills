import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../core/api/api_config.dart';
import '../models/screening.dart';
import 'demo_account.dart';

/// Seam for the screening flow; tests inject fakes.
abstract class ScreeningApiClient {
  Future<ScreeningQuestionnaire> fetchQuestionnaire();

  Future<ScreeningResult> submit({
    required Map<String, bool> redFlagAnswers,
    required List<String> vocabularyChecked,
    int? intelligibility,
  });
}

class HttpScreeningApiClient implements ScreeningApiClient {
  HttpScreeningApiClient({
    required this._account,
    http.Client? httpClient,
    this.baseUrl = kApiBase,
  }) : _http = httpClient ?? http.Client();

  final DemoAccountRepository _account;
  final http.Client _http;
  final String baseUrl;

  @override
  Future<ScreeningQuestionnaire> fetchQuestionnaire() async {
    final childId = await _account.childId();
    final resp = await _http.get(
      Uri.parse('$baseUrl/children/$childId/screening/questionnaire'),
    );
    if (resp.statusCode != 200) {
      throw ApiException('questionnaire failed (${resp.statusCode})');
    }
    return ScreeningQuestionnaire.fromJson(
      jsonDecode(resp.body) as Map<String, dynamic>,
    );
  }

  @override
  Future<ScreeningResult> submit({
    required Map<String, bool> redFlagAnswers,
    required List<String> vocabularyChecked,
    int? intelligibility,
  }) async {
    final childId = await _account.childId();
    final resp = await _http.post(
      Uri.parse('$baseUrl/children/$childId/screening'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'red_flag_answers': redFlagAnswers,
        'vocabulary_checked': vocabularyChecked,
        'intelligibility': intelligibility,
      }),
    );
    if (resp.statusCode != 201) {
      throw ApiException('screening submit failed (${resp.statusCode})');
    }
    return ScreeningResult.fromJson(
      jsonDecode(resp.body) as Map<String, dynamic>,
    );
  }
}
