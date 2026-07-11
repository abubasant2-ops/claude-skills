import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../data/models/screening.dart';
import '../../data/services/screening_api_client.dart';

const Map<String, String> _redFlagAr = {
  'no_words_by_18m': 'لا كلمات مفردة عند عمر ١٨ شهرًا',
  'under_50_words_by_24m': 'أقل من ٥٠ كلمة عند عمر سنتين',
  'no_two_word_combos_by_24m': 'لا يجمع كلمتين عند عمر سنتين',
  'unintelligible_at_4y': 'كلامه غير مفهوم للغرباء بعد ٤ سنوات',
  'regression': 'فقدان مهارات سابقة (نكوص)',
  'suspected_hearing_loss': 'اشتباه ضعف سمع',
};

/// L1 — parent screening: red-flag questions + vocabulary checklist +
/// intelligibility rating. Evaluation happens server-side; the result is
/// shown as a traffic light with a plain-Arabic recommendation.
class ScreeningScreen extends StatefulWidget {
  const ScreeningScreen({super.key, required this.screeningApi});

  final ScreeningApiClient screeningApi;

  @override
  State<ScreeningScreen> createState() => _ScreeningScreenState();
}

class _ScreeningScreenState extends State<ScreeningScreen> {
  late Future<ScreeningQuestionnaire> _questionnaire;
  final Map<String, bool> _redFlagAnswers = {};
  final Set<String> _vocabularyChecked = {};
  int? _intelligibility;
  bool _submitting = false;
  ScreeningResult? _result;

  @override
  void initState() {
    super.initState();
    _questionnaire = widget.screeningApi.fetchQuestionnaire();
  }

  Future<void> _submit() async {
    setState(() => _submitting = true);
    try {
      final result = await widget.screeningApi.submit(
        redFlagAnswers: _redFlagAnswers,
        vocabularyChecked: _vocabularyChecked.toList(),
        intelligibility: _intelligibility,
      );
      if (!mounted) return;
      setState(() => _result = result);
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('تعذّر إرسال الفحص، حاولوا مرة أخرى')),
      );
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('الفحص المبدئي')),
      body: _result != null
          ? _ResultView(result: _result!)
          : FutureBuilder<ScreeningQuestionnaire>(
              future: _questionnaire,
              builder: (context, snapshot) {
                if (snapshot.hasError) {
                  return const Center(
                      child: Text('تعذّر تحميل الأسئلة من الخادم'));
                }
                if (!snapshot.hasData) {
                  return const Center(child: CircularProgressIndicator());
                }
                return _buildForm(snapshot.data!);
              },
            ),
    );
  }

  Widget _buildForm(ScreeningQuestionnaire q) {
    final answeredAll =
        q.redFlagQuestions.every((rq) => _redFlagAnswers.containsKey(rq.id)) &&
            (q.intelligibilityOptions.isEmpty || _intelligibility != null);
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        const Text(
          'أجيبوا عن الأسئلة التالية عن طفلكم — يستغرق الفحص نحو ٥ دقائق.',
          style: TextStyle(color: Colors.black54),
        ),
        const SizedBox(height: 16),
        for (final question in q.redFlagQuestions) ...[
          _YesNoQuestion(
            key: Key('q-${question.id}'),
            text: question.textAr,
            value: _redFlagAnswers[question.id],
            onChanged: (v) =>
                setState(() => _redFlagAnswers[question.id] = v),
          ),
          const SizedBox(height: 10),
        ],
        if (q.vocabularyWords.isNotEmpty) ...[
          const SizedBox(height: 8),
          const Text('أي هذه الكلمات يقولها طفلكم؟',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final word in q.vocabularyWords)
                FilterChip(
                  label: Text(word),
                  selected: _vocabularyChecked.contains(word),
                  selectedColor: LafzaColors.teal.withValues(alpha: 0.2),
                  onSelected: (on) => setState(() => on
                      ? _vocabularyChecked.add(word)
                      : _vocabularyChecked.remove(word)),
                ),
            ],
          ),
        ],
        if (q.intelligibilityOptions.isNotEmpty) ...[
          const SizedBox(height: 18),
          const Text('كم يفهم الغرباء من كلام طفلكم؟',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
          RadioGroup<int>(
            groupValue: _intelligibility,
            onChanged: (v) => setState(() => _intelligibility = v),
            child: Column(
              children: [
                for (final option in q.intelligibilityOptions)
                  RadioListTile<int>(
                    key: Key('intel-${option.value}'),
                    title: Text(option.textAr),
                    value: option.value,
                  ),
              ],
            ),
          ),
        ],
        const SizedBox(height: 20),
        FilledButton(
          key: const Key('submit-screening'),
          onPressed: answeredAll && !_submitting ? _submit : null,
          child: Text(_submitting ? 'جارٍ التقييم…' : 'عرض النتيجة'),
        ),
        const SizedBox(height: 30),
      ],
    );
  }
}

class _YesNoQuestion extends StatelessWidget {
  const _YesNoQuestion({
    super.key,
    required this.text,
    required this.value,
    required this.onChanged,
  });

  final String text;
  final bool? value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(14),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        child: Row(
          children: [
            Expanded(child: Text(text, style: const TextStyle(fontSize: 15))),
            const SizedBox(width: 8),
            ChoiceChip(
              label: const Text('نعم'),
              selected: value == true,
              selectedColor: LafzaColors.teal.withValues(alpha: 0.2),
              onSelected: (_) => onChanged(true),
            ),
            const SizedBox(width: 6),
            ChoiceChip(
              label: const Text('لا'),
              selected: value == false,
              selectedColor: LafzaColors.saffron.withValues(alpha: 0.3),
              onSelected: (_) => onChanged(false),
            ),
          ],
        ),
      ),
    );
  }
}

class _ResultView extends StatelessWidget {
  const _ResultView({required this.result});

  final ScreeningResult result;

  Color get _color => switch (result.trafficLight) {
        'green' => LafzaColors.success,
        'amber' => LafzaColors.saffron,
        _ => LafzaColors.alert,
      };

  String get _title => switch (result.trafficLight) {
        'green' => 'لا مؤشرات مقلقة',
        'amber' => 'يحتاج متابعة',
        _ => 'يحتاج تقييمًا متخصصًا',
      };

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        Center(
          child: Container(
            width: 120,
            height: 120,
            decoration: BoxDecoration(shape: BoxShape.circle, color: _color),
            child: Center(
              child: Text(
                '${result.severity}/4',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 30,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
          ),
        ),
        const SizedBox(height: 16),
        Center(
          child: Text(
            _title,
            style: TextStyle(
                fontSize: 22, fontWeight: FontWeight.bold, color: _color),
          ),
        ),
        const SizedBox(height: 16),
        Material(
          color: Colors.white,
          borderRadius: BorderRadius.circular(16),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Text(result.recommendationAr,
                style: const TextStyle(height: 1.8)),
          ),
        ),
        if (result.redFlags.isNotEmpty) ...[
          const SizedBox(height: 16),
          const Text('المؤشرات المرصودة:',
              style: TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          for (final flag in result.redFlags)
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(
                children: [
                  Icon(Icons.flag_rounded, size: 18, color: _color),
                  const SizedBox(width: 8),
                  Expanded(child: Text(_redFlagAr[flag] ?? flag)),
                ],
              ),
            ),
        ],
        const SizedBox(height: 20),
        OutlinedButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('العودة إلى ركن الوالدين'),
        ),
      ],
    );
  }
}
