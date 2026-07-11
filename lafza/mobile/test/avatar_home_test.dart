import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:lafza_mobile/core/app.dart';
import 'package:lafza_mobile/features/home/avatar_home_screen.dart';

void main() {
  testWidgets(
      'avatar home opens from welcome, renders RTL with mascot, coins and 3 missions',
      (tester) async {
    await tester.pumpWidget(const LafzaApp());
    await tester.pumpAndSettle();

    // Welcome CTA navigates to the avatar home.
    await tester.tap(find.text('هَيَّا نَبْدَأ'));
    await tester.pumpAndSettle();
    expect(find.byType(AvatarHomeScreen), findsOneWidget);

    // Still RTL on the new screen.
    final BuildContext context =
        tester.element(find.byType(AvatarHomeScreen));
    expect(Directionality.of(context), TextDirection.rtl);

    // Mascot and greeting (vocalized).
    expect(find.text('لَفُّوظ'), findsOneWidget);
    expect(find.text('مَرْحَبًا يَا بَطَل!'), findsOneWidget);

    // Coin counter shows the mock balance in Arabic-Indic digits...
    expect(find.text('١٢٨'), findsOneWidget);

    // ...and sits in the RIGHT half of the screen (top-start under RTL).
    final Size screen = tester.getSize(find.byType(AvatarHomeScreen));
    final Offset coins =
        tester.getCenter(find.byKey(const Key('coin-counter')));
    expect(coins.dx, greaterThan(screen.width / 2),
        reason: 'coin counter must be on the right edge in RTL');

    // Three mission cards, icon + one vocalized word each.
    expect(find.text('أَصْوَاتِي'), findsOneWidget);
    expect(find.text('كَلِمَاتِي'), findsOneWidget);
    expect(find.text('قِصَصِي'), findsOneWidget);
    expect(find.byIcon(Icons.mic_rounded), findsOneWidget);
    expect(find.byIcon(Icons.menu_book_rounded), findsOneWidget);
    expect(find.byIcon(Icons.auto_stories_rounded), findsOneWidget);
  });
}
