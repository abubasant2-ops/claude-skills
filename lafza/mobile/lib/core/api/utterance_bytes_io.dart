import 'dart:io';
import 'dart:typed_data';

/// Mobile/desktop: the recorder hands us a real file path.
Future<Uint8List> readUtteranceBytes(String path) => File(path).readAsBytes();
