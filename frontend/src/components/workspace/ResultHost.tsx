import React from 'react';
import { Layers, FileQuestion, Shield, AlertCircle } from 'lucide-react';
import type { GenericResultBlock } from '../../types';
import { getResultRenderer } from './resultRegistry';

interface ResultHostProps {
  /** Active result block passed from current turn or null for empty state */
  activeBlock: GenericResultBlock | null;
  /** Available result blocks for multi-result selection */
  resultBlocks?: GenericResultBlock[];
  /** Callback when user selects another result block */
  onSelectBlock?: (block: GenericResultBlock) => void;
  /** Whether the result pane is currently loading data */
  isLoading?: boolean;
  /** Error message if result retrieval failed */
  errorMessage?: string | null;
  /** Callback for user interactions inside child renderers */
  onResultAction?: (actionVerb: string, parameters: Record<string, unknown>) => void;
  className?: string;
}

export const ResultHost: React.FC<ResultHostProps> = ({
  activeBlock,
  resultBlocks,
  onSelectBlock,
  isLoading = false,
  errorMessage = null,
  onResultAction,
  className = '',
}) => {
  return (
    <div
      className={`h-full flex flex-col bg-surface-card dark:bg-slate-900/40 border-l border-surface-border dark:border-surface-darkBorder transition-colors overflow-hidden ${className}`}
      aria-label="Contextual Results Workspace"
    >
      {/* Result Pane Header */}
      <div className="py-2.5 px-4 border-b border-surface-border dark:border-surface-darkBorder flex items-center justify-between gap-2 shrink-0 bg-white dark:bg-surface-darkBg">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-brand-700 dark:text-blue-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-ink-primary dark:text-white">
            Contextual Display
          </span>
        </div>
        {activeBlock && (
          <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700">
            {activeBlock.type}
          </span>
        )}
      </div>

      {/* Multi-result pill selector when more than one block is available */}
      {resultBlocks && resultBlocks.length > 1 && (
        <div className="flex items-center gap-1.5 overflow-x-auto py-1.5 px-4 bg-slate-50 dark:bg-slate-800/60 border-b border-surface-border dark:border-surface-darkBorder shrink-0">
          <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mr-1 shrink-0">Results:</span>
          {resultBlocks.map((b) => (
            <button
              key={b.id}
              type="button"
              onClick={() => onSelectBlock?.(b)}
              className={`px-2.5 py-0.5 rounded text-xs font-medium transition-colors whitespace-nowrap ${
                b.id === activeBlock?.id
                  ? 'bg-brand-700 text-white dark:bg-blue-600 shadow-sm'
                  : 'bg-white dark:bg-slate-800 text-ink-muted dark:text-slate-300 hover:text-ink-primary dark:hover:text-white border border-surface-border dark:border-surface-darkBorder'
              }`}
            >
              {b.title || b.type}
            </button>
          ))}
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-5">
        {isLoading ? (
          /* Neutral Loading State (no fake rows) */
          <div className="h-full flex flex-col items-center justify-center gap-3 p-6 text-center">
            <div className="w-8 h-8 rounded-full border-2 border-brand-700 border-t-transparent animate-spin" />
            <p className="text-sm font-medium text-ink-secondary dark:text-slate-300">
              Retrieving authorized response...
            </p>
            <p className="text-xs text-ink-muted dark:text-slate-500">
              Verifying permissions & query bounds
            </p>
          </div>
        ) : errorMessage ? (
          /* Error State */
          <div className="rounded-flat border border-state-dangerBorder bg-state-dangerBg p-4 flex items-start gap-3 text-state-danger">
            <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
            <div className="text-sm">
              <h3 className="font-semibold mb-1">Result Unavailable</h3>
              <p>{errorMessage}</p>
            </div>
          </div>
        ) : activeBlock ? (
          /* Render Active Block via Registry or Clean Fallback */
          (() => {
            const CustomRenderer = getResultRenderer(activeBlock.type);
            if (CustomRenderer) {
              return <CustomRenderer block={activeBlock} onAction={onResultAction} />;
            }

            /* Fallback renderer when teammate has not yet implemented this specific card */
            return (
              <div className="rounded-flat border border-surface-border dark:border-surface-darkBorder bg-white dark:bg-slate-800 p-5 transition-colors">
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-flat bg-slate-100 dark:bg-slate-700 flex items-center justify-center shrink-0">
                    <FileQuestion className="w-4 h-4 text-slate-500 dark:text-slate-400" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="font-semibold text-ink-primary dark:text-white text-base">
                        {activeBlock.title || 'Contextual Result'}
                      </h3>
                      {activeBlock.isSensitive && (
                        <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-amber-100 text-amber-900 dark:bg-amber-900/60 dark:text-amber-200">
                          Verified Actor Required
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-ink-muted dark:text-slate-400 mb-3">
                      Renderer module for <code>{activeBlock.type}</code> will be mounted here by next stage.
                    </p>
                    <div className="p-3 rounded bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-700 text-xs text-slate-600 dark:text-slate-300">
                      Payload received successfully from backend. Renderer component interface is ready.
                    </div>
                  </div>
                </div>
              </div>
            );
          })()
        ) : (
          /* Safe, Honest Empty State */
          <div className="h-full min-h-[240px] flex flex-col items-center justify-center text-center p-6 border-2 border-dashed border-slate-200 dark:border-slate-800 rounded-flat-lg">
            <div className="w-12 h-12 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center mb-3">
              <Shield className="w-6 h-6 text-slate-400 dark:text-slate-500" />
            </div>
            <h3 className="text-sm font-semibold text-ink-primary dark:text-white mb-1">
              Contextual Results Will Appear Here
            </h3>
            <p className="text-xs text-ink-muted dark:text-slate-400 max-w-sm leading-relaxed mb-4">
              Your authorized profile and supported contextual results appear here after the backend completes the required voice checks.
            </p>
            <div className="inline-flex items-center gap-2 text-[11px] text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-800/80 px-3 py-1.5 rounded-full border border-slate-200 dark:border-slate-700">
              <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
              <span>Zero private records displayed prior to verification</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
