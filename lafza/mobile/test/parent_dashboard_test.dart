import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:lafza_mobile/core/theme/app_theme.dart';
import 'package:lafza_mobile/data/models/parent_summary.dart';
import 'package:lafza_mobile/data/models/score_result.dart';
import 'package:lafza_mobile/data/services/gamification_service.dart';
import 'package:lafza_mobile/data/services/parent_api_client.dart';
import 'package:lafza_mobile/data/services/reminder_settings.dart';
import 'package:lafza_mobile/data/services/scoring_client.dart';
import 'package:lafza_mobile/features/parent/parent_dashboard_screen.dart';

import 'helpers/recording_voice.dart';

class _FakeParentApi implements ParentApiClient {
  int fetches = 0;

  @override
  Future<ParentSummary> fetchSummary() async {
    fetches++;
    return ParentSummary.fromJson({
      'streak_days': 3,
      'week_practice_seconds': 420,
      'week_attempts': 6,
      'daily': [
        for (var i = 6; i >= 0; i--)
          {
            'day': DateTime(2026, 7, 5 + (6 - i)).toIso8601String(),
            'seconds': i == 0 ? 120 : (i == 4 ? 300 : 0),
          },
      ],
      'phonemes': [
        {
          'phoneme': 'ر',
          'attempts': 5,
          'first_gop': 38,
          'latest_gop': 41,
          'latest_error_type': 'lateralization',
        },
        {
          'phoneme': 'ش',
          'attempts': 1,
          'first_gop': 64,
          'latest_gop': 64,
          'latest_error_type': 'substitution',
        },
      ],
      'plan': {
        'target_phonemes': ['ش', 'ق', 'ص'],
        'status': 'draft',
      },
    });
  }
}

class _NoopScoring implements ScoringClient {
  @override
  Future<ScoreResult> scoreUtterance({
    required String audioPath,
    required String targetPhoneme,
    required String position,
  }) async =>
      throw UnimplementedError();

  @override
  Future<void> logPractice({
    required String stimulusId,
    required int durationSec,
    required ScoreResult result,
  }) async {}
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
      'parent dashboard renders streak, weekly minutes, home program, reminder and report',
      (tester) async {
    final gamification =
        GamificationService(clock: () => DateTime(2026, 7, 15));
    final reminders = ReminderSettings();

    await tester.pumpWidget(_harness(ParentDashboardScreen(
      parentApi: _FakeParentApi(),
      gamification: gamification,
      reminders: reminders,
      scoringClient: _NoopScoring(),
      voice: RecordingVoice(),
    )));
    await tester.pumpAndSettle();

    // RTL + title.
    final context =
        tester.element(find.byType(ParentDashboardScreen));
    expect(Directionality.of(context), TextDirection.rtl);
    expect(find.text('ركن الوالدين'), findsOneWidget);

    // Dashboard stats from the (fake) backend: streak ٣, minutes ٧ (420s).
    expect(find.text('٣'), findsOneWidget);
    expect(find.text('سلسلة الأيام'), findsOneWidget);
    expect(find.text('٧'), findsOneWidget);
    expect(find.text('دقائق الأسبوع'), findsOneWidget);

    // Home program lists today's 3 missions (scroll — ListView is lazy).
    final scrollable = find.byType(Scrollable).first;
    await tester.scrollUntilVisible(
        find.text('البرنامج المنزلي اليوم (٠/٣)'), 150,
        scrollable: scrollable);
    for (final mission in gamification.todaysMissions) {
      await tester.scrollUntilVisible(find.text(mission.titleAr), 150,
          scrollable: scrollable);
      expect(find.text(mission.titleAr), findsOneWidget);
    }

    // Reminder: off by default; toggling enables it and shows the time row.
    await tester.scrollUntilVisible(
        find.byKey(const Key('reminder-switch')), 150,
        scrollable: scrollable);
    expect(find.text('التذكير متوقف'), findsOneWidget);
    await tester.tap(find.byKey(const Key('reminder-switch')));
    await tester.pumpAndSettle();
    expect(reminders.enabled, isTrue);
    expect(find.byKey(const Key('reminder-time')), findsOneWidget);
    expect(find.textContaining('سنذكّركم يوميًا'), findsOneWidget);

    // Weekly report: attempts count, plan targets, weakest-first rows.
    await tester.scrollUntilVisible(
        find.text('تقرير الأسبوع (٦ محاولة)'), 150,
        scrollable: scrollable);
    expect(find.textContaining('أهداف الخطة'), findsOneWidget);
    expect(find.textContaining('بانتظار اعتماد الأخصائي'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('٤١'), 150,
        scrollable: scrollable);
    expect(find.text('٤١'), findsOneWidget); // ر latest
    expect(find.textContaining('لثغة جانبية'), findsOneWidget);
    expect(find.byIcon(Icons.trending_up_rounded), findsOneWidget); // 38→41
  });
}
