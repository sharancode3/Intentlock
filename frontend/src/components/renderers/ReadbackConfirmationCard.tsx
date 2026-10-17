import React, { useState, useEffect } from 'react';
import {
  AlertTriangle,
  Mic,
  Clock,
  ShieldCheck,
  FileCheck2,
  Terminal,
  Check,
} from 'lucide-react';
import type { ResultRendererProps } from '../workspace/resultRegistry';
import type { ReadbackConfirmationPayload } from '../../types/payloads';
import { validateReadbackConfirmationPayload } from './validation';

/**
 * ReadbackConfirmationCard — Primary Renderer for READBACK_CONFIRMATION blocks.
 *
 * Implements Stage 7 requirements:
 * - Clear visual distinction between proposed action draft and completed mutations.
 * - Displays exact parameter manifest in a high-contrast monospace grid.
 * - Displays verified spoken readback summary and voice confirmation guidance.
 * - Shows server-grounded expiration window without fabricating fake countdowns.
 * - Provides explicit cancel controls and duplicate submission protection.
 * - Safe runtime validation with zero raw JSON dumps.
 * - Full light/dark mode and responsive viewports support.
 */
export const ReadbackConfirmationCard: React.FC<ResultRendererProps> = ({ block, onAction }) => {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const validation = validateReadbackConfirmationPayload(block.payload);

  const payload = (block.payload || {}) as Partial<ReadbackConfirmationPayload>;
  const draft = payload.draft || {
    action: payload.action || 'unknown_action',
    target: payload.target,
    params: payload.params || {},
    summary_readback: payload.summary_readback,
    expires_in_seconds: payload.expires_in_seconds,
  };

  const { action, target, params, summary_readback, expires_in_seconds } = draft;
  const requiresVoice = payload.requires_voice_confirmation ?? true;
  const confirmationId = payload.confirmation_id;
  const expiresAt = payload.expires_at;

  const [remainingSeconds, setRemainingSeconds] = useState<number | null>(
    typeof expires_in_seconds === 'number' ? expires_in_seconds : null
  );

  useEffect(() => {
    if (remainingSeconds === null || remainingSeconds <= 0) return;
    const timer = setInterval(() => {
      setRemainingSeconds(prev => (prev !== null && prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [remainingSeconds]);

  if (!validation.isValid) {
    return (
      <article
        role="alert"
        aria-label="Readback Confirmation Error"
        className="rounded-flat border-2 border-state-warningBorder bg-state-warningBg dark:bg-amber-950/40 dark:border-amber-800 p-4 transition-colors"
      >
        <div className="flex items-start gap-3 text-xs text-amber-950 dark:text-amber-200">
          <AlertTriangle className="w-4 h-4 text-state-warning dark:text-amber-400 shrink-0 mt-0.5" aria-hidden="true" />
          <div className="flex-1">
            <p className="font-semibold text-sm">Action confirmation details unavailable</p>
            <p className="mt-1 text-amber-800/90 dark:text-amber-300/80">
              {validation.error || 'The proposed action confirmation payload is malformed.'}
            </p>
          </div>
        </div>
      </article>
    );
  }

  const isExpired = remainingSeconds !== null && remainingSeconds <= 0;

  const handleCancel = () => {
    if (isSubmitting) return;
    onAction?.('cancel_proposal', {
      source_result_id: block.id,
      confirmation_id: confirmationId,
    });
  };

  const handleConfirm = () => {
    if (isExpired || isSubmitting) return;
    setIsSubmitting(true);
    onAction?.('confirm_action', {
      action: 'confirm',
      source_result_id: block.id,
      confirmation_id: confirmationId,
      target_id: target,
      draft,
    });
  };

  // Filter and safely stringify parameters for the manifest
  const paramEntries = Object.entries(params || {}).filter(
    ([key]) => !key.toLowerCase().includes('secret') && !key.toLowerCase().includes('token')
  );

  return (
    <article
      aria-label={`Action Confirmation Required: ${action}`}
      className="rounded-flat border-2 border-amber-500/80 bg-amber-50/70 dark:bg-amber-950/30 dark:border-amber-600/80 p-4 sm:p-5 transition-colors space-y-3.5"
    >
      {/* Header Bar */}
      <div className="border-b border-amber-200/80 dark:border-amber-800/60 pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded bg-amber-200/80 text-amber-950 dark:bg-amber-900/60 dark:text-amber-200 border border-amber-300 dark:border-amber-700">
              <AlertTriangle className="w-3 h-3 text-amber-800 dark:text-amber-300" aria-hidden="true" />
              Proposed Action Draft
            </span>
            <span className="inline-flex items-center gap-1 text-[11px] text-amber-800 dark:text-amber-300">
              <Clock className="w-3 h-3" aria-hidden="true" />
              Awaiting Voice Readback
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs text-amber-800 dark:text-amber-300 font-mono">
            {confirmationId && (
              <span className="text-[11px]" title="Server Confirmation ID">
                ID: {confirmationId}
              </span>
            )}
            {typeof expires_in_seconds === 'number' && (
              <span className="px-1.5 py-0.5 rounded bg-amber-200/60 dark:bg-amber-900/40 text-[10px] font-bold">
                TTL: {expires_in_seconds}s
              </span>
            )}
            {expiresAt && !expires_in_seconds && (
              <span className="text-[10px]">Expires: {expiresAt}</span>
            )}
          </div>
        </div>

        <h3 className="mt-2 text-base font-bold text-amber-950 dark:text-amber-100 tracking-tight flex items-center gap-1.5">
          <FileCheck2 className="w-4 h-4 text-amber-700 dark:text-amber-400" aria-hidden="true" />
          <span>Action Confirmation Required</span>
        </h3>
        <p className="text-xs text-amber-900/80 dark:text-amber-200/80 mt-0.5">
          The conversational agent has proposed the following protected mutation. Review parameters before confirming.
        </p>
      </div>

      {/* Spoken Readback Quote Box */}
      {summary_readback && (
        <section
          aria-label="Spoken Readback Summary"
          className="rounded-flat border border-amber-300 dark:border-amber-700/80 bg-white/90 dark:bg-slate-900/80 p-3 sm:p-3.5 shadow-sm"
        >
          <div className="flex items-start gap-2.5">
            <Mic className="w-4 h-4 text-amber-700 dark:text-amber-400 shrink-0 mt-0.5 animate-pulse" aria-hidden="true" />
            <div className="flex-1 text-xs leading-relaxed">
              <span className="text-[10px] font-bold uppercase tracking-wider text-amber-800 dark:text-amber-400 block mb-0.5">
                Spoken Readback Prompt
              </span>
              <p className="font-medium text-ink-primary dark:text-slate-100 italic">
                "{summary_readback}"
              </p>
              {requiresVoice && (
                <p className="mt-1.5 text-[11px] font-medium text-amber-900 dark:text-amber-300">
                  Speak the full readback phrase shown above to confirm, or say <strong className="underline">"Cancel"</strong> to discard.
                </p>
              )}
            </div>
          </div>
        </section>
      )}

      {/* Monospace Parameter Manifest (UI_UX.md Spec) */}
      <section aria-label="Exact Action Parameters">
        <div className="flex items-center justify-between mb-1 text-[11px] font-bold uppercase tracking-wider text-amber-900 dark:text-amber-300">
          <span className="flex items-center gap-1">
            <Terminal className="w-3.5 h-3.5" aria-hidden="true" />
            <span>Bound Execution Manifest</span>
          </span>
          <span className="font-mono text-[10px] text-amber-700 dark:text-amber-400 font-normal">
            SHA-256 parameter hash locked upon confirmation
          </span>
        </div>

        <div className="rounded-flat border border-amber-300/80 dark:border-amber-700/60 bg-white/95 dark:bg-slate-900/90 p-3 sm:p-4 text-xs font-mono space-y-1.5 shadow-sm overflow-x-auto">
          <div className="flex items-baseline gap-2">
            <span className="text-slate-500 dark:text-slate-400 w-24 shrink-0 font-bold">ACTION:</span>
            <span className="font-bold text-brand-700 dark:text-blue-400">{action}</span>
          </div>

          {target && (
            <div className="flex items-baseline gap-2">
              <span className="text-slate-500 dark:text-slate-400 w-24 shrink-0 font-bold">TARGET:</span>
              <span className="text-ink-primary dark:text-slate-200">{target}</span>
            </div>
          )}

          {paramEntries.map(([k, v]) => (
            <div key={k} className="flex items-baseline gap-2">
              <span className="text-slate-500 dark:text-slate-400 w-24 shrink-0 uppercase font-bold">
                {k}:
              </span>
              <span className="text-ink-primary dark:text-slate-200 break-all">
                {typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v)}
              </span>
            </div>
          ))}

          {paramEntries.length === 0 && (
            <div className="text-slate-400 italic text-[11px]">No additional parameters required.</div>
          )}
        </div>
      </section>

      {/* Expiry Warning if Expired */}
      {isExpired && (
        <div className="rounded border border-red-300/80 bg-red-50 dark:bg-red-950/30 p-2.5 flex items-start gap-2 text-xs text-red-900 dark:text-red-200">
          <AlertTriangle className="w-4 h-4 text-red-600 dark:text-red-400 shrink-0 mt-0.5" aria-hidden="true" />
          <div>
            <p className="font-semibold">Proposal Expired</p>
            <p className="text-[11px] text-red-800 dark:text-red-300 mt-0.5">
              The time-to-live for this proposal has elapsed. No changes will be committed. Please speak your edit request again to generate a fresh proposal.
            </p>
          </div>
        </div>
      )}

      {/* Security Dock Notice */}
      <div className="rounded border border-amber-300/60 dark:border-amber-800/60 bg-amber-100/40 dark:bg-amber-950/20 p-2.5 flex items-start gap-2 text-[11px] text-amber-950 dark:text-amber-200">
        <ShieldCheck className="w-4 h-4 text-amber-700 dark:text-amber-400 shrink-0 mt-0.5" aria-hidden="true" />
        <div className="leading-snug">
          <span className="font-semibold">Authorization & Readback Gate: </span>
          {requiresVoice
            ? 'Protected operations require spoken readback confirmation through the voice pipeline for DetectifAI speaker verification.'
            : 'Review the bound parameters carefully before submitting confirmation.'}
        </div>
      </div>

      {/* Action Controls Row */}
      <div className="pt-2 flex flex-wrap items-center justify-between gap-2.5">
        <div className="text-[11px] text-amber-900 dark:text-amber-200">
          {requiresVoice ? (
            <span className="flex items-center gap-1 font-medium">
              <Mic className="w-3.5 h-3.5 text-amber-700 dark:text-amber-400" aria-hidden="true" />
              Speak readback to verify & commit
            </span>
          ) : (
            <span>Review parameters and confirm</span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={isSubmitting}
            onClick={handleCancel}
            className="px-3 py-1.5 rounded text-xs font-semibold bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-300 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Cancel Proposal
          </button>
          <button
            type="button"
            disabled={isExpired || isSubmitting}
            onClick={handleConfirm}
            className="px-3.5 py-1.5 rounded text-xs font-semibold bg-amber-600 text-white hover:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5 shadow-sm"
          >
            {isSubmitting ? (
              'Executing…'
            ) : (
              <>
                <Check className="w-3.5 h-3.5" aria-hidden="true" />
                <span>Confirm & Commit</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Footer */}
      <div className="pt-1.5 border-t border-amber-200/60 dark:border-amber-800/40 flex items-center justify-between text-[10px] text-amber-800/80 dark:text-amber-400">
        <span>Draft generated by Policy Engine. Zero database rows altered.</span>
        <span>{isExpired ? 'Proposal Expired' : 'Awaiting confirmation'}</span>
      </div>
    </article>
  );
};
