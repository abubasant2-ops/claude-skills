import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../home/avatar_home_screen.dart';

class WelcomeScreen extends StatelessWidget {
  const WelcomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                // Mascot placeholder until لَفُّوظ artwork exists.
                const CircleAvatar(
                  radius: 64,
                  backgroundColor: LafzaColors.teal,
                  child: Icon(
                    Icons.record_voice_over_rounded,
                    size: 72,
                    color: LafzaColors.saffron,
                  ),
                ),
                const SizedBox(height: 32),
                Text(
                  'أَهْلًا بِكَ فِي لَفْظَة!',
                  textAlign: TextAlign.center,
                  style: AppTheme.childWord.copyWith(
                    fontSize: 40,
                    fontWeight: FontWeight.bold,
                    color: LafzaColors.teal,
                  ),
                ),
                const SizedBox(height: 16),
                const Text(
                  'مَعًا نَتَعَلَّمُ النُّطْقَ الصَّحِيحَ مَعَ صَدِيقِكَ لَفُّوظ',
                  textAlign: TextAlign.center,
                  style: AppTheme.childWord,
                ),
                const SizedBox(height: 48),
                FilledButton(
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => const AvatarHomeScreen(),
                    ),
                  ),
                  child: const Text('هَيَّا نَبْدَأ'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
