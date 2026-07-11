import 'package:flutter/material.dart';

import '../../core/audio/mission_recorder.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/arabic_numbers.dart';
import '../../data/models/stimulus_item.dart';
import '../../data/services/mock_scoring_service.dart';

enum _PlayerState { idle, recording, analyzing, result }

/// S2 — mission player: stimulus card (picture + vocalized word + listen
/// button) and a big mic button. Records locally, then shows a mock GOP
/// result ring. No backend calls in Phase B.
class MissionPlayerScreen extends StatefulWidget {
  MissionPlayerScreen({
    super.key,
    required this.stimulus,
    MissionRecorder? recorder,
    MockScoringService? scoringService,
  })  : recorder = recorder ?? RecordMissionRecorder(),
        scoringService = scoringService ?? MockScoringService();

  final StimulusItem stimulus;
  final MissionRecorder recorder;
  final MockScoringService scoringService;

  @override
  State<MissionPlayerScreen> createState() => _MissionPlayerScreenState();
}

class _MissionPlayerScreenState extends State<MissionPlayerScreen> {
  _PlayerState _state = _PlayerState.idle;
  ScoreResult? _result;

  /// Per-session guardian consent (hard rule 5). Replaced by the child's
  /// stored consent_flags check when the backend is wired in (Phase C).
  bool _consentGranted = false;

  @override
  void dispose() {
    widget.recorder.dispose();
    super.dispose();
  }

  Future<bool> _ensureGuardianConsent() async {
    if (_consentGranted) return true;
    final bool? agreed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('مُوَافَقَةُ وَلِيِّ الأَمْر'),
        content: const Text(
          'يَحْتَاجُ تَسْجِيلُ صَوْتِ الطِّفْلِ إِلَى مُوَافَقَةِ وَلِيِّ الأَمْرِ قَبْلَ البَدْءِ. '
          'التَّسْجِيلُ مَحَلِّيٌّ فَقَط فِي هٰذِهِ المَرْحَلَة.',
          style: TextStyle(height: 1.8),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('لَيْسَ الآن'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('أُوَافِق'),
          ),
        ],
      ),
    );
    _consentGranted = agreed ?? false;
    return _consentGranted;
  }

  Future<void> _startRecording() async {
    if (!await _ensureGuardianConsent()) return;
    if (!await widget.recorder.hasPermission()) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('لَمْ يُسْمَحْ بِاسْتِخْدَامِ المَيكرُوفُون')),
      );
      return;
    }
    try {
      await widget.recorder.start();
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('تَعَذَّرَ بَدْءُ التَّسْجِيل، حَاوِلْ مَرَّةً أُخْرَى')),
      );
      return;
    }
    if (!mounted) return;
    setState(() => _state = _PlayerState.recording);
  }

  Future<void> _stopRecording() async {
    final String? audioPath = await widget.recorder.stop();
    if (!mounted) return;
    setState(() => _state = _PlayerState.analyzing);

    // Mock latency so the child sees the analyzing state; the real scoring
    // round-trip replaces this in Phase C.
    await Future<void>.delayed(const Duration(milliseconds: 1500));
    if (!mounted) return;
    setState(() {
      _result = widget.scoringService.scoreUtterance(
        targetPhoneme: widget.stimulus.targetPhoneme,
        position: widget.stimulus.position,
        audioPath: audioPath,
      );
      _state = _PlayerState.result;
    });
  }

  void _reset() => setState(() {
        _result = null;
        _state = _PlayerState.idle;
      });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('مُهِمَّةُ حَرْفِ «${widget.stimulus.targetPhoneme}»'),
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            children: [
              Expanded(
                flex: 5,
                child: Center(
                  child: FittedBox(
                    fit: BoxFit.scaleDown,
                    child: _StimulusCard(stimulus: widget.stimulus),
                  ),
                ),
              ),
              Expanded(
                flex: 4,
                child: Center(
                  child: FittedBox(
                    fit: BoxFit.scaleDown,
                    child: _buildStateArea(),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildStateArea() {
    switch (_state) {
      case _PlayerState.idle:
        return _MicButton(onPressed: _startRecording);
      case _PlayerState.recording:
        return _RecordingIndicator(onStop: _stopRecording);
      case _PlayerState.analyzing:
        return const _AnalyzingIndicator();
      case _PlayerState.result:
        return _ResultView(result: _result!, onRetry: _reset);
    }
  }
}

class _StimulusCard extends StatelessWidget {
  const _StimulusCard({required this.stimulus});

  final StimulusItem stimulus;

  IconData get _pictureIcon => switch (stimulus.picture) {
        StimulusPicture.sun => Icons.wb_sunny_rounded,
      };

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Colors.white,
      elevation: 3,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 40, vertical: 28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(_pictureIcon, size: 110, color: LafzaColors.saffron),
            const SizedBox(height: 12),
            Text(
              stimulus.wordAr,
              style: AppTheme.childWord.copyWith(
                fontSize: 44,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 8),
            IconButton.filledTonal(
              iconSize: 34,
              tooltip: 'اِسْتَمِعْ لِلنُّطْقِ الصَّحِيح',
              onPressed: () {
                // Model-pronunciation audio arrives with library content
                // (Phase C); button is wired so the layout is final.
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                    content: Text('سَتَسْمَعُ النُّطْقَ النَّمُوذَجِيَّ هُنَا قَرِيبًا'),
                  ),
                );
              },
              icon: const Icon(Icons.volume_up_rounded),
            ),
          ],
        ),
      ),
    );
  }
}

class _MicButton extends StatelessWidget {
  const _MicButton({required this.onPressed});

  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          width: 96,
          height: 96,
          child: FilledButton(
            key: const Key('mic-button'),
            style: FilledButton.styleFrom(
              shape: const CircleBorder(),
              backgroundColor: LafzaColors.teal,
              padding: EdgeInsets.zero,
            ),
            onPressed: onPressed,
            child: const Icon(Icons.mic_rounded, size: 48, color: Colors.white),
          ),
        ),
        const SizedBox(height: 12),
        const Text('اِضْغَطْ وَقُلِ الكَلِمَة', style: AppTheme.childWord),
      ],
    );
  }
}

class _RecordingIndicator extends StatelessWidget {
  const _RecordingIndicator({required this.onStop});

  final VoidCallback onStop;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          width: 96,
          height: 96,
          child: FilledButton(
            key: const Key('stop-button'),
            style: FilledButton.styleFrom(
              shape: const CircleBorder(),
              backgroundColor: LafzaColors.alert,
              padding: EdgeInsets.zero,
            ),
            onPressed: onStop,
            child:
                const Icon(Icons.stop_rounded, size: 48, color: Colors.white),
          ),
        ),
        const SizedBox(height: 12),
        const Text('جَارِي التَّسْجِيل…', style: AppTheme.childWord),
      ],
    );
  }
}

class _AnalyzingIndicator extends StatelessWidget {
  const _AnalyzingIndicator();

  @override
  Widget build(BuildContext context) {
    return const Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          width: 72,
          height: 72,
          child: CircularProgressIndicator(
            strokeWidth: 7,
            color: LafzaColors.saffron,
          ),
        ),
        SizedBox(height: 16),
        Text('قَيْدَ التَّحْلِيل…', style: AppTheme.childWord),
      ],
    );
  }
}

class _ResultView extends StatelessWidget {
  const _ResultView({required this.result, required this.onRetry});

  final ScoreResult result;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        GopRing(score: result.gopScore),
        const SizedBox(height: 12),
        Text(
          result.isGood ? 'أَحْسَنْتَ! رَائِع' : 'قَرِيب! حَاوِلْ مَرَّةً أُخْرَى',
          style: AppTheme.childWord.copyWith(
            color: result.isGood ? LafzaColors.success : LafzaColors.saffron,
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(height: 8),
        TextButton.icon(
          onPressed: onRetry,
          icon: const Icon(Icons.replay_rounded),
          label: const Text('مَرَّةً أُخْرَى'),
        ),
      ],
    );
  }
}

/// Score dial: green when good (≥70), amber otherwise (blueprint S2).
class GopRing extends StatelessWidget {
  const GopRing({super.key, required this.score});

  final int score;

  @override
  Widget build(BuildContext context) {
    final Color color =
        score >= 70 ? LafzaColors.success : LafzaColors.saffron;
    return SizedBox(
      width: 132,
      height: 132,
      child: Stack(
        fit: StackFit.expand,
        children: [
          CircularProgressIndicator(
            value: score / 100,
            strokeWidth: 10,
            strokeCap: StrokeCap.round,
            color: color,
            backgroundColor: color.withValues(alpha: 0.15),
          ),
          Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  toArabicIndicDigits(score),
                  style: TextStyle(
                    fontSize: 36,
                    fontWeight: FontWeight.bold,
                    color: color,
                  ),
                ),
                const Text(
                  'مِنْ ١٠٠',
                  style: TextStyle(fontSize: 14, color: LafzaColors.navy),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
