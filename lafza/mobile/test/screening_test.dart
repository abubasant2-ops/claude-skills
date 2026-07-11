import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:lafza_mobile/core/theme/app_theme.dart';
import 'package:lafza_mobile/data/models/screening.dart';
import 'package:lafza_mobile/data/services/screening_api_client.dart';
import 'package:lafza_mobile/features/parent/screening_screen.dart';

class _FakeScreeningApi implements ScreeningApiClient {
  Map<String, bool>? submittedRedFlags;
  List<String>? submittedVocabulary;
  int? submittedIntelligibility;

  @override
  Future<ScreeningQuestionnaire> fetchQuestionnaire() async =>
      ScreeningQuestionnaire.fromJson({
        'instrument_version': 'screening-v1',
        'age_months': 36,
        'red_flag_questions': [
          {'id': 'no_single_words', 'text_ar': 'هل ينطق طفلك كلمات مفردة مفهومة (مثل: ماما، بابا)؟'},
          {'id': 'regression', 'text_ar': 'هل فقد طفلك كلمات أو مهارات تواصل كان يتقنها سابقًا؟'},
        ],
        'vocabulary_words': ['ماما', 'بابا', 'ماء'],
        'intelligibility_options': [
          {'value': 4, 'text_ar': 'كل كلامه تقريبًا'},
          {'value': 2, 'text_ar': 'نصفه تقريبًا'},
        ],
      });

  @override
  Future<ScreeningResult> submit({
    required Map<String, bool> redFlagAnswers,
    required List<String> vocabularyChecked,
    int? intelligibility,
  }) async {
    submittedRedFlags = redFlagAnswers;
    submittedVocabulary = vocabularyChecked;
    submittedIntelligibility = intelligibility;
    return ScreeningResult.fromJson({
      'severity': 4,
      'red_flags': ['regression'],
      'traffic_light': 'red',
      'refer_immediately': true,
      'recommendation_ar': 'ننصح بتقييم كامل لدى أخصائي نطق ولغة.',
    });
  }
}

Widget _harness(Widget home) => MaterialApp(
      theme: AppTheme.light,
      locale: const Locale('ar'),
      supportedLocales: const [Locale('ar')],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      builder: (context, child) =>
          Directionality(textDirection: TextDirection.rtl, child: child!),
      home: home,
    );

void main() {
  testWidgets(
      'screening: renders questionnaire, requires answers, submits and shows result',
      (tester) async {
    final api = _FakeScreeningApi();
    await tester.pumpWidget(_harness(ScreeningScreen(screeningApi: api)));
    await tester.pumpAndSettle();

    // Questions rendered; submit disabled until everything is answered.
    expect(find.textContaining('هل ينطق طفلك كلمات مفردة'), findsOneWidget);
    final submit = find.byKey(const Key('submit-screening'));
    expect(tester.widget<FilledButton>(submit).enabled, isFalse);

    // Answer: single words نعم, regression نعم; pick a word; intelligibility.
    await tester.tap(find.descendant(
        of: find.byKey(const Key('q-no_single_words')),
        matching: find.text('نعم')));
    await tester.tap(find.descendant(
        of: find.byKey(const Key('q-regression')),
        matching: find.text('نعم')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('ماما'));
    await tester.scrollUntilVisible(find.byKey(const Key('intel-2')), 100);
    await tester.tap(find.byKey(const Key('intel-2')));
    await tester.pumpAndSettle();

    expect(tester.widget<FilledButton>(submit).enabled, isTrue);
    await tester.scrollUntilVisible(submit, 100);
    await tester.tap(submit);
    await tester.pumpAndSettle();

    // Answers reached the client.
    expect(api.submittedRedFlags,
        {'no_single_words': true, 'regression': true});
    expect(api.submittedVocabulary, ['ماما']);
    expect(api.submittedIntelligibility, 2);

    // Result view: severity, red title, referral recommendation, flag label.
    expect(find.text('4/4'), findsOneWidget);
    expect(find.text('يحتاج تقييمًا متخصصًا'), findsOneWidget);
    expect(find.textContaining('ننصح بتقييم كامل'), findsOneWidget);
    expect(find.text('فقدان مهارات سابقة (نكوص)'), findsOneWidget);
  });
}
