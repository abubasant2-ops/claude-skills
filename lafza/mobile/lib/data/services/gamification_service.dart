import 'dart:math';

import 'package:flutter/foundation.dart';

import '../content/mission_pool.dart';
import '../models/badge.dart';
import '../models/daily_mission.dart';

/// Gamification core: coins, badges, and the day's 3 auto-picked missions.
///
/// Coins are EARNED ONLY — there is no purchase path anywhere in the app
/// and none may be added (child-safety rule; blueprint §13: no purchases
/// by children, no loot boxes). State is in-memory for this phase; it moves
/// server-side with sessions/adherence when the parent account lands.
class GamificationService extends ChangeNotifier {
  GamificationService({DateTime Function()? clock})
      : _clock = clock ?? DateTime.now {
    _todaysMissions = _pickDailyMissions();
  }

  static const int effortReward = 10; // per completed rep (effort-based)
  static const int goodBonus = 15; // extra when GOP crosses the threshold
  static const int _dailyMissionCount = 3;
  static const int _coinCollectorThreshold = 100;

  final DateTime Function() _clock;

  int _coins = 0;
  bool _hadGoodResult = false;
  final Set<BadgeId> _earnedBadges = {};
  final Set<String> _completedMissionIds = {};
  late final List<DailyMission> _todaysMissions;

  int get coins => _coins;
  List<DailyMission> get todaysMissions => List.unmodifiable(_todaysMissions);
  Set<BadgeId> get earnedBadges => Set.unmodifiable(_earnedBadges);
  bool isCompleted(String missionId) =>
      _completedMissionIds.contains(missionId);
  int get completedTodayCount =>
      _todaysMissions.where((m) => isCompleted(m.id)).length;

  /// Deterministic per-day pick: same child, same day → same 3 missions.
  /// The adaptive engine replaces this seed with plan targets later.
  List<DailyMission> _pickDailyMissions() {
    final DateTime today = _clock();
    final int dayOfYear =
        today.difference(DateTime(today.year)).inDays + 1;
    final Random random = Random(today.year * 1000 + dayOfYear);
    final pool = [...missionPool]..shuffle(random);
    return pool.take(_dailyMissionCount).toList();
  }

  /// Award coins for a scored attempt and mark the mission complete.
  /// Returns badges newly unlocked by this attempt (for voice/celebration).
  List<BadgeSpec> recordMissionResult({
    required String missionId,
    required bool good,
  }) {
    _coins += effortReward + (good ? goodBonus : 0);
    _completedMissionIds.add(missionId);
    if (good) _hadGoodResult = true;

    final List<BadgeSpec> newlyEarned = _evaluateBadges();
    notifyListeners();
    return newlyEarned;
  }

  List<BadgeSpec> _evaluateBadges() {
    final List<BadgeSpec> newly = [];

    void tryEarn(BadgeId id, bool condition) {
      if (condition && _earnedBadges.add(id)) {
        newly.add(badgeCatalog.firstWhere((b) => b.id == id));
      }
    }

    tryEarn(BadgeId.firstMission, _completedMissionIds.isNotEmpty);
    tryEarn(BadgeId.clearSpeech, _hadGoodResult);
    tryEarn(BadgeId.dailyStar, completedTodayCount >= _dailyMissionCount);
    tryEarn(BadgeId.coinCollector, _coins >= _coinCollectorThreshold);
    return newly;
  }
}
