import React from 'react';
import { BookOpen, FileText, AlertCircle, Tag } from 'lucide-react';
import type { ResultRendererProps } from '../workspace/resultRegistry';
import { validatePublicFaqPayload } from './validation';

/**
 * PublicFaqCard — Renderer for PUBLIC_FAQ result blocks.
 *
 * Adheres strictly to UI_UX.md section 6:
 * - Bordered container (no box-shadow, flat border)
 * - Badge: "PUBLIC KNOWLEDGE"
 * - Question heading + verified answer body
 * - Optional document source pill and category
 * - Safe fallback for malformed or missing payloads
 * - Dark mode and mobile responsive support
 */
export const PublicFaqCard: React.FC<ResultRendererProps> = ({ block }) => {
  const validation = validatePublicFaqPayload(block.payload);

  if (!validation.isValid) {
    return (
      <article
        className="rounded-flat border-2 border-surface-border dark:border-surface-darkBorder bg-surface-card dark:bg-slate-800/60 p-4 transition-colors"
        aria-label="FAQ Content Error"
      >
        <div className="flex items-start gap-3 text-ink-muted dark:text-slate-400 text-xs">
          <AlertCircle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" aria-hidden="true" />
          <div className="flex-1">
            <h4 className="font-semibold text-ink-primary dark:text-white text-sm mb-1">
              FAQ Content Unavailable
            </h4>
            <p>{validation.error}</p>
          </div>
        </div>
      </article>
    );
  }

  const { question, answer, source_document, category } = validation.data;
  const displayQuestion = question || block.title || 'Knowledge Base FAQ';

  return (
    <article
      className="rounded-flat border-2 border-surface-border dark:border-surface-darkBorder bg-white dark:bg-slate-800/90 p-4 sm:p-5 transition-colors space-y-3"
      aria-label={`FAQ: ${displayQuestion}`}
    >
      {/* Header with Badge & Category */}
      <header className="flex flex-wrap items-center justify-between gap-2 pb-1 border-b border-surface-border/50 dark:border-surface-darkBorder/50">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 bg-slate-100 dark:bg-slate-700/80 text-slate-700 dark:text-slate-300 font-bold px-2.5 py-0.5 text-[11px] rounded-flat uppercase tracking-wider">
            <BookOpen className="w-3 h-3 text-brand-700 dark:text-blue-400" aria-hidden="true" />
            Public Knowledge
          </span>
          {category && (
            <span className="inline-flex items-center gap-1 text-xs text-ink-muted dark:text-slate-400">
              <Tag className="w-3 h-3" aria-hidden="true" />
              <span>{category}</span>
            </span>
          )}
        </div>
        {block.timestamp && (
          <span className="text-[10px] font-mono text-ink-muted dark:text-slate-500">
            {block.timestamp}
          </span>
        )}
      </header>

      {/* Question Heading */}
      <h3 className="text-sm sm:text-base font-bold text-ink-primary dark:text-white leading-snug break-words">
        {displayQuestion}
      </h3>

      {/* Answer Body */}
      <div className="text-sm font-normal text-ink-secondary dark:text-slate-200 leading-relaxed whitespace-pre-line break-words">
        {answer}
      </div>

      {/* Optional Document Source Pill */}
      {source_document && (
        <footer className="pt-2 border-t border-surface-border/50 dark:border-surface-darkBorder/50">
          <div className="inline-flex items-center gap-1.5 text-xs text-ink-muted dark:text-slate-400 font-mono bg-slate-50 dark:bg-slate-900/60 px-2.5 py-1 rounded-flat border border-surface-border dark:border-surface-darkBorder">
            <FileText className="w-3.5 h-3.5 text-slate-400 dark:text-slate-500" aria-hidden="true" />
            <span>Doc: {source_document}</span>
          </div>
        </footer>
      )}
    </article>
  );
};
