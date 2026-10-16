import React, { useState } from 'react';
import { WorkspaceHeader } from '../workspace/WorkspaceHeader';
import { ConversationPanel } from '../workspace/ConversationPanel';
import { TurnStatus } from '../workspace/TurnStatus';
import { MicDock } from '../workspace/MicDock';
import { ResultHost } from '../workspace/ResultHost';
import { SettingsModal } from '../workspace/SettingsModal';
import { useSettings } from '../../hooks/useSettings';
import type { LiveTranscript } from '../../utils/voiceClient';
import type {
  ConversationMessage,
  SessionInfo,
  GenericResultBlock,
  TurnStatusNotice,
} from '../../types';

interface AppShellProps {
  isLocalRenderTest?: boolean;
  candidateEmployeeId?: string;
  onSelectCandidate?: (id: string) => void;
  evidenceSummary?: string;
  captureEpoch?: number;
  microphoneDisabled?: boolean;
  onLiveTranscript?: (event: LiveTranscript) => void;
  session: SessionInfo;
  messages: ConversationMessage[];
  currentTurnStatus: TurnStatusNotice;
  activeResultBlock: GenericResultBlock | null;
  isResultLoading?: boolean;
  resultError?: string | null;
  testFixtureId?: string;
  onSelectTestFixture?: (fixtureId: string) => void;
  isPlayingAudio?: boolean;
  onStopAudio?: () => void;
  onReplayAudio?: () => void;
  hasAudioToReplay?: boolean;
  onAudioCaptured: (audioBlob: Blob, durationMs: number, turnId?: string) => void | Promise<void>;
  onTextSubmitted?: (text: string) => void;
  onEndSession: () => void;
  onResultAction?: (actionVerb: string, parameters: Record<string, unknown>) => void;
  onSelectResultBlock?: (block: GenericResultBlock) => void;
}

export const AppShell: React.FC<AppShellProps> = ({
  isLocalRenderTest = false,
  candidateEmployeeId = 'EMP-1001', onSelectCandidate, evidenceSummary,
  captureEpoch = 0, microphoneDisabled = false, onLiveTranscript,
  session,
  messages,
  currentTurnStatus,
  activeResultBlock,
  isResultLoading = false,
  resultError = null,
  testFixtureId = 'employee_self',
  onSelectTestFixture,
  isPlayingAudio = false,
  onStopAudio,
  onReplayAudio,
  hasAudioToReplay = false,
  onAudioCaptured,
  onTextSubmitted,
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

      {/* Persistent Local Render Test Indicator Banner */}
      {isLocalRenderTest ? <div className="w-full bg-amber-50 dark:bg-amber-950/40 border-b border-amber-200 dark:border-amber-800/60 px-4 py-2 flex flex-wrap items-center justify-between gap-3 text-xs shrink-0">
        <div className="flex items-center gap-2 text-amber-900 dark:text-amber-200 font-semibold">
          <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse shrink-0" />
          <span>Local render test — Detectif verification not run</span>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <label htmlFor="test-fixture-select" className="text-amber-800 dark:text-amber-300 font-medium">
            Test Context:
          </label>
          <select
            id="test-fixture-select"
            value={testFixtureId}
            onChange={(e) => onSelectTestFixture?.(e.target.value)}
            className="px-2.5 py-1 text-xs rounded border border-amber-300 dark:border-amber-700 bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-100 font-medium focus:outline-none focus:ring-1 focus:ring-amber-500"
          >
            <option value="employee_self">Aarav Mehta (EMP-1001) — Self Scope</option>
            <option value="manager_team">Priya Sharma (EMP-2001) — Manager Team Scope</option>
            <option value="executive_all">Arvind Rao (EMP-4002) — VP All-Company Scope</option>
            <option value="anonymous_visitor">Anonymous Visitor — Public FAQ Only</option>
          </select>

          {/* Audio Playback Controls */}
          {isPlayingAudio && onStopAudio && (
            <button
              type="button"
              onClick={onStopAudio}
              className="px-2.5 py-1 text-xs font-semibold rounded bg-red-600 hover:bg-red-700 text-white transition-colors flex items-center gap-1 shadow-none"
            >
              <span>Stop Audio</span>
            </button>
          )}

          {!isPlayingAudio && hasAudioToReplay && onReplayAudio && (
            <button
              type="button"
              onClick={onReplayAudio}
              className="px-2.5 py-1 text-xs font-semibold rounded bg-amber-100 dark:bg-amber-900/60 hover:bg-amber-200 dark:hover:bg-amber-800 text-amber-900 dark:text-amber-100 border border-amber-300 dark:border-amber-700 transition-colors flex items-center gap-1"
            >
              <span>Replay Audio</span>
            </button>
          )}
        </div>
      </div>

      : <div className="px-4 py-2 border-b border-surface-border dark:border-slate-700 bg-slate-50 dark:bg-slate-900 flex flex-wrap items-center justify-between gap-2 text-xs">
        <label className="flex items-center gap-2 text-ink-primary dark:text-white">
          Claim employee ID
          <select aria-label="Claim employee ID" value={candidateEmployeeId} disabled={microphoneDisabled}
            onChange={event => onSelectCandidate?.(event.target.value)}
            className="border rounded px-2 py-1 bg-white text-slate-900 dark:bg-slate-800 dark:text-white">
            <option value="EMP-1001">EMP-1001 — Employee</option>
            <option value="EMP-2001">EMP-2001 — Engineering manager</option>
            <option value="EMP-4002">EMP-4002 — CTO</option>
          </select>
        </label>
        <span className="text-slate-600 dark:text-slate-300">{evidenceSummary}</span>
        <div className="flex gap-2">
          <button type="button" onClick={onEndSession} className="underline">Reset conversation</button>
          {isPlayingAudio && <button type="button" onClick={onStopAudio} className="underline">Stop Audio</button>}
          {!isPlayingAudio && hasAudioToReplay && <button type="button" onClick={onReplayAudio} className="underline">Replay Audio</button>}
        </div>
      </div>}

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
            isSessionVerified={session.state === 'VERIFIED' || (isLocalRenderTest && testFixtureId !== 'anonymous_visitor')}
          />

          {/* Anchored Microphone Action Dock with Typed Test Input */}
          <MicDock key={captureEpoch} onAudioCaptured={onAudioCaptured} onTextSubmitted={onTextSubmitted}
            onLiveTranscript={onLiveTranscript} disabled={microphoneDisabled}
            disabledReason={isPlayingAudio ? 'Playing response' : 'Processing voice turn'}
            previewEnabled={!isLocalRenderTest} />
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
