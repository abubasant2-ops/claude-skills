/// Payload of GET /children/{id}/parent-summary (P1 dashboard + P3 report).
class ParentSummary {
  const ParentSummary({
    required this.streakDays,
    required this.weekPracticeSeconds,
    required this.weekAttempts,
    required this.daily,
    required this.phonemes,
    required this.plan,
  });

  factory ParentSummary.fromJson(Map<String, dynamic> json) => ParentSummary(
        streakDays: json['streak_days'] as int,
        weekPracticeSeconds: json['week_practice_seconds'] as int,
        weekAttempts: json['week_attempts'] as int,
        daily: [
          for (final d in json['daily'] as List)
            DailyPractice.fromJson(d as Map<String, dynamic>),
        ],
        phonemes: [
          for (final p in json['phonemes'] as List)
            PhonemeReportRow.fromJson(p as Map<String, dynamic>),
        ],
        plan: json['plan'] == null
            ? null
            : PlanSummary.fromJson(json['plan'] as Map<String, dynamic>),
      );

  final int streakDays;
  final int weekPracticeSeconds;
  final int weekAttempts;
  final List<DailyPractice> daily; // 7 entries, oldest → today
  final List<PhonemeReportRow> phonemes; // weakest first
  final PlanSummary? plan;
}

class DailyPractice {
  const DailyPractice({required this.day, required this.seconds});

  factory DailyPractice.fromJson(Map<String, dynamic> json) => DailyPractice(
        day: DateTime.parse(json['day'] as String),
        seconds: json['seconds'] as int,
      );

  final DateTime day;
  final int seconds;
}

class PhonemeReportRow {
  const PhonemeReportRow({
    required this.phoneme,
    required this.attempts,
    required this.firstGop,
    required this.latestGop,
    required this.latestErrorType,
  });

  factory PhonemeReportRow.fromJson(Map<String, dynamic> json) =>
      PhonemeReportRow(
        phoneme: json['phoneme'] as String,
        attempts: json['attempts'] as int,
        firstGop: json['first_gop'] as int,
        latestGop: json['latest_gop'] as int,
        latestErrorType: json['latest_error_type'] as String?,
      );

  final String phoneme;
  final int attempts;
  final int firstGop;
  final int latestGop;
  final String? latestErrorType;

  int get delta => latestGop - firstGop;
}

class PlanSummary {
  const PlanSummary({required this.targetPhonemes, required this.status});

  factory PlanSummary.fromJson(Map<String, dynamic> json) => PlanSummary(
        targetPhonemes: [
          for (final p in json['target_phonemes'] as List) p as String,
        ],
        status: json['status'] as String,
      );

  final List<String> targetPhonemes;
  final String status;
}
