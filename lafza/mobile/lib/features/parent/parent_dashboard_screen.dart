import 'package:flutter/material.dart';

import '../../core/audio/mascot_voice.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/arabic_numbers.dart';
import '../../core/widgets/stimulus_icons.dart';
import '../../data/models/parent_summary.dart';
import '../../data/models/stimulus_item.dart';
import '../../data/services/gamification_service.dart';
import '../../data/services/parent_api_client.dart';
import '../../data/services/reminder_settings.dart';
import '../../data/services/scoring_client.dart';
import '../mission/mission_player_screen.dart';

const Map<String, String> _errorTypeAr = {
  'lateralization': 'لثغة جانبية',
  'substitution': 'إبدال',
  'distortion': 'تحريف',
  'omission': 'حذف',
};

/// P1–P3 — parent corner: streak + weekly minutes dashboard, daily home
/// program (the 3 auto-picked missions), daily reminder preference, and a
/// simplified weekly report. All numbers come from the backend summary.
class ParentDashboardScreen extends StatefulWidget {
  const ParentDashboardScreen({
    super.key,
    required this.parentApi,
    required this.gamification,
    required this.reminders,
    required this.scoringClient,
    required this.voice,
  });

  final ParentApiClient parentApi;
  final GamificationService gamification;
  final ReminderSettings reminders;
  final ScoringClient scoringClient;
  final MascotVoice voice;

  @override
  State<ParentDashboardScreen> createState() => _ParentDashboardScreenState();
}

class _ParentDashboardScreenState extends State<ParentDashboardScreen> {
  late Future<ParentSummary> _summary;

  @override
  void initState() {
    super.initState();
    _summary = widget.parentApi.fetchSummary();
  }

  void _reload() =>
      setState(() => _summary = widget.parentApi.fetchSummary());

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('ركن الوالدين')),
      body: FutureBuilder<ParentSummary>(
        future: _summary,
        builder: (context, snapshot) {
          if (snapshot.hasError) {
            return Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Text('تعذّر تحميل البيانات من الخادم'),
                  const SizedBox(height: 12),
                  FilledButton(
                    onPressed: _reload,
                    child: const Text('إعادة المحاولة'),
                  ),
                ],
              ),
            );
          }
          if (!snapshot.hasData) {
            return const Center(child: CircularProgressIndicator());
          }
          final summary = snapshot.data!;
          return RefreshIndicator(
            onRefresh: () async => _reload(),
            child: ListView(
              padding: const EdgeInsets.all(20),
              children: [
                _StatsRow(summary: summary),
                const SizedBox(height: 16),
                _WeekBars(daily: summary.daily),
                const SizedBox(height: 24),
                _HomeProgram(
                  gamification: widget.gamification,
                  onOpenMission: _openMission,
                ),
                const SizedBox(height: 24),
                _ReminderCard(reminders: widget.reminders),
                const SizedBox(height: 24),
                _WeeklyReport(summary: summary),
              ],
            ),
          );
        },
      ),
    );
  }

  Future<void> _openMission(String missionId, StimulusItem stimulus) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => MissionPlayerScreen(
          stimulus: stimulus,
          missionId: missionId,
          gamification: widget.gamification,
          voice: widget.voice,
          scoringClient: widget.scoringClient,
        ),
      ),
    );
    _reload(); // practice may have changed minutes/report
  }
}

class _StatsRow extends StatelessWidget {
  const _StatsRow({required this.summary});

  final ParentSummary summary;

  @override
  Widget build(BuildContext context) {
    final minutes = (summary.weekPracticeSeconds / 60).ceil();
    return Row(
      children: [
        Expanded(
          child: _StatCard(
            icon: Icons.local_fire_department_rounded,
            color: LafzaColors.saffron,
            value: toArabicIndicDigits(summary.streakDays),
            label: 'سلسلة الأيام',
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _StatCard(
            icon: Icons.timer_rounded,
            color: LafzaColors.teal,
            value: toArabicIndicDigits(minutes),
            label: 'دقائق الأسبوع',
          ),
        ),
      ],
    );
  }
}

class _StatCard extends StatelessWidget {
  const _StatCard({
    required this.icon,
    required this.color,
    required this.value,
    required this.label,
  });

  final IconData icon;
  final Color color;
  final String value;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        boxShadow: const [
          BoxShadow(color: Colors.black12, blurRadius: 6, offset: Offset(0, 2)),
        ],
      ),
      child: Column(
        children: [
          Icon(icon, size: 34, color: color),
          const SizedBox(height: 6),
          Text(
            value,
            style: TextStyle(
              fontSize: 30,
              fontWeight: FontWeight.bold,
              color: color,
            ),
          ),
          Text(label, style: const TextStyle(color: LafzaColors.navy)),
        ],
      ),
    );
  }
}

class _WeekBars extends StatelessWidget {
  const _WeekBars({required this.daily});

  final List<DailyPractice> daily;

  @override
  Widget build(BuildContext context) {
    final int maxSeconds =
        daily.fold(0, (m, d) => d.seconds > m ? d.seconds : m);
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('تدريب آخر ٧ أيام',
              style: TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 12),
          SizedBox(
            height: 64,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                for (final d in daily)
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 3),
                      child: Container(
                        height: maxSeconds == 0
                            ? 4
                            : 4 + 56 * d.seconds / maxSeconds,
                        decoration: BoxDecoration(
                          color: d.seconds > 0
                              ? LafzaColors.teal
                              : Colors.black12,
                          borderRadius: BorderRadius.circular(4),
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _HomeProgram extends StatelessWidget {
  const _HomeProgram({
    required this.gamification,
    required this.onOpenMission,
  });

  final GamificationService gamification;
  final void Function(String missionId, StimulusItem stimulus) onOpenMission;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: gamification,
      builder: (context, _) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'البرنامج المنزلي اليوم '
            '(${toArabicIndicDigits(gamification.completedTodayCount)}/'
            '${toArabicIndicDigits(gamification.todaysMissions.length)})',
            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
          ),
          const SizedBox(height: 10),
          for (final mission in gamification.todaysMissions)
            Card(
              color: Colors.white,
              child: ListTile(
                leading: Icon(
                  stimulusIcon(mission.stimulus.picture),
                  color: LafzaColors.teal,
                ),
                title: Text(mission.titleAr, style: AppTheme.childWord.copyWith(fontSize: 20)),
                subtitle: Text('حرف «${mission.stimulus.targetPhoneme}»'),
                trailing: gamification.isCompleted(mission.id)
                    ? const Icon(Icons.check_circle_rounded,
                        color: LafzaColors.success)
                    : const Icon(Icons.play_circle_rounded,
                        color: LafzaColors.saffron),
                onTap: () => onOpenMission(mission.id, mission.stimulus),
              ),
            ),
        ],
      ),
    );
  }
}

class _ReminderCard extends StatelessWidget {
  const _ReminderCard({required this.reminders});

  final ReminderSettings reminders;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: reminders,
      builder: (context, _) => Material(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        child: Column(
          children: [
            SwitchListTile(
              key: const Key('reminder-switch'),
              title: const Text('تذكير يومي بالتمرين',
                  style: TextStyle(fontWeight: FontWeight.bold)),
              subtitle: Text(
                reminders.enabled
                    ? 'سنذكّركم يوميًا عند ${_formatTime(reminders.time)}'
                    : 'التذكير متوقف',
              ),
              value: reminders.enabled,
              onChanged: reminders.setEnabled,
            ),
            if (reminders.enabled)
              ListTile(
                key: const Key('reminder-time'),
                leading: const Icon(Icons.schedule_rounded,
                    color: LafzaColors.teal),
                title: Text('وقت التذكير: ${_formatTime(reminders.time)}'),
                onTap: () async {
                  final picked = await showTimePicker(
                    context: context,
                    initialTime: reminders.time,
                  );
                  if (picked != null) reminders.setTime(picked);
                },
              ),
          ],
        ),
      ),
    );
  }

  String _formatTime(TimeOfDay t) {
    final h = toArabicIndicDigits(t.hour);
    final m = t.minute.toString().padLeft(2, '0');
    return '$h:${toArabicIndicDigits(int.parse(m)).padLeft(2, '٠')}';
  }
}

class _WeeklyReport extends StatelessWidget {
  const _WeeklyReport({required this.summary});

  final ParentSummary summary;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'تقرير الأسبوع (${toArabicIndicDigits(summary.weekAttempts)} محاولة)',
          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
        ),
        const SizedBox(height: 10),
        if (summary.plan != null)
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(12),
            margin: const EdgeInsets.only(bottom: 10),
            decoration: BoxDecoration(
              color: LafzaColors.teal.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Text(
              'أهداف الخطة: ${summary.plan!.targetPhonemes.join(' ، ')} '
              '(${summary.plan!.status == 'draft' ? 'بانتظار اعتماد الأخصائي' : summary.plan!.status})',
              style: const TextStyle(color: LafzaColors.navy),
            ),
          ),
        if (summary.phonemes.isEmpty)
          const Text('لا يوجد تدريب هذا الأسبوع بعد')
        else
          for (final row in summary.phonemes)
            Card(
              color: Colors.white,
              child: ListTile(
                leading: CircleAvatar(
                  backgroundColor: LafzaColors.teal,
                  child: Text(
                    row.phoneme,
                    style: const TextStyle(color: Colors.white, fontSize: 20),
                  ),
                ),
                title: Row(
                  children: [
                    Text(
                      toArabicIndicDigits(row.latestGop),
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 20,
                        color: row.latestGop >= 70
                            ? LafzaColors.success
                            : LafzaColors.saffron,
                      ),
                    ),
                    const SizedBox(width: 6),
                    if (row.delta != 0)
                      Icon(
                        row.delta > 0
                            ? Icons.trending_up_rounded
                            : Icons.trending_down_rounded,
                        size: 20,
                        color: row.delta > 0
                            ? LafzaColors.success
                            : LafzaColors.alert,
                      ),
                  ],
                ),
                subtitle: Text(
                  '${toArabicIndicDigits(row.attempts)} محاولات'
                  '${row.latestErrorType != null ? ' · ${_errorTypeAr[row.latestErrorType] ?? row.latestErrorType}' : ''}',
                ),
              ),
            ),
      ],
    );
  }
}
