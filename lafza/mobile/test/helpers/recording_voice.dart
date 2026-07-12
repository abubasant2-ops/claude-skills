import 'package:lafza_mobile/core/audio/mascot_voice.dart';

/// Test double: records which mascot lines were played instead of using the
/// audioplayers plugin (unavailable in widget tests).
class RecordingVoice implements MascotVoice {
  final List<MascotLine> played = [];

  @override
  Future<void> play(MascotLine line) async => played.add(line);

  @override
  Future<void> dispose() async {}
}
