import 'package:flutter_test/flutter_test.dart';

import 'package:lafza_mobile/data/models/badge.dart';
import 'package:lafza_mobile/data/services/gamification_service.dart';

GamificationService _serviceOn(DateTime day) =>
    GamificationService(clock: () => day);

void main() {
  test('daily missions: 3 picked, deterministic per day, differ across days',
      () {
    final a = _serviceOn(DateTime(2026, 7, 15));
    final b = _serviceOn(DateTime(2026, 7, 15));
    final c = _serviceOn(DateTime(2026, 7, 16));

    expect(a.todaysMissions, hasLength(3));
    expect(
      a.todaysMissions.map((m) => m.id).toList(),
      b.todaysMissions.map((m) => m.id).toList(),
      reason: 'same day must pick the same missions',
    );
    // Different day → different seed (order or set may change).
    expect(
      a.todaysMissions.map((m) => m.id).toList(),
      isNot(c.todaysMissions.map((m) => m.id).toList()),
    );
  });

  test('coins: effort reward always, good bonus when score is good', () {
    final service = _serviceOn(DateTime(2026, 7, 15));
    final m = service.todaysMissions;

    service.recordMissionResult(missionId: m[0].id, good: false);
    expect(service.coins, GamificationService.effortReward);

    service.recordMissionResult(missionId: m[1].id, good: true);
    expect(
      service.coins,
      GamificationService.effortReward * 2 + GamificationService.goodBonus,
    );
    expect(service.completedTodayCount, 2);
  });

  test('badges unlock: first mission, clear speech, daily star, collector',
      () {
    final service = _serviceOn(DateTime(2026, 7, 15));
    final m = service.todaysMissions;

    var newly =
        service.recordMissionResult(missionId: m[0].id, good: true);
    expect(newly.map((b) => b.id),
        containsAll([BadgeId.firstMission, BadgeId.clearSpeech]));

    newly = service.recordMissionResult(missionId: m[1].id, good: false);
    expect(newly, isEmpty); // nothing new mid-way

    newly = service.recordMissionResult(missionId: m[2].id, good: true);
    expect(newly.map((b) => b.id), contains(BadgeId.dailyStar));

    // Grind repeats until the coin collector badge fires at >= 100.
    while (!service.earnedBadges.contains(BadgeId.coinCollector)) {
      newly = service.recordMissionResult(missionId: m[0].id, good: true);
    }
    expect(service.coins, greaterThanOrEqualTo(100));
    expect(newly.map((b) => b.id), contains(BadgeId.coinCollector));
  });

  test('notifies listeners on every recorded result', () {
    final service = _serviceOn(DateTime(2026, 7, 15));
    var notifications = 0;
    service.addListener(() => notifications++);
    service.recordMissionResult(
        missionId: service.todaysMissions[0].id, good: true);
    service.recordMissionResult(
        missionId: service.todaysMissions[1].id, good: false);
    expect(notifications, 2);
  });
}
