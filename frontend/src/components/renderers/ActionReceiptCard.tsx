import React from 'react';
import {
  ShieldCheck,
  ShieldAlert,
  AlertCircle,
  Database,
  Hash,
  KeyRound,
  User,
  Calendar,
  CheckCircle2,
  XCircle,
  FileText,
} from 'lucide-react';
import type { ResultRendererProps } from '../workspace/resultRegistry';
import type { ActionReceiptPayload } from '../../types/payloads';
import { validateActionReceiptPayload } from './validation';

/**
 * ActionReceiptCard — Primary Renderer for ACTION_RECEIPT blocks.
 *
 * Implements Stage 7 requirements:
 * - Displays the SQLite action operation ID, actor, action, and timestamp.
 * - Displays the bound payload SHA-256 hash prefix for reference.
 * - Clear visual distinction between successful commits, failures, and policy denials.
 * - Zero client-side transaction fabrication or grant minting.
 * - Accessible read-only semantic markup.
 * - Safe runtime validation with zero raw JSON dumps.
 */
export const ActionReceiptCard: React.FC<ResultRendererProps> = ({ block }) => {
  const validation = validateActionReceiptPayload(block.payload);

  if (!validation.isValid) {
    return (
      <article
        role="alert"
        aria-label="Action Receipt Error"
        className="rounded-flat border-2 border-state-dangerBorder bg-state-dangerBg dark:bg-red-950/40 dark:border-red-800 p-4 transition-colors"
      >
        <div className="flex items-start gap-3 text-xs text-red-950 dark:text-red-200">
          <AlertCircle className="w-4 h-4 text-state-danger dark:text-red-400 shrink-0 mt-0.5" aria-hidden="true" />
          <div className="flex-1">
            <p className="font-semibold text-sm">Action receipt details unavailable</p>
            <p className="mt-1 text-red-800/90 dark:text-red-300/80">
              {validation.error || 'The committed action receipt payload is malformed.'}
            </p>
          </div>
        </div>
      </article>
    );
  }

  const payload = block.payload as ActionReceiptPayload;
  const receipt = payload.receipt || {
    tx_id: payload.tx_id || 'unknown_tx',
    actor: payload.actor || 'unknown_actor',
    timestamp: payload.timestamp || new Date().toISOString(),
    req_id: payload.req_id,
    action: payload.action,
    resource_id: payload.resource_id,
    status: payload.status,
    grant_hash_prefix: payload.grant_hash_prefix,
  };

  const {
    tx_id,
    actor,
    timestamp,
    req_id,
    action,
    resource_id,
    status = 'COMMITTED',
    grant_hash_prefix,
  } = receipt;

  const isSuccess = status === 'COMMITTED' || status === 'SUCCESS';
  const isFailed = status === 'FAILED' || status === 'DENIED';

  return (
    <article
      aria-label={`Action Execution Receipt: ${tx_id}`}
      className="rounded-lg border-2 border-slate-900 bg-slate-900 text-slate-100 p-4 sm:p-5 shadow-lg space-y-4 font-sans"
    >
      {/* Certificate Header */}
      <div className="border-b border-slate-800 pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-emerald-400">
              {isSuccess ? (
                <ShieldCheck className="w-4 h-4 text-emerald-400" aria-hidden="true" />
              ) : (
                <ShieldAlert className="w-4 h-4 text-red-400" aria-hidden="true" />
              )}
              IntentLock Execution Receipt
            </span>
          </div>

          {/* Trust Seal Badge */}
          <div>
            {isSuccess && (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                <CheckCircle2 className="w-3 h-3 text-emerald-400" aria-hidden="true" />
                Verified & Committed
              </span>
            )}
            {isFailed && (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-red-500/20 text-red-300 border border-red-500/40">
                <XCircle className="w-3 h-3 text-red-400" aria-hidden="true" />
                Mutation Aborted
              </span>
            )}
            {!isSuccess && !isFailed && (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-slate-800 text-slate-300 border border-slate-700">
                Status: {status}
              </span>
            )}
          </div>
        </div>

        <h3 className="mt-2 text-base font-bold text-white tracking-tight flex items-center gap-2">
          <Database className="w-4 h-4 text-slate-400" aria-hidden="true" />
          <span>Committed Ticket Action</span>
        </h3>
        {payload.summary && (
          <p className="text-xs text-slate-300 mt-0.5">{payload.summary}</p>
        )}
      </div>

      {/* 2-Column Receipt Matrix Grid (UI_UX.md Spec) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs bg-slate-950/70 p-3.5 rounded-md border border-slate-800/80 font-mono">
        <div>
          <span className="text-[10px] uppercase font-bold text-slate-500 block mb-0.5 flex items-center gap-1">
            <Hash className="w-3 h-3" aria-hidden="true" />
            Operation ID
          </span>
          <span className="text-emerald-400 font-bold select-all break-all">{tx_id}</span>
        </div>

        <div>
          <span className="text-[10px] uppercase font-bold text-slate-500 block mb-0.5 flex items-center gap-1">
            <User className="w-3 h-3" aria-hidden="true" />
            Authenticated Actor
          </span>
          <span className="text-slate-200 select-all">{actor}</span>
        </div>

        {action && (
          <div>
            <span className="text-[10px] uppercase font-bold text-slate-500 block mb-0.5 flex items-center gap-1">
              <FileText className="w-3 h-3" aria-hidden="true" />
              Executed Operation
            </span>
            <span className="text-blue-300 font-bold">{action}</span>
          </div>
        )}

        {resource_id !== undefined && (
          <div>
            <span className="text-[10px] uppercase font-bold text-slate-500 block mb-0.5 flex items-center gap-1">
              <Database className="w-3 h-3" aria-hidden="true" />
              Mutated Resource
            </span>
            <span className="text-amber-300 font-bold">
              {typeof resource_id === 'number' ? `#${resource_id}` : String(resource_id)}
            </span>
          </div>
        )}

        {grant_hash_prefix && (
          <div>
            <span className="text-[10px] uppercase font-bold text-slate-500 block mb-0.5 flex items-center gap-1">
              <KeyRound className="w-3 h-3" aria-hidden="true" />
              Bound Payload Hash
            </span>
            <span className="text-slate-300 select-all" title="SHA-256 Parameter Hash Prefix">
              {grant_hash_prefix}...
            </span>
          </div>
        )}

        {req_id && (
          <div>
            <span className="text-[10px] uppercase font-bold text-slate-500 block mb-0.5 flex items-center gap-1">
              <Hash className="w-3 h-3" aria-hidden="true" />
              Request Reference
            </span>
            <span className="text-slate-400 select-all">{req_id}</span>
          </div>
        )}

        <div className="sm:col-span-2">
          <span className="text-[10px] uppercase font-bold text-slate-500 block mb-0.5 flex items-center gap-1">
            <Calendar className="w-3 h-3" aria-hidden="true" />
            Execution Timestamp (UTC)
          </span>
          <span className="text-slate-300">{timestamp}</span>
        </div>
      </div>

      {/* Audit Footnote */}
      <div className="pt-2 border-t border-slate-800 flex items-center justify-between text-[10px] text-slate-500">
        <span>SQLite ticket event recorded at commit.</span>
        <span>IntentLock action store</span>
      </div>
    </article>
  );
};
