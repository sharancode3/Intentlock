import React from 'react';
import {
  ArrowLeft,
  Ticket,
  User,
  Tag,
  Building,
  Calendar,
  Clock,
  AlertCircle,
  CheckCircle2,
} from 'lucide-react';
import type { TicketRecord, TicketPriority, TicketStatus } from '../../types/payloads';
import { TicketTimeline } from './TicketTimeline';

export interface TicketDetailsProps {
  ticket: TicketRecord;
  onBack?: () => void;
  className?: string;
}

/**
 * Priority pill styles matching UI_UX.md Section 6.
 */
export function getPriorityBadgeClass(priority: TicketPriority): string {
  const normalized = String(priority).toUpperCase();
  switch (normalized) {
    case 'URGENT':
      return 'bg-red-100 text-red-800 border-red-300 dark:bg-red-950/60 dark:text-red-300 dark:border-red-800';
    case 'HIGH':
      return 'bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800';
    case 'NORMAL':
      return 'bg-blue-100 text-blue-800 border-blue-300 dark:bg-blue-950/60 dark:text-blue-300 dark:border-blue-800';
    case 'LOW':
    default:
      return 'bg-slate-100 text-slate-800 border-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700';
  }
}

/**
 * Status pill styles.
 */
export function getStatusBadgeClass(status: TicketStatus): string {
  const normalized = String(status).toUpperCase();
  switch (normalized) {
    case 'OPEN':
      return 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/50 dark:text-blue-300 dark:border-blue-800';
    case 'IN_PROGRESS':
      return 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/50 dark:text-amber-300 dark:border-amber-800';
    case 'RESOLVED':
      return 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/50 dark:text-emerald-300 dark:border-emerald-800';
    case 'CLOSED':
      return 'bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700';
    default:
      return 'bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700';
  }
}

/**
 * TicketDetails — Full detailed card for a single support ticket.
 */
export const TicketDetails: React.FC<TicketDetailsProps> = ({
  ticket,
  onBack,
  className = '',
}) => {
  const priorityClass = getPriorityBadgeClass(ticket.priority);
  const statusClass = getStatusBadgeClass(ticket.status);

  return (
    <article
      aria-label={`Ticket Details: ${ticket.title}`}
      className={`space-y-4 ${className}`}
    >
      {/* Navigation and Header Actions */}
      <div className="flex items-center justify-between gap-2 pb-2 border-b border-surface-border/50 dark:border-surface-darkBorder/50">
        {onBack && (
          <button
            type="button"
            onClick={onBack}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-brand-700 dark:text-blue-400 hover:text-brand-800 dark:hover:text-blue-300 py-1 px-2.5 rounded-flat border border-surface-border dark:border-surface-darkBorder bg-white dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-700 transition-colors"
            aria-label="Back to ticket list"
          >
            <ArrowLeft className="w-3.5 h-3.5" aria-hidden="true" />
            <span>Back to Tickets</span>
          </button>
        )}

        <div className="flex items-center gap-2 ml-auto">
          <span className="font-mono text-xs font-bold px-2.5 py-0.5 rounded-flat bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700">
            #{ticket.ticket_id}
          </span>
          <span className={`px-2 py-0.5 text-xs font-bold rounded-flat border uppercase tracking-wider ${priorityClass}`}>
            {ticket.priority}
          </span>
          <span className={`px-2 py-0.5 text-xs font-semibold rounded-flat border uppercase tracking-wider ${statusClass}`}>
            {ticket.status}
          </span>
        </div>
      </div>

      {/* Ticket Title & Identity */}
      <div>
        <h3 className="text-base sm:text-lg font-bold text-ink-primary dark:text-white leading-snug break-words">
          {ticket.title}
        </h3>
        {ticket.category && (
          <div className="mt-1.5 inline-flex items-center gap-1 text-xs text-ink-muted dark:text-slate-400 bg-slate-50 dark:bg-slate-900/60 px-2 py-0.5 rounded border border-surface-border/60 dark:border-surface-darkBorder/60">
            <Tag className="w-3 h-3 text-slate-400" aria-hidden="true" />
            <span>Category: {ticket.category}</span>
          </div>
        )}
      </div>

      {/* Description body */}
      {ticket.description ? (
        <div className="rounded-flat border border-surface-border dark:border-surface-darkBorder bg-slate-50/60 dark:bg-slate-900/40 p-3.5 text-sm text-ink-secondary dark:text-slate-200 leading-relaxed whitespace-pre-line break-words">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-muted dark:text-slate-400 mb-1">
            Description
          </h4>
          <p>{ticket.description}</p>
        </div>
      ) : (
        <div className="text-xs text-ink-muted dark:text-slate-400 italic">
          No detailed description provided with this ticket.
        </div>
      )}

      {/* Attributes Grid */}
      <dl className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
        {ticket.assigned_to && (
          <div className="p-2.5 rounded-flat bg-white dark:bg-slate-800/80 border border-surface-border dark:border-surface-darkBorder">
            <dt className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted dark:text-slate-400">
              Assigned To
            </dt>
            <dd className="font-medium text-ink-primary dark:text-slate-200 mt-0.5 flex items-center gap-1.5">
              <User className="w-3.5 h-3.5 text-slate-400" aria-hidden="true" />
              <span>{ticket.assigned_to}</span>
            </dd>
          </div>
        )}

        {ticket.owner_id && (
          <div className="p-2.5 rounded-flat bg-white dark:bg-slate-800/80 border border-surface-border dark:border-surface-darkBorder">
            <dt className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted dark:text-slate-400">
              Reporter / Owner
            </dt>
            <dd className="font-mono text-xs font-medium text-ink-primary dark:text-slate-200 mt-0.5">
              {ticket.owner_id}
            </dd>
          </div>
        )}

        {ticket.created_at && (
          <div className="p-2.5 rounded-flat bg-white dark:bg-slate-800/80 border border-surface-border dark:border-surface-darkBorder">
            <dt className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted dark:text-slate-400">
              Created Timestamp
            </dt>
            <dd className="font-mono text-[11px] text-slate-600 dark:text-slate-300 mt-0.5 flex items-center gap-1.5">
              <Calendar className="w-3.5 h-3.5 text-slate-400" aria-hidden="true" />
              <span>{ticket.created_at}</span>
            </dd>
          </div>
        )}

        {ticket.updated_at && (
          <div className="p-2.5 rounded-flat bg-white dark:bg-slate-800/80 border border-surface-border dark:border-surface-darkBorder">
            <dt className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted dark:text-slate-400">
              Last Updated
            </dt>
            <dd className="font-mono text-[11px] text-slate-600 dark:text-slate-300 mt-0.5 flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-slate-400" aria-hidden="true" />
              <span>{ticket.updated_at}</span>
            </dd>
          </div>
        )}
      </dl>

      {/* Embedded Lifecycle Timeline */}
      <TicketTimeline
        events={ticket.events}
        createdAt={ticket.created_at}
        updatedAt={ticket.updated_at}
      />
    </article>
  );
};
