/**
 * Bilingual support.
 *
 * Arabic is not an afterthought here: the locale drives the document
 * direction, the numeral system and the calendar, and every metric the API
 * returns already carries both an English and an Arabic label. Translating
 * chrome while leaving indicator names in English is the usual failure
 * mode of "bilingual" hospital dashboards, and it makes them unusable for
 * the Arabic-first half of the audience.
 */

import ar from '@/messages/ar.json';
import en from '@/messages/en.json';

export const LOCALES = ['en', 'ar'] as const;
export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = 'en';

const DICTIONARIES: Record<Locale, Record<string, string>> = { en, ar };

export function isLocale(value: string): value is Locale {
  return (LOCALES as readonly string[]).includes(value);
}

export function direction(locale: Locale): 'rtl' | 'ltr' {
  return locale === 'ar' ? 'rtl' : 'ltr';
}

export function translator(locale: Locale) {
  const dictionary = DICTIONARIES[locale] ?? DICTIONARIES[DEFAULT_LOCALE];
  return (key: string, fallback?: string): string =>
    dictionary[key] ?? fallback ?? DICTIONARIES[DEFAULT_LOCALE][key] ?? key;
}

/** Pick the label the API supplied for the active locale. */
export function localisedLabel(
  locale: Locale,
  labelEn: string,
  labelAr?: string | null,
): string {
  if (locale === 'ar' && labelAr) return labelAr;
  return labelEn;
}

/**
 * Arabic hospital reporting in the Gulf overwhelmingly uses Western
 * digits, so `latn` is forced rather than letting the locale default to
 * Arabic-Indic numerals. Clinical staff read both, but mixed numeral
 * systems across a dashboard are genuinely hard to scan.
 */
export function formatNumber(
  value: number | null | undefined,
  locale: Locale,
  digits = 1,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return new Intl.NumberFormat(locale === 'ar' ? 'ar-SA-u-nu-latn' : 'en-GB', {
    minimumFractionDigits: Number.isInteger(value) ? 0 : digits,
    maximumFractionDigits: digits,
  }).format(value);
}

export function formatDate(value: string, locale: Locale): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale === 'ar' ? 'ar-SA-u-nu-latn-ca-gregory' : 'en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }).format(date);
}

/** Units are rendered next to the number, so they need translating too. */
const UNIT_LABELS: Record<string, { en: string; ar: string }> = {
  '%': { en: '%', ar: '٪' },
  min: { en: 'min', ar: 'دقيقة' },
  hours: { en: 'hrs', ar: 'ساعة' },
  days: { en: 'days', ar: 'يوم' },
  patients: { en: 'patients', ar: 'مريض' },
  visits: { en: 'visits', ar: 'زيارة' },
  score: { en: '', ar: '' },
  NPS: { en: 'NPS', ar: 'NPS' },
  'per 1000 patient days': { en: '/1k pt-days', ar: '/١٠٠٠ يوم مريض' },
  'per 1000 discharges': { en: '/1k disch.', ar: '/١٠٠٠ خروج' },
  'patients/RN': { en: 'pt/RN', ar: 'مريض/ممرض' },
  'patients/day': { en: 'pt/day', ar: 'مريض/يوم' },
  'discharges/bed': { en: 'disch./bed', ar: 'خروج/سرير' },
};

export function formatUnit(unit: string, locale: Locale): string {
  const entry = UNIT_LABELS[unit];
  if (!entry) return unit;
  return locale === 'ar' ? entry.ar : entry.en;
}
