import React from 'react';

export interface StreamingTextProps {
  /** The text content to display (can be partial or finalized) */
  text: string;
  /** Whether the text is currently being streamed incrementally */
  isStreaming?: boolean;
  /** Whether to suppress pulsing animations per user accessibility setting */
  reducedMotion?: boolean;
  /** Additional CSS class names */
  className?: string;
}

/**
 * StreamingText — Streaming-ready plain text renderer.
 *
 * Requirements:
 * - Renders partial text immediately as tokens arrive.
 * - Suppresses caret/cursor once streaming completes.
 * - Preserves whitespace and line breaks without HTML execution.
 * - Strictly avoids dangerouslySetInnerHTML.
 * - Accessible via aria-live="polite" and aria-busy.
 * - Respects reduced-motion preferences.
 */
export const StreamingText: React.FC<StreamingTextProps> = React.memo(({
  text,
  isStreaming = false,
  reducedMotion = false,
  className = '',
}) => {
  // Empty state while streaming (initial token arrival delay)
  if (!text && isStreaming) {
    return (
      <div
        role="status"
        aria-live="polite"
        aria-busy="true"
        className={`flex items-center gap-1.5 py-1 text-ink-muted dark:text-slate-400 text-xs ${className}`}
      >
        <span
          className={`w-2 h-2 rounded-full bg-brand-600 dark:bg-blue-400 ${
            reducedMotion ? 'opacity-80' : 'motion-safe:animate-pulse'
          }`}
          aria-hidden="true"
        />
        <span
          className={`w-2 h-2 rounded-full bg-brand-600 dark:bg-blue-400 ${
            reducedMotion ? 'opacity-80' : 'motion-safe:animate-pulse [animation-delay:150ms]'
          }`}
          aria-hidden="true"
        />
        <span
          className={`w-2 h-2 rounded-full bg-brand-600 dark:bg-blue-400 ${
            reducedMotion ? 'opacity-80' : 'motion-safe:animate-pulse [animation-delay:300ms]'
          }`}
          aria-hidden="true"
        />
        <span className="sr-only">Generating response...</span>
      </div>
    );
  }

  // Safe fallback if text is empty and not streaming
  if (!text) {
    return null;
  }

  return (
    <div
      aria-live={isStreaming ? 'polite' : undefined}
      aria-busy={isStreaming ? 'true' : undefined}
      className={`break-words whitespace-pre-wrap ${className}`}
    >
      <span>{text}</span>
      {isStreaming && (
        <span
          className={`inline-block w-1.5 h-4 ml-0.5 align-middle bg-brand-600 dark:bg-blue-400 rounded-sm ${
            reducedMotion ? 'opacity-90' : 'motion-safe:animate-pulse'
          }`}
          aria-hidden="true"
        />
      )}
    </div>
  );
});

StreamingText.displayName = 'StreamingText';
