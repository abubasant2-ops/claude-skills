import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import '../data/services/gamification_service.dart';
import '../features/welcome/welcome_screen.dart';
import 'audio/mascot_voice.dart';
import 'theme/app_theme.dart';

class LafzaApp extends StatefulWidget {
  const LafzaApp({super.key, this.gamification, this.voice});

  /// Injectable for tests; real instances are created by default.
  final GamificationService? gamification;
  final MascotVoice? voice;

  @override
  State<LafzaApp> createState() => _LafzaAppState();
}

class _LafzaAppState extends State<LafzaApp> {
  late final GamificationService _gamification =
      widget.gamification ?? GamificationService();
  late final MascotVoice _voice = widget.voice ?? AssetMascotVoice();

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
      home: WelcomeScreen(gamification: _gamification, voice: _voice),
    );
  }
}
