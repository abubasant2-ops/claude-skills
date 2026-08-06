import { notFound } from 'next/navigation';
import { ErrorState, Panel } from '@/components/panels';
import { CommandNav, LocaleToggle, PageHeader } from '@/components/shell';
import { UploadForm } from './upload-form';
import { ApiError, getImportBatches } from '@/lib/api';
import { formatNumber, isLocale, translator, type Locale } from '@/lib/i18n';

export const dynamic = 'force-dynamic';

const STATE_TONE: Record<string, string> = {
  LOADED: 'text-status-green',
  VALIDATED: 'text-status-amber',
  REJECTED: 'text-status-red',
  REVERSED: 'text-ink-faint',
};

function qualityTone(score: number | null): string {
  if (score === null) return 'text-ink-faint';
  if (score >= 90) return 'text-status-green';
  if (score >= 70) return 'text-status-amber';
  return 'text-status-red';
}

export default async function ImportPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ facility?: string }>;
}) {
  const { locale: rawLocale } = await params;
  const { facility } = await searchParams;
  if (!isLocale(rawLocale)) notFound();
  const locale: Locale = rawLocale;
  const t = translator(locale);
  const facilityId = facility ? Number(facility) : 1;

  let batches: any[] = [];
  let loadError: string | null = null;
  try {
    batches = (await getImportBatches(facilityId)).batches;
  } catch (error) {
    loadError = error instanceof ApiError ? error.message : 'Unexpected error.';
  }

  return (
    <div className="space-y-4">
      <PageHeader locale={locale} title={t('import.title')}>
        <LocaleToggle locale={locale} path="/import" />
      </PageHeader>
      <CommandNav locale={locale} activeSlug="" preset="last_30d" />

      <Panel title={t('import.title')} subtitle={t('import.intro')}>
        <UploadForm facilityId={facilityId} locale={locale} />
      </Panel>

      {loadError ? (
        <ErrorState title={t('error.title')} message={loadError} hint={t('error.hint')} />
      ) : (
        <Panel title={t('import.batches')}>
          {batches.length === 0 ? (
            <p className="text-sm text-ink-muted">{t('label.noData')}</p>
          ) : (
            <div className="scroll-x">
              <table className="data">
                <thead>
                  <tr>
                    <th>{t('import.dataset')}</th>
                    <th>{t('import.file')}</th>
                    <th className="text-end">{t('import.rows')}</th>
                    <th className="text-end">{t('import.loaded')}</th>
                    <th className="text-end">{t('import.rejected')}</th>
                    <th className="text-end">{t('import.quality')}</th>
                    <th>{t('import.state')}</th>
                    <th>{t('import.uploaded')}</th>
                  </tr>
                </thead>
                <tbody>
                  {batches.map((batch) => (
                    <tr key={batch.batch_id}>
                      <td className="font-medium">{batch.dataset}</td>
                      <td className="max-w-[220px] truncate text-ink-muted" title={batch.filename}>
                        {batch.filename}
                      </td>
                      <td className="text-end tabular-nums">
                        {formatNumber(batch.row_count, locale, 0)}
                      </td>
                      <td className="text-end tabular-nums">
                        {formatNumber(batch.accepted_rows, locale, 0)}
                      </td>
                      <td
                        className={`text-end tabular-nums ${
                          batch.rejected_rows > 0 ? 'text-status-amber' : ''
                        }`}
                      >
                        {formatNumber(batch.rejected_rows, locale, 0)}
                      </td>
                      <td
                        className={`text-end tabular-nums font-semibold ${qualityTone(
                          batch.quality_score,
                        )}`}
                      >
                        {batch.quality_score === null
                          ? '—'
                          : formatNumber(batch.quality_score, locale)}
                      </td>
                      <td className={STATE_TONE[batch.state] ?? ''}>{batch.state}</td>
                      <td className="text-xs text-ink-muted">
                        {String(batch.uploaded_at ?? '').replace('T', ' ').slice(0, 16)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      )}
    </div>
  );
}
