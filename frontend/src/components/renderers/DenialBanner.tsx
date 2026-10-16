import React from 'react';
import { ShieldAlert, ArrowRight, Info } from 'lucide-react';
import type { ResultRendererProps } from '../workspace/resultRegistry';
import { validateDenialBannerPayload } from './validation';

/**
 * DenialBanner — Renderer for DENIAL_BANNER result blocks.
 *
 * Requirements:
 * - Clear, professional denial messaging returned by the backend policy engine.
 * - Distinguishes denial from generic network or application crashes.
 * - Never calculates authorization locally.
 * - Never discloses internal policy rules, employee secrets, or stack traces.
 * - Never provides an unauthorized retry or bypass button.
 * - Accessible via role="alert" with semantic markup.
 * - Full light/dark mode support.
 */
export const DenialBanner: React.FC<ResultRendererProps> = ({ block }) => {
  const validation = validateDenialBannerPayload(block.payload);

  if (!validation.isValid) {
    return (
      <section
        role="alert"
        aria-label="Access Denied"
        className="rounded-flat border-2 border-state-dangerBorder bg-state-dangerBg dark:bg-red-950/40 dark:border-red-800 p-4 transition-colors"
      >
        <div className="flex items-start gap-3">
          <ShieldAlert className="w-5 h-5 text-state-danger dark:text-red-400 shrink-0 mt-0.5" aria-hidden="true" />
          <div className="flex-1 text-sm text-red-950 dark:text-red-200 leading-relaxed">
            <h4 className="font-semibold text-base mb-1 tracking-tight">
              {block.title || 'Access Denied'}
            </h4>
            <p className="text-xs">
              Access to this requested action or resource was denied by policy. Additional details are unavailable.
            </p>
          </div>
        </div>
      </section>
    );
  }

  const { message, code, reason, next_step } = validation.data;
  const displayTitle = block.title || 'Access Denied';

  return (
    <section
      role="alert"
      aria-label={displayTitle}
      className="rounded-flat border-2 border-state-dangerBorder bg-state-dangerBg dark:bg-red-950/40 dark:border-red-800 p-4 sm:p-5 transition-colors space-y-3"
    >
      {/* Denial Header */}
      <header className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-red-200 dark:border-red-800/60">
        <div className="flex items-center gap-2">
          <ShieldAlert className="w-5 h-5 text-state-danger dark:text-red-400 shrink-0" aria-hidden="true" />
          <h3 className="font-bold text-base text-red-950 dark:text-red-100 tracking-tight">
            {displayTitle}
          </h3>
        </div>
        {code && (
          <span className="font-mono text-[11px] font-semibold px-2 py-0.5 rounded-flat bg-red-100 dark:bg-red-900/60 text-red-800 dark:text-red-200 border border-red-200 dark:border-red-700/60 uppercase">
            {code}
          </span>
        )}
      </header>

      {/* Primary Message */}
      <p className="text-sm text-red-950 dark:text-red-200 leading-relaxed font-normal break-words">
        {message}
      </p>

      {/* Optional Safe Reason */}
      {reason && (
        <div className="flex items-start gap-2 text-xs text-red-900 dark:text-red-300 bg-white/70 dark:bg-slate-900/40 p-2.5 rounded-flat border border-red-200/80 dark:border-red-800/50">
          <Info className="w-4 h-4 text-red-600 dark:text-red-400 shrink-0 mt-0.5" aria-hidden="true" />
          <div className="leading-relaxed">
            <span className="font-semibold">Reason: </span>
            <span>{reason}</span>
          </div>
        </div>
      )}

      {/* Optional Safe Next Step / Guidance */}
      {next_step && (
        <footer className="flex items-start gap-2 text-xs text-red-900 dark:text-red-300 pt-1">
          <ArrowRight className="w-3.5 h-3.5 text-state-danger dark:text-red-400 shrink-0 mt-0.5" aria-hidden="true" />
          <div className="leading-relaxed">
            <span className="font-semibold">Suggested Step: </span>
            <span>{next_step}</span>
          </div>
        </footer>
      )}

      {/* Security Audit Footnote */}
      <div className="pt-2 border-t border-red-200/60 dark:border-red-900/40 flex items-center justify-between text-[10px] text-red-800/70 dark:text-red-400/60">
        <span>Deterministic policy engine decision.</span>
        <span>Zero database rows altered</span>
      </div>
    </section>
  );
};
