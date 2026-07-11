import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

/// Thin seam over the microphone so screens stay testable and the
/// implementation can change without touching callers.
abstract class MissionRecorder {
  Future<bool> hasPermission();
  Future<void> start();

  /// Returns the local file path (or blob URL on web) of the utterance.
  Future<String?> stop();

  Future<void> dispose();
}

class RecordMissionRecorder implements MissionRecorder {
  final AudioRecorder _recorder = AudioRecorder();

  @override
  Future<bool> hasPermission() => _recorder.hasPermission();

  @override
  Future<void> start() async {
    // Local-only capture; nothing is uploaded in Phase B. The temp file is
    // never logged and real retention/purge is the backend's job (Phase C).
    String path = '';
    if (!kIsWeb) {
      final dir = await getTemporaryDirectory();
      path = '${dir.path}/utterance_${DateTime.now().millisecondsSinceEpoch}.m4a';
    }
    // Browsers' MediaRecorder has no AAC support — opus/webm there.
    final AudioEncoder encoder =
        kIsWeb ? AudioEncoder.opus : AudioEncoder.aacLc;
    await _recorder.start(RecordConfig(encoder: encoder), path: path);
  }

  @override
  Future<String?> stop() => _recorder.stop();

  @override
  Future<void> dispose() => _recorder.dispose();
}
