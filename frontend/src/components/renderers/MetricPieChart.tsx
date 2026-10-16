import React, { useState } from 'react';
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
} from 'recharts';
import type { MetricDataPoint } from '../../types';

interface MetricPieChartProps {
  data: MetricDataPoint[];
  title?: string;
  unit?: string;
}

// Accessible, distinct categorical color palette suitable for both light & dark themes
const PIE_COLORS = [
  '#3b82f6', // blue-500
  '#10b981', // emerald-500
  '#f59e0b', // amber-500
  '#ef4444', // red-500
  '#8b5cf6', // violet-500
  '#06b6d4', // cyan-500
  '#ec4899', // pink-500
  '#64748b', // slate-500
];

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{
    name: string;
    value: number;
    payload: MetricDataPoint & { percentage?: number };
  }>;
  unit?: string;
}

const CustomPieTooltip: React.FC<CustomTooltipProps> = ({ active, payload, unit }) => {
  if (active && payload && payload.length > 0) {
    const item = payload[0];
    const pct = item.payload.percentage;
    return (
      <div
        role="tooltip"
        className="rounded-lg border border-slate-700 bg-slate-900/95 px-3 py-2 text-xs shadow-xl backdrop-blur-sm"
      >
        <p className="font-semibold text-slate-100">{item.name}</p>
        <p className="mt-0.5 text-slate-300">
          Value:{' '}
          <span className="font-mono font-medium text-blue-400">
            {item.value.toLocaleString()}
            {unit ? ` ${unit}` : ''}
          </span>
          {typeof pct === 'number' && !isNaN(pct) && (
            <span className="ml-1.5 text-slate-400">({pct.toFixed(1)}%)</span>
          )}
        </p>
      </div>
    );
  }
  return null;
};

export const MetricPieChart: React.FC<MetricPieChartProps> = ({
  data,
  title,
  unit,
}) => {
  const [showTable, setShowTable] = useState(false);

  // Safeguard: empty data array
  if (!data || data.length === 0) {
    return (
      <div
        role="region"
        aria-label="Empty distribution chart"
        className="flex flex-col items-center justify-center rounded-lg border border-dashed border-slate-700/60 bg-slate-900/30 p-8 text-center"
      >
        <svg
          aria-hidden="true"
          className="h-10 w-10 text-slate-500"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M11 3.055A9.001 9.001 0 1020.945 13H11V3.055z"
          />
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M20.488 9H15V3.512A9.025 9.025 0 0120.488 9z"
          />
        </svg>
        <p className="mt-2 text-sm font-medium text-slate-300">No chart data available</p>
        <p className="mt-1 text-xs text-slate-500">
          The requested metric distribution contains zero data points.
        </p>
      </div>
    );
  }

  // Calculate total sum safely; avoid division by zero
  const totalValue = data.reduce((acc, curr) => {
    const val = typeof curr.count === 'number' ? curr.count : typeof curr.value === 'number' ? curr.value : 0;
    return acc + (Number.isFinite(val) ? val : 0);
  }, 0);
  const isAllZero = totalValue === 0;

  // Enrich data with safe percentages and normalized fields
  const enrichedData = data.map((d) => {
    const val = typeof d.count === 'number' ? d.count : typeof d.value === 'number' ? d.value : 0;
    const label = d.label || d.name || 'Category';
    return {
      ...d,
      name: label,
      label: label,
      value: val,
      count: val,
      percentage: isAllZero ? 0 : (val / totalValue) * 100,
    };
  });

  return (
    <div
      role="region"
      aria-label={title || 'Metric distribution chart'}
      className="flex flex-col rounded-lg border border-slate-800/80 bg-slate-900/60 p-4 transition-colors"
    >
      <div className="mb-3 flex items-center justify-between">
        {title ? (
          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            {title}
          </h4>
        ) : (
          <span />
        )}
        <button
          type="button"
          onClick={() => setShowTable((prev) => !prev)}
          className="text-xs text-blue-400 underline-offset-2 hover:text-blue-300 hover:underline focus:outline-none focus:ring-1 focus:ring-blue-500"
          aria-expanded={showTable}
          aria-controls="pie-accessible-table"
        >
          {showTable ? 'Hide data table' : 'View data table'}
        </button>
      </div>

      {isAllZero && (
        <div className="mb-2 rounded border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-300">
          All categories report 0 counts. Total measured sum is 0.
        </div>
      )}

      {/* Recharts Pie container */}
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart margin={{ top: 10, right: 10, bottom: 10, left: 10 }}>
            <Pie
              data={enrichedData}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              outerRadius={80}
              innerRadius={42} // Donut style for modern clean presentation
              paddingAngle={2}
              isAnimationActive={false} // Avoid unnecessary animation for predictable rendering & a11y
            >
              {enrichedData.map((_, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={PIE_COLORS[index % PIE_COLORS.length]}
                  stroke="#0f172a"
                  strokeWidth={2}
                />
              ))}
            </Pie>
            <Tooltip content={<CustomPieTooltip unit={unit} />} />
            <Legend
              verticalAlign="bottom"
              height={36}
              formatter={(value: string) => (
                <span className="text-xs text-slate-300">{value}</span>
              )}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>

      {/* Accessible textual fallback / inspection table */}
      {showTable && (
        <div id="pie-accessible-table" className="mt-3 overflow-x-auto border-t border-slate-800 pt-3">
          <table className="w-full text-left text-xs text-slate-300">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400">
                <th scope="col" className="pb-1 font-medium">Category</th>
                <th scope="col" className="pb-1 text-right font-medium">Value</th>
                <th scope="col" className="pb-1 text-right font-medium">Share</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {enrichedData.map((row, idx) => (
                <tr key={idx} className="hover:bg-slate-800/30">
                  <td className="py-1 font-medium text-slate-200 flex items-center gap-1.5">
                    <span
                      className="inline-block h-2 w-2 rounded-full"
                      style={{ backgroundColor: PIE_COLORS[idx % PIE_COLORS.length] }}
                      aria-hidden="true"
                    />
                    {row.name}
                  </td>
                  <td className="py-1 text-right font-mono text-slate-100">
                    {row.value.toLocaleString()}
                    {unit ? ` ${unit}` : ''}
                  </td>
                  <td className="py-1 text-right font-mono text-slate-400">
                    {isAllZero ? '0.0%' : `${row.percentage.toFixed(1)}%`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
