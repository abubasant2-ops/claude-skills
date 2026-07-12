/// One articulation stimulus: a picture-backed vocalized word targeting a
/// specific phoneme in a specific position.
class StimulusItem {
  const StimulusItem({
    required this.id,
    required this.wordAr,
    required this.targetPhoneme,
    required this.position,
    required this.picture,
  });

  final String id;

  /// Fully vocalized (بِالتَّشْكِيل).
  final String wordAr;

  /// Single Arabic letter, e.g. «ش».
  final String targetPhoneme;

  /// initial | medial | final — mirrors the backend enum values.
  final String position;

  final StimulusPicture picture;
}

/// Picture placeholders until illustrated assets exist (content pipeline).
enum StimulusPicture { sun, moon, book, toy, face, image }
