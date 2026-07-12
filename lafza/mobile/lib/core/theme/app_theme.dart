import 'package:flutter/material.dart';

/// Lafza brand palette (blueprint §9 — warm, clinical-playful).
abstract final class LafzaColors {
  static const Color teal = Color(0xFF0F6E6B); // primary
  static const Color saffron = Color(0xFFF2A93B); // accent
  static const Color success = Color(0xFF2FA66A);
  static const Color alert = Color(0xFFE2574C);
  static const Color surface = Color(0xFFFAF8F4); // off-white
  static const Color navy = Color(0xFF1B2A4A); // professional dashboards
}

abstract final class LafzaFonts {
  static const String ui = 'IBMPlexSansArabic';

  /// For child-facing vocalized words (بِالتَّشْكِيل) — Naskh keeps diacritics legible.
  static const String childText = 'NotoNaskhArabic';
}

abstract final class AppTheme {
  static ThemeData get light {
    final ColorScheme scheme = ColorScheme.fromSeed(
      seedColor: LafzaColors.teal,
      primary: LafzaColors.teal,
      secondary: LafzaColors.saffron,
      error: LafzaColors.alert,
      surface: LafzaColors.surface,
    );

    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: LafzaColors.surface,
      fontFamily: LafzaFonts.ui,
      appBarTheme: const AppBarTheme(
        backgroundColor: LafzaColors.teal,
        foregroundColor: Colors.white,
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: LafzaColors.saffron,
          foregroundColor: LafzaColors.navy,
          textStyle: const TextStyle(
            fontFamily: LafzaFonts.ui,
            fontWeight: FontWeight.w700,
            fontSize: 20,
          ),
          padding: const EdgeInsets.symmetric(horizontal: 40, vertical: 18),
        ),
      ),
    );
  }

  /// Style for child-facing vocalized words: ≥28pt, line-height 1.6+ so
  /// diacritics never clip (blueprint §9 typography rules).
  static const TextStyle childWord = TextStyle(
    fontFamily: LafzaFonts.childText,
    fontSize: 32,
    height: 1.8,
    color: LafzaColors.navy,
  );
}
