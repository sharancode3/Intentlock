import React, { useRef, useEffect, useState, useCallback } from 'react';
import { Bot, User, FileQuestion, ArrowDown, AlertCircle } from 'lucide-react';
import { IntentLockLogo } from '../common/IntentLockLogo';
import { getResultRenderer } from './resultRegistry';
import { StreamingText } from '../renderers/StreamingText';
import type { ConversationMessage, GenericResultBlock, ViewMode } from '../../types';

interface ConversationPanelProps {
  messages: ConversationMessage[];
  onResultAction?: (actionVerb: string, parameters: Record<string, unknown>) => void;
  className?: string;
  /** Active view mode: 'split' (dual-pane) or 'feed' (unified stream) */
  viewMode?: ViewMode;
  /** ID of the currently active result block displayed in ResultHost */
  activeResultBlockId?: string | null;
  /** Callback to select a historical result block into ResultHost */
  onSelectResultBlock?: (block: GenericResultBlock) => void;
  /** User preference to suppress smooth scrolling animations */
  reducedMotion?: boolean;
  /** Whether the session is currently authenticated/verified */
  isSessionVerified?: boolean;
}

export const ConversationPanel: React.FC<ConversationPanelProps> = ({
  messages,
  onResultAction,
  className = '',
  viewMode = 'split',
  activeResultBlockId = null,
  onSelectResultBlock,
  reducedMotion = false,
  isSessionVerified = false,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  // Track whether the user is scrolled near the bottom (threshold: 80px)
  const [isAtBottom, setIsAtBottom] = useState(true);
  const [showJumpButton, setShowJumpButton] = useState(false);

  // Passive scroll handler to detect user scrolling away from bottom
  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    const atBottom = distanceFromBottom < 80;
    setIsAtBottom(atBottom);
    setShowJumpButton(!atBottom);
  }, []);

  // Jump to latest message smoothly or instantaneously per accessibility preference
  const scrollToBottom = useCallback((behavior?: ScrollBehavior) => {
    const chosenBehavior = behavior ?? (reducedMotion ? 'auto' : 'smooth');
    bottomRef.current?.scrollIntoView({ behavior: chosenBehavior });
    setIsAtBottom(true);
    setShowJumpButton(false);
  }, [reducedMotion]);

  // Smart auto-scroll: only scrolls down when the user was already near the bottom
  useEffect(() => {
    if (isAtBottom) {
      bottomRef.current?.scrollIntoView({
        behavior: reducedMotion ? 'auto' : 'smooth',
      });
    }
  }, [messages, isAtBottom, reducedMotion]);

  const isSplitView = viewMode === 'split';

  return (
    <div className="relative flex-1 flex flex-col min-h-0 overflow-hidden">
      <div
        ref={containerRef}
        onScroll={handleScroll}
        role="log"
        aria-label="Conversation history"
        aria-live="polite"
        className={`flex-1 overflow-y-auto p-4 sm:p-6 flex flex-col gap-4 min-h-0 ${className}`}
      >
        {/* Default Greeting / System Help Card with Custom Logo */}
        <div className="rounded-flat border border-surface-border dark:border-surface-darkBorder bg-surface-card dark:bg-slate-900/60 p-4 transition-colors">
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-flat bg-brand-50 dark:bg-blue-950 border border-brand-200 dark:border-blue-800 flex items-center justify-center shrink-0">
              <IntentLockLogo size={20} />
            </div>
            <div className="text-sm leading-relaxed text-ink-secondary dark:text-slate-300">
              <h2 className="font-semibold text-ink-primary dark:text-white mb-1">
                IntentLock Shared Workspace
              </h2>
              <p className="mb-2">
                You can verbally ask public company questions at any time (e.g.{' '}
                <em>"What is the office visitor policy?"</em>).
              </p>
              <p className="text-xs text-ink-muted dark:text-slate-400 bg-white dark:bg-slate-800/80 p-2.5 rounded border border-slate-200 dark:border-slate-700">
                <strong>Need private records or ticket actions?</strong> State your employee ID (e.g.{' '}
                <em>"I am Charlie Davis, EMP-1001"</em>). The backend will verify your voice profile before providing access.
              </p>
            </div>
          </div>
        </div>

        {/* Message Stream */}
        {messages.map((message) => {
          const isUser = message.sender === 'user';

          if (message.sender === 'system') {
            return (
              <div
                key={message.id}
                className="text-center my-1 text-xs text-ink-muted dark:text-slate-400 font-mono"
              >
                --- {message.text} ---
              </div>
            );
          }

          const hasAttachedResult = Boolean(message.resultBlock);
          const isAttachedResultActive =
            hasAttachedResult && message.resultBlock?.id === activeResultBlockId;

          return (
            <div
              key={message.id}
              className={`flex flex-col gap-2 max-w-[96%] sm:max-w-[88%] ${
                isUser ? 'self-end items-end' : 'self-start items-start'
              }`}
            >
              <div className={`flex items-start gap-2.5 ${isUser ? 'flex-row-reverse' : ''}`}>
                {/* Avatar icon */}
                <div
                  className={`w-7 h-7 rounded-flat flex items-center justify-center shrink-0 mt-0.5 border ${
                    isUser
                      ? 'bg-slate-200 dark:bg-slate-700 border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-200'
                      : 'bg-brand-50 dark:bg-blue-950 border-brand-200 dark:border-blue-800 text-brand-700 dark:text-blue-400'
                  }`}
                  aria-hidden="true"
                >
                  {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
                </div>

                {/* Message Bubble */}
                <div
                  className={`rounded-flat-lg p-3 sm:p-3.5 text-sm leading-relaxed border transition-colors shadow-none ${
                    isUser
                      ? 'bg-brand-700 text-white border-brand-800'
                      : 'bg-white dark:bg-slate-800 text-ink-primary dark:text-slate-100 border-surface-border dark:border-surface-darkBorder'
                  }`}
                >
                  {/* Assistant Text rendered via StreamingText, User text rendered plain */}
                  {isUser ? (
                    <div className="break-words whitespace-pre-wrap">{message.text}</div>
                  ) : (
                    <StreamingText
                      text={message.text}
                      isStreaming={message.isStreaming}
                      reducedMotion={reducedMotion}
                    />
                  )}

                  {/* Optional message-level error display */}
                  {message.status === 'error' && message.errorMessage && (
                    <div className="mt-2 flex items-center gap-1.5 text-xs text-state-danger dark:text-red-400 bg-state-dangerBg dark:bg-red-950/40 p-2 rounded-flat border border-state-dangerBorder dark:border-red-800">
                      <AlertCircle className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                      <span>{message.errorMessage}</span>
                    </div>
                  )}

                  <div
                    className={`text-[10px] mt-1.5 text-right font-mono ${
                      isUser ? 'text-blue-100' : 'text-slate-400 dark:text-slate-500'
                    }`}
                  >
                    {message.timestamp}
                  </div>
                </div>
              </div>

              {/* Contextual Result Block Placement (Layout-Aware) */}
              {message.resultBlock && (
                <div className="w-full mt-1 pl-9">
                  {/* Security Boundary: If block is marked sensitive and session is not verified, lock/hide it */}
                  {message.resultBlock.isSensitive && !isSessionVerified ? (
                    <div
                      className="rounded-flat border border-surface-border/70 dark:border-surface-darkBorder/70 bg-slate-50 dark:bg-slate-900/40 p-2.5 flex items-center justify-between gap-2 text-xs transition-colors"
                      aria-label={`Protected Result: ${message.resultBlock.title || 'Result'} is locked`}
                    >
                      <div className="flex items-center gap-2 text-ink-muted dark:text-slate-400 min-w-0">
                        <FileQuestion className="w-3.5 h-3.5 text-slate-400 shrink-0" aria-hidden="true" />
                        <span className="font-medium truncate">
                          {message.resultBlock.title || 'Protected Contextual Result'}
                        </span>
                      </div>
                      <span className="text-[11px] font-medium text-ink-muted dark:text-slate-400 bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded-flat shrink-0">
                        Session Closed &bull; Protected
                      </span>
                    </div>
                  ) : isSplitView ? (
                    /* SPLIT VIEW POLICY:
                     * 1. If this block is currently active in ResultHost, show a compact reference badge
                     *    to eliminate duplicate full-size cards.
                     * 2. If this block is historical (an earlier turn), show a compact card with
                     *    a "View in Results Pane" button so earlier results remain 100% discoverable.
                     */
                    isAttachedResultActive ? (
                      <div
                        className="rounded-flat border border-brand-200 dark:border-blue-900 bg-brand-50/70 dark:bg-blue-950/40 p-2.5 flex items-center justify-between gap-2 text-xs transition-colors"
                        aria-label={`Contextual Result: ${message.resultBlock.title || 'Result'} is active in right pane`}
                      >
                        <div className="flex items-center gap-2 text-brand-950 dark:text-blue-100 min-w-0">
                          <span
                            className={`w-2 h-2 rounded-full bg-brand-600 dark:bg-blue-400 shrink-0 ${
                              reducedMotion ? 'opacity-90' : 'motion-safe:animate-pulse'
                            }`}
                            aria-hidden="true"
                          />
                          <span className="font-semibold truncate">
                            {message.resultBlock.title || 'Contextual Result'}
                          </span>
                        </div>
                        <span className="text-[11px] font-semibold text-brand-700 dark:text-blue-400 bg-white dark:bg-slate-800 px-2 py-0.5 rounded-flat border border-brand-200 dark:border-blue-800 shrink-0">
                          Active in Contextual Display →
                        </span>
                      </div>
                    ) : (
                      <div
                        className="rounded-flat border border-surface-border dark:border-surface-darkBorder bg-surface-card dark:bg-slate-800/60 p-2.5 flex items-center justify-between gap-2 text-xs transition-colors"
                        aria-label={`Historical Result: ${message.resultBlock.title || 'Result'}`}
                      >
                        <div className="flex items-center gap-2 text-ink-primary dark:text-white min-w-0">
                          <FileQuestion className="w-3.5 h-3.5 text-slate-400 shrink-0" aria-hidden="true" />
                          <span className="font-medium truncate">
                            {message.resultBlock.title || 'Contextual Result'}
                          </span>
                        </div>
                        <button
                          type="button"
                          onClick={() => onSelectResultBlock?.(message.resultBlock!)}
                          className="text-[11px] font-semibold text-brand-700 dark:text-blue-400 hover:text-brand-800 dark:hover:text-blue-300 bg-white dark:bg-slate-700 px-2.5 py-1 rounded-flat border border-surface-border dark:border-surface-darkBorder shrink-0 focus:outline-none focus:ring-2 focus:ring-brand-700 transition-colors"
                          aria-label={`View ${message.resultBlock.title || 'result'} in Contextual Display`}
                        >
                          View Result →
                        </button>
                      </div>
                    )
                  ) : (
                    /* FEED VIEW POLICY:
                     * Render the full-size custom card or fallback inline directly in the chat stream.
                     */
                    (() => {
                      const CustomRenderer = getResultRenderer(message.resultBlock.type);
                      if (CustomRenderer) {
                        return (
                          <CustomRenderer
                            block={message.resultBlock}
                            onAction={onResultAction}
                          />
                        );
                      }

                      return (
                        <div className="rounded-flat border border-surface-border dark:border-surface-darkBorder bg-surface-card dark:bg-slate-800/80 p-3.5 text-xs text-ink-secondary dark:text-slate-300">
                          <div className="flex items-center gap-2 font-semibold text-ink-primary dark:text-white mb-1">
                            <FileQuestion className="w-4 h-4 text-slate-400" />
                            <span>{message.resultBlock.title || 'Contextual Result'}</span>
                          </div>
                          <p className="text-ink-muted dark:text-slate-400">
                            Renderer module for <code>{message.resultBlock.type}</code> is registered for next stage.
                          </p>
                        </div>
                      );
                    })()
                  )}
                </div>
              )}
            </div>
          );
        })}

        <div ref={bottomRef} />
      </div>

      {/* Accessible "Jump to latest" floating button */}
      {showJumpButton && (
        <div className="absolute bottom-3 left-1/2 -translate-x-1/2 z-10">
          <button
            type="button"
            onClick={() => scrollToBottom()}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-brand-700 text-white hover:bg-brand-800 dark:bg-blue-600 dark:hover:bg-blue-700 text-xs font-semibold shadow-md focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-brand-700 transition-transform active:scale-95"
            aria-label="Scroll to newest messages"
          >
            <ArrowDown className="w-3.5 h-3.5" aria-hidden="true" />
            <span>Jump to latest</span>
          </button>
        </div>
      )}
    </div>
  );
};
