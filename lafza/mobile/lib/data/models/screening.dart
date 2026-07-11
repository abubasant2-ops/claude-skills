/// Screening instrument + result (GET/POST /children/{id}/screening*).
class ScreeningQuestionnaire {
  const ScreeningQuestionnaire({
    required this.instrumentVersion,
    required this.ageMonths,
    required this.redFlagQuestions,
    required this.vocabularyWords,
    required this.intelligibilityOptions,
  });

  factory ScreeningQuestionnaire.fromJson(Map<String, dynamic> json) =>
      ScreeningQuestionnaire(
        instrumentVersion: json['instrument_version'] as String,
        ageMonths: json['age_months'] as int,
        redFlagQuestions: [
          for (final q in json['red_flag_questions'] as List)
            RedFlagQuestion.fromJson(q as Map<String, dynamic>),
        ],
        vocabularyWords: [
          for (final w in json['vocabulary_words'] as List) w as String,
        ],
        intelligibilityOptions: [
          for (final o in json['intelligibility_options'] as List)
            IntelligibilityOption.fromJson(o as Map<String, dynamic>),
        ],
      );

  final String instrumentVersion;
  final int ageMonths;
  final List<RedFlagQuestion> redFlagQuestions;
  final List<String> vocabularyWords;
  final List<IntelligibilityOption> intelligibilityOptions;
}

class RedFlagQuestion {
  const RedFlagQuestion({required this.id, required this.textAr});

  factory RedFlagQuestion.fromJson(Map<String, dynamic> json) =>
      RedFlagQuestion(
        id: json['id'] as String,
        textAr: json['text_ar'] as String,
      );

  final String id;
  final String textAr;
}

class IntelligibilityOption {
  const IntelligibilityOption({required this.value, required this.textAr});

  factory IntelligibilityOption.fromJson(Map<String, dynamic> json) =>
      IntelligibilityOption(
        value: json['value'] as int,
        textAr: json['text_ar'] as String,
      );

  final int value;
  final String textAr;
}

class ScreeningResult {
  const ScreeningResult({
    required this.severity,
    required this.redFlags,
    required this.trafficLight,
    required this.referImmediately,
    required this.recommendationAr,
  });

  factory ScreeningResult.fromJson(Map<String, dynamic> json) =>
      ScreeningResult(
        severity: json['severity'] as int,
        redFlags: [for (final f in json['red_flags'] as List) f as String],
        trafficLight: json['traffic_light'] as String,
        referImmediately: json['refer_immediately'] as bool,
        recommendationAr: json['recommendation_ar'] as String,
      );

  final int severity; // 0–4
  final List<String> redFlags;
  final String trafficLight; // green | amber | red
  final bool referImmediately;
  final String recommendationAr;
}
