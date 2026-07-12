import 'package:flutter/material.dart';

import '../../data/models/stimulus_item.dart';

/// Material-icon placeholders per stimulus picture until illustrated
/// assets exist (content pipeline).
IconData stimulusIcon(StimulusPicture picture) => switch (picture) {
      StimulusPicture.sun => Icons.wb_sunny_rounded,
      StimulusPicture.moon => Icons.dark_mode_rounded,
      StimulusPicture.book => Icons.menu_book_rounded,
      StimulusPicture.toy => Icons.toys_rounded,
      StimulusPicture.face => Icons.face_rounded,
      StimulusPicture.image => Icons.image_rounded,
    };
