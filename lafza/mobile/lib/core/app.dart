import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import '../features/welcome/welcome_screen.dart';
import 'theme/app_theme.dart';

class LafzaApp extends StatelessWidget {
  const LafzaApp({super.key});

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
      home: const WelcomeScreen(),
    );
  }
}
