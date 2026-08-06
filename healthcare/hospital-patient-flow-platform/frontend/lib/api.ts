/**
 * Typed client for the analytics API.
 *
 * Dashboard fetches run on the server so the browser never talks to the
 * warehouse directly and no API host leaks into the bundle. Every call
 * declares a revalidate window rather than caching indefinitely: an
 * operations dashboard showing yesterday's occupancy without saying so is
 * worse than one that admits it is loading.
 */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000';

export type RagStatus = 'green' | 'amber' | 'red' | 'unknown';

export interface Metric {
  key: string;
  label_en: string;
  label_ar: string;
  value: number | null;
  unit: string;
  numerator: number | null;
  denominator: number | null;
  target: number | null;
  status: RagStatus;
  trend_pct: number | null;
  higher_is_better: boolean;
  context: Record<string, unknown>;
}

export interface Alert {
  metric: string;
  label_en: string;
  label_ar: string;
  severity: 'red' | 'amber';
  value: number;
  target: number | null;
  unit: string;
  message_en: string;
}

export interface UnitRow {
  unit_id: number;
  unit_code: string;
  unit_name_en: string;
  unit_name_ar: string | null;
  unit_kind: string;
  staffed_beds: number;
  patient_days: number;
  occupancy_rate: number;
  average_daily_census: number;
  peak_census: number;
  discharges: number;
  alos_days: number | null;
  bed_turnover_rate: number;
}

export interface Heatmap {
  units: string[];
  dates: string[];
  values: (number | null)[][];
}

export interface DashboardPayload {
  role: string;
  facility_id: number;
  period: { start: string; end: string };
  tiles: Metric[];
  alerts: Alert[];
  sections: Record<string, any>;
  coverage: Record<string, number>;
  generated_at: string;
}

export interface TrendPayload {
  grain: string;
  labels: string[];
  series: Record<string, (number | null)[]>;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail?: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, revalidate = 120): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      next: { revalidate },
      headers: { Accept: 'application/json' },
    });
  } catch (cause) {
    // A dead API must surface as a clear message on the page, not as an
    // empty dashboard that reads like a hospital with no patients.
    throw new ApiError(
      `Cannot reach the analytics API at ${API_BASE}. Is the backend running?`,
      503,
      cause instanceof Error ? cause.message : undefined,
    );
  }

  if (!response.ok) {
    let detail: string | undefined;
    try {
      detail = (await response.json())?.detail;
    } catch {
      detail = undefined;
    }
    throw new ApiError(
      detail ?? `Request failed: ${response.status} ${response.statusText}`,
      response.status,
      detail,
    );
  }
  return (await response.json()) as T;
}

function periodQuery(params: {
  facilityId?: number;
  start?: string;
  end?: string;
  preset?: string;
  grain?: string;
}): string {
  const query = new URLSearchParams();
  query.set('facility_id', String(params.facilityId ?? 1));
  if (params.preset) query.set('preset', params.preset);
  if (params.start) query.set('start', params.start);
  if (params.end) query.set('end', params.end);
  if (params.grain) query.set('grain', params.grain);
  return query.toString();
}

export function getDashboard(
  role: string,
  params: { facilityId?: number; preset?: string; start?: string; end?: string },
): Promise<DashboardPayload> {
  return request<DashboardPayload>(
    `/api/v1/dashboards/${role}?${periodQuery(params)}`,
  );
}

export function getTrend(
  metricKeys: string[],
  params: {
    facilityId?: number;
    start?: string;
    end?: string;
    preset?: string;
    grain?: string;
  },
): Promise<TrendPayload> {
  const query = new URLSearchParams(periodQuery(params));
  metricKeys.forEach((key) => query.append('metric_keys', key));
  return request<TrendPayload>(`/api/v1/trends?${query.toString()}`);
}

export function getUnitDrilldown(params: {
  facilityId?: number;
  preset?: string;
  start?: string;
  end?: string;
}): Promise<{ units: UnitRow[]; heatmap: Heatmap; period: any }> {
  return request(`/api/v1/drilldown/units?${periodQuery(params)}`);
}

export function getPredictions(params: {
  facilityId?: number;
  horizonDays?: number;
}): Promise<any> {
  const query = new URLSearchParams();
  query.set('facility_id', String(params.facilityId ?? 1));
  query.set('horizon_days', String(params.horizonDays ?? 14));
  // Forecasts are expensive to compute and change slowly; a 15-minute
  // window is far more useful than hammering the model on every render.
  return request(`/api/v1/predictions?${query.toString()}`, 900);
}

export function getFacilities(): Promise<{ facilities: any[] }> {
  return request('/api/v1/facilities', 3600);
}

export function getImportBatches(facilityId = 1): Promise<{ batches: any[] }> {
  return request(`/api/v1/import/batches?facility_id=${facilityId}&limit=25`, 30);
}

export function exportUrl(
  scope: string,
  fmt: 'csv' | 'json',
  params: { facilityId?: number; start?: string; end?: string },
): string {
  const query = new URLSearchParams(periodQuery(params));
  query.set('scope', scope);
  query.set('fmt', fmt);
  return `${API_BASE}/api/v1/export?${query.toString()}`;
}
