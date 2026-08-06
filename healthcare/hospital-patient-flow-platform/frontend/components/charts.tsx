'use client';

/**
 * ECharts wrappers.
 *
 * All charts share one theme so a colour means the same thing everywhere:
 * the accent blue is "actual", the muted band is "uncertainty", and the
 * red/amber/green set is reserved for benchmark status. Charts inherit the
 * document direction so Arabic renders right-to-left without a second
 * configuration.
 */

import ReactECharts from 'echarts-for-react';
import { useEffect, useState } from 'react';

const AXIS = {
  axisLine: { lineStyle: { color: '#1e2d47' } },
  axisLabel: { color: '#93a4bd', fontSize: 11 },
  splitLine: { lineStyle: { color: 'rgba(30,45,71,0.6)' } },
};

const BASE = {
  backgroundColor: 'transparent',
  textStyle: { color: '#e8eef7', fontFamily: 'inherit' },
  grid: { left: 48, right: 20, top: 28, bottom: 40, containLabel: true },
  tooltip: {
    trigger: 'axis' as const,
    backgroundColor: '#111b2e',
    borderColor: '#1e2d47',
    textStyle: { color: '#e8eef7' },
  },
};

function useIsRtl(): boolean {
  const [rtl, setRtl] = useState(false);
  useEffect(() => {
    setRtl(document.documentElement.dir === 'rtl');
  }, []);
  return rtl;
}

function Chart({ option, height = 300 }: { option: any; height?: number }) {
  return (
    <ReactECharts
      option={option}
      style={{ height, width: '100%' }}
      opts={{ renderer: 'canvas' }}
      notMerge
    />
  );
}

/** Metric over time, with an optional target line. */
export function TrendChart({
  labels,
  series,
  target,
  seriesName,
  height = 280,
}: {
  labels: string[];
  series: (number | null)[];
  target?: number | null;
  seriesName: string;
  height?: number;
}) {
  const rtl = useIsRtl();
  const option = {
    ...BASE,
    xAxis: { type: 'category', data: labels, inverse: rtl, ...AXIS },
    yAxis: { type: 'value', ...AXIS },
    series: [
      {
        name: seriesName,
        type: 'line',
        smooth: 0.25,
        showSymbol: false,
        connectNulls: false,
        data: series,
        lineStyle: { width: 2.5, color: '#38bdf8' },
        areaStyle: { color: 'rgba(56,189,248,0.12)' },
        // The target sits on the series so it appears in the tooltip and
        // the legend rather than floating as an unexplained line.
        markLine:
          target === null || target === undefined
            ? undefined
            : {
                silent: true,
                symbol: 'none',
                label: { formatter: `${seriesName} target`, color: '#93a4bd', fontSize: 10 },
                lineStyle: { color: '#fbbf24', type: 'dashed' },
                data: [{ yAxis: target }],
              },
      },
    ],
  };
  return <Chart option={option} height={height} />;
}

/** Unit × day occupancy matrix. */
export function OccupancyHeatmap({
  units,
  dates,
  values,
  height = 420,
}: {
  units: string[];
  dates: string[];
  values: (number | null)[][];
  height?: number;
}) {
  const rtl = useIsRtl();
  const points: [number, number, number | string][] = [];
  values.forEach((row, unitIndex) => {
    row.forEach((value, dateIndex) => {
      points.push([dateIndex, unitIndex, value === null ? '-' : value]);
    });
  });

  const option = {
    ...BASE,
    grid: { left: 130, right: 24, top: 16, bottom: 70, containLabel: false },
    tooltip: {
      ...BASE.tooltip,
      trigger: 'item',
      formatter: (p: any) =>
        `${units[p.value[1]]}<br/>${dates[p.value[0]]}<br/><b>${p.value[2]}%</b>`,
    },
    xAxis: {
      type: 'category',
      data: dates.map((d) => d.slice(5)),
      inverse: rtl,
      splitArea: { show: false },
      axisLabel: { color: '#93a4bd', fontSize: 10, rotate: 60 },
      axisLine: AXIS.axisLine,
    },
    yAxis: {
      type: 'category',
      data: units,
      axisLabel: { color: '#93a4bd', fontSize: 11 },
      axisLine: AXIS.axisLine,
      splitArea: { show: false },
    },
    visualMap: {
      min: 40,
      max: 105,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 4,
      textStyle: { color: '#93a4bd' },
      // Green through amber to red: the same direction as every RAG tile,
      // with the switch to red at the point occupancy stops being safe.
      inRange: { color: ['#1d4ed8', '#34d399', '#fbbf24', '#f87171', '#991b1b'] },
    },
    series: [
      {
        type: 'heatmap',
        data: points,
        emphasis: { itemStyle: { borderColor: '#e8eef7', borderWidth: 1 } },
        progressive: 2000,
      },
    ],
  };
  return <Chart option={option} height={height} />;
}

/** Forecast with its uncertainty band, appended to recent actuals. */
export function ForecastChart({
  actualLabels,
  actualValues,
  forecast,
  seriesName,
  rangeName,
  height = 320,
}: {
  actualLabels: string[];
  actualValues: (number | null)[];
  forecast: { date: string; predicted: number; lower: number; upper: number }[];
  seriesName: string;
  rangeName: string;
  height?: number;
}) {
  const rtl = useIsRtl();
  const labels = [...actualLabels, ...forecast.map((p) => p.date)];
  const pad = actualLabels.map(() => null);

  // The band is drawn as a transparent floor plus a stacked ribbon, which
  // is how ECharts expresses a confidence interval on a line chart.
  const lower = [...pad, ...forecast.map((p) => p.lower)];
  const spread = [...pad, ...forecast.map((p) => p.upper - p.lower)];
  const predicted = [...pad, ...forecast.map((p) => p.predicted)];

  // Join the two lines so the forecast starts where the actuals stop.
  if (actualValues.length > 0) {
    const lastIndex = actualValues.length - 1;
    const last = actualValues[lastIndex];
    if (last !== null && last !== undefined) {
      predicted[lastIndex] = last;
      lower[lastIndex] = last;
      spread[lastIndex] = 0;
    }
  }

  const option = {
    ...BASE,
    legend: { data: [seriesName, rangeName], textStyle: { color: '#93a4bd' }, top: 0 },
    grid: { ...BASE.grid, top: 40 },
    xAxis: {
      type: 'category',
      data: labels.map((d) => d.slice(5)),
      inverse: rtl,
      ...AXIS,
    },
    yAxis: { type: 'value', ...AXIS },
    series: [
      {
        name: 'floor',
        type: 'line',
        data: lower,
        stack: 'band',
        symbol: 'none',
        lineStyle: { opacity: 0 },
        areaStyle: { opacity: 0 },
        silent: true,
        tooltip: { show: false },
      },
      {
        name: rangeName,
        type: 'line',
        data: spread,
        stack: 'band',
        symbol: 'none',
        lineStyle: { opacity: 0 },
        areaStyle: { color: 'rgba(56,189,248,0.16)' },
        silent: true,
      },
      {
        name: seriesName,
        type: 'line',
        data: [...actualValues, ...forecast.map(() => null)],
        showSymbol: false,
        connectNulls: false,
        lineStyle: { width: 2.5, color: '#38bdf8' },
      },
      {
        name: `${seriesName} (forecast)`,
        type: 'line',
        data: predicted,
        showSymbol: false,
        connectNulls: false,
        lineStyle: { width: 2.5, color: '#38bdf8', type: 'dashed' },
      },
    ],
  };
  return <Chart option={option} height={height} />;
}

/** ED census and boarders per hour, with the NEDOCS overlay. */
export function EdHourlyChart({
  hourly,
  height = 300,
}: {
  hourly: { bucket_start: string; census: number; boarders: number; nedocs_score: number }[];
  height?: number;
}) {
  const rtl = useIsRtl();
  const labels = hourly.map((h) => h.bucket_start.slice(5, 16).replace('T', ' '));

  const option = {
    ...BASE,
    legend: { data: ['Census', 'Boarders', 'NEDOCS'], textStyle: { color: '#93a4bd' }, top: 0 },
    grid: { ...BASE.grid, top: 40 },
    xAxis: { type: 'category', data: labels, inverse: rtl, ...AXIS },
    yAxis: [
      { type: 'value', name: 'Patients', ...AXIS },
      {
        type: 'value',
        name: 'NEDOCS',
        max: 200,
        ...AXIS,
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: 'Census',
        type: 'line',
        data: hourly.map((h) => h.census),
        showSymbol: false,
        lineStyle: { width: 2, color: '#38bdf8' },
        areaStyle: { color: 'rgba(56,189,248,0.10)' },
      },
      {
        name: 'Boarders',
        type: 'line',
        data: hourly.map((h) => h.boarders),
        showSymbol: false,
        lineStyle: { width: 2, color: '#fbbf24' },
      },
      {
        name: 'NEDOCS',
        type: 'line',
        yAxisIndex: 1,
        data: hourly.map((h) => h.nedocs_score),
        showSymbol: false,
        lineStyle: { width: 1.5, color: '#f87171', opacity: 0.8 },
        // 100 is the published threshold at which a department is
        // formally overcrowded rather than merely busy.
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: '#f87171', type: 'dotted' },
          label: { formatter: 'Overcrowded', color: '#f87171', fontSize: 10 },
          data: [{ yAxis: 100 }],
        },
      },
    ],
  };
  return <Chart option={option} height={height} />;
}

/** Horizontal bars ranking where patient time is lost. */
export function BottleneckChart({
  items,
  height = 260,
}: {
  items: { label: string; hours: number; median: number }[];
  height?: number;
}) {
  const option = {
    ...BASE,
    grid: { left: 8, right: 40, top: 16, bottom: 24, containLabel: true },
    tooltip: {
      ...BASE.tooltip,
      trigger: 'item',
      formatter: (p: any) =>
        `${p.name}<br/>${p.value} avoidable patient-hours<br/>median ${
          items[p.dataIndex].median
        } min`,
    },
    xAxis: { type: 'value', ...AXIS },
    yAxis: {
      type: 'category',
      data: items.map((i) => i.label).reverse(),
      axisLabel: { color: '#93a4bd', fontSize: 11, width: 150, overflow: 'truncate' },
      axisLine: AXIS.axisLine,
    },
    series: [
      {
        type: 'bar',
        data: items.map((i) => i.hours).reverse(),
        barMaxWidth: 22,
        itemStyle: { color: '#38bdf8', borderRadius: [0, 4, 4, 0] },
      },
    ],
  };
  return <Chart option={option} height={height} />;
}
