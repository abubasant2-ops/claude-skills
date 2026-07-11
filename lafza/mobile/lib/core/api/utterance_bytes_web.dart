import 'dart:typed_data';

import 'package:http/http.dart' as http;

/// Web: the recorder returns a blob: URL; fetch its bytes in-browser.
Future<Uint8List> readUtteranceBytes(String path) =>
    http.readBytes(Uri.parse(path));
