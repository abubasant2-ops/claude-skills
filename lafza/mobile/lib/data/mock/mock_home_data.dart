import '../models/daily_mission.dart';

/// Mock home-screen data until the backend is wired in (Phase C).

const int mockCoinBalance = 128;

const List<DailyMission> mockDailyMissions = [
  DailyMission(id: 'mission-sounds', titleAr: 'أَصْوَاتِي', kind: MissionKind.sounds),
  DailyMission(id: 'mission-words', titleAr: 'كَلِمَاتِي', kind: MissionKind.words),
  DailyMission(id: 'mission-stories', titleAr: 'قِصَصِي', kind: MissionKind.stories),
];
