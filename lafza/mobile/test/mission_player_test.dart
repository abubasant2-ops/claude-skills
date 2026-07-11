import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:lafza_mobile/core/audio/mascot_voice.dart';
import 'package:lafza_mobile/core/audio/mission_recorder.dart';
import 'package:lafza_mobile/core/theme/app_theme.dart';
import 'package:lafza_mobile/data/content/mission_pool.dart';
import 'package:lafza_mobile/data/models/badge.dart';
import 'package:lafza_mobile/data/models/score_result.dart';
import 'package:lafza_mobile/data/services/gamification_service.dart';
import 'package:lafza_mobile/data/services/scoring_client.dart';
import 'package:lafza_mobile/features/mission/mission_player_screen.dart';

import 'helpers/recording_voice.dart';

final mockSunStimulus = missionPool.first.stimulus; // شَمْس / ش / initial

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

class _FakeScoringClient implements ScoringClient {
  String? receivedAudioPath;
  bool goodScore = false;
  int practiceLogs = 0;

  @override
  Future<ScoreResult> scoreUtterance({
    required String audioPath,
    required String targetPhoneme,
    required String position,
  }) async {
    receivedAudioPath = audioPath;
    // Small delay so the analyzing state is observable in the test.
    await Future<void>.delayed(const Duration(milliseconds: 300));
    return ScoreResult(
      phoneme: targetPhoneme,
      position: position,
      gopScore: goodScore ? 82 : 64,
      errorType: goodScore ? null : 'substitution',
      confidence: 0.91,
    );
  }

  @override
  Future<void> logPractice({
    required String stimulusId,
    required int durationSec,
    required ScoreResult result,
  }) async {
    practiceLogs++;
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
      'mission player: stimulus card, consent gate, record → analyze → scored result',
      (tester) async {
    final recorder = _FakeRecorder();
    final scoringClient = _FakeScoringClient();
    await tester.pumpWidget(_harness(
      MissionPlayerScreen(
        stimulus: mockSunStimulus,
        recorder: recorder,
        scoringClient: scoringClient,
      ),
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

    // Stop → analyzing state while the scoring client round-trips.
    await tester.tap(find.byKey(const Key('stop-button')));
    await tester.pump(const Duration(milliseconds: 100));
    expect(recorder.stopped, isTrue);
    expect(find.text('قَيْدَ التَّحْلِيل…'), findsOneWidget);

    // Client response arrives → GOP ring shows the backend score «٦٤».
    await tester.pump(const Duration(milliseconds: 400));
    expect(scoringClient.receivedAudioPath, '/tmp/fake-utterance.m4a');
    expect(find.byType(GopRing), findsOneWidget);
    expect(find.text('٦٤'), findsOneWidget);
    expect(find.text('مِنْ ١٠٠'), findsOneWidget);

    // Retry resets to idle.
    await tester.tap(find.text('مَرَّةً أُخْرَى'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('mic-button')), findsOneWidget);
  });

  testWidgets('declining consent never starts the recorder', (tester) async {
    final recorder = _FakeRecorder();
    await tester.pumpWidget(_harness(
      MissionPlayerScreen(
        stimulus: mockSunStimulus,
        recorder: recorder,
        scoringClient: _FakeScoringClient(),
      ),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('mic-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('لَيْسَ الآن'));
    await tester.pumpAndSettle();

    expect(recorder.started, isFalse);
    expect(find.byKey(const Key('mic-button')), findsOneWidget);
  });

  testWidgets(
      'good result awards coins, completes the mission, unlocks badges, mascot praises',
      (tester) async {
    final gamification =
        GamificationService(clock: () => DateTime(2026, 7, 15));
    final mission = gamification.todaysMissions.first;
    final voice = RecordingVoice();

    await tester.pumpWidget(_harness(
      MissionPlayerScreen(
        stimulus: mission.stimulus,
        missionId: mission.id,
        gamification: gamification,
        voice: voice,
        recorder: _FakeRecorder(),
        scoringClient: _FakeScoringClient()..goodScore = true,
      ),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('mic-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('أُوَافِق'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('stop-button')));
    await tester.pump(const Duration(milliseconds: 500));

    // Coins: effort 10 + good bonus 15; mission completed; chip visible.
    expect(gamification.coins, 25);
    expect(gamification.isCompleted(mission.id), isTrue);
    expect(find.byKey(const Key('earned-coins')), findsOneWidget);
    expect(find.text('+٢٥ عُمْلَة'), findsOneWidget);

    // Badges for first mission + clear speech; mascot praised then celebrated.
    expect(gamification.earnedBadges,
        containsAll([BadgeId.firstMission, BadgeId.clearSpeech]));
    expect(voice.played, contains(MascotLine.praise));
    expect(voice.played, contains(MascotLine.badgeUnlocked));
    await tester.pumpAndSettle();
  });

  testWidgets('low score plays try-again line and awards effort coins only',
      (tester) async {
    final gamification =
        GamificationService(clock: () => DateTime(2026, 7, 15));
    final mission = gamification.todaysMissions.first;
    final voice = RecordingVoice();

    await tester.pumpWidget(_harness(
      MissionPlayerScreen(
        stimulus: mission.stimulus,
        missionId: mission.id,
        gamification: gamification,
        voice: voice,
        recorder: _FakeRecorder(),
        scoringClient: _FakeScoringClient()..goodScore = false,
      ),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('mic-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('أُوَافِق'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('stop-button')));
    await tester.pump(const Duration(milliseconds: 500));

    expect(gamification.coins, 10); // effort only, no bonus
    expect(find.text('+١٠ عُمْلَة'), findsOneWidget);
    expect(voice.played, contains(MascotLine.tryAgain));
    expect(voice.played, isNot(contains(MascotLine.praise)));
    await tester.pumpAndSettle();
  });
}
