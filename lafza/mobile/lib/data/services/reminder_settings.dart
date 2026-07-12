import 'package:flutter/material.dart';

/// Daily practice reminder preference (P2).
///
/// Holds the on/off state and time-of-day. Actual OS notification
/// scheduling is wired on device builds (flutter_local_notifications);
/// web has no daily-notification support, so this stays a preference seam.
class ReminderSettings extends ChangeNotifier {
  bool _enabled = false;
  TimeOfDay _time = const TimeOfDay(hour: 18, minute: 0);

  bool get enabled => _enabled;
  TimeOfDay get time => _time;

  void setEnabled(bool value) {
    _enabled = value;
    notifyListeners();
  }

  void setTime(TimeOfDay value) {
    _time = value;
    notifyListeners();
  }
}
