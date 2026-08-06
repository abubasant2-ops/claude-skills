import { notFound } from 'next/navigation';
import { ForecastChart } from '@/components/charts';
import { ErrorState, Panel } from '@/components/panels';
import { CommandNav, LocaleToggle, PageHeader } from '@/components/shell';
import { ApiError, getPredictions, getTrend } from '@/lib/api';
import { formatNumber, isLocale, translator, type Locale } from '@/lib/i18n';

export const dynamic = 'force-dynamic';

function ModelBadge({
  model,
  locale,
  accuracyLabel,
  skillLabel,
}: {
  model: any;
  locale: Locale;
  accuracyLabel: string;
  skillLabel: string;
}) {
  const skill = model?.skill_vs_baseline_pct;
  return (
    <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-ink-muted">
      <div>
        <dt className="inline">Model: </dt>
        <dd className="inline text-ink">{model?.algorithm ?? 'unavailable'}</dd>
      </div>
      {model?.training_rows && (
        <div>
          <dt className="inline">Trained on: </dt>
          <dd className="inline text-ink">{model.training_rows} days</dd>
        </div>
      )}
      {model?.mae !== undefined && (
        <div>
          <dt className="inline">{accuracyLabel}: </dt>
          <dd className="inline text-ink">±{formatNumber(model.mae, locale)} MAE</dd>
        </div>
      )}
      {skill !== undefined && skill !== null && (
        <div>
          <dt className="inline">{skillLabel}: </dt>
          {/* A negative skill score means the model is not beating a naive
              carry-forward. Showing it is the point: capacity decisions
              should not rest on a model that has not earned them. */}
          <dd className={`inline ${skill > 0 ? 'text-status-green' : 'text-status-amber'}`}>
            {skill > 0 ? '+' : ''}
            {formatNumber(skill, locale)}%
          </dd>
        </div>
      )}
      {model?.fallback_reason && (
        <div className="w-full text-status-amber">
          Falling back to a seasonal baseline: {model.fallback_reason}
        </div>
      )}
    </dl>
  );
}

export default async function ForecastPage({
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

  let predictions: any;
  let history: any;
  try {
    [predictions, history] = await Promise.all([
      getPredictions({ facilityId, horizonDays: 14 }),
      getTrend(['occupancy_rate'], { facilityId, preset: 'last_30d', grain: 'day' }),
    ]);
  } catch (error) {
    const message =
      error instanceof ApiError ? error.message : 'Unexpected error loading forecasts.';
    return (
      <div className="space-y-4">
        <CommandNav locale={locale} activeSlug="" preset="last_30d" />
        <ErrorState title={t('error.title')} message={message} hint={t('error.hint')} />
      </div>
    );
  }

  const occupancy = predictions.occupancy_forecast ?? {};
  const icu = predictions.icu_forecast ?? {};
  const discharges = predictions.discharge_forecast ?? {};
  const crowding = predictions.ed_crowding ?? {};
  const warnings = predictions.bottleneck_warnings ?? [];
  const anomalies = predictions.anomalies ?? [];
  const riskPatients = predictions.high_risk_patients ?? [];

  return (
    <div className="space-y-4">
      <PageHeader locale={locale} title={t('nav.forecast')}>
        <LocaleToggle locale={locale} path="/forecast" />
      </PageHeader>
      <CommandNav locale={locale} activeSlug="" preset="last_30d" />

      <Panel
        title={`${t('label.forecast')} — ${t('table.occupancy')}`}
        subtitle="Shaded band is the 95% interval, widened with the forecast horizon"
      >
        <ForecastChart
          actualLabels={history.labels ?? []}
          actualValues={history.series?.occupancy_rate ?? []}
          forecast={occupancy.points ?? []}
          seriesName={t('table.occupancy')}
          rangeName={t('label.forecastRange')}
        />
        <ModelBadge
          model={occupancy.model}
          locale={locale}
          accuracyLabel={t('label.accuracy')}
          skillLabel={t('label.skill')}
        />
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Critical care utilisation forecast">
          <ForecastChart
            actualLabels={[]}
            actualValues={[]}
            forecast={icu.points ?? []}
            seriesName="ICU"
            rangeName={t('label.forecastRange')}
            height={250}
          />
          <ModelBadge
            model={icu.model}
            locale={locale}
            accuracyLabel={t('label.accuracy')}
            skillLabel={t('label.skill')}
          />
        </Panel>

        <Panel title="Expected discharges">
          <ForecastChart
            actualLabels={[]}
            actualValues={[]}
            forecast={discharges.points ?? []}
            seriesName="Discharges"
            rangeName={t('label.forecastRange')}
            height={250}
          />
          <ModelBadge
            model={discharges.model}
            locale={locale}
            accuracyLabel={t('label.accuracy')}
            skillLabel={t('label.skill')}
          />
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Emergency department crowding risk" subtitle="Four hours ahead">
          {crowding.available ? (
            <div className="space-y-2">
              <p className="text-3xl font-semibold tabular-nums">
                {formatNumber((crowding.probability_overcrowded ?? 0) * 100, locale, 0)}%
                <span
                  className={`ms-3 align-middle text-sm font-medium ${
                    crowding.risk_band === 'HIGH'
                      ? 'text-status-red'
                      : crowding.risk_band === 'MODERATE'
                        ? 'text-status-amber'
                        : 'text-status-green'
                  }`}
                >
                  {crowding.risk_band}
                </span>
              </p>
              <p className="text-xs text-ink-muted">
                Current NEDOCS {formatNumber(crowding.current_nedocs, locale, 0)} · as of{' '}
                {String(crowding.as_of ?? '').replace('T', ' ').slice(0, 16)}
              </p>
              {crowding.model?.metrics?.roc_auc && (
                <p className="text-xs text-ink-faint">
                  Backtest AUC {formatNumber(crowding.model.metrics.roc_auc, locale, 3)}
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-ink-muted">{crowding.reason ?? t('label.noData')}</p>
          )}
        </Panel>

        <Panel title={t('label.warnings')}>
          {warnings.length === 0 ? (
            <p className="text-sm text-status-green">
              No capacity threshold is forecast to be breached in the next 14 days.
            </p>
          ) : (
            <ul className="space-y-2">
              {warnings.slice(0, 6).map((w: any, index: number) => (
                <li
                  key={`${w.date}-${w.kind}-${index}`}
                  className={`rounded-lg border-s-4 bg-white/5 p-3 text-sm ${
                    w.severity === 'CRITICAL' ? 'border-status-red' : 'border-status-amber'
                  }`}
                >
                  <span className="font-medium">{w.date}</span>
                  <span className="ms-2 text-xs uppercase text-ink-muted">{w.kind}</span>
                  <p className="mt-1 text-xs text-ink-muted">
                    {locale === 'ar' && w.message_ar ? w.message_ar : w.message_en}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title={t('label.anomalies')}>
          {anomalies.length === 0 ? (
            <p className="text-sm text-ink-muted">{t('label.noData')}</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {anomalies.slice(0, 8).map((a: any) => (
                <li key={a.service_date} className="rounded-lg bg-white/5 p-3">
                  <span className="font-medium">{a.service_date}</span>
                  <span
                    className={`ms-2 text-xs uppercase ${
                      a.severity === 'CRITICAL' ? 'text-status-red' : 'text-status-amber'
                    }`}
                  >
                    {a.severity}
                  </span>
                  <p className="mt-1 text-xs text-ink-muted">{a.explanation_en}</p>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel
          title={t('label.riskPatients')}
          subtitle="Operational prioritisation aid for the flow team — not a clinical decision tool"
        >
          {riskPatients.length === 0 ? (
            <p className="text-sm text-ink-muted">{t('label.noData')}</p>
          ) : (
            <div className="scroll-x">
              <table className="data">
                <thead>
                  <tr>
                    <th>Encounter</th>
                    <th className="text-end">Risk</th>
                    <th>Main drivers</th>
                  </tr>
                </thead>
                <tbody>
                  {riskPatients.slice(0, 10).map((p: any) => (
                    <tr key={p.encounter_id}>
                      <td className="tabular-nums">{p.encounter_id}</td>
                      <td
                        className={`text-end tabular-nums font-semibold ${
                          p.risk_band === 'HIGH'
                            ? 'text-status-red'
                            : p.risk_band === 'MODERATE'
                              ? 'text-status-amber'
                              : 'text-ink'
                        }`}
                      >
                        {formatNumber(p.risk_probability * 100, locale, 0)}%
                      </td>
                      <td className="text-xs text-ink-muted">
                        {(p.drivers ?? [])
                          .map((d: any) => `${d.feature.replace(/_/g, ' ')}`)
                          .join(', ')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
