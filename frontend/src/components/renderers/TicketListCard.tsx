import React, { useState } from 'react';
import {
  Ticket,
  AlertCircle,
  Search,
  Filter,
  Tag,
  ChevronRight,
} from 'lucide-react';
import type { ResultRendererProps } from '../workspace/resultRegistry';
import type { TicketStatus } from '../../types/payloads';
import { validateTicketListPayload } from './validation';
import { TicketDetails, getPriorityBadgeClass, getStatusBadgeClass } from './TicketDetails';

/**
 * TicketListCard — Renderer for TICKET_LIST result blocks.
 *
 * Implements Stage 4 requirements:
 * - Structured ticket table / card list
 * - Priority and status indicators conforming to UI_UX.md
 * - Responsive desktop table and mobile stacked card list
 * - Interactive local ticket selection drill-down into TicketDetails
 * - Client-side search and status filter
 * - Safe validation fallback with zero raw JSON dumps
 * - Full light/dark mode support
 */
export const TicketListCard: React.FC<ResultRendererProps> = ({ block }) => {
  const validation = validateTicketListPayload(block.payload);

  const [selectedTicketId, setSelectedTicketId] = useState<string | number | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'ALL' | TicketStatus>('ALL');

  if (!validation.isValid) {
    return (
      <article
        className="rounded-flat border-2 border-surface-border dark:border-surface-darkBorder bg-surface-card dark:bg-slate-800/60 p-4 transition-colors"
        aria-label="Ticket List Error"
      >
        <div className="flex items-start gap-3 text-ink-muted dark:text-slate-400 text-xs">
          <AlertCircle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" aria-hidden="true" />
          <div className="flex-1">
            <h4 className="font-semibold text-ink-primary dark:text-white text-sm mb-1">
              Ticket Data Unavailable
            </h4>
            <p>{validation.error}</p>
          </div>
        </div>
      </article>
    );
  }

  const { tickets, title } = validation.data;
  const displayTitle = title || block.title || 'Assigned Support Tickets';

  // Find currently selected ticket if active
  const selectedTicket = selectedTicketId === null ? null
    : tickets.find((t) => String(t.ticket_id) === String(selectedTicketId)) || null;

  // Filtered tickets based on search query and status
  const filteredTickets = tickets.filter((ticket) => {
      // Status filter
      if (statusFilter !== 'ALL') {
        if (ticket.status.toUpperCase() !== statusFilter.toUpperCase()) {
          return false;
        }
      }
      // Search query
      if (searchQuery.trim().length > 0) {
        const query = searchQuery.toLowerCase().trim();
        const matchesTitle = ticket.title.toLowerCase().includes(query);
        const matchesId = String(ticket.ticket_id).toLowerCase().includes(query);
        const matchesCategory = ticket.category?.toLowerCase().includes(query) ?? false;
        const matchesAssignee = ticket.assigned_to?.toLowerCase().includes(query) ?? false;
        return matchesTitle || matchesId || matchesCategory || matchesAssignee;
      }
      return true;
  });

  // If a ticket is selected, render TicketDetails in place with Back navigation
  if (selectedTicket) {
    return (
      <article
        className="rounded-flat border-2 border-surface-border dark:border-surface-darkBorder bg-white dark:bg-slate-800/90 p-4 sm:p-5 transition-colors shadow-none"
        aria-label={`Ticket ${selectedTicket.ticket_id} Details`}
      >
        <TicketDetails
          ticket={selectedTicket}
          onBack={() => setSelectedTicketId(null)}
        />
      </article>
    );
  }

  return (
    <article
      className="rounded-flat border-2 border-surface-border dark:border-surface-darkBorder bg-white dark:bg-slate-800/90 p-4 sm:p-5 transition-colors space-y-3.5 shadow-none"
      aria-label={`Ticket List: ${displayTitle}`}
    >
      {/* Header with Classification Badge & Count */}
      <header className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-surface-border/50 dark:border-surface-darkBorder/50">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 bg-slate-100 dark:bg-slate-700/80 text-slate-700 dark:text-slate-300 font-bold px-2.5 py-0.5 text-[11px] rounded-flat uppercase tracking-wider">
            <Ticket className="w-3.5 h-3.5 text-brand-700 dark:text-blue-400" aria-hidden="true" />
            Scoped Tickets
          </span>
          <span className="inline-flex items-center px-2 py-0.5 text-[11px] font-mono font-semibold rounded-flat bg-slate-50 dark:bg-slate-900 text-slate-600 dark:text-slate-300 border border-surface-border dark:border-surface-darkBorder">
            {tickets.length} {tickets.length === 1 ? 'record' : 'records'}
          </span>
        </div>
        {block.timestamp && (
          <span className="text-[10px] font-mono text-ink-muted dark:text-slate-500">
            {block.timestamp}
          </span>
        )}
      </header>

      {/* Title */}
      <h3 className="text-sm sm:text-base font-bold text-ink-primary dark:text-white leading-snug break-words">
        {displayTitle}
      </h3>

      {/* Filter / Search Bar (rendered when tickets exist) */}
      {tickets.length > 0 && (
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 pt-1 text-xs">
          <div className="relative flex-1">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" aria-hidden="true" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by title, ID, category..."
              className="w-full pl-8 pr-3 py-1.5 rounded-flat text-xs border border-surface-border dark:border-surface-darkBorder bg-slate-50 dark:bg-slate-900 text-ink-primary dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-700 transition-colors"
              aria-label="Filter tickets by keyword"
            />
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            <Filter className="w-3.5 h-3.5 text-slate-400" aria-hidden="true" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as 'ALL' | TicketStatus)}
              className="px-2 py-1.5 rounded-flat text-xs border border-surface-border dark:border-surface-darkBorder bg-slate-50 dark:bg-slate-900 text-ink-primary dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-700 transition-colors"
              aria-label="Filter tickets by lifecycle status"
            >
              <option value="ALL">All Statuses</option>
              <option value="OPEN">Open</option>
              <option value="IN_PROGRESS">In Progress</option>
              <option value="RESOLVED">Resolved</option>
              <option value="CLOSED">Closed</option>
            </select>
          </div>
        </div>
      )}

      {/* Main Ticket Presentation: Empty state vs Desktop Table vs Mobile Stacked Cards */}
      {filteredTickets.length === 0 ? (
        <div className="text-center py-6 px-4 rounded-flat border border-dashed border-slate-200 dark:border-slate-700 text-xs text-ink-muted dark:text-slate-400 space-y-1">
          <p className="font-semibold text-ink-primary dark:text-white">
            {tickets.length === 0 ? 'No Support Tickets Found' : 'No Matching Tickets'}
          </p>
          <p className="text-[11px]">
            {tickets.length === 0
              ? 'You have zero open or assigned tickets matching your verified identity and role scope.'
              : 'Try clearing your search query or status filter to see other records.'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {/* Desktop Table View (visible on >= sm screens) */}
          <div className="hidden sm:block overflow-hidden rounded-flat border border-surface-border dark:border-surface-darkBorder">
            <table className="w-full text-left border-collapse text-xs">
              <thead className="bg-slate-100 dark:bg-slate-900/80 text-[11px] font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 border-b border-surface-border dark:border-surface-darkBorder">
                <tr>
                  <th scope="col" className="py-2.5 px-3 font-mono">ID</th>
                  <th scope="col" className="py-2.5 px-3">Title & Category</th>
                  <th scope="col" className="py-2.5 px-3">Priority</th>
                  <th scope="col" className="py-2.5 px-3">Status</th>
                  <th scope="col" className="py-2.5 px-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border/60 dark:divide-surface-darkBorder/60 bg-white dark:bg-slate-800/90">
                {filteredTickets.map((t) => (
                  <tr
                    key={String(t.ticket_id)}
                    className="hover:bg-slate-50 dark:hover:bg-slate-700/40 transition-colors cursor-pointer group"
                    onClick={() => setSelectedTicketId(t.ticket_id)}
                  >
                    <td className="py-2.5 px-3 font-mono font-bold text-ink-primary dark:text-white shrink-0">
                      #{t.ticket_id}
                    </td>
                    <td className="py-2.5 px-3 min-w-[160px]">
                      <div className="font-semibold text-ink-primary dark:text-white group-hover:text-brand-700 dark:group-hover:text-blue-400 transition-colors line-clamp-1">
                        {t.title}
                      </div>
                      {t.category && (
                        <div className="text-[10px] text-ink-muted dark:text-slate-400 flex items-center gap-1 mt-0.5">
                          <Tag className="w-2.5 h-2.5 text-slate-400" />
                          <span>{t.category}</span>
                          {t.assigned_to && <span>&bull; Assigned: {t.assigned_to}</span>}
                        </div>
                      )}
                    </td>
                    <td className="py-2.5 px-3 shrink-0">
                      <span className={`px-2 py-0.5 rounded text-[11px] font-bold border uppercase tracking-wider ${getPriorityBadgeClass(t.priority)}`}>
                        {t.priority}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 shrink-0">
                      <span className={`px-2 py-0.5 rounded text-[11px] font-semibold border uppercase tracking-wider ${getStatusBadgeClass(t.status)}`}>
                        {t.status}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-right shrink-0">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedTicketId(t.ticket_id);
                        }}
                        className="inline-flex items-center gap-1 text-[11px] font-semibold text-brand-700 dark:text-blue-400 hover:text-brand-800 dark:hover:text-blue-300 py-1 px-2 rounded hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                        aria-label={`View details for ticket ${t.ticket_id}`}
                      >
                        <span>Details</span>
                        <ChevronRight className="w-3.5 h-3.5" aria-hidden="true" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile Stacked Card View (visible on < sm screens) */}
          <div className="sm:hidden space-y-2">
            {filteredTickets.map((t) => (
              <div
                key={String(t.ticket_id)}
                onClick={() => setSelectedTicketId(t.ticket_id)}
                className="p-3 rounded-flat border border-surface-border dark:border-surface-darkBorder bg-slate-50/60 dark:bg-slate-900/40 hover:bg-slate-100 dark:hover:bg-slate-800/80 transition-colors cursor-pointer space-y-2"
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setSelectedTicketId(t.ticket_id);
                  }
                }}
                aria-label={`Ticket ${t.ticket_id}: ${t.title}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono font-bold text-xs text-ink-primary dark:text-white">
                    #{t.ticket_id}
                  </span>
                  <div className="flex items-center gap-1.5">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold border uppercase tracking-wider ${getPriorityBadgeClass(t.priority)}`}>
                      {t.priority}
                    </span>
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold border uppercase tracking-wider ${getStatusBadgeClass(t.status)}`}>
                      {t.status}
                    </span>
                  </div>
                </div>

                <h4 className="text-xs font-semibold text-ink-primary dark:text-white leading-snug break-words">
                  {t.title}
                </h4>

                <div className="flex items-center justify-between gap-2 pt-1 border-t border-slate-200/60 dark:border-slate-800 text-[11px] text-ink-muted dark:text-slate-400">
                  <span>{t.category || 'General'}</span>
                  <span className="text-brand-700 dark:text-blue-400 font-semibold inline-flex items-center gap-0.5">
                    <span>View Details</span>
                    <ChevronRight className="w-3 h-3" />
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </article>
  );
};
