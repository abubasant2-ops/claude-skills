import 'stimulus_item.dart';

/// A daily mission: practice one stimulus word. Three are auto-picked per
/// day by GamificationService.
class DailyMission {
  const DailyMission({required this.id, required this.stimulus});

  final String id;
  final StimulusItem stimulus;

  /// Card label — the vocalized target word (icon + one word).
  String get titleAr => stimulus.wordAr;
}
