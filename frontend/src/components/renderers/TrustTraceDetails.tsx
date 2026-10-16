import React from 'react';
import {
  X,
  ShieldAlert,
  ShieldCheck,
  Clock,
  KeyRound,
  FileText,
  Network,
  Info,
} from 'lucide-react';
import type { TrustTraceNode } from '../../types/payloads';

interface TrustTraceDetailsProps {
  node: TrustTraceNode | null;
  onClose: () => void;
}

export const TrustTraceDetails: React.FC<TrustTraceDetailsProps> = ({ node, onClose }) => {
  if (!node) return null;

  const {
    id,
    label,
    stage,
    status,
    detail,
    timestamp,
    reason,
    policy_decision,
    receipt_id,
    turn_id,
    requesting_agent,
    receiving_agent,
    requested_capability,
    handshake_outcome,
  } = node;

  const isPositive = status === 'PASS' || status === 'SUCCESS';
  const isNegative = status === 'FAIL' || status === 'DENIED' || status === 'ABORTED';
  const isPending = status === 'PENDING';

  return (
    <aside
      aria-label={`Security details for ${label}`}
      className="rounded-flat border-2 border-surface-border dark:border-surface-darkBorder bg-surface-card dark:bg-slate-900/90 p-3.5 text-xs shadow-md space-y-3"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2 border-b border-surface-border/60 dark:border-surface-darkBorder/60 pb-2">
        <div className="flex items-start gap-2">
          {isPositive && (
            <ShieldCheck className="w-4 h-4 text-emerald-600 dark:text-emerald-400 mt-0.5 shrink-0" aria-hidden="true" />
          )}
          {isNegative && (
            <ShieldAlert className="w-4 h-4 text-red-600 dark:text-red-400 mt-0.5 shrink-0" aria-hidden="true" />
          )}
          {isPending && (
            <Clock className="w-4 h-4 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" aria-hidden="true" />
          )}
          {!isPositive && !isNegative && !isPending && (
            <Info className="w-4 h-4 text-slate-500 mt-0.5 shrink-0" aria-hidden="true" />
          )}
          <div>
            <h4 className="font-bold text-ink-primary dark:text-slate-100 text-sm leading-tight">
              {label}
            </h4>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                {stage}
              </span>
              <span
                className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${
                  isPositive
                    ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300'
                    : isNegative
                    ? 'bg-red-100 text-red-800 dark:bg-red-950/60 dark:text-red-300'
                    : 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300'
                }`}
              >
                {status}
              </span>
            </div>
          </div>
        </div>

        <button
          type="button"
          onClick={onClose}
          className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1 rounded focus:outline-none focus:ring-1 focus:ring-brand-700"
          aria-label="Close node details"
        >
          <X className="w-4 h-4" aria-hidden="true" />
        </button>
      </div>

      {/* Attributes Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
        <div>
          <span className="text-slate-400 dark:text-slate-500 block">Checkpoint ID:</span>
          <span className="font-mono text-slate-700 dark:text-slate-200 select-all">{id}</span>
        </div>
        {timestamp && (
          <div>
            <span className="text-slate-400 dark:text-slate-500 block">Recorded At:</span>
            <span className="font-mono text-slate-700 dark:text-slate-200">{timestamp}</span>
          </div>
        )}
        {turn_id && (
          <div>
            <span className="text-slate-400 dark:text-slate-500 block">Turn Correlation:</span>
            <span className="font-mono text-slate-700 dark:text-slate-200">{turn_id}</span>
          </div>
        )}
        {receipt_id && (
          <div>
            <span className="text-slate-400 dark:text-slate-500 block">Receipt / Hash Ref:</span>
            <span className="font-mono text-emerald-600 dark:text-emerald-400 select-all font-semibold">
              {receipt_id}
            </span>
          </div>
        )}
      </div>

      {/* Detail Snippet */}
      {detail && (
        <div className="rounded border border-surface-border/60 dark:border-surface-darkBorder/60 bg-white/50 dark:bg-slate-800/40 p-2">
          <span className="text-[10px] uppercase font-bold text-slate-400 block mb-0.5">Summary</span>
          <p className="text-xs text-ink-primary dark:text-slate-200 font-mono">{detail}</p>
        </div>
      )}

      {/* Reason or Denial Explanation */}
      {reason && (
        <div className="rounded border border-red-200 dark:border-red-900/60 bg-red-50/60 dark:bg-red-950/20 p-2">
          <span className="text-[10px] uppercase font-bold text-red-600 dark:text-red-400 block mb-0.5 flex items-center gap-1">
            <FileText className="w-3 h-3" aria-hidden="true" />
            Decision Rationale
          </span>
          <p className="text-xs text-red-900 dark:text-red-200">{reason}</p>
        </div>
      )}

      {/* Policy Evaluation Detail */}
      {policy_decision && (
        <div className="rounded border border-blue-200 dark:border-blue-900/60 bg-blue-50/60 dark:bg-blue-950/20 p-2">
          <span className="text-[10px] uppercase font-bold text-blue-600 dark:text-blue-400 block mb-0.5 flex items-center gap-1">
            <KeyRound className="w-3 h-3" aria-hidden="true" />
            Policy Rule Evaluation
          </span>
          <p className="text-xs text-blue-900 dark:text-blue-200">{policy_decision}</p>
        </div>
      )}

      {/* Agent-to-Agent Handshake Section */}
      {(requesting_agent || receiving_agent || requested_capability) && (
        <div className="rounded border border-indigo-200 dark:border-indigo-900/60 bg-indigo-50/60 dark:bg-indigo-950/20 p-2 space-y-1">
          <span className="text-[10px] uppercase font-bold text-indigo-700 dark:text-indigo-300 block mb-1 flex items-center gap-1">
            <Network className="w-3 h-3" aria-hidden="true" />
            Agent Identity Handshake
          </span>
          {requesting_agent && (
            <div className="flex justify-between text-[11px]">
              <span className="text-indigo-600/80 dark:text-indigo-400">Requesting Agent:</span>
              <span className="font-mono font-medium text-slate-800 dark:text-slate-200">{requesting_agent}</span>
            </div>
          )}
          {receiving_agent && (
            <div className="flex justify-between text-[11px]">
              <span className="text-indigo-600/80 dark:text-indigo-400">Receiving Agent:</span>
              <span className="font-mono font-medium text-slate-800 dark:text-slate-200">{receiving_agent}</span>
            </div>
          )}
          {requested_capability && (
            <div className="flex justify-between text-[11px]">
              <span className="text-indigo-600/80 dark:text-indigo-400">Capability:</span>
              <span className="font-mono font-medium text-slate-800 dark:text-slate-200">{requested_capability}</span>
            </div>
          )}
          {handshake_outcome && (
            <div className="flex justify-between text-[11px] pt-1 border-t border-indigo-200/60 dark:border-indigo-900/40">
              <span className="text-indigo-600/80 dark:text-indigo-400">Outcome:</span>
              <span className="font-semibold text-slate-900 dark:text-white uppercase text-[10px]">{handshake_outcome}</span>
            </div>
          )}
        </div>
      )}

      {/* Security Footer Notice */}
      <div className="text-[10px] text-slate-400 dark:text-slate-500 pt-1 border-t border-surface-border/40 dark:border-surface-darkBorder/40">
        Deterministic security telemetry recorded by backend gateway. Read-only audit view.
      </div>
    </aside>
  );
};
