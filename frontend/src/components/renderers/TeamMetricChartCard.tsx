import React from 'react';
import {
  BarChart3,
  PieChart as PieChartIcon,
  AlertCircle,
  Calendar,
  Users,
  ShieldCheck,
} from 'lucide-react';
import type { ResultRendererProps } from '../workspace/resultRegistry';
import type { TeamMetricChartPayload } from '../../types/payloads';
import { validateTeamMetricChartPayload } from './validation';
import { MetricSummaryCards } from './MetricSummaryCards';
import { MetricBarChart } from './MetricBarChart';
import { MetricPieChart } from './MetricPieChart';
import { MetricTimeChart } from './MetricTimeChart';

/**
 * TeamMetricChartCard — Primary Renderer for TEAM_METRIC_CHART result blocks.
 *
 * Implements Stage 5 requirements:
 * - Validates TEAM_METRIC_CHART payload
 * - Renders KPI summary cards when supported/present
 * - Renders BAR or PIE distribution charts using Recharts
 * - Displays team & time-range scoping metadata
 * - Handles empty datasets and invalid payloads safely without raw JSON dumps
 * - Fully responsive (Split View, Feed View, mobile)
 * - Supports light & dark themes conforming to IntentLock design system
 */
export const TeamMetricChartCard: React.FC<ResultRendererProps> = ({ block }) => {
  const validation = validateTeamMetricChartPayload(block.payload);

  if (!validation.isValid) {
    return (
      <article
        className="rounded-flat border-2 border-surface-border dark:border-surface-darkBorder bg-surface-card dark:bg-slate-800/60 p-4 transition-colors"
        aria-label="Team Analytics Error"
      >
        <div className="flex items-start gap-3 text-ink-muted dark:text-slate-400 text-xs">
          <AlertCircle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" aria-hidden="true" />
          <div className="flex-1">
            <p className="font-semibold text-ink-primary dark:text-slate-200">
              Analytics data is unavailable
            </p>
            <p className="mt-1 text-slate-500 dark:text-slate-400">
              The team metric chart payload could not be rendered: {validation.error || 'Invalid chart specification'}.
            </p>
          </div>
        </div>
      </article>
    );
  }

  const payload = block.payload as unknown as TeamMetricChartPayload;
  const { chart_type, title, data, unit, team_id, time_range, kpis } = payload;

  return (
    <article
      className="rounded-flat border-2 border-surface-border dark:border-surface-darkBorder bg-surface-card dark:bg-slate-800/60 p-4 transition-colors space-y-4"
      aria-label={`Team Analytics: ${title || 'Metrics'}`}
    >
      {/* Header section with Scoping & Meta information */}
      <div className="border-b border-surface-border/60 dark:border-surface-darkBorder/60 pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded bg-brand-700/10 text-brand-700 dark:bg-blue-500/20 dark:text-blue-300">
              {chart_type === 'BAR' ? (
                <BarChart3 className="w-3 h-3" aria-hidden="true" />
              ) : (
                <PieChartIcon className="w-3 h-3" aria-hidden="true" />
              )}
              {payload.category || (unit === 'employees' || unit === 'people' ? 'Workforce Analytics' : 'Manager Analytics')}
            </span>
            <span className="inline-flex items-center gap-1 text-[11px] text-slate-500 dark:text-slate-400">
              <ShieldCheck className="w-3 h-3 text-emerald-500" aria-hidden="true" />
              {payload.category === 'Biometrics' ? 'Standalone diagnostic' : 'Authorized Scope'}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500 dark:text-slate-400">
            {team_id && (
              <span className="inline-flex items-center gap-1" title="Authorized Team Identifier">
                <Users className="w-3.5 h-3.5 text-slate-400" aria-hidden="true" />
                <span className="font-mono text-ink-primary dark:text-slate-200">{team_id}</span>
              </span>
            )}
            {time_range && (
              <span className="inline-flex items-center gap-1" title="Analytics Time Range">
                <Calendar className="w-3.5 h-3.5 text-slate-400" aria-hidden="true" />
                <span>{time_range}</span>
              </span>
            )}
          </div>
        </div>

        <h3 className="mt-2 text-base font-bold text-ink-primary dark:text-slate-100">
          {title || 'Team Metrics'}
        </h3>
      </div>

      {/* Optional KPI Summary Cards */}
      {kpis && (
        <section aria-label="Team Key Performance Indicators">
          <MetricSummaryCards kpis={kpis} />
        </section>
      )}

      {/* Main Chart Visualization */}
      <section aria-label="Metric Chart">
        {chart_type === 'BAR' && (
          <MetricBarChart data={data} title={title} unit={unit} />
        )}
        {chart_type === 'PIE' && (
          <MetricPieChart data={data} title={title} unit={unit} />
        )}
        {(chart_type === 'LINE' || chart_type === 'AREA') && (
          <MetricTimeChart data={data} variant={chart_type} />
        )}
      </section>

      {/* Security & Data Integrity Footer */}
      <div className="pt-2 border-t border-surface-border/40 dark:border-surface-darkBorder/40 flex items-center justify-between text-[11px] text-slate-400 dark:text-slate-500">
        <span>
          {payload.category === 'Biometrics'
            ? 'Provider evidence only. This diagnostic does not grant private workspace access.'
            : unit === 'employees'
            ? 'Aggregate workforce metrics computed server-side under executive RBAC.'
            : 'Aggregate metrics computed server-side under manager RBAC.'}
        </span>
        <span>Local presentation only</span>
      </div>
    </article>
  );
};
