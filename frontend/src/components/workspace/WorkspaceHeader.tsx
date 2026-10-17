import React from 'react';
import { ShieldCheck, ShieldAlert, LogOut, Settings as SettingsIcon, Clock, Columns, MessageSquare } from 'lucide-react';
import { IntentLockLogo } from '../common/IntentLockLogo';
import type { SessionInfo, ViewMode } from '../../types';

interface WorkspaceHeaderProps {
  session: SessionInfo;
  viewMode?: ViewMode;
  onToggleViewMode?: () => void;
  onEndSession: () => void;
  onOpenSettings: () => void;
}

export const WorkspaceHeader: React.FC<WorkspaceHeaderProps> = ({
  session,
  viewMode = 'split',
  onToggleViewMode,
  onEndSession,
  onOpenSettings,
}) => {
  const isVerified = session.state === 'VERIFIED' && session.actor;
  const isExpired = session.state === 'EXPIRED';
  const isVerifying = session.state === 'VERIFYING';

  return (
    <header className="w-full bg-white dark:bg-surface-darkBg border-b border-surface-border dark:border-surface-darkBorder py-2.5 px-4 sm:px-6 flex items-center justify-between gap-3 shrink-0">
      {/* Brand Identity with Custom Logo */}
      <div className="flex items-center gap-3 min-w-0">
        <IntentLockLogo size={34} />
        <div className="min-w-0">
          <h1 className="text-base sm:text-lg font-bold tracking-tight text-ink-primary dark:text-white leading-tight">
            IntentLock
          </h1>
          <p className="text-xs text-ink-muted dark:text-slate-400 truncate">
            Shared AI Helpdesk &bull; Verified Voice Gateway
          </p>
        </div>
      </div>

      {/* Right Controls */}
      <div className="flex items-center gap-2 sm:gap-3 shrink-0">
        {/* Desktop View Mode Switcher (Split vs Feed) */}
        {onToggleViewMode && (
          <button
            type="button"
            onClick={onToggleViewMode}
            className="hidden lg:flex items-center gap-1.5 px-2.5 py-1.5 rounded-flat text-xs font-medium text-slate-700 dark:text-slate-300 border border-surface-border dark:border-surface-darkBorder bg-surface-card dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors focus:outline-none focus:ring-2 focus:ring-brand-700 min-h-[36px]"
            title={viewMode === 'split' ? 'Switch to Full Feed View' : 'Switch to Split Dual-Pane View'}
            aria-label="Toggle workspace view mode"
          >
            {viewMode === 'split' ? (
              <>
                <Columns className="w-3.5 h-3.5 text-brand-700 dark:text-blue-400" />
                <span>Split View</span>
              </>
            ) : (
              <>
                <MessageSquare className="w-3.5 h-3.5 text-brand-700 dark:text-blue-400" />
                <span>Feed View</span>
              </>
            )}
          </button>
        )}

        {/* Truthful Session Status Badge */}
        {isVerified ? (
          <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-flat bg-state-successBg border border-state-successBorder text-emerald-900 dark:bg-emerald-950/50 dark:border-emerald-800 dark:text-emerald-200 text-xs sm:text-sm font-medium">
            <ShieldCheck className="w-4 h-4 text-state-success shrink-0" aria-hidden="true" />
            <div className="flex items-center gap-1.5 truncate max-w-[130px] sm:max-w-[220px]">
              <span className="truncate font-semibold">{session.actor?.fullName}</span>
              <span className="text-xs opacity-75 hidden md:inline">({session.actor?.employeeId})</span>
              {session.actor?.role && (
                <span className="text-[10px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded bg-emerald-200/80 dark:bg-emerald-900/60 text-emerald-900 dark:text-emerald-200 hidden sm:inline">
                  {session.actor.role}
                </span>
              )}
            </div>
            {session.actor && session.actor.expiresInSeconds > 0 && (
              <span className="inline-flex items-center gap-1 text-[11px] font-mono px-1.5 py-0.5 rounded bg-emerald-100/80 dark:bg-emerald-900/60 text-emerald-800 dark:text-emerald-300">
                <Clock className="w-3 h-3" />
                {session.actor.expiresInSeconds}s
              </span>
            )}
          </div>
        ) : isVerifying ? (
          <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-flat bg-state-warningBg border border-state-warningBorder text-amber-900 dark:bg-amber-950/50 dark:border-amber-800 dark:text-amber-200 text-xs sm:text-sm font-medium animate-pulse-subtle">
            <span className="w-2 h-2 rounded-full bg-state-warning shrink-0" />
            <span>Verifying Voice...</span>
          </div>
        ) : isExpired ? (
          <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-flat bg-state-dangerBg border border-state-dangerBorder text-red-900 dark:bg-red-950/50 dark:border-red-800 dark:text-red-200 text-xs sm:text-sm font-medium">
            <ShieldAlert className="w-4 h-4 text-state-danger shrink-0" aria-hidden="true" />
            <span>Session Expired</span>
          </div>
        ) : (
          <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-flat bg-slate-100 border border-slate-200 text-slate-700 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-300 text-xs sm:text-sm font-medium">
            <span className="w-2 h-2 rounded-full bg-slate-400 shrink-0" />
            <span className="truncate">Anonymous Visitor</span>
          </div>
        )}

        {/* Conditional End Session Action */}
        {(isVerified || isExpired) && (
          <button
            type="button"
            onClick={onEndSession}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-flat text-xs sm:text-sm font-medium text-state-danger border border-state-dangerBorder hover:bg-state-dangerBg active:bg-red-100 dark:hover:bg-red-950/40 transition-colors focus:outline-none focus:ring-2 focus:ring-state-danger min-h-[36px]"
            title="End current session and clear private records"
            aria-label="End active session"
          >
            <LogOut className="w-4 h-4 shrink-0" />
            <span className="hidden sm:inline">End Session</span>
          </button>
        )}

        {/* Settings Modal Trigger */}
        <button
          type="button"
          onClick={onOpenSettings}
          className="p-2 rounded-flat text-slate-600 dark:text-slate-300 hover:text-ink-primary dark:hover:text-white border border-surface-border dark:border-surface-darkBorder bg-surface-card dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors focus:outline-none focus:ring-2 focus:ring-brand-700 min-h-[36px] min-w-[36px] flex items-center justify-center"
          title="Open Workspace Settings"
          aria-label="Workspace settings"
        >
          <SettingsIcon className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
};
