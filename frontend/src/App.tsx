import { useState, useCallback, useEffect } from 'react';
import { AppShell } from './components/layout/AppShell';
import type {
  SessionInfo,
  ConversationMessage,
  GenericResultBlock,
  TurnStatusNotice,
} from './types';

export function App() {
  // 1. Truthful Session State (Default: ANONYMOUS, zero credentials)
  const [session, setSession] = useState<SessionInfo>({
    state: 'ANONYMOUS',
    sessionId: null,
  });

  // 2. Chronological Conversation Messages
  const [messages, setMessages] = useState<ConversationMessage[]>([
    {
      id: 'msg-welcome',
      sender: 'assistant',
      text: 'Hello. I am the IntentLock Shared AI Helpdesk. You can verbally ask public company questions immediately. If you need to view your private tickets or submit a hardware issue, please state your employee ID.',
      timestamp: 'Ready',
    },
  ]);

  // 3. Current Turn Status
  const [turnStatus, setTurnStatus] = useState<TurnStatusNotice>({
    type: 'idle',
  });

  // 4. Contextual Result Block (Starts strictly null / empty)
  const [activeResultBlock, setActiveResultBlock] = useState<GenericResultBlock | null>(null);
  const [isResultLoading, setIsResultLoading] = useState(false);
  const [resultError, setResultError] = useState<string | null>(null);

  // 5. Minimal Browser Audio Capture Handler
  const handleAudioCaptured = useCallback((audioBlob: Blob, durationMs: number) => {
    const elapsedSec = (durationMs / 1000).toFixed(1);
    
    // Append real user audio event notice
    const userMsgId = `msg-user-${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      {
        id: userMsgId,
        sender: 'user',
        text: `Voice utterance captured (${elapsedSec}s, ${Math.round(audioBlob.size / 1024)} KB)`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
    ]);

    // Show transient processing status
    setTurnStatus({
      type: 'transcribing',
      message: 'Processing turn audio in memory...',
    });

    // In this frontend foundation, we do not call a nonexistent backend.
    // Provide clean, honest feedback about the next integration step.
    window.setTimeout(() => {
      setTurnStatus({
        type: 'idle',
      });

      const sampleBlock: GenericResultBlock = {
        id: `blk-${Date.now()}`,
        type: 'PUBLIC_FAQ',
        title: 'Public Knowledge Base: Hardware Request Policies',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        isSensitive: false,
        payload: {
          question: 'What is the policy for hardware and peripheral requests?',
          answer: 'Standard peripherals do not require manager approval; high-tier hardware requires biometric verification.',
          category: 'IT Equipment & Peripherals',
          source_document: 'IT_Hardware_Policy_v2.4.pdf',
          summary: 'Standard peripherals do not require manager approval; high-tier hardware requires biometric verification.',
        },
      };

      setActiveResultBlock(sampleBlock);

      setMessages((prev) => [
        ...prev,
        {
          id: `msg-asst-${Date.now()}`,
          sender: 'assistant',
          text: 'Voice turn received by frontend foundation. Backend STT, DetectifAI dual checks, and policy routing will connect to this handler tomorrow morning. Contextual result attached below:',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          resultBlock: sampleBlock,
        },
      ]);
    }, 1200);
  }, []);

  // 6. End Session Handler (Wipes all private state)
  const handleEndSession = useCallback(() => {
    setSession({
      state: 'ANONYMOUS',
      sessionId: null,
    });
    setActiveResultBlock(null);
    setResultError(null);
    setIsResultLoading(false);

    setMessages((prev) => [
      ...prev,
      {
        id: `msg-sys-${Date.now()}`,
        sender: 'system',
        text: 'Session ended. All private context wiped from workspace.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
    ]);
  }, []);

  // 7. Result Action Handler (Pluggable seam for future readback confirmations)
  const handleResultAction = useCallback((actionVerb: string, parameters: Record<string, unknown>) => {
    console.log('[IntentLock] Result Action Invoked:', actionVerb, parameters);
  }, []);

  // Expose test simulation hook for automated verification in test runners & dev tools
  useEffect(() => {
    (window as unknown as { __intentLockSimulateVoiceTurn?: typeof handleAudioCaptured }).__intentLockSimulateVoiceTurn = handleAudioCaptured;
    return () => {
      delete (window as unknown as { __intentLockSimulateVoiceTurn?: typeof handleAudioCaptured }).__intentLockSimulateVoiceTurn;
    };
  }, [handleAudioCaptured]);

  return (
    <AppShell
      session={session}
      messages={messages}
      currentTurnStatus={turnStatus}
      activeResultBlock={activeResultBlock}
      isResultLoading={isResultLoading}
      resultError={resultError}
      onAudioCaptured={handleAudioCaptured}
      onEndSession={handleEndSession}
      onResultAction={handleResultAction}
      onSelectResultBlock={setActiveResultBlock}
    />
  );
}

export default App;
