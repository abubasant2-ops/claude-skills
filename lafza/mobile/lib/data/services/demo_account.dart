import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../core/api/api_config.dart';

/// DEV bootstrap shared by every API client: creates ONE throwaway
/// parent → child → session on first use so all features talk about the
/// same child. Goes away when auth + child profiles land; the consent flag
/// mirrors the in-app guardian-consent gate.
class DemoAccountRepository {
  DemoAccountRepository({http.Client? httpClient, this.baseUrl = kApiBase})
      : _http = httpClient ?? http.Client();

  final http.Client _http;
  final String baseUrl;

  String? _childId;
  String? _sessionId;
  Future<void>? _bootstrap;

  Future<String> childId() async {
    await (_bootstrap ??= _createAccount());
    return _childId!;
  }

  Future<String> sessionId() async {
    await (_bootstrap ??= _createAccount());
    return _sessionId!;
  }

  Future<void> _createAccount() async {
    final user = await _post('/users', {
      'role': 'parent',
      'phone': '+9665demo${DateTime.now().millisecondsSinceEpoch}',
      'password': 'demo-pass-123',
    });
    final child = await _post('/children', {
      'guardian_id': user['id'],
      'dob': '2020-01-01',
      'sex': 'male',
      'consent_flags': {'audio_capture': true},
    });
    final session = await _post('/sessions', {'child_id': child['id']});
    _childId = child['id'] as String;
    _sessionId = session['id'] as String;
  }

  Future<Map<String, dynamic>> _post(
      String path, Map<String, dynamic> body) async {
    final resp = await _http.post(
      Uri.parse('$baseUrl$path'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );
    if (resp.statusCode != 201) {
      throw ApiException('POST $path failed (${resp.statusCode})');
    }
    return jsonDecode(resp.body) as Map<String, dynamic>;
  }
}

class ApiException implements Exception {
  ApiException(this.message);

  final String message;

  @override
  String toString() => 'ApiException: $message';
}
