/// A single daily mission shown on the child's avatar home screen.
class DailyMission {
  const DailyMission({
    required this.id,
    required this.titleAr,
    required this.kind,
  });

  final String id;

  /// Fully vocalized Arabic title (بِالتَّشْكِيل) — one word.
  final String titleAr;

  final MissionKind kind;
}

enum MissionKind { sounds, words, stories }
