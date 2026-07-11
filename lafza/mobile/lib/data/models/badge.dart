import 'package:flutter/material.dart';

enum BadgeId { firstMission, dailyStar, coinCollector, clearSpeech }

/// Badge metadata for the reward system. Earned state lives in
/// GamificationService; this catalog is static content.
class BadgeSpec {
  const BadgeSpec({
    required this.id,
    required this.titleAr,
    required this.icon,
  });

  final BadgeId id;

  /// Vocalized (بِالتَّشْكِيل) — child-facing.
  final String titleAr;

  final IconData icon;
}

const List<BadgeSpec> badgeCatalog = [
  BadgeSpec(
    id: BadgeId.firstMission,
    titleAr: 'أَوَّلُ خُطْوَة',
    icon: Icons.flag_rounded,
  ),
  BadgeSpec(
    id: BadgeId.dailyStar,
    titleAr: 'نَجْمَةُ اليَوْم',
    icon: Icons.star_rounded,
  ),
  BadgeSpec(
    id: BadgeId.coinCollector,
    titleAr: 'كَنْزُ العُمْلَات',
    icon: Icons.savings_rounded,
  ),
  BadgeSpec(
    id: BadgeId.clearSpeech,
    titleAr: 'نُطْقٌ رَائِع',
    icon: Icons.record_voice_over_rounded,
  ),
];
