import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../core/utils/arabic_numbers.dart';
import '../../data/mock/mock_home_data.dart';
import '../../data/mock/mock_mission_data.dart';
import '../../data/models/daily_mission.dart';
import '../mission/mission_player_screen.dart';

/// S1 — child's avatar home: mascot لَفُّوظ center, coin counter at the top
/// start edge (= right in RTL), three daily-mission cards at the bottom.
class AvatarHomeScreen extends StatelessWidget {
  const AvatarHomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            children: [
              Row(
                children: [
                  _CoinCounter(coins: mockCoinBalance),
                ],
              ),
              const Spacer(),
              const _Mascot(),
              const Spacer(),
              Row(
                children: [
                  for (final mission in mockDailyMissions)
                    Expanded(
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 6),
                        child: _MissionCard(mission: mission),
                      ),
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _CoinCounter extends StatelessWidget {
  const _CoinCounter({required this.coins});

  final int coins;

  @override
  Widget build(BuildContext context) {
    return Container(
      key: const Key('coin-counter'),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(24),
        boxShadow: const [
          BoxShadow(color: Colors.black12, blurRadius: 6, offset: Offset(0, 2)),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.paid_rounded, color: LafzaColors.saffron, size: 28),
          const SizedBox(width: 8),
          Text(
            toArabicIndicDigits(coins),
            style: const TextStyle(
              fontSize: 22,
              fontWeight: FontWeight.bold,
              color: LafzaColors.navy,
            ),
          ),
        ],
      ),
    );
  }
}

class _Mascot extends StatelessWidget {
  const _Mascot();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Container(
          width: 200,
          height: 200,
          decoration: const BoxDecoration(
            shape: BoxShape.circle,
            color: LafzaColors.teal,
            boxShadow: [
              BoxShadow(
                color: Colors.black26,
                blurRadius: 16,
                offset: Offset(0, 6),
              ),
            ],
          ),
          // Placeholder until لَفُّوظ artwork exists.
          child: const Icon(
            Icons.record_voice_over_rounded,
            size: 100,
            color: LafzaColors.saffron,
          ),
        ),
        const SizedBox(height: 20),
        Text(
          'لَفُّوظ',
          style: AppTheme.childWord.copyWith(
            fontSize: 36,
            fontWeight: FontWeight.bold,
            color: LafzaColors.teal,
          ),
        ),
        const SizedBox(height: 8),
        const Text(
          'مَرْحَبًا يَا بَطَل!',
          textAlign: TextAlign.center,
          style: AppTheme.childWord,
        ),
      ],
    );
  }
}

class _MissionCard extends StatelessWidget {
  const _MissionCard({required this.mission});

  final DailyMission mission;

  IconData get _icon => switch (mission.kind) {
        MissionKind.sounds => Icons.mic_rounded,
        MissionKind.words => Icons.menu_book_rounded,
        MissionKind.stories => Icons.auto_stories_rounded,
      };

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(20),
      elevation: 2,
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: () {
          if (mission.kind == MissionKind.sounds) {
            Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) =>
                    MissionPlayerScreen(stimulus: mockSunStimulus),
              ),
            );
          }
          // Other play zones (words, stories) arrive with library content.
        },
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 18),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(_icon, size: 44, color: LafzaColors.teal),
              const SizedBox(height: 10),
              Text(
                mission.titleAr,
                style: AppTheme.childWord.copyWith(fontSize: 20),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
