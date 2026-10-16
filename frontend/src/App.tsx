import { useState, useCallback, useEffect, useRef } from 'react';
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

  // Invalidation epoch to prevent stale async operations from repopulating revoked data
  const sessionEpochRef = useRef(0);

  // 5. Minimal Browser Audio Capture Handler
  const handleAudioCaptured = useCallback((audioBlob: Blob, durationMs: number) => {
    const elapsedSec = (durationMs / 1000).toFixed(1);
    const turnEpoch = sessionEpochRef.current;
    
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
      // If session was ended or invalidated while this turn was processing, discard the result
      if (turnEpoch !== sessionEpochRef.current) {
        return;
      }

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

  // Helper to purge protected/sensitive state and invalidate pending async operations
  const purgeProtectedData = useCallback(() => {
    sessionEpochRef.current += 1;
    setActiveResultBlock((prev) => (prev?.isSensitive ? null : prev));
    setMessages((prev) =>
      prev.map((msg) => {
        if (msg.resultBlock?.isSensitive) {
          return {
            ...msg,
            resultBlock: undefined,
            resultBlockId: undefined,
          };
        }
        return msg;
      })
    );
  }, []);

  // 6. End Session Handler (Wipes private state, increments epoch, and purges sensitive blocks)
  const handleEndSession = useCallback(() => {
    setSession({
      state: 'ANONYMOUS',
      sessionId: null,
    });
    setResultError(null);
    setIsResultLoading(false);
    purgeProtectedData();

    setMessages((prev) => [
      ...prev,
      {
        id: `msg-sys-${Date.now()}`,
        sender: 'system',
        text: 'Session ended. All private context wiped from workspace.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
    ]);
  }, [purgeProtectedData]);

  // 7. Purge sensitive blocks when session transitions to EXPIRED
  useEffect(() => {
    if (session.state === 'EXPIRED') {
      const timer = window.setTimeout(() => {
        purgeProtectedData();
      }, 0);
      return () => window.clearTimeout(timer);
    }
  }, [session.state, purgeProtectedData]);

  // 8. Result Selection Handler (Guards sensitive results against activation outside verified session)
  const handleSelectResultBlock = useCallback(
    (block: GenericResultBlock) => {
      // Security boundary: Sensitive result blocks cannot be reopened without an active verified session
      if (block.isSensitive && session.state !== 'VERIFIED') {
        return;
      }
      setActiveResultBlock(block);
    },
    [session.state]
  );

  // 9. Result Action Handler (Pluggable seam for future readback confirmations)
  const handleResultAction = useCallback((actionVerb: string, parameters: Record<string, unknown>) => {
    console.log('[IntentLock] Result Action Invoked:', actionVerb, parameters);
  }, []);

  // Optional development-only fixture loader via query parameter for automated verification
  useEffect(() => {
    if (import.meta.env.DEV) {
      const params = new URLSearchParams(window.location.search);
      const fixtureParam = params.get('fixture');
      if (fixtureParam) {
        import('./components/renderers/fixtures').then((f) => {
          if (fixtureParam === 'employee_profile' || fixtureParam === 'profile') {
            setSession({
              state: 'VERIFIED',
              sessionId: 'sess_test_dev',
              actor: {
                employeeId: 'emp_1042',
                fullName: 'Charlie Davis',
                role: 'employee',
                expiresInSeconds: 90,
              },
            });
            setActiveResultBlock(f.validEmployeeProfileCompleteFixture);
          } else if (fixtureParam === 'minimal') {
            setActiveResultBlock(f.validEmployeeProfileMinimalFixture);
          } else if (fixtureParam === 'invalid') {
            setActiveResultBlock(f.invalidEmployeeProfileMissingNameFixture);
          } else if (fixtureParam === 'tickets' || fixtureParam === 'ticket_list') {
            setSession({
              state: 'VERIFIED',
              sessionId: 'sess_test_dev',
              actor: {
                employeeId: 'emp_1042',
                fullName: 'Charlie Davis',
                role: 'employee',
                expiresInSeconds: 90,
              },
            });
            setActiveResultBlock(f.validTicketListMultipleFixture);
          } else if (fixtureParam === 'tickets_empty') {
            setSession({
              state: 'VERIFIED',
              sessionId: 'sess_test_dev',
              actor: {
                employeeId: 'emp_1042',
                fullName: 'Charlie Davis',
                role: 'employee',
                expiresInSeconds: 90,
              },
            });
            setActiveResultBlock(f.validTicketListEmptyFixture);
          } else if (fixtureParam === 'tickets_invalid') {
            setActiveResultBlock(f.invalidTicketListMissingIdFixture);
          } else if (fixtureParam === 'metrics_bar' || fixtureParam === 'metrics') {
            setSession({
              state: 'VERIFIED',
              sessionId: 'sess_test_manager',
              actor: {
                employeeId: 'mgr_9001',
                fullName: 'Jordan Taylor (Lead Manager)',
                role: 'manager',
                expiresInSeconds: 120,
              },
            });
            setActiveResultBlock(f.validTeamMetricBarFixture);
          } else if (fixtureParam === 'metrics_pie') {
            setSession({
              state: 'VERIFIED',
              sessionId: 'sess_test_manager',
              actor: {
                employeeId: 'mgr_9001',
                fullName: 'Jordan Taylor (Lead Manager)',
                role: 'manager',
                expiresInSeconds: 120,
              },
            });
            setActiveResultBlock(f.validTeamMetricPieFixture);
          } else if (fixtureParam === 'metrics_empty') {
            setSession({
              state: 'VERIFIED',
              sessionId: 'sess_test_manager',
              actor: {
                employeeId: 'mgr_9001',
                fullName: 'Jordan Taylor (Lead Manager)',
                role: 'manager',
                expiresInSeconds: 120,
              },
            });
            setActiveResultBlock(f.emptyTeamMetricChartFixture);
          } else if (fixtureParam === 'metrics_all_zero') {
            setSession({
              state: 'VERIFIED',
              sessionId: 'sess_test_manager',
              actor: {
                employeeId: 'mgr_9001',
                fullName: 'Jordan Taylor (Lead Manager)',
                role: 'manager',
                expiresInSeconds: 120,
              },
            });
            setActiveResultBlock(f.allZeroTeamMetricChartFixture);
          } else if (fixtureParam === 'metrics_invalid') {
            setActiveResultBlock(f.invalidTeamMetricChartMissingFieldsFixture);
          } else if (fixtureParam === 'trust_success' || fixtureParam === 'trust') {
            setSession({
              state: 'VERIFIED',
              sessionId: 'sess_charlie_1042',
              actor: {
                employeeId: 'emp_1042',
                fullName: 'Charlie Davis',
                role: 'employee',
                expiresInSeconds: 90,
              },
            });
            setActiveResultBlock(f.validTrustTraceSuccessFixture);
          } else if (fixtureParam === 'trust_denied') {
            setSession({
              state: 'VERIFIED',
              sessionId: 'sess_charlie_1042',
              actor: {
                employeeId: 'emp_1042',
                fullName: 'Charlie Davis',
                role: 'employee',
                expiresInSeconds: 90,
              },
            });
            setActiveResultBlock(f.validTrustTraceDeniedFixture);
          } else if (fixtureParam === 'trust_speaker_failed' || fixtureParam === 'trust_fail') {
            setActiveResultBlock(f.validTrustTraceSpeakerMismatchFixture);
          } else if (fixtureParam === 'trust_pending') {
            setActiveResultBlock(f.validTrustTracePendingFixture);
          } else if (fixtureParam === 'trust_parallel') {
            setSession({
              state: 'VERIFIED',
              sessionId: 'sess_charlie_1042',
              actor: {
                employeeId: 'emp_1042',
                fullName: 'Charlie Davis',
                role: 'employee',
                expiresInSeconds: 90,
              },
            });
            setActiveResultBlock(f.validTrustTraceParallelFixture);
          } else if (fixtureParam === 'trust_empty') {
            setActiveResultBlock(f.emptyTrustTraceFixture);
          } else if (fixtureParam === 'trust_invalid') {
            setActiveResultBlock(f.invalidTrustTraceDanglingEdgeFixture);
          } else if (fixtureParam === 'readback' || fixtureParam === 'readback_canonical') {
            setSession({
              state: 'VERIFIED',
              sessionId: 'sess_charlie_1042',
              actor: {
                employeeId: 'emp_1042',
                fullName: 'Charlie Davis',
                role: 'employee',
                expiresInSeconds: 90,
              },
            });
            setActiveResultBlock(f.validReadbackConfirmationPendingFixture);
          } else if (fixtureParam === 'readback_minimal') {
            setSession({
              state: 'VERIFIED',
              sessionId: 'sess_charlie_1042',
              actor: {
                employeeId: 'emp_1042',
                fullName: 'Charlie Davis',
                role: 'employee',
                expiresInSeconds: 90,
              },
            });
            setActiveResultBlock(f.validReadbackConfirmationMinimalFixture);
          } else if (fixtureParam === 'readback_invalid') {
            setActiveResultBlock(f.invalidReadbackConfirmationMissingActionFixture);
          } else if (fixtureParam === 'readback_malformed_params') {
            setActiveResultBlock(f.invalidReadbackConfirmationMalformedParamsFixture);
          } else if (fixtureParam === 'receipt' || fixtureParam === 'receipt_success') {
            setSession({
              state: 'VERIFIED',
              sessionId: 'sess_charlie_1042',
              actor: {
                employeeId: 'emp_1042',
                fullName: 'Charlie Davis',
                role: 'employee',
                expiresInSeconds: 90,
              },
            });
            setActiveResultBlock(f.validActionReceiptSuccessFixture);
          } else if (fixtureParam === 'receipt_failed') {
            setSession({
              state: 'VERIFIED',
              sessionId: 'sess_charlie_1042',
              actor: {
                employeeId: 'emp_1042',
                fullName: 'Charlie Davis',
                role: 'employee',
                expiresInSeconds: 90,
              },
            });
            setActiveResultBlock(f.validActionReceiptFailedFixture);
          } else if (fixtureParam === 'receipt_denied') {
            setSession({
              state: 'VERIFIED',
              sessionId: 'sess_charlie_1042',
              actor: {
                employeeId: 'emp_1042',
                fullName: 'Charlie Davis',
                role: 'employee',
                expiresInSeconds: 90,
              },
            });
            setActiveResultBlock(f.validActionReceiptDeniedFixture);
          } else if (fixtureParam === 'receipt_invalid') {
            setActiveResultBlock(f.invalidActionReceiptMissingTxIdFixture);
          } else if (fixtureParam === 'denial' || fixtureParam === 'denial_complete') {
            setActiveResultBlock(f.validDenialBannerCompleteFixture);
          } else if (fixtureParam === 'denial_min') {
            setActiveResultBlock(f.validDenialBannerMinimalFixture);
          } else if (fixtureParam === 'denial_invalid') {
            setActiveResultBlock(f.invalidDenialBannerMissingMessageFixture);
          }
        });
      }
    }
  }, []);

  // Expose test simulation hooks for automated verification in dev tools & subagents
  useEffect(() => {
    if (import.meta.env.DEV) {
      (window as unknown as Record<string, unknown>).__intentLockDevHelpers = {
        setSession,
        setActiveResultBlock,
        setMessages,
        handleEndSession,
        handleAudioCaptured,
      };
    }
    (window as unknown as { __intentLockSimulateVoiceTurn?: typeof handleAudioCaptured }).__intentLockSimulateVoiceTurn = handleAudioCaptured;
    return () => {
      delete (window as unknown as { __intentLockSimulateVoiceTurn?: typeof handleAudioCaptured }).__intentLockSimulateVoiceTurn;
      if (import.meta.env.DEV) {
        delete (window as unknown as Record<string, unknown>).__intentLockDevHelpers;
      }
    };
  }, [handleAudioCaptured, handleEndSession]);

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
      onSelectResultBlock={handleSelectResultBlock}
    />
  );
}

export default App;
