import '../models/stimulus_item.dart';

/// Mock stimulus until the therapy library content lands (Phase C).
/// «شَمْس» targets ش in initial position — the blueprint's demo word.
const StimulusItem mockSunStimulus = StimulusItem(
  id: 'stimulus-sun',
  wordAr: 'شَمْس',
  targetPhoneme: 'ش',
  position: 'initial',
  picture: StimulusPicture.sun,
);
