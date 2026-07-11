import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import '../data/services/api_scoring_client.dart';
import '../data/services/demo_account.dart';
import '../data/services/gamification_service.dart';
import '../data/services/parent_api_client.dart';
import '../data/services/reminder_settings.dart';
import '../data/services/scoring_client.dart';
import '../data/services/screening_api_client.dart';
import '../features/welcome/welcome_screen.dart';
import 'audio/mascot_voice.dart';
import 'theme/app_theme.dart';

class LafzaApp extends StatefulWidget {
  const LafzaApp({
    super.key,
    this.gamification,
    this.voice,
    this.scoringClient,
    this.parentApi,
    this.screeningApi,
    this.reminders,
  });

  /// Injectable for tests; real instances are created by default and share
  /// ONE DemoAccountRepository so every feature talks about the same child.
  final GamificationService? gamification;
  final MascotVoice? voice;
  final ScoringClient? scoringClient;
  final ParentApiClient? parentApi;
  final ScreeningApiClient? screeningApi;
  final ReminderSettings? reminders;

  @override
  State<LafzaApp> createState() => _LafzaAppState();
}

class _LafzaAppState extends State<LafzaApp> {
  late final DemoAccountRepository _account = DemoAccountRepository();
  late final GamificationService _gamification =
      widget.gamification ?? GamificationService();
  late final MascotVoice _voice = widget.voice ?? AssetMascotVoice();
  late final ScoringClient _scoringClient =
      widget.scoringClient ?? ApiScoringClient(account: _account);
  late final ParentApiClient _parentApi =
      widget.parentApi ?? HttpParentApiClient(account: _account);
  late final ScreeningApiClient _screeningApi =
      widget.screeningApi ?? HttpScreeningApiClient(account: _account);
  late final ReminderSettings _reminders =
      widget.reminders ?? ReminderSettings();

  @override
  void dispose() {
    _voice.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'لفظة',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light,
      locale: const Locale('ar'),
      supportedLocales: const [Locale('ar')],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      // RTL enforced app-wide regardless of device locale (CLAUDE.md rule 1).
      builder: (context, child) => Directionality(
        textDirection: TextDirection.rtl,
        child: child!,
      ),
      home: WelcomeScreen(
        gamification: _gamification,
        voice: _voice,
        scoringClient: _scoringClient,
        parentApi: _parentApi,
        screeningApi: _screeningApi,
        reminders: _reminders,
      ),
    );
  }
}
