import '../models/daily_mission.dart';
import '../models/stimulus_item.dart';

/// Mission pool covering 6 of the 12 MVP letters — deterministic content
/// until the full therapy library (Phase D content pipeline) lands.
const List<DailyMission> missionPool = [
  DailyMission(
    id: 'mission-ش',
    stimulus: StimulusItem(
      id: 'stimulus-sun',
      wordAr: 'شَمْس',
      targetPhoneme: 'ش',
      position: 'initial',
      picture: StimulusPicture.sun,
    ),
  ),
  DailyMission(
    id: 'mission-ق',
    stimulus: StimulusItem(
      id: 'stimulus-moon',
      wordAr: 'قَمَر',
      targetPhoneme: 'ق',
      position: 'initial',
      picture: StimulusPicture.moon,
    ),
  ),
  DailyMission(
    id: 'mission-ك',
    stimulus: StimulusItem(
      id: 'stimulus-book',
      wordAr: 'كِتَاب',
      targetPhoneme: 'ك',
      position: 'initial',
      picture: StimulusPicture.book,
    ),
  ),
  DailyMission(
    id: 'mission-ل',
    stimulus: StimulusItem(
      id: 'stimulus-toy',
      wordAr: 'لُعْبَة',
      targetPhoneme: 'ل',
      position: 'initial',
      picture: StimulusPicture.toy,
    ),
  ),
  DailyMission(
    id: 'mission-ر',
    stimulus: StimulusItem(
      id: 'stimulus-head',
      wordAr: 'رَأْس',
      targetPhoneme: 'ر',
      position: 'initial',
      picture: StimulusPicture.face,
    ),
  ),
  DailyMission(
    id: 'mission-ص',
    stimulus: StimulusItem(
      id: 'stimulus-picture',
      wordAr: 'صُورَة',
      targetPhoneme: 'ص',
      position: 'initial',
      picture: StimulusPicture.image,
    ),
  ),
];
