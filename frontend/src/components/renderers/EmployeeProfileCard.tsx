import React from 'react';
import { User, ShieldCheck, Mail, Building2, Briefcase, FolderGit2, AlertCircle } from 'lucide-react';
import type { ResultRendererProps } from '../workspace/resultRegistry';
import { validateEmployeeProfilePayload } from './validation';

/**
 * EmployeeProfileCard — Renderer for EMPLOYEE_PROFILE result blocks.
 *
 * Adheres strictly to UI_UX.md section 6, TRD, and SECURITY.md:
 * - Render employee name, ID, role/title.
 * - Render department and team when available.
 * - Render corporate email when available.
 * - Render active projects list when provided.
 * - Render employment status only when present in the actual contract.
 * - Safe fallback for malformed or missing payloads without raw JSON dumps.
 * - Flat border design system matching PublicFaqCard and DenialBanner.
 * - Dark mode, responsive wrapping, and accessible semantic markup.
 * - Zero administrative controls, zero client-calculated verification.
 */
export const EmployeeProfileCard: React.FC<ResultRendererProps> = ({ block }) => {
  const validation = validateEmployeeProfilePayload(block.payload);

  if (!validation.isValid) {
    return (
      <article
        className="rounded-flat border-2 border-surface-border dark:border-surface-darkBorder bg-surface-card dark:bg-slate-800/60 p-4 transition-colors"
        aria-label="Employee Profile Unavailable"
      >
        <div className="flex items-start gap-3 text-ink-muted dark:text-slate-400 text-xs">
          <AlertCircle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" aria-hidden="true" />
          <div className="flex-1">
            <h4 className="font-semibold text-ink-primary dark:text-white text-sm mb-1">
              Employee Profile Unavailable
            </h4>
            <p>{validation.error}</p>
          </div>
        </div>
      </article>
    );
  }

  const { employee } = validation.data;
  const { id, name, role, department, team, email, active_projects, status } = employee;

  // Format role for presentation (e.g. "manager" -> "Manager")
  const formattedRole = role ? role.charAt(0).toUpperCase() + role.slice(1) : '';

  return (
    <article
      className="rounded-flat border-2 border-surface-border dark:border-surface-darkBorder bg-white dark:bg-slate-800/90 p-4 sm:p-5 transition-colors space-y-4"
      aria-label={`Employee Profile: ${name}`}
    >
      {/* Header with Classification Badge & Employee ID */}
      <header className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-surface-border/50 dark:border-surface-darkBorder/50">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 bg-slate-100 dark:bg-slate-700/80 text-slate-700 dark:text-slate-300 font-bold px-2.5 py-0.5 text-[11px] rounded-flat uppercase tracking-wider">
            <ShieldCheck className="w-3.5 h-3.5 text-brand-700 dark:text-blue-400" aria-hidden="true" />
            Verified Directory
          </span>
          {status && (
            <span className="inline-flex items-center px-2 py-0.5 text-[11px] font-semibold rounded-flat bg-emerald-50 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800/60">
              {status}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs font-semibold px-2 py-0.5 rounded-flat bg-slate-50 dark:bg-slate-900 text-slate-700 dark:text-slate-300 border border-surface-border dark:border-surface-darkBorder">
            {id}
          </span>
          {block.timestamp && (
            <span className="text-[10px] font-mono text-ink-muted dark:text-slate-500">
              {block.timestamp}
            </span>
          )}
        </div>
      </header>

      {/* Primary Identity Section */}
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-flat bg-brand-50 dark:bg-blue-950/60 border border-brand-200 dark:border-blue-800 flex items-center justify-center shrink-0 mt-0.5">
          <User className="w-5 h-5 text-brand-700 dark:text-blue-400" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-base sm:text-lg font-bold text-ink-primary dark:text-white leading-tight break-words">
            {name}
          </h3>
          <div className="flex flex-wrap items-center gap-2 mt-1">
            <span className="inline-flex items-center gap-1 text-xs font-semibold text-brand-800 dark:text-blue-300 bg-brand-50/80 dark:bg-blue-950/40 px-2 py-0.5 rounded border border-brand-200/60 dark:border-blue-900/60">
              <Briefcase className="w-3 h-3 shrink-0" aria-hidden="true" />
              <span>{formattedRole}</span>
            </span>
          </div>
        </div>
      </div>

      {/* Metadata Attributes: Department, Team, Email */}
      {(department || team || email) && (
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 pt-2 border-t border-surface-border/50 dark:border-surface-darkBorder/50 text-xs text-ink-secondary dark:text-slate-300">
          {(department || team) && (
            <div className="flex items-start gap-2 bg-slate-50/60 dark:bg-slate-900/40 p-2.5 rounded-flat border border-surface-border/50 dark:border-surface-darkBorder/50">
              <Building2 className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" aria-hidden="true" />
              <div className="min-w-0">
                <dt className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted dark:text-slate-400">
                  Department & Team
                </dt>
                <dd className="font-medium text-ink-primary dark:text-slate-200 break-words mt-0.5">
                  {department}
                  {department && team ? ' • ' : ''}
                  {team}
                </dd>
              </div>
            </div>
          )}

          {email && (
            <div className="flex items-start gap-2 bg-slate-50/60 dark:bg-slate-900/40 p-2.5 rounded-flat border border-surface-border/50 dark:border-surface-darkBorder/50">
              <Mail className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" aria-hidden="true" />
              <div className="min-w-0">
                <dt className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted dark:text-slate-400">
                  Email Address
                </dt>
                <dd className="font-mono text-xs text-ink-primary dark:text-slate-200 break-all mt-0.5">
                  {email}
                </dd>
              </div>
            </div>
          )}
        </dl>
      )}

      {/* Active Projects (rendered when provided) */}
      {active_projects && (
        <div className="pt-2 border-t border-surface-border/50 dark:border-surface-darkBorder/50 space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-ink-primary dark:text-white">
            <FolderGit2 className="w-3.5 h-3.5 text-slate-400" aria-hidden="true" />
            <span>Active Projects ({active_projects.length})</span>
          </div>

          {active_projects.length > 0 ? (
            <ul className="flex flex-wrap gap-1.5" aria-label="Assigned projects">
              {active_projects.map((project, idx) => (
                <li
                  key={`${project}-${idx}`}
                  className="inline-flex items-center text-xs font-medium bg-slate-50 dark:bg-slate-900/60 text-slate-700 dark:text-slate-300 px-2.5 py-1 rounded-flat border border-surface-border dark:border-surface-darkBorder break-words max-w-full"
                >
                  {project}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-ink-muted dark:text-slate-400 italic">
              No active project assignments.
            </p>
          )}
        </div>
      )}
    </article>
  );
};
