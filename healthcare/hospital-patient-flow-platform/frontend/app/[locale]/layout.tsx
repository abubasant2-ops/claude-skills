import { notFound } from 'next/navigation';
import { DEFAULT_LOCALE, LOCALES, direction, isLocale, translator } from '@/lib/i18n';

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

/**
 * Owns `lang` and `dir`. Setting the direction on the document rather than
 * on a wrapper is what lets Tailwind's logical properties (ms-, ps-,
 * text-start) mirror the whole interface for Arabic without a second
 * stylesheet.
 */
export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();

  const t = translator(locale);

  return (
    <html lang={locale} dir={direction(locale)}>
      <body>
        <div className="mx-auto max-w-[1600px] px-4 py-4 sm:px-6 lg:px-8">
          {children}
          <footer className="mt-8 border-t border-canvas-border pt-4 text-xs text-ink-faint">
            {t('app.title')} · {t('app.subtitle')}
          </footer>
        </div>
      </body>
    </html>
  );
}

export const dynamicParams = false;
export { DEFAULT_LOCALE };
