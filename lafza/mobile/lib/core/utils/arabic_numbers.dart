const List<String> _arabicIndicDigits = [
  '٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩', //
];

/// 128 → «١٢٨» — Eastern Arabic numerals for child-facing counters.
String toArabicIndicDigits(int value) => value
    .toString()
    .split('')
    .map((c) => c == '-' ? '-' : _arabicIndicDigits[int.parse(c)])
    .join();
