import type { Metric } from '@/lib/api';
import { formatNumber, formatUnit, localisedLabel, type Locale } from '@/lib/i18n';

const STATUS_STYLES: Record<string, { bar: string; text: string; ring: string }> = {
  green: { bar: 'bg-status-green', text: 'text-status-green', ring: 'ring-status-green/30' },
  amber: { bar: 'bg-status-amber', text: 'text-status-amber', ring: 'ring-status-amber/30' },
  red: { bar: 'bg-status-red', text: 'text-status-red', ring: 'ring-status-red/40' },
  unknown: { bar: 'bg-status-unknown', text: 'text-ink-faint', ring: 'ring-white/5' },
};

/**
 * A single indicator.
 *
 * The value is always shown alongside its target and its movement against
 * the previous period. A number on its own invites the reader to invent a
 * benchmark, and the invented one is usually wrong.
 */
export function MetricTile({
  metric,
  locale,
  targetLabel,
  comparisonLabel,
  noDataLabel,
}: {
  metric: Metric;
  locale: Locale;
  targetLabel: string;
  comparisonLabel: string;
  noDataLabel: string;
}) {
  const style = STATUS_STYLES[metric.status] ?? STATUS_STYLES.unknown;
  const label = localisedLabel(locale, metric.label_en, metric.label_ar);
  const unit = formatUnit(metric.unit, locale);
  const hasValue = metric.value !== null && metric.value !== undefined;

  // "Better" depends on the metric: falling door-to-doctor is good,
  // falling satisfaction is not.
  const trend = metric.trend_pct;
  const trendIsGood =
    trend === null || trend === undefined
      ? null
      : metric.higher_is_better
        ? trend >= 0
        : trend <= 0;

  return (
    <article
      className={`tile flex flex-col justify-between gap-3 ring-1 ${style.ring}`}
      aria-label={label}
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="tile-label leading-snug">{label}</h3>
        <span
          className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${style.bar}`}
          aria-hidden="true"
        />
      </div>

      <div className="flex items-baseline gap-1.5">
        {hasValue ? (
          <>
            <span className={`tile-value ${style.text}`}>
              {formatNumber(metric.value, locale, metric.unit === '%' ? 1 : 2)}
            </span>
            {unit && <span className="text-sm text-ink-muted">{unit}</span>}
          </>
        ) : (
          <span className="tile-value text-ink-faint">{noDataLabel}</span>
        )}
      </div>

      <dl className="space-y-0.5 text-xs text-ink-muted">
        {metric.target !== null && metric.target !== undefined && (
          <div className="flex justify-between gap-2">
            <dt>{targetLabel}</dt>
            <dd className="tabular-nums text-ink">
              {formatNumber(metric.target, locale)}
              {unit && ` ${unit}`}
            </dd>
          </div>
        )}
        {trend !== null && trend !== undefined && (
          <div className="flex justify-between gap-2">
            <dt>{comparisonLabel}</dt>
            <dd
              className={`tabular-nums ${
                trendIsGood === null
                  ? 'text-ink'
                  : trendIsGood
                    ? 'text-status-green'
                    : 'text-status-red'
              }`}
            >
              {trend >= 0 ? '+' : '−'}
              {formatNumber(Math.abs(trend), locale)}%
            </dd>
          </div>
        )}
      </dl>
    </article>
  );
}

export function MetricGrid({
  metrics,
  locale,
  targetLabel,
  comparisonLabel,
  noDataLabel,
}: {
  metrics: Metric[];
  locale: Locale;
  targetLabel: string;
  comparisonLabel: string;
  noDataLabel: string;
}) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {metrics.map((metric) => (
        <MetricTile
          key={metric.key}
          metric={metric}
          locale={locale}
          targetLabel={targetLabel}
          comparisonLabel={comparisonLabel}
          noDataLabel={noDataLabel}
        />
      ))}
    </div>
  );
}
