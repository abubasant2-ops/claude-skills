'use client';

import { useState } from 'react';
import { API_BASE } from '@/lib/api';
import type { Locale } from '@/lib/i18n';

const DATASETS = [
  'units',
  'encounters',
  'ed_visits',
  'bed_movements',
  'orders',
  'icu_stays',
  'or_cases',
  'vitals',
  'safety_events',
  'staffing',
  'patient_experience',
] as const;

const SEVERITY_TONE: Record<string, string> = {
  CRITICAL: 'text-status-red',
  ERROR: 'text-status-red',
  WARNING: 'text-status-amber',
  INFO: 'text-ink-muted',
};

/**
 * Upload wizard.
 *
 * Defaults to a dry run. A hospital's first upload is almost always a
 * probe -- "will this file even work?" -- and letting them see the column
 * mapping and the quality report before anything is written removes the
 * fear of corrupting the warehouse on the first try.
 */
export function UploadForm({ facilityId, locale }: { facilityId: number; locale: Locale }) {
  const [dataset, setDataset] = useState<string>('encounters');
  const [file, setFile] = useState<File | null>(null);
  const [dryRun, setDryRun] = useState(true);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!file) return;

    setBusy(true);
    setError(null);
    setResult(null);

    const body = new FormData();
    body.append('dataset', dataset);
    body.append('file', file);
    body.append('facility_id', String(facilityId));
    body.append('dry_run', String(dryRun));

    try {
      const response = await fetch(`${API_BASE}/api/v1/import/upload`, {
        method: 'POST',
        body,
      });
      const payload = await response.json();
      if (!response.ok) {
        setError(payload?.detail ?? `Upload failed (${response.status})`);
      } else {
        setResult(payload);
      }
    } catch {
      setError(`Cannot reach the API at ${API_BASE}. Is the backend running?`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          Dataset
          <select
            value={dataset}
            onChange={(event) => setDataset(event.target.value)}
            className="rounded-lg border border-canvas-border bg-canvas px-3 py-2 text-sm text-ink"
          >
            {DATASETS.map((key) => (
              <option key={key} value={key}>
                {key}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          File (.xlsx, .xlsm, .csv)
          <input
            type="file"
            accept=".xlsx,.xlsm,.csv"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            className="rounded-lg border border-canvas-border bg-canvas px-3 py-1.5 text-sm text-ink file:me-3 file:rounded file:border-0 file:bg-white/10 file:px-3 file:py-1 file:text-ink"
          />
        </label>

        <label className="flex items-center gap-2 pb-2 text-xs text-ink-muted">
          <input
            type="checkbox"
            checked={dryRun}
            onChange={(event) => setDryRun(event.target.checked)}
            className="h-4 w-4 rounded border-canvas-border bg-canvas"
          />
          Validate only (do not load)
        </label>

        <button
          type="submit"
          disabled={!file || busy}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-canvas transition disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? 'Checking…' : dryRun ? 'Validate' : 'Upload and load'}
        </button>
      </form>

      {error && (
        <p className="rounded-lg border border-status-red/40 bg-status-red/10 p-3 text-sm text-status-red">
          {error}
        </p>
      )}

      {result && <UploadReport result={result} />}
    </div>
  );
}

function UploadReport({ result }: { result: any }) {
  const findings = result.validation?.findings ?? [];
  const dimensions = result.validation?.dimension_scores ?? {};

  return (
    <div className="space-y-3 rounded-lg border border-canvas-border bg-white/5 p-4">
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1 text-sm">
        <span>
          Batch <b className="tabular-nums">{result.batch_id}</b>
        </span>
        <span>
          State{' '}
          <b
            className={
              result.state === 'LOADED'
                ? 'text-status-green'
                : result.state === 'REJECTED'
                  ? 'text-status-red'
                  : 'text-status-amber'
            }
          >
            {result.state}
          </b>
        </span>
        <span className="tabular-nums">
          {result.row_count} rows · {result.loaded_rows} loaded · {result.rejected_rows}{' '}
          quarantined
        </span>
        <span>
          Quality{' '}
          <b
            className={
              result.quality_score >= 90
                ? 'text-status-green'
                : result.quality_score >= 70
                  ? 'text-status-amber'
                  : 'text-status-red'
            }
          >
            {result.quality_score}
          </b>
        </span>
      </div>

      {Object.keys(dimensions).length > 0 && (
        <dl className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-muted">
          {Object.entries(dimensions).map(([name, score]) => (
            <div key={name}>
              <dt className="inline capitalize">{name}: </dt>
              <dd className="inline tabular-nums text-ink">{String(score)}</dd>
            </div>
          ))}
        </dl>
      )}

      {result.column_mapping && (
        <details className="text-xs">
          <summary className="cursor-pointer text-ink-muted">
            Column mapping ({Object.keys(result.column_mapping).length} matched
            {result.unmapped_columns?.length
              ? `, ${result.unmapped_columns.length} unmapped`
              : ''}
            )
          </summary>
          <ul className="mt-2 space-y-0.5 text-ink-muted">
            {Object.entries(result.column_mapping).map(([field, source]) => (
              <li key={field}>
                <span className="text-ink">{String(source)}</span> → {field}
              </li>
            ))}
            {(result.unmapped_columns ?? []).map((column: string) => (
              <li key={column} className="text-ink-faint">
                {column} → (ignored)
              </li>
            ))}
          </ul>
        </details>
      )}

      {findings.length > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">
            Data quality findings
          </h4>
          <ul className="space-y-1.5 text-xs">
            {findings.map((finding: any, index: number) => (
              <li key={`${finding.rule_code}-${index}`} className="flex gap-2">
                <span className={`shrink-0 font-semibold ${SEVERITY_TONE[finding.severity]}`}>
                  {finding.severity}
                </span>
                <span className="text-ink-muted">{finding.message_en}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
