import 'package:flutter/material.dart';

import '../../core/audio/mascot_voice.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/arabic_numbers.dart';
import '../../core/widgets/stimulus_icons.dart';
import '../../data/models/badge.dart';
import '../../data/models/daily_mission.dart';
import '../../data/services/gamification_service.dart';
import '../../data/services/parent_api_client.dart';
import '../../data/services/reminder_settings.dart';
import '../../data/services/screening_api_client.dart';
import '../../data/services/scoring_client.dart';
import '../mission/mission_player_screen.dart';
import '../parent/parent_dashboard_screen.dart';

/// S1 — child's avatar home: mascot لَفُّوظ center (greets by voice),
/// live coin counter at the top start edge (right in RTL), badges sheet,
/// and today's 3 auto-picked mission cards at the bottom.
class AvatarHomeScreen extends StatefulWidget {
  const AvatarHomeScreen({
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
  State<AvatarHomeScreen> createState() => _AvatarHomeScreenState();
}

class _AvatarHomeScreenState extends State<AvatarHomeScreen> {
  @override
  void initState() {
    super.initState();
    widget.voice.play(MascotLine.greeting);
  }

  Future<void> _openMission(DailyMission mission) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => MissionPlayerScreen(
          stimulus: mission.stimulus,
          missionId: mission.id,
          gamification: widget.gamification,
          voice: widget.voice,
          scoringClient: widget.scoringClient,
        ),
      ),
    );
  }

  void _openParentCorner() {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => ParentDashboardScreen(
          parentApi: widget.parentApi,
          gamification: widget.gamification,
          reminders: widget.reminders,
          scoringClient: widget.scoringClient,
          screeningApi: widget.screeningApi,
          voice: widget.voice,
        ),
      ),
    );
  }

  void _showBadges() {
    final earned = widget.gamification.earnedBadges;
    showModalBottomSheet<void>(
      context: context,
      builder: (context) => Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'شَارَاتِي',
              style: AppTheme.childWord.copyWith(
                fontWeight: FontWeight.bold,
                color: LafzaColors.teal,
              ),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                for (final badge in badgeCatalog)
                  Expanded(
                    child: Column(
                      children: [
                        Icon(
                          badge.icon,
                          size: 44,
                          color: earned.contains(badge.id)
                              ? LafzaColors.saffron
                              : Colors.black26,
                        ),
                        const SizedBox(height: 6),
                        Text(
                          badge.titleAr,
                          textAlign: TextAlign.center,
                          style: AppTheme.childWord.copyWith(
                            fontSize: 14,
                            color: earned.contains(badge.id)
                                ? LafzaColors.navy
                                : Colors.black38,
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: ListenableBuilder(
            listenable: widget.gamification,
            builder: (context, _) {
              final g = widget.gamification;
              return Column(
                children: [
                  Row(
                    children: [
                      _CoinCounter(coins: g.coins),
                      const Spacer(),
                      IconButton.filledTonal(
                        key: const Key('parent-button'),
                        tooltip: 'ركن الوالدين',
                        onPressed: _openParentCorner,
                        icon: const Icon(
                          Icons.family_restroom_rounded,
                          color: LafzaColors.navy,
                        ),
                      ),
                      const SizedBox(width: 8),
                      IconButton.filledTonal(
                        key: const Key('badges-button'),
                        tooltip: 'شَارَاتِي',
                        onPressed: _showBadges,
                        icon: Icon(
                          Icons.military_tech_rounded,
                          color: g.earnedBadges.isEmpty
                              ? Colors.black38
                              : LafzaColors.saffron,
                        ),
                      ),
                    ],
                  ),
                  const Spacer(),
                  const _Mascot(),
                  const Spacer(),
                  Text(
                    'مَهَامُّ اليَوْم: '
                    '${toArabicIndicDigits(g.completedTodayCount)}/'
                    '${toArabicIndicDigits(g.todaysMissions.length)}',
                    style: AppTheme.childWord.copyWith(fontSize: 20),
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      for (final mission in g.todaysMissions)
                        Expanded(
                          child: Padding(
                            padding:
                                const EdgeInsets.symmetric(horizontal: 6),
                            child: _MissionCard(
                              mission: mission,
                              completed: g.isCompleted(mission.id),
                              onTap: () => _openMission(mission),
                            ),
                          ),
                        ),
                    ],
                  ),
                ],
              );
            },
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
        // Speech bubble mirrors the greeting voice line (visual-dominant
        // feedback groundwork for hearing-impairment mode).
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(20),
            boxShadow: const [
              BoxShadow(
                  color: Colors.black12, blurRadius: 6, offset: Offset(0, 2)),
            ],
          ),
          child: Text(
            mascotLineTextAr[MascotLine.greeting]!,
            style: AppTheme.childWord.copyWith(fontSize: 20),
          ),
        ),
        const SizedBox(height: 14),
        Container(
          width: 180,
          height: 180,
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
            size: 90,
            color: LafzaColors.saffron,
          ),
        ),
        const SizedBox(height: 14),
        Text(
          'لَفُّوظ',
          style: AppTheme.childWord.copyWith(
            fontSize: 32,
            fontWeight: FontWeight.bold,
            color: LafzaColors.teal,
          ),
        ),
      ],
    );
  }
}

class _MissionCard extends StatelessWidget {
  const _MissionCard({
    required this.mission,
    required this.completed,
    required this.onTap,
  });

  final DailyMission mission;
  final bool completed;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: completed ? LafzaColors.success.withValues(alpha: 0.12) : Colors.white,
      borderRadius: BorderRadius.circular(20),
      elevation: completed ? 0 : 2,
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              completed
                  ? const Icon(Icons.check_circle_rounded,
                      size: 40, color: LafzaColors.success)
                  : Icon(stimulusIcon(mission.stimulus.picture),
                      size: 40, color: LafzaColors.teal),
              const SizedBox(height: 8),
              Text(
                mission.titleAr,
                style: AppTheme.childWord.copyWith(fontSize: 19),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
