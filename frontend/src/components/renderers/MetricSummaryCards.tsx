import React from 'react';
import { Ticket, CheckCircle2, Clock, ShieldCheck, AlertCircle } from 'lucide-react';
import type { MetricKpiSummary } from '../../types/payloads';

export interface MetricSummaryCardsProps {
  kpis: MetricKpiSummary;
  className?: string;
}

/**
 * MetricSummaryCards — Renders aggregate KPI summary cards for managers.
 *
 * INVARIANTS:
 * 1. Missing metrics are omitted, NOT coerced to 0. Zero means a measured count of zero.
 * 2. Percentages display '%' only when the field represents an actual percentage/rate.
 * 3. Units are displayed accurately without guessing.
 */
export const MetricSummaryCards: React.FC<MetricSummaryCardsProps> = ({ kpis, className = '' }) => {
  const cards: Array<{
    id: string;
    label: string;
    value: string | number;
    unit?: string;
    subtext?: string;
    icon: React.ReactNode;
    colorClass: string;
  }> = [];

  if (typeof kpis.total_tickets === 'number') {
    cards.push({
      id: 'total',
      label: 'Total Tickets',
      value: kpis.total_tickets,
      icon: <Ticket className="w-4 h-4 text-slate-500" aria-hidden="true" />,
      colorClass: 'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800',
    });
  }

  if (typeof kpis.open_tickets === 'number') {
    cards.push({
      id: 'open',
      label: 'Open Queue',
      value: kpis.open_tickets,
      icon: <AlertCircle className="w-4 h-4 text-blue-600 dark:text-blue-400" aria-hidden="true" />,
      colorClass: 'border-blue-200 dark:border-blue-900/60 bg-blue-50/50 dark:bg-blue-950/30 text-blue-950 dark:text-blue-100',
    });
  }

  if (typeof kpis.in_progress_tickets === 'number') {
    cards.push({
      id: 'in_progress',
      label: 'In Progress',
      value: kpis.in_progress_tickets,
      icon: <Clock className="w-4 h-4 text-amber-600 dark:text-amber-400" aria-hidden="true" />,
      colorClass: 'border-amber-200 dark:border-amber-900/60 bg-amber-50/50 dark:bg-amber-950/30 text-amber-950 dark:text-amber-100',
    });
  }

  if (typeof kpis.resolved_tickets === 'number') {
    cards.push({
      id: 'resolved',
      label: 'Resolved',
      value: kpis.resolved_tickets,
      icon: <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" aria-hidden="true" />,
      colorClass: 'border-emerald-200 dark:border-emerald-900/60 bg-emerald-50/50 dark:bg-emerald-950/30 text-emerald-950 dark:text-emerald-100',
    });
  }

  if (typeof kpis.closed_tickets === 'number') {
    cards.push({
      id: 'closed',
      label: 'Closed',
      value: kpis.closed_tickets,
      icon: <CheckCircle2 className="w-4 h-4 text-slate-500" aria-hidden="true" />,
      colorClass: 'border-slate-200 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-900/40',
    });
  }

  if (kpis.avg_resolution_time) {
    if (typeof kpis.avg_resolution_time === 'string') {
      cards.push({
        id: 'avg_time',
        label: 'Avg Resolution',
        value: kpis.avg_resolution_time,
        icon: <Clock className="w-4 h-4 text-brand-600 dark:text-blue-400" aria-hidden="true" />,
        colorClass: 'border-blue-200 dark:border-blue-900 bg-brand-50/40 dark:bg-blue-950/20 text-slate-900 dark:text-blue-100',
      });
    } else if (typeof kpis.avg_resolution_time === 'object' && typeof kpis.avg_resolution_time.value === 'number') {
      cards.push({
        id: 'avg_time',
        label: 'Avg Resolution',
        value: kpis.avg_resolution_time.value,
        unit: kpis.avg_resolution_time.unit,
        icon: <Clock className="w-4 h-4 text-brand-600 dark:text-blue-400" aria-hidden="true" />,
        colorClass: 'border-blue-200 dark:border-blue-900 bg-brand-50/40 dark:bg-blue-950/20 text-slate-900 dark:text-blue-100',
      });
    }
  }

  const rawSla =
    typeof kpis.sla_compliance_rate === 'number'
      ? kpis.sla_compliance_rate
      : typeof kpis.sla_compliance_pct === 'number'
      ? kpis.sla_compliance_pct
      : undefined;

  if (typeof rawSla === 'number') {
    cards.push({
      id: 'sla',
      label: 'SLA Compliance',
      value: `${rawSla}%`,
      icon: <ShieldCheck className="w-4 h-4 text-emerald-600 dark:text-emerald-400" aria-hidden="true" />,
      colorClass: 'border-emerald-200 dark:border-emerald-900/60 bg-emerald-50/50 dark:bg-emerald-950/30 text-emerald-950 dark:text-emerald-100',
    });
  }

  // Custom items if provided
  if (kpis.items && kpis.items.length > 0) {
    kpis.items.forEach((item, idx) => {
      cards.push({
        id: `custom-${idx}`,
        label: item.label,
        value: item.value,
        unit: item.unit,
        subtext: item.description,
        icon: <ShieldCheck className="w-4 h-4 text-slate-400" aria-hidden="true" />,
        colorClass: 'border-surface-border dark:border-surface-darkBorder bg-white dark:bg-slate-800',
      });
    });
  }

  if (cards.length === 0) {
    return null;
  }

  return (
    <div
      aria-label="Key Performance Indicators"
      className={`grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2.5 ${className}`}
    >
      {cards.map((c) => (
        <div
          key={c.id}
          className={`p-3 rounded-flat border transition-colors flex flex-col justify-between ${c.colorClass}`}
        >
          <div className="flex items-center justify-between gap-1 text-ink-muted dark:text-slate-400 mb-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider truncate">
              {c.label}
            </span>
            <span className="shrink-0">{c.icon}</span>
          </div>
          <div className="flex items-baseline gap-1 mt-0.5">
            <span className="text-lg sm:text-xl font-bold font-mono tracking-tight text-ink-primary dark:text-white">
              {c.value}
            </span>
            {c.unit && (
              <span className="text-xs text-ink-muted dark:text-slate-400 font-medium">
                {c.unit}
              </span>
            )}
          </div>
          {c.subtext && (
            <p className="text-[10px] text-ink-muted dark:text-slate-400 truncate mt-1">
              {c.subtext}
            </p>
          )}
        </div>
      ))}
    </div>
  );
};
