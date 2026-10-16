import { useState, useCallback, useEffect, useRef } from 'react';
import { AppShell } from './components/layout/AppShell';
import { useSettings } from './hooks/useSettings';
import { createStreamingMessage, finalizeMessage } from './utils/messageHelpers';
import type {
  SessionInfo,
  ConversationMessage,
  GenericResultBlock,
  TurnStatusNotice,
} from './types';

const TEST_GATEWAY_URL = 'http://127.0.0.1:8001';

export function App() {
  const { settings } = useSettings();

  // 1. Truthful Session State (Default: ANONYMOUS, zero credentials)
  const [session, setSession] = useState<SessionInfo>({
    state: 'ANONYMOUS',
    sessionId: null,
  });

  // Test Fixture Context (Isolated local development context; does not set session state to VERIFIED)
  const [testFixtureId, setTestFixtureId] = useState<string>('employee_self');

  // 2. Chronological Conversation Messages
  const [messages, setMessages] = useState<ConversationMessage[]>([
    {
      id: 'msg-welcome',
      sender: 'assistant',
      text: 'Local render test: Running as Aarav Mehta (EMP-1001, Application Engineering). Permitted scope: your own employee profile, active projects, and public helpdesk FAQ. You can speak into the microphone or type below.',
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

  // Audio Playback Controller
  const audioElementRef = useRef<HTMLAudioElement | null>(null);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  const [lastAudioPayload, setLastAudioPayload] = useState<{ base64: string; mimeType: string } | null>(null);

  const stopAudio = useCallback(() => {
    if (audioElementRef.current) {
      audioElementRef.current.pause();
      audioElementRef.current = null;
    }
    setIsPlayingAudio(false);
  }, []);

  const playAudio = useCallback(
    (base64: string, mimeType: string) => {
      stopAudio();
      setLastAudioPayload({ base64, mimeType });

      if (!settings.voicePlaybackEnabled) {
        return;
      }

      try {
        const audioUrl = `data:${mimeType};base64,${base64}`;
        const audio = new Audio(audioUrl);
        audio.volume = Math.max(0, Math.min(1, settings.voiceVolume));
        audioElementRef.current = audio;

        audio.onplay = () => setIsPlayingAudio(true);
        audio.onended = () => {
          setIsPlayingAudio(false);
          audioElementRef.current = null;
        };
        audio.onerror = () => {
          setIsPlayingAudio(false);
          audioElementRef.current = null;
        };

        audio.play().catch((e) => {
          console.warn('[IntentLock] Autoplay blocked or audio playback error:', e);
          setIsPlayingAudio(false);
        });
      } catch (e) {
        console.warn('[IntentLock] Audio initialization error:', e);
        setIsPlayingAudio(false);
      }
    },
    [settings.voicePlaybackEnabled, settings.voiceVolume, stopAudio]
  );

  const replayAudio = useCallback(() => {
    if (lastAudioPayload) {
      playAudio(lastAudioPayload.base64, lastAudioPayload.mimeType);
    }
  }, [lastAudioPayload, playAudio]);

  // Fixture Context Switching
  const handleSelectTestFixture = useCallback(
    (fixtureId: string) => {
      stopAudio();
      setTestFixtureId(fixtureId);
      sessionEpochRef.current += 1;
      setActiveResultBlock(null);
      setResultError(null);
      setIsResultLoading(false);

      let introText = 'Local render test ready.';
      if (fixtureId === 'employee_self') {
        introText =
          'Local render test: Running as Aarav Mehta (EMP-1001, Application Engineering). Permitted scope: your own employee profile, active projects, and public helpdesk FAQ.';
      } else if (fixtureId === 'manager_team') {
        introText =
          'Local render test: Running as Priya Sharma (EMP-2001, Engineering Manager). Permitted scope: Engineering team members, direct report profiles, and team metrics.';
      } else if (fixtureId === 'executive_all') {
        introText =
          'Local render test: Running as Arvind Rao (EMP-4002, VP of Engineering). Permitted scope: all department profiles, headcount, and company-wide metrics.';
      } else if (fixtureId === 'anonymous_visitor') {
        introText =
          'Local render test: Running as Anonymous Visitor (no authentication). Permitted scope: public FAQ only. Requests for employee or team records will trigger policy denials.';
      }

      setMessages([
        {
          id: `msg-welcome-${Date.now()}`,
          sender: 'assistant',
          text: introText,
          timestamp: 'Ready',
        },
      ]);
    },
    [stopAudio]
  );

  // 5. Real Browser Audio Capture Handler (Faster-Whisper STT -> Scoped Retrieval -> Ollama -> Kokoro TTS)
  const handleAudioCaptured = useCallback(
    async (audioBlob: Blob, durationMs: number) => {
      const elapsedSec = (durationMs / 1000).toFixed(1);
      const turnEpoch = sessionEpochRef.current;
      const turnId = `turn-${Date.now()}`;
      const userMsgId = `msg-user-${Date.now()}`;

      // 1. Create stable user message placeholder with transcribing status
      const provisionalMsg = createStreamingMessage(
        userMsgId,
        'user',
        `Transcribing spoken utterance (${elapsedSec}s)...`,
        turnId
      );
      setMessages((prev) => [...prev, provisionalMsg]);

      // 2. Set turn status
      setTurnStatus({
        type: 'transcribing',
        message: 'Faster-Whisper transcribing speech...',
      });
      setIsResultLoading(true);
      setResultError(null);

      // 3. Dispatch to local test gateway
      try {
        const formData = new FormData();
        formData.append('audio_file', audioBlob, 'turn_audio.webm');
        formData.append('fixture_id', testFixtureId);
        formData.append('turn_id', turnId);
        formData.append('conversation_id', 'conv-local-test');

        const response = await fetch(`${TEST_GATEWAY_URL}/api/test/turn/audio`, {
          method: 'POST',
          body: formData,
        });

        if (turnEpoch !== sessionEpochRef.current) {
          return; // Stale or cancelled turn
        }

        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`Test gateway error (${response.status}): ${errorText}`);
        }

        const data = await response.json();

        if (turnEpoch !== sessionEpochRef.current) {
          return;
        }

        // Check if audio was silence or below threshold
        const transcript = data.user_transcript || '';
        const isUnvoiced =
          transcript.includes('No speech detected') || transcript.includes('Silence or unvoiced');

        // Finalize user message with authoritative final transcript
        setMessages((prev) => finalizeMessage(prev, userMsgId, transcript));

        if (isUnvoiced) {
          setTurnStatus({ type: 'idle' });
          setIsResultLoading(false);
          return;
        }

        // Append assistant reply with attached typed ResultBlock
        const asstMsgId = `msg-asst-${Date.now()}`;
        const asstBlock = data.result_block as GenericResultBlock;

        setMessages((prev) => [
          ...prev,
          {
            id: asstMsgId,
            sender: 'assistant',
            text: data.assistant_text,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            turnId,
            resultBlock: asstBlock,
            resultBlockId: asstBlock?.id,
            status: 'complete',
          },
        ]);

        setActiveResultBlock(asstBlock);
        setTurnStatus({ type: 'idle' });
        setIsResultLoading(false);

        // Real neural TTS speech playback via Kokoro ONNX
        if (data.tts_audio_base64) {
          playAudio(data.tts_audio_base64, data.audio_mime_type || 'audio/wav');
        }
      } catch (err: unknown) {
        if (turnEpoch !== sessionEpochRef.current) return;
        const message = err instanceof Error ? err.message : 'Audio processing failed.';
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === userMsgId
              ? { ...msg, status: 'error', errorMessage: message, isStreaming: false }
              : msg
          )
        );
        setTurnStatus({
          type: 'error',
          message: 'Speech recognition or reasoning failed. Check gateway connection.',
        });
        setIsResultLoading(false);
        setResultError(message);
      }
    },
    [testFixtureId, playAudio]
  );

  // 6. Direct Typed Input Handler (supporting test automation, keyboard access, and text testing)
  const handleTextSubmitted = useCallback(
    async (text: string) => {
      const turnEpoch = sessionEpochRef.current;
      const turnId = `turn-${Date.now()}`;
      const userMsgId = `msg-user-${Date.now()}`;

      // 1. Authoritative user message immediately
      setMessages((prev) => [
        ...prev,
        {
          id: userMsgId,
          sender: 'user',
          text: text.trim(),
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          turnId,
          status: 'complete',
        },
      ]);

      setTurnStatus({
        type: 'reasoning',
        message: 'Ollama local model generating grounded answer...',
      });
      setIsResultLoading(true);
      setResultError(null);

      try {
        const response = await fetch(`${TEST_GATEWAY_URL}/api/test/turn/text`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text: text.trim(),
            fixture_id: testFixtureId,
            turn_id: turnId,
            conversation_id: 'conv-local-test',
          }),
        });

        if (turnEpoch !== sessionEpochRef.current) return;

        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`Test gateway error (${response.status}): ${errorText}`);
        }

        const data = await response.json();
        if (turnEpoch !== sessionEpochRef.current) return;

        const asstMsgId = `msg-asst-${Date.now()}`;
        const asstBlock = data.result_block as GenericResultBlock;

        setMessages((prev) => [
          ...prev,
          {
            id: asstMsgId,
            sender: 'assistant',
            text: data.assistant_text,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            turnId,
            resultBlock: asstBlock,
            resultBlockId: asstBlock?.id,
            status: 'complete',
          },
        ]);

        setActiveResultBlock(asstBlock);
        setTurnStatus({ type: 'idle' });
        setIsResultLoading(false);

        if (data.tts_audio_base64) {
          playAudio(data.tts_audio_base64, data.audio_mime_type || 'audio/wav');
        }
      } catch (err: unknown) {
        if (turnEpoch !== sessionEpochRef.current) return;
        const message = err instanceof Error ? err.message : 'Text processing failed.';
        setTurnStatus({
          type: 'error',
          message: 'Model reasoning or retrieval failed. Check gateway connection.',
        });
        setIsResultLoading(false);
        setResultError(message);
      }
    },
    [testFixtureId, playAudio]
  );

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

  // 7. End Session Handler (Wipes private state, increments epoch, and purges sensitive blocks)
  const handleEndSession = useCallback(() => {
    stopAudio();
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
  }, [purgeProtectedData, stopAudio]);

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
      // Security boundary: Sensitive result blocks cannot be reopened without an active verified session or authorized test context
      if (block.isSensitive && session.state !== 'VERIFIED' && testFixtureId === 'anonymous_visitor') {
        return;
      }
      setActiveResultBlock(block);
    },
    [session.state, testFixtureId]
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
        handleTextSubmitted,
        handleSelectTestFixture,
        playAudio,
        stopAudio,
        replayAudio,
      };
    }
    (window as unknown as { __intentLockSimulateVoiceTurn?: typeof handleAudioCaptured }).__intentLockSimulateVoiceTurn = handleAudioCaptured;
    return () => {
      delete (window as unknown as { __intentLockSimulateVoiceTurn?: typeof handleAudioCaptured }).__intentLockSimulateVoiceTurn;
      if (import.meta.env.DEV) {
        delete (window as unknown as Record<string, unknown>).__intentLockDevHelpers;
      }
    };
  }, [handleAudioCaptured, handleEndSession, handleTextSubmitted, handleSelectTestFixture, playAudio, stopAudio, replayAudio]);

  return (
    <AppShell
      isLocalRenderTest
      session={session}
      messages={messages}
      currentTurnStatus={turnStatus}
      activeResultBlock={activeResultBlock}
      isResultLoading={isResultLoading}
      resultError={resultError}
      testFixtureId={testFixtureId}
      onSelectTestFixture={handleSelectTestFixture}
      isPlayingAudio={isPlayingAudio}
      onStopAudio={stopAudio}
      onReplayAudio={replayAudio}
      hasAudioToReplay={Boolean(lastAudioPayload)}
      onAudioCaptured={handleAudioCaptured}
      onTextSubmitted={handleTextSubmitted}
      onEndSession={handleEndSession}
      onResultAction={handleResultAction}
      onSelectResultBlock={handleSelectResultBlock}
    />
  );
}

export default App;
