import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:lafza_mobile/core/audio/mission_recorder.dart';
import 'package:lafza_mobile/core/theme/app_theme.dart';
import 'package:lafza_mobile/data/mock/mock_mission_data.dart';
import 'package:lafza_mobile/features/mission/mission_player_screen.dart';

class _FakeRecorder implements MissionRecorder {
  bool started = false;
  bool stopped = false;

  @override
  Future<bool> hasPermission() async => true;

  @override
  Future<void> start() async => started = true;

  @override
  Future<String?> stop() async {
    stopped = true;
    return '/tmp/fake-utterance.m4a';
  }

  @override
  Future<void> dispose() async {}
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
      'mission player: stimulus card, consent gate, record → analyze → mock result',
      (tester) async {
    final recorder = _FakeRecorder();
    await tester.pumpWidget(_harness(
      MissionPlayerScreen(stimulus: mockSunStimulus, recorder: recorder),
    ));
    await tester.pumpAndSettle();

    // Stimulus card: picture + vocalized word + listen button.
    expect(find.byIcon(Icons.wb_sunny_rounded), findsOneWidget);
    expect(find.text('شَمْس'), findsOneWidget);
    expect(find.byIcon(Icons.volume_up_rounded), findsOneWidget);

    // Mic tap opens the guardian-consent gate first (hard rule 5).
    await tester.tap(find.byKey(const Key('mic-button')));
    await tester.pumpAndSettle();
    expect(find.text('مُوَافَقَةُ وَلِيِّ الأَمْر'), findsOneWidget);
    expect(recorder.started, isFalse, reason: 'must not record before consent');

    await tester.tap(find.text('أُوَافِق'));
    await tester.pumpAndSettle();

    // Recording state.
    expect(recorder.started, isTrue);
    expect(find.text('جَارِي التَّسْجِيل…'), findsOneWidget);

    // Stop → analyzing state.
    await tester.tap(find.byKey(const Key('stop-button')));
    await tester.pump(const Duration(milliseconds: 100));
    expect(recorder.stopped, isTrue);
    expect(find.text('قَيْدَ التَّحْلِيل…'), findsOneWidget);

    // Mock latency elapses → GOP result ring with Arabic-Indic score.
    await tester.pump(const Duration(milliseconds: 1600));
    expect(find.byType(GopRing), findsOneWidget);
    expect(find.text('مِنْ ١٠٠'), findsOneWidget);

    // Retry resets to idle.
    await tester.tap(find.text('مَرَّةً أُخْرَى'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('mic-button')), findsOneWidget);
  });

  testWidgets('declining consent never starts the recorder', (tester) async {
    final recorder = _FakeRecorder();
    await tester.pumpWidget(_harness(
      MissionPlayerScreen(stimulus: mockSunStimulus, recorder: recorder),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('mic-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('لَيْسَ الآن'));
    await tester.pumpAndSettle();

    expect(recorder.started, isFalse);
    expect(find.byKey(const Key('mic-button')), findsOneWidget);
  });
}
