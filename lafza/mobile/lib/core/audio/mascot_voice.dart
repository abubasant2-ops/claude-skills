import 'package:audioplayers/audioplayers.dart';

/// What لَفُّوظ can say. Clips are bundled assets (offline-first) — espeak
/// placeholders until studio-recorded child-voice lines arrive.
enum MascotLine { greeting, praise, tryAgain, badgeUnlocked }

/// Vocalized text mirrored in the UI speech bubble (accessibility +
/// hearing-impairment mode groundwork).
const Map<MascotLine, String> mascotLineTextAr = {
  MascotLine.greeting: 'أَهْلًا! أَنَا لَفُّوظ',
  MascotLine.praise: 'أَحْسَنْت! رَائِع',
  MascotLine.tryAgain: 'قَرِيب! حَاوِلْ مَرَّةً أُخْرَى',
  MascotLine.badgeUnlocked: 'مَبْرُوك! شَارَةٌ جَدِيدَة',
};

abstract class MascotVoice {
  Future<void> play(MascotLine line);
  Future<void> dispose();
}

class AssetMascotVoice implements MascotVoice {
  final AudioPlayer _player = AudioPlayer();

  static const Map<MascotLine, String> _assets = {
    MascotLine.greeting: 'audio/mascot/greeting.wav',
    MascotLine.praise: 'audio/mascot/praise.wav',
    MascotLine.tryAgain: 'audio/mascot/try_again.wav',
    MascotLine.badgeUnlocked: 'audio/mascot/badge.wav',
  };

  @override
  Future<void> play(MascotLine line) async {
    try {
      await _player.stop();
      await _player.play(AssetSource(_assets[line]!));
    } catch (_) {
      // Voice is enhancement, never a blocker (e.g. autoplay restrictions).
    }
  }

  @override
  Future<void> dispose() => _player.dispose();
}
