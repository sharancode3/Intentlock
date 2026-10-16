import React, { useState } from 'react';
import { WorkspaceHeader } from '../workspace/WorkspaceHeader';
import { ConversationPanel } from '../workspace/ConversationPanel';
import { TurnStatus } from '../workspace/TurnStatus';
import { MicDock } from '../workspace/MicDock';
import { ResultHost } from '../workspace/ResultHost';
import { SettingsModal } from '../workspace/SettingsModal';
import { useSettings } from '../../hooks/useSettings';
import type {
  ConversationMessage,
  SessionInfo,
  GenericResultBlock,
  TurnStatusNotice,
} from '../../types';

interface AppShellProps {
  session: SessionInfo;
  messages: ConversationMessage[];
  currentTurnStatus: TurnStatusNotice;
  activeResultBlock: GenericResultBlock | null;
  isResultLoading?: boolean;
  resultError?: string | null;
  onAudioCaptured: (audioBlob: Blob, durationMs: number) => void;
  onEndSession: () => void;
  onResultAction?: (actionVerb: string, parameters: Record<string, unknown>) => void;
  onSelectResultBlock?: (block: GenericResultBlock) => void;
}

export const AppShell: React.FC<AppShellProps> = ({
  session,
  messages,
  currentTurnStatus,
  activeResultBlock,
  isResultLoading = false,
  resultError = null,
  onAudioCaptured,
  onEndSession,
  onResultAction,
  onSelectResultBlock,
}) => {
  const { settings, updateSettings } = useSettings();
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [mobileActiveTab, setMobileActiveTab] = useState<'chat' | 'results'>('chat');

  // When a new result block arrives on mobile, auto-hint or allow viewing results
  const hasActiveResult = Boolean(activeResultBlock);

  const isSplitMode = settings.viewMode === 'split';
  const handleToggleViewMode = () => {
    updateSettings({ viewMode: isSplitMode ? 'feed' : 'split' });
  };

  const handleSelectResultBlock = (block: GenericResultBlock) => {
    onSelectResultBlock?.(block);
    // On mobile screens, automatically switch to results tab to reveal the selected block
    setMobileActiveTab('results');
  };

  return (
    <div className="h-screen w-screen flex flex-col bg-white dark:bg-surface-darkBg overflow-hidden select-none sm:select-text">
      {/* 1. Global Header */}
      <WorkspaceHeader
        session={session}
        viewMode={settings.viewMode}
        onToggleViewMode={handleToggleViewMode}
        onEndSession={onEndSession}
        onOpenSettings={() => setIsSettingsOpen(true)}
      />

      {/* Mobile Tab Switcher (Visible only on < lg screens when results exist) */}
      <div className="lg:hidden flex border-b border-surface-border dark:border-surface-darkBorder bg-slate-50 dark:bg-slate-900/60 shrink-0">
        <button
          type="button"
          onClick={() => setMobileActiveTab('chat')}
          className={`flex-1 py-2.5 text-xs font-semibold text-center border-b-2 transition-colors ${
            mobileActiveTab === 'chat'
              ? 'border-brand-700 text-brand-700 dark:text-blue-400 bg-white dark:bg-slate-800'
              : 'border-transparent text-ink-muted dark:text-slate-400 hover:text-ink-primary'
          }`}
        >
          Conversation ({messages.length})
        </button>
        <button
          type="button"
          onClick={() => setMobileActiveTab('results')}
          className={`flex-1 py-2.5 text-xs font-semibold text-center border-b-2 transition-colors flex items-center justify-center gap-1.5 ${
            mobileActiveTab === 'results'
              ? 'border-brand-700 text-brand-700 dark:text-blue-400 bg-white dark:bg-slate-800'
              : 'border-transparent text-ink-muted dark:text-slate-400 hover:text-ink-primary'
          }`}
        >
          <span>Contextual Results</span>
          {hasActiveResult && (
            <span className="w-2 h-2 rounded-full bg-brand-700 dark:bg-blue-400 animate-pulse" />
          )}
        </button>
      </div>

      {/* 2. Main Workspace Body: Dual-Pane (Split) or Unified Stream (Feed) */}
      <main className="flex-1 flex overflow-hidden min-h-0 relative">
        {/* Left Pane / Main Conversation Timeline */}
        <section
          aria-label="Conversation timeline"
          className={`flex flex-col bg-white dark:bg-surface-darkBg min-h-0 min-w-0 transition-all duration-200 ${
            isSplitMode
              ? 'flex-1 lg:w-5/12'
              : 'flex-1 w-full max-w-4xl mx-auto'
          } ${
            mobileActiveTab === 'chat' ? 'flex' : 'hidden lg:flex'
          }`}
        >
          {/* Turn Status Notice Banner */}
          {currentTurnStatus.type !== 'idle' && (
            <div className="p-3 border-b border-surface-border dark:border-surface-darkBorder shrink-0 bg-slate-50 dark:bg-slate-900/40">
              <TurnStatus status={currentTurnStatus} />
            </div>
          )}

          {/* Chronological Chat Messages with Layout-Aware Result Placement */}
          <ConversationPanel
            messages={messages}
            onResultAction={onResultAction}
            viewMode={settings.viewMode}
            activeResultBlockId={activeResultBlock?.id}
            onSelectResultBlock={handleSelectResultBlock}
            reducedMotion={settings.reducedMotion}
          />

          {/* Anchored Microphone Action Dock */}
          <MicDock onAudioCaptured={onAudioCaptured} />
        </section>

        {/* Right Pane: Contextual Results Host (Visible in Split Mode or Mobile Results tab) */}
        {isSplitMode && (
          <aside
            aria-label="Contextual results display"
            className={`flex-1 lg:w-7/12 h-full min-h-0 min-w-0 ${
              mobileActiveTab === 'results' ? 'flex flex-col' : 'hidden lg:flex flex-col'
            }`}
          >
            <ResultHost
              activeBlock={activeResultBlock}
              isLoading={isResultLoading}
              errorMessage={resultError}
              onResultAction={onResultAction}
            />
          </aside>
        )}

        {/* Mobile-only view for results when in Feed Mode */}
        {!isSplitMode && mobileActiveTab === 'results' && (
          <aside
            aria-label="Contextual results display"
            className="flex-1 w-full h-full min-h-0 min-w-0 flex flex-col lg:hidden"
          >
            <ResultHost
              activeBlock={activeResultBlock}
              isLoading={isResultLoading}
              errorMessage={resultError}
              onResultAction={onResultAction}
            />
          </aside>
        )}
      </main>

      {/* 3. Settings Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        settings={settings}
        onUpdateSettings={updateSettings}
      />
    </div>
  );
};
