import React from 'react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell,
} from 'recharts';
import type { MetricDataPoint } from '../../types/payloads';

export interface MetricBarChartProps {
  data: MetricDataPoint[];
  title?: string;
  unit?: string;
  className?: string;
}

const DEFAULT_BAR_COLORS = [
  '#1d4ed8', // brand-700 blue
  '#059669', // emerald-600
  '#d97706', // amber-600
  '#dc2626', // red-600
  '#7c3aed', // violet-600
  '#0891b2', // cyan-600
];

function getBarColor(item: MetricDataPoint, index: number): string {
  if (item.color) return item.color;
  if (item.priority) {
    const p = item.priority.toUpperCase();
    if (p === 'URGENT') return '#dc2626';
    if (p === 'HIGH') return '#d97706';
    if (p === 'NORMAL') return '#2563eb';
    if (p === 'LOW') return '#64748b';
  }
  return DEFAULT_BAR_COLORS[index % DEFAULT_BAR_COLORS.length];
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{ payload: MetricDataPoint; value: number }>;
  unit?: string;
}

const CustomBarTooltip: React.FC<CustomTooltipProps> = ({ active, payload, unit }) => {
  if (active && payload && payload.length > 0) {
    const data = payload[0].payload;
    const countVal = typeof data.count === 'number' ? data.count : typeof data.value === 'number' ? data.value : 0;
    const labelVal = data.label || data.name || 'Category';
    return (
      <div className="rounded-flat border border-surface-border dark:border-surface-darkBorder bg-white/95 dark:bg-slate-900/95 p-2.5 text-xs shadow-md">
        <p className="font-semibold text-ink-primary dark:text-white mb-0.5">{labelVal}</p>
        <p className="font-mono text-brand-700 dark:text-blue-400 font-bold">
          Count: {countVal.toLocaleString()}{unit ? ` ${unit}` : ''}
        </p>
        {data.priority && (
          <p className="text-[10px] text-ink-muted dark:text-slate-400 uppercase">
            Priority: {data.priority}
          </p>
        )}
      </div>
    );
  }
  return null;
};

/**
 * MetricBarChart — Responsive vertical bar chart for manager team analytics.
 */
export const MetricBarChart: React.FC<MetricBarChartProps> = ({ data, unit, className = '' }) => {
  if (!data || data.length === 0) {
    return (
      <div className="py-8 text-center text-xs text-ink-muted dark:text-slate-400 border border-dashed border-slate-200 dark:border-slate-800 rounded-flat">
        No bar chart data points supplied for this metric.
      </div>
    );
  }

  // Normalize points for safe Recharts consumption
  const normalizedPoints = data.map((d) => {
    const countVal = typeof d.count === 'number' ? d.count : typeof d.value === 'number' ? d.value : 0;
    const labelVal = d.label || d.name || 'Category';
    return {
      ...d,
      label: labelVal,
      count: countVal,
      value: countVal,
    };
  });

  // Maximum value for axis scaling
  const maxVal = Math.max(...normalizedPoints.map((d) => d.count), 5);

  return (
    <div className={`space-y-3 ${className}`}>
      {/* Visual Chart Area with Responsive Container */}
      <div className="h-64 sm:h-72 w-full pt-2" aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={normalizedPoints} margin={{ top: 10, right: 10, left: -20, bottom: 25 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#94a3b8" strokeOpacity={0.2} />
            <XAxis
              dataKey="label"
              tickLine={false}
              axisLine={{ stroke: '#94a3b8', strokeOpacity: 0.3 }}
              interval={0}
              tick={{ fontSize: 11, fill: '#64748b' }}
              angle={-20}
              textAnchor="end"
              height={40}
            />
            <YAxis
              allowDecimals={false}
              domain={[0, maxVal]}
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 11, fill: '#64748b' }}
            />
            <Tooltip content={<CustomBarTooltip unit={unit} />} />
            <Bar dataKey="count" radius={[3, 3, 0, 0]} maxBarSize={48}>
              {normalizedPoints.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={getBarColor(entry, index)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Accessible Textual Data Listing (Screen-reader and non-color inspection) */}
      <div className="border-t border-surface-border/50 dark:border-surface-darkBorder/50 pt-2.5">
        <details className="text-xs group">
          <summary className="font-semibold text-ink-muted dark:text-slate-400 cursor-pointer hover:text-ink-primary dark:hover:text-white transition-colors focus:outline-none focus:ring-1 focus:ring-brand-700 py-1">
            <span>View Accessible Data Table ({normalizedPoints.length} categories)</span>
          </summary>
          <div className="mt-2 overflow-x-auto rounded border border-surface-border dark:border-surface-darkBorder">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 dark:bg-slate-900 text-ink-muted dark:text-slate-400 uppercase text-[10px] font-bold border-b border-surface-border dark:border-surface-darkBorder">
                <tr>
                  <th scope="col" className="py-1.5 px-3">Category</th>
                  <th scope="col" className="py-1.5 px-3 text-right">Count</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border/40 dark:divide-surface-darkBorder/40">
                {normalizedPoints.map((pt, idx) => (
                  <tr key={idx} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                    <td className="py-1.5 px-3 font-medium text-ink-primary dark:text-white">
                      {pt.label}
                    </td>
                    <td className="py-1.5 px-3 text-right font-mono font-bold text-brand-700 dark:text-blue-400">
                      {pt.count.toLocaleString()}{unit ? ` ${unit}` : ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </div>
    </div>
  );
};

