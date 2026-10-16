import React from 'react';
import { History, Clock, User, ArrowRight } from 'lucide-react';
import type { TicketEvent } from '../../types/payloads';

export interface TicketTimelineProps {
  /** Genuine event history array from the backend */
  events?: TicketEvent[];
  /** Ticket creation timestamp if known */
  createdAt?: string;
  /** Ticket last updated timestamp if known */
  updatedAt?: string;
  className?: string;
}

/**
 * TicketTimeline — Chronological event history renderer for support tickets.
 *
 * ARCHITECTURAL INVARIANT:
 * Zero fabricated events. If backend has not yet recorded genuine lifecycle events,
 * this component displays an honest notice stating that event ledger history is not
 * yet active, rather than fabricating transitions or pretending current status is a timeline.
 */
export const TicketTimeline: React.FC<TicketTimelineProps> = ({
  events,
  createdAt,
  updatedAt,
  className = '',
}) => {
  const hasEvents = events && events.length > 0;

  return (
    <section
      aria-label="Ticket lifecycle history"
      className={`rounded-flat border border-surface-border dark:border-surface-darkBorder bg-slate-50/50 dark:bg-slate-900/40 p-4 transition-colors ${className}`}
    >
      <header className="flex items-center justify-between gap-2 pb-2.5 mb-3 border-b border-surface-border/60 dark:border-surface-darkBorder/60">
        <div className="flex items-center gap-2">
          <History className="w-4 h-4 text-brand-700 dark:text-blue-400" aria-hidden="true" />
          <h4 className="text-xs font-bold uppercase tracking-wider text-ink-primary dark:text-white">
            Lifecycle Event History
          </h4>
        </div>
        {hasEvents && (
          <span className="text-[11px] font-mono text-ink-muted dark:text-slate-400">
            {events.length} {events.length === 1 ? 'event' : 'events'}
          </span>
        )}
      </header>

      {hasEvents ? (
        <ol className="relative border-l-2 border-slate-200 dark:border-slate-700 ml-2.5 space-y-4 py-1">
          {events.map((ev, idx) => {
            const isLast = idx === events.length - 1;
            return (
              <li key={ev.id || `${ev.timestamp}-${idx}`} className="ml-4 relative">
                {/* Timeline node bullet */}
                <span
                  className={`absolute -left-[23px] top-1 w-3.5 h-3.5 rounded-full border-2 bg-white dark:bg-slate-900 ${
                    isLast
                      ? 'border-brand-600 dark:border-blue-400 ring-2 ring-brand-100 dark:ring-blue-950'
                      : 'border-slate-400 dark:border-slate-500'
                  }`}
                  aria-hidden="true"
                />

                <div className="flex flex-wrap items-center justify-between gap-1 text-[11px] text-ink-muted dark:text-slate-400">
                  <div className="flex items-center gap-1.5 font-semibold text-ink-primary dark:text-slate-200">
                    <span className="px-1.5 py-0.5 rounded text-[10px] uppercase font-mono bg-slate-200 dark:bg-slate-800 text-slate-800 dark:text-slate-300">
                      {ev.type}
                    </span>
                    {ev.actor && (
                      <span className="inline-flex items-center gap-0.5 text-xs text-ink-muted dark:text-slate-400 font-normal">
                        <User className="w-3 h-3 text-slate-400" aria-hidden="true" />
                        <span>{ev.actor}</span>
                      </span>
                    )}
                  </div>
                  <time className="font-mono text-[10px] text-slate-500 dark:text-slate-400">
                    {ev.timestamp}
                  </time>
                </div>

                <p className="text-xs text-ink-secondary dark:text-slate-300 mt-1 leading-relaxed break-words">
                  {ev.description}
                </p>

                {/* Transition detail if available */}
                {ev.old_value && ev.new_value && (
                  <div className="inline-flex items-center gap-1.5 mt-1 text-[11px] font-mono text-slate-600 dark:text-slate-400 bg-white dark:bg-slate-800 px-2 py-0.5 rounded border border-surface-border dark:border-surface-darkBorder">
                    <span className="line-through text-slate-400">{ev.old_value}</span>
                    <ArrowRight className="w-3 h-3 text-slate-400" aria-hidden="true" />
                    <span className="font-semibold text-brand-700 dark:text-blue-300">{ev.new_value}</span>
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      ) : (
        /* Honest, truthful state when backend event history is not yet connected */
        <div className="py-3 px-3.5 rounded-flat bg-white dark:bg-slate-800/80 border border-surface-border dark:border-surface-darkBorder text-xs text-ink-muted dark:text-slate-400 space-y-2">
          <div className="flex items-start gap-2">
            <Clock className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" aria-hidden="true" />
            <div className="leading-relaxed">
              <p className="font-medium text-ink-primary dark:text-white mb-0.5">
                No Event History Ledger Recorded
              </p>
              <p className="text-[11px]">
                Detailed event transitions (assignments, status changes, and reassignment audits) will appear here once the backend PostgreSQL event ledger is connected.
              </p>
            </div>
          </div>

          {(createdAt || updatedAt) && (
            <div className="pt-2 border-t border-slate-100 dark:border-slate-700 flex flex-wrap gap-4 text-[11px] font-mono text-slate-500 dark:text-slate-400">
              {createdAt && <span>Created: {createdAt}</span>}
              {updatedAt && <span>Updated: {updatedAt}</span>}
            </div>
          )}
        </div>
      )}
    </section>
  );
};
