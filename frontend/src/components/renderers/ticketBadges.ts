/**
 * IntentLock — Ticket Badge Utility Functions
 * Track 3: UNCLONE AGENTS (UNCLONE Hackathon 2026, BMSCE & DetectifAI)
 */

import type { TicketPriority, TicketStatus } from '../../types/payloads';

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
    case 'PENDING':
      return 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/50 dark:text-amber-300 dark:border-amber-800';
    case 'BLOCKED':
      return 'bg-red-50 text-red-700 border-red-200 dark:bg-red-950/50 dark:text-red-300 dark:border-red-800';
    case 'RESOLVED':
    case 'CLOSED':
      return 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/50 dark:text-emerald-300 dark:border-emerald-800';
    default:
      return 'bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700';
  }
}
