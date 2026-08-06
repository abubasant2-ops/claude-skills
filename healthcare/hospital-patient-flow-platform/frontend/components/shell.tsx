import Link from 'next/link';
import type { Locale } from '@/lib/i18n';
import { formatDate, translator } from '@/lib/i18n';

export const ROLE_ROUTES = [
  { slug: 'ceo', role: 'CEO', key: 'nav.ceo' },
  { slug: 'coo', role: 'COO', key: 'nav.coo' },
  { slug: 'ed', role: 'ED_DIRECTOR', key: 'nav.ed' },
  { slug: 'beds', role: 'BED_MANAGER', key: 'nav.beds' },
  { slug: 'cno', role: 'CNO', key: 'nav.cno' },
  { slug: 'quality', role: 'QUALITY', key: 'nav.quality' },
] as const;

export const PERIOD_PRESETS = ['last_7d', 'last_30d', 'last_90d', 'mtd', 'qtd', 'ytd'] as const;
export type Preset = (typeof PERIOD_PRESETS)[number];

export function roleForSlug(slug: string): string | null {
  return ROLE_ROUTES.find((r) => r.slug === slug)?.role ?? null;
}

export function CommandNav({
  locale,
  activeSlug,
  preset,
}: {
  locale: Locale;
  activeSlug: string;
  preset: string;
}) {
  const t = translator(locale);
  const query = `?preset=${preset}`;

  return (
    <nav
      className="flex flex-wrap items-center gap-1.5"
      aria-label={t('app.title')}
    >
      {ROLE_ROUTES.map((route) => {
        const active = route.slug === activeSlug;
        return (
          <Link
            key={route.slug}
            href={`/${locale}/command/${route.slug}${query}`}
            aria-current={active ? 'page' : undefined}
            className={`rounded-lg px-3 py-1.5 text-sm transition ${
              active
                ? 'bg-accent text-canvas font-semibold'
                : 'bg-white/5 text-ink-muted hover:bg-white/10 hover:text-ink'
            }`}
          >
            {t(route.key)}
          </Link>
        );
      })}
      <span className="mx-1 h-5 w-px bg-canvas-border" aria-hidden="true" />
      <Link
        href={`/${locale}/forecast`}
        className="rounded-lg bg-white/5 px-3 py-1.5 text-sm text-ink-muted transition hover:bg-white/10 hover:text-ink"
      >
        {t('nav.forecast')}
      </Link>
      <Link
        href={`/${locale}/import`}
        className="rounded-lg bg-white/5 px-3 py-1.5 text-sm text-ink-muted transition hover:bg-white/10 hover:text-ink"
      >
        {t('nav.import')}
      </Link>
    </nav>
  );
}

export function PeriodPicker({
  locale,
  basePath,
  active,
}: {
  locale: Locale;
  basePath: string;
  active: string;
}) {
  const t = translator(locale);
  return (
    <div className="flex flex-wrap gap-1" role="group" aria-label={t('label.period')}>
      {PERIOD_PRESETS.map((preset) => (
        <Link
          key={preset}
          href={`${basePath}?preset=${preset}`}
          aria-current={preset === active ? 'true' : undefined}
          className={`rounded-md px-2.5 py-1 text-xs transition ${
            preset === active
              ? 'bg-white/15 font-semibold text-ink'
              : 'text-ink-muted hover:bg-white/10'
          }`}
        >
          {t(`period.${preset}`)}
        </Link>
      ))}
    </div>
  );
}

export function LocaleToggle({
  locale,
  path,
}: {
  locale: Locale;
  path: string;
}) {
  const other: Locale = locale === 'en' ? 'ar' : 'en';
  return (
    <Link
      href={`/${other}${path}`}
      className="rounded-lg border border-canvas-border px-2.5 py-1 text-xs text-ink-muted transition hover:border-accent hover:text-ink"
      lang={other}
      hrefLang={other}
    >
      {other === 'ar' ? 'العربية' : 'English'}
    </Link>
  );
}

export function PageHeader({
  locale,
  title,
  period,
  generatedAt,
  children,
}: {
  locale: Locale;
  title: string;
  period?: { start: string; end: string };
  generatedAt?: string;
  children?: React.ReactNode;
}) {
  const t = translator(locale);
  return (
    <header className="flex flex-wrap items-end justify-between gap-3 border-b border-canvas-border pb-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {period && (
          <p className="mt-0.5 text-xs text-ink-muted">
            {t('label.period')}: {formatDate(period.start, locale)} –{' '}
            {formatDate(period.end, locale)}
            {generatedAt && (
              <>
                {' · '}
                {t('label.generated')} {generatedAt.replace('T', ' ')}
              </>
            )}
          </p>
        )}
      </div>
      {children}
    </header>
  );
}

/**
 * Row counts behind the period.
 *
 * A dashboard that renders identically on 40,000 records and on 12 is a
 * trap; showing the coverage lets a reader judge whether a metric is worth
 * acting on.
 */
export function CoverageBar({
  coverage,
  locale,
}: {
  coverage: Record<string, number>;
  locale: Locale;
}) {
  const t = translator(locale);
  const entries = Object.entries(coverage).filter(([, value]) => value > 0);
  if (entries.length === 0) return null;

  return (
    <p className="text-xs text-ink-faint">
      {t('label.coverage')}:{' '}
      {entries
        .map(([key, value]) => `${key.replace(/_/g, ' ')} ${value.toLocaleString('en-GB')}`)
        .join(' · ')}
    </p>
  );
}
