import { notFound } from 'next/navigation';
import { BottleneckChart, EdHourlyChart, OccupancyHeatmap } from '@/components/charts';
import { MetricGrid } from '@/components/MetricTile';
import {
  AlertPanel,
  BottleneckTable,
  EmptyState,
  ErrorState,
  NursingTable,
  Panel,
  UnitTable,
} from '@/components/panels';
import {
  CommandNav,
  CoverageBar,
  LocaleToggle,
  PageHeader,
  PeriodPicker,
  ROLE_ROUTES,
  roleForSlug,
} from '@/components/shell';
import { ApiError, exportUrl, getDashboard, type DashboardPayload } from '@/lib/api';
import { isLocale, translator, type Locale } from '@/lib/i18n';

export function generateStaticParams() {
  return ROLE_ROUTES.map((route) => ({ role: route.slug }));
}

// Dashboards are recomputed from the warehouse on demand; the API applies
// its own caching, so the page itself is always rendered fresh.
export const dynamic = 'force-dynamic';

export default async function CommandCentre({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string; role: string }>;
  searchParams: Promise<{ preset?: string; facility?: string }>;
}) {
  const { locale: rawLocale, role: slug } = await params;
  const { preset = 'last_30d', facility } = await searchParams;

  if (!isLocale(rawLocale)) notFound();
  const locale: Locale = rawLocale;
  const role = roleForSlug(slug);
  if (!role) notFound();

  const t = translator(locale);
  const facilityId = facility ? Number(facility) : 1;
  const basePath = `/${locale}/command/${slug}`;

  let dashboard: DashboardPayload;
  try {
    dashboard = await getDashboard(role, { facilityId, preset });
  } catch (error) {
    const message =
      error instanceof ApiError ? error.message : 'Unexpected error loading the dashboard.';
    return (
      <div className="space-y-4">
        <CommandNav locale={locale} activeSlug={slug} preset={preset} />
        <ErrorState title={t('error.title')} message={message} hint={t('error.hint')} />
      </div>
    );
  }

  const sections = dashboard.sections ?? {};
  const capacity = sections.capacity ?? {};
  const emergency = sections.emergency ?? {};
  const journey = sections.journey ?? {};
  const nursing = sections.nursing ?? {};

  const hasAnyData = Object.values(dashboard.coverage ?? {}).some((v) => v > 0);

  return (
    <div className="space-y-4">
      <PageHeader
        locale={locale}
        title={t(`role.${role}`)}
        period={dashboard.period}
        generatedAt={dashboard.generated_at}
      >
        <div className="flex flex-wrap items-center gap-2">
          <PeriodPicker locale={locale} basePath={basePath} active={preset} />
          <a
            href={exportUrl('metrics', 'csv', {
              facilityId,
              start: dashboard.period.start,
              end: dashboard.period.end,
            })}
            className="rounded-lg border border-canvas-border px-2.5 py-1 text-xs text-ink-muted transition hover:border-accent hover:text-ink"
          >
            {t('label.exportCsv')}
          </a>
          <LocaleToggle locale={locale} path={`/command/${slug}?preset=${preset}`} />
        </div>
      </PageHeader>

      <CommandNav locale={locale} activeSlug={slug} preset={preset} />

      {!hasAnyData ? (
        <EmptyState title={t('empty.title')} hint={t('empty.hint')} />
      ) : (
        <>
          <MetricGrid
            metrics={dashboard.tiles}
            locale={locale}
            targetLabel={t('label.target')}
            comparisonLabel={t('label.vsPrevious')}
            noDataLabel={t('label.noData')}
          />

          <CoverageBar coverage={dashboard.coverage} locale={locale} />

          <AlertPanel
            alerts={dashboard.alerts}
            locale={locale}
            title={t('label.alerts')}
            emptyMessage={t('label.noAlerts')}
          />

          {capacity.heatmap?.units?.length > 0 && (
            <Panel title={t('label.occupancyHeatmap')}>
              <OccupancyHeatmap
                units={capacity.heatmap.units}
                dates={capacity.heatmap.dates}
                values={capacity.heatmap.values}
                height={Math.max(240, capacity.heatmap.units.length * 26 + 110)}
              />
            </Panel>
          )}

          {emergency.hourly?.length > 0 && (
            <Panel
              title="Emergency department load"
              subtitle="Hourly census, admitted patients still waiting for a bed, and the NEDOCS crowding score"
            >
              <EdHourlyChart hourly={emergency.hourly.slice(-336)} />
            </Panel>
          )}

          {journey.bottlenecks?.length > 0 && (
            <Panel
              title={t('label.bottlenecks')}
              subtitle="Median delay above target, multiplied by how many patients hit it"
            >
              <BottleneckChart
                items={journey.bottlenecks.map((b: any) => ({
                  label: locale === 'ar' ? b.label_ar : b.label_en,
                  hours: b.avoidable_patient_hours,
                  median: b.median_min,
                }))}
              />
              <div className="mt-4">
                <BottleneckTable
                  rows={journey.segments ?? []}
                  locale={locale}
                  labels={{
                    segment: t('table.segment'),
                    cases: t('table.cases'),
                    median: t('table.median'),
                    p90: t('table.p90'),
                    target: t('label.target'),
                    excess: t('table.excess'),
                  }}
                />
              </div>
            </Panel>
          )}

          {capacity.units?.length > 0 && (
            <Panel title={t('label.units')}>
              <UnitTable
                units={capacity.units}
                locale={locale}
                labels={{
                  unit: t('table.unit'),
                  beds: t('table.beds'),
                  occupancy: t('table.occupancy'),
                  census: t('table.census'),
                  peak: t('table.peak'),
                  discharges: t('table.discharges'),
                  alos: t('table.alos'),
                  turnover: t('table.turnover'),
                }}
              />
            </Panel>
          )}

          {nursing.units?.length > 0 && (
            <Panel
              title={t('nav.cno')}
              subtitle="Patient days are derived from the bed-movement trail, not from the roster's own census"
            >
              <NursingTable
                rows={nursing.units}
                locale={locale}
                labels={{
                  unit: t('table.unit'),
                  nchpd: t('table.nchpd'),
                  rnHppd: t('table.rnHppd'),
                  skillMix: t('table.skillMix'),
                  overtime: t('table.overtime'),
                  vacancy: t('table.vacancy'),
                }}
              />
            </Panel>
          )}
        </>
      )}
    </div>
  );
}
