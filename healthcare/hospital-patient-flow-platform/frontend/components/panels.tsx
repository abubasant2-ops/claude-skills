import type { Alert, UnitRow } from '@/lib/api';
import { formatNumber, localisedLabel, type Locale } from '@/lib/i18n';

export function Panel({
  title,
  subtitle,
  action,
  children,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="tile">
      <header className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h2 className="section-title">{title}</h2>
          {subtitle && <p className="mt-0.5 text-xs text-ink-muted">{subtitle}</p>}
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}

/**
 * Indicators outside target, worst first.
 *
 * Each row states the value, the target and the gap in words. A colour
 * chip alone tells a director something is wrong but not what or by how
 * much, which is the difference between a dashboard and a decision.
 */
export function AlertPanel({
  alerts,
  locale,
  title,
  emptyMessage,
}: {
  alerts: Alert[];
  locale: Locale;
  title: string;
  emptyMessage: string;
}) {
  if (alerts.length === 0) {
    return (
      <Panel title={title}>
        <p className="text-sm text-status-green">{emptyMessage}</p>
      </Panel>
    );
  }

  return (
    <Panel title={title}>
      <ul className="space-y-2">
        {alerts.map((alert) => (
          <li
            key={alert.metric}
            className={`flex items-start gap-3 rounded-lg border-s-4 bg-white/5 p-3 ${
              alert.severity === 'red' ? 'border-status-red' : 'border-status-amber'
            }`}
          >
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">
                {localisedLabel(locale, alert.label_en, alert.label_ar)}
              </p>
              <p className="mt-0.5 text-xs text-ink-muted">{alert.message_en}</p>
            </div>
            <span
              className={`shrink-0 tabular-nums text-sm font-semibold ${
                alert.severity === 'red' ? 'text-status-red' : 'text-status-amber'
              }`}
            >
              {formatNumber(alert.value, locale)}
              {alert.unit === '%' ? '%' : ''}
            </span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function occupancyTone(rate: number): string {
  if (rate >= 95) return 'text-status-red';
  if (rate >= 90) return 'text-status-amber';
  if (rate < 60) return 'text-ink-faint';
  return 'text-status-green';
}

export function UnitTable({
  units,
  locale,
  labels,
}: {
  units: UnitRow[];
  locale: Locale;
  labels: Record<string, string>;
}) {
  return (
    <div className="scroll-x">
      <table className="data">
        <thead>
          <tr>
            <th>{labels.unit}</th>
            <th className="text-end">{labels.beds}</th>
            <th className="text-end">{labels.occupancy}</th>
            <th className="text-end">{labels.census}</th>
            <th className="text-end">{labels.peak}</th>
            <th className="text-end">{labels.discharges}</th>
            <th className="text-end">{labels.alos}</th>
            <th className="text-end">{labels.turnover}</th>
          </tr>
        </thead>
        <tbody>
          {units.map((unit) => (
            <tr key={unit.unit_id}>
              <td>
                <span className="font-medium">
                  {localisedLabel(locale, unit.unit_name_en, unit.unit_name_ar)}
                </span>
                <span className="ms-2 rounded bg-white/10 px-1.5 py-0.5 text-[10px] uppercase text-ink-muted">
                  {unit.unit_kind}
                </span>
              </td>
              <td className="text-end tabular-nums">{formatNumber(unit.staffed_beds, locale, 0)}</td>
              <td className={`text-end tabular-nums font-semibold ${occupancyTone(unit.occupancy_rate)}`}>
                {formatNumber(unit.occupancy_rate, locale)}%
              </td>
              <td className="text-end tabular-nums">{formatNumber(unit.average_daily_census, locale)}</td>
              <td className="text-end tabular-nums">{formatNumber(unit.peak_census, locale, 0)}</td>
              <td className="text-end tabular-nums">{formatNumber(unit.discharges, locale, 0)}</td>
              <td className="text-end tabular-nums">{formatNumber(unit.alos_days, locale)}</td>
              <td className="text-end tabular-nums">{formatNumber(unit.bed_turnover_rate, locale)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function BottleneckTable({
  rows,
  locale,
  labels,
}: {
  rows: any[];
  locale: Locale;
  labels: Record<string, string>;
}) {
  return (
    <div className="scroll-x">
      <table className="data">
        <thead>
          <tr>
            <th>{labels.segment}</th>
            <th className="text-end">{labels.cases}</th>
            <th className="text-end">{labels.median}</th>
            <th className="text-end">{labels.p90}</th>
            <th className="text-end">{labels.target}</th>
            <th className="text-end">{labels.excess}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.segment}>
              <td className="font-medium">
                {localisedLabel(locale, row.label_en, row.label_ar)}
              </td>
              <td className="text-end tabular-nums">{formatNumber(row.cases, locale, 0)}</td>
              <td className="text-end tabular-nums">{formatNumber(row.median_min, locale, 0)}</td>
              <td className="text-end tabular-nums text-ink-muted">
                {formatNumber(row.p90_min, locale, 0)}
              </td>
              <td className="text-end tabular-nums text-ink-muted">
                {row.target_min === null ? '—' : formatNumber(row.target_min, locale, 0)}
              </td>
              <td
                className={`text-end tabular-nums font-semibold ${
                  row.avoidable_patient_hours > 0 ? 'text-status-amber' : 'text-ink-faint'
                }`}
              >
                {formatNumber(row.avoidable_patient_hours, locale, 0)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function NursingTable({
  rows,
  locale,
  labels,
}: {
  rows: any[];
  locale: Locale;
  labels: Record<string, string>;
}) {
  return (
    <div className="scroll-x">
      <table className="data">
        <thead>
          <tr>
            <th>{labels.unit}</th>
            <th className="text-end">{labels.nchpd}</th>
            <th className="text-end">{labels.rnHppd}</th>
            <th className="text-end">{labels.skillMix}</th>
            <th className="text-end">{labels.overtime}</th>
            <th className="text-end">{labels.vacancy}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.unit_id}>
              <td className="font-medium">{row.unit_name}</td>
              <td className="text-end tabular-nums">{formatNumber(row.nchpd, locale, 2)}</td>
              <td className="text-end tabular-nums">{formatNumber(row.rn_hppd, locale, 2)}</td>
              <td className="text-end tabular-nums">{formatNumber(row.rn_skill_mix, locale)}%</td>
              <td
                className={`text-end tabular-nums ${
                  row.overtime_rate > 8 ? 'text-status-red' : ''
                }`}
              >
                {formatNumber(row.overtime_rate, locale)}%
              </td>
              <td
                className={`text-end tabular-nums ${
                  row.vacancy_rate > 10 ? 'text-status-amber' : ''
                }`}
              >
                {formatNumber(row.vacancy_rate, locale)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ErrorState({
  title,
  message,
  hint,
}: {
  title: string;
  message: string;
  hint: string;
}) {
  return (
    <div className="tile border-status-red/40">
      <h2 className="section-title text-status-red">{title}</h2>
      <p className="mt-2 text-sm text-ink">{message}</p>
      <p className="mt-1 text-xs text-ink-muted">{hint}</p>
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="tile text-center">
      <h2 className="section-title">{title}</h2>
      <p className="mt-1 text-sm text-ink-muted">{hint}</p>
    </div>
  );
}
