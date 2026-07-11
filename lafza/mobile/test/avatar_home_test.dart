import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:lafza_mobile/core/app.dart';
import 'package:lafza_mobile/core/audio/mascot_voice.dart';
import 'package:lafza_mobile/data/services/gamification_service.dart';
import 'package:lafza_mobile/features/home/avatar_home_screen.dart';

import 'helpers/recording_voice.dart';

void main() {
  testWidgets(
      'avatar home: RTL, greeting voice, live coins, badges button, 3 daily missions',
      (tester) async {
    final gamification =
        GamificationService(clock: () => DateTime(2026, 7, 15));
    final voice = RecordingVoice();
    await tester.pumpWidget(
      LafzaApp(gamification: gamification, voice: voice),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('هَيَّا نَبْدَأ'));
    await tester.pumpAndSettle();
    expect(find.byType(AvatarHomeScreen), findsOneWidget);

    // Mascot greeted by voice on arrival, bubble mirrors the line.
    expect(voice.played, contains(MascotLine.greeting));
    expect(find.text(mascotLineTextAr[MascotLine.greeting]!), findsOneWidget);

    // Still RTL; coin counter starts at ٠ on the right half (top-start).
    final BuildContext context =
        tester.element(find.byType(AvatarHomeScreen));
    expect(Directionality.of(context), TextDirection.rtl);
    expect(find.text('٠'), findsOneWidget);
    final Size screen = tester.getSize(find.byType(AvatarHomeScreen));
    final Offset coins =
        tester.getCenter(find.byKey(const Key('coin-counter')));
    expect(coins.dx, greaterThan(screen.width / 2));

    // Badges button present; sheet lists the full catalog (locked).
    await tester.tap(find.byKey(const Key('badges-button')));
    await tester.pumpAndSettle();
    expect(find.text('شَارَاتِي'), findsOneWidget);
    expect(find.text('أَوَّلُ خُطْوَة'), findsOneWidget);
    await tester.tapAt(const Offset(10, 10)); // dismiss sheet
    await tester.pumpAndSettle();

    // Today's 3 auto-picked mission cards are rendered (icon + one word).
    expect(gamification.todaysMissions, hasLength(3));
    expect(find.text('مَهَامُّ اليَوْم: ٠/٣'), findsOneWidget);
    for (final mission in gamification.todaysMissions) {
      expect(find.text(mission.titleAr), findsOneWidget);
    }
  });
}
