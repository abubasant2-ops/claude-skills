import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../core/api/api_config.dart';
import '../models/parent_summary.dart';
import 'demo_account.dart';

/// Seam for the parent dashboard data; tests inject fakes.
abstract class ParentApiClient {
  Future<ParentSummary> fetchSummary();
}

class HttpParentApiClient implements ParentApiClient {
  HttpParentApiClient({
    required this._account,
    http.Client? httpClient,
    this.baseUrl = kApiBase,
  }) : _http = httpClient ?? http.Client();

  final DemoAccountRepository _account;
  final http.Client _http;
  final String baseUrl;

  @override
  Future<ParentSummary> fetchSummary() async {
    final childId = await _account.childId();
    final resp = await _http
        .get(Uri.parse('$baseUrl/children/$childId/parent-summary'));
    if (resp.statusCode != 200) {
      throw ApiException('parent summary failed (${resp.statusCode})');
    }
    return ParentSummary.fromJson(
        jsonDecode(resp.body) as Map<String, dynamic>);
  }
}
