import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:lafza_mobile/core/app.dart';
import 'package:lafza_mobile/data/services/gamification_service.dart';
import 'package:lafza_mobile/features/welcome/welcome_screen.dart';

import 'helpers/recording_voice.dart';

void main() {
  testWidgets('app renders the Arabic welcome screen in RTL with Lafza theme',
      (tester) async {
    await tester.pumpWidget(LafzaApp(
      gamification: GamificationService(clock: () => DateTime(2026, 7, 15)),
      voice: RecordingVoice(),
    ));
    await tester.pumpAndSettle();

    // Welcome screen is shown.
    expect(find.byType(WelcomeScreen), findsOneWidget);

    // RTL is in effect for the rendered screen (CLAUDE.md rule 1).
    final BuildContext context = tester.element(find.byType(Scaffold));
    expect(Directionality.of(context), TextDirection.rtl);

    // Arabic locale is active.
    expect(Localizations.localeOf(context), const Locale('ar'));

    // Vocalized Arabic text is present (rule 2: بالتشكيل).
    expect(find.text('أَهْلًا بِكَ فِي لَفْظَة!'), findsOneWidget);
    expect(find.text('هَيَّا نَبْدَأ'), findsOneWidget);

    // Lafza brand colors are wired into the theme.
    final ThemeData theme = Theme.of(context);
    expect(theme.colorScheme.primary, const Color(0xFF0F6E6B)); // teal
    expect(theme.colorScheme.secondary, const Color(0xFFF2A93B)); // saffron
  });
}
