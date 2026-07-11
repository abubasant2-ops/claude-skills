import 'package:flutter/material.dart';

import '../../core/audio/mascot_voice.dart';
import '../../core/theme/app_theme.dart';
import '../../data/services/gamification_service.dart';
import '../../data/services/parent_api_client.dart';
import '../../data/services/reminder_settings.dart';
import '../../data/services/screening_api_client.dart';
import '../../data/services/scoring_client.dart';
import '../home/avatar_home_screen.dart';

class WelcomeScreen extends StatelessWidget {
  const WelcomeScreen({
    super.key,
    required this.gamification,
    required this.voice,
    required this.scoringClient,
    required this.parentApi,
    required this.screeningApi,
    required this.reminders,
  });

  final GamificationService gamification;
  final MascotVoice voice;
  final ScoringClient scoringClient;
  final ParentApiClient parentApi;
  final ScreeningApiClient screeningApi;
  final ReminderSettings reminders;

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
                      builder: (_) => AvatarHomeScreen(
                        gamification: gamification,
                        voice: voice,
                        scoringClient: scoringClient,
                        parentApi: parentApi,
                        screeningApi: screeningApi,
                        reminders: reminders,
                      ),
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
