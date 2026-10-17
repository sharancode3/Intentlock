import { useCallback, useEffect, useRef, useState } from 'react';
import { AppShell } from './components/layout/AppShell';
import { useSettings } from './hooks/useSettings';
import { API_BASE } from './utils/voiceClient';
import {
  resolveTurnStatus,
  resolveEvidenceSummary,
  resolveSafeResultBlocks,
} from './utils/statusPresentation';
import type { LiveTranscript } from './utils/voiceClient';
import type { ConversationMessage, GenericResultBlock, SelectedEntityContext, SessionInfo, TurnStatusNotice, VoiceTurnResponse } from './types';

type TurnReply = VoiceTurnResponse;
const anonymous: SessionInfo = { state: 'ANONYMOUS', sessionId: null };
const welcome = (): ConversationMessage => ({
  id: crypto.randomUUID(),
  sender: 'assistant',
  text: 'Welcome to IntentLock. For employee access, state your employee ID (e.g. "My employee ID is EMP-1001. Show my workspace."). Public helpdesk assistance is available without authentication.',
  timestamp: 'Ready',
});

export default function LiveApp() {
  const { settings } = useSettings();
  const [session, setSession] = useState<SessionInfo>(anonymous);
  const [candidate, setCandidate] = useState<string | null>(null);
  const [messages, setMessages] = useState<ConversationMessage[]>([welcome()]);
  const [status, setStatus] = useState<TurnStatusNotice>({ type: 'idle' });
  const [block, setBlock] = useState<GenericResultBlock | null>(null);
  const [availableBlocks, setAvailableBlocks] = useState<GenericResultBlock[]>([]);
  const [selectedEntity, setSelectedEntity] = useState<SelectedEntityContext | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [lastAudio, setLastAudio] = useState<TurnReply['speech_audio']>(undefined);
  const [evidence, setEvidence] = useState('Voice-First: State your employee ID or ask a public question');
  const [captureEpoch, setCaptureEpoch] = useState(0);
  const epoch = useRef(0);
  const request = useRef<AbortController | null>(null);
  const actionRequest = useRef<AbortController | null>(null);
  const actionSequence = useRef(0);
  const sessionRef = useRef(session);
  useEffect(() => { sessionRef.current = session; }, [session]);
  const selectedEntityRef = useRef<SelectedEntityContext | null>(null);
  useEffect(() => { selectedEntityRef.current = selectedEntity; }, [selectedEntity]);
  const expiresAt = useRef<number | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioDone = useRef<(() => void) | null>(null);
  const audioPlaySequence = useRef(0);
  const busyRef = useRef(false);
  const submittedTurnsRef = useRef<Set<string>>(new Set());

  const stopAudio = useCallback(() => {
    audioPlaySequence.current += 1;
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.removeAttribute('src');
      audioRef.current.load();
      audioRef.current = null;
    }
    audioDone.current?.(); audioDone.current = null; setPlaying(false);
  }, []);

  const playAudio = useCallback(async (payload: NonNullable<TurnReply['speech_audio']>) => {
    stopAudio();
    if (!settings.voicePlaybackEnabled) return;
    const currentSeq = ++audioPlaySequence.current;
    await new Promise<void>(resolve => {
      try {
        const audio = new Audio(`data:${payload.mime_type};base64,${payload.base64_audio}`);
        audioRef.current = audio; audioDone.current = resolve;
        audio.volume = Math.max(0, Math.min(1, settings.voiceVolume));
        const done = () => {
          if (audioPlaySequence.current === currentSeq) {
            if (audioRef.current === audio) {
              audioRef.current = null;
              audioDone.current = null;
              setPlaying(false);
            }
          }
          resolve();
        };
        audio.onended = done;
        audio.onerror = () => {
          if (audioPlaySequence.current === currentSeq) {
            setError('Audio playback error occurred.');
            done();
          } else {
            resolve();
          }
        };
        setPlaying(true);
        void audio.play().catch(err => {
          if (audioPlaySequence.current === currentSeq) {
            if (err instanceof DOMException && (err.name === 'NotAllowedError' || err.name === 'AbortError')) {
              setError('Autoplay restricted by browser. Tap Replay Audio to listen.');
            } else {
              setError('Audio playback unavailable.');
            }
            done();
          } else {
            resolve();
          }
        });
      } catch {
        resolve();
      }
    });
  }, [settings.voicePlaybackEnabled, settings.voiceVolume, stopAudio]);

  const replayAudio = useCallback(() => {
    if (sessionRef.current.state === 'EXPIRED') return;
    if (lastAudio) void playAudio(lastAudio);
  }, [lastAudio, playAudio]);

  const clearSession = useCallback(() => {
    const token = sessionRef.current.sessionId;
    epoch.current += 1; actionSequence.current += 1;
    audioPlaySequence.current += 1;
    request.current?.abort(); request.current = null;
    actionRequest.current?.abort(); actionRequest.current = null; stopAudio();
    submittedTurnsRef.current.clear();
    expiresAt.current = null; setSession(anonymous); sessionRef.current = anonymous;
    setSelectedEntity(null); selectedEntityRef.current = null;
    setBlock(null); setAvailableBlocks([]); setMessages([welcome()]); setLastAudio(undefined);
    setEvidence('Voice-First: State your employee ID or ask a public question'); setBusy(false); busyRef.current = false;
    setStatus({ type: 'idle' }); setError(null); setCaptureEpoch(value => value + 1);
    if (token) void fetch(`${API_BASE}/api/v1/voice/session/end`, {
      method: 'POST', headers: { Authorization: `Bearer ${token}` },
    }).catch(() => setError('Backend session termination could not be confirmed. Local private content was cleared.'));
  }, [stopAudio]);
  useEffect(() => {
    const timer = setInterval(() => {
      if (expiresAt.current === null) return;
      const remaining = Math.max(0, Math.ceil((expiresAt.current - Date.now()) / 1000));
      if (!remaining) {
        expiresAt.current = null;
        epoch.current += 1;
        actionSequence.current += 1;
        audioPlaySequence.current += 1;
        request.current?.abort();
        request.current = null;
        actionRequest.current?.abort();
        actionRequest.current = null;
        stopAudio();
        submittedTurnsRef.current.clear();
        const expiredState: SessionInfo = { state: 'EXPIRED', sessionId: null };
        setSession(expiredState);
        sessionRef.current = expiredState;
        setSelectedEntity(null);
        selectedEntityRef.current = null;
        setBlock(null);
        setAvailableBlocks([]);
        setLastAudio(undefined);
        setEvidence('Session expired · Re-verification required for private workspace access');
        setStatus({
          type: 'denial',
          message: 'Your session has expired. Please state your employee ID again to continue.',
        });
      } else {
        setSession(value => value.actor ? { ...value, actor: { ...value.actor, expiresInSeconds: remaining } } : value);
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [stopAudio]);
  useEffect(() => () => { request.current?.abort(); actionRequest.current?.abort(); stopAudio(); }, [stopAudio]);

  const onTranscript = useCallback(({ turnId, text, isFinal, cancelled }: LiveTranscript) => {
    const id = `user-${turnId}`;
    setMessages(previous => {
      if (cancelled) return previous.filter(message => message.id !== id);
      const existing = previous.find(value => value.id === id);
      if (existing && existing.status === 'complete' && !isFinal) return previous;
      const message: ConversationMessage = {
        id,
        sender: 'user',
        text: text || 'Listening…',
        timestamp: existing?.timestamp || new Date().toLocaleTimeString(),
        turnId,
        status: isFinal ? 'pending' : 'streaming',
        isStreaming: !isFinal,
      };
      return existing ? previous.map(value => value.id === id ? message : value) : [...previous, message];
    });
  }, []);

  const refreshAuthoritativeData = useCallback(async (committedAction: string, resourceId?: string) => {
    const token = sessionRef.current.sessionId;
    if (!token || sessionRef.current.state !== 'VERIFIED') return;
    const currentEpoch = epoch.current;

    // Remove any consumed proposal blocks from active and available blocks
    setAvailableBlocks(prev => prev.filter(b => b.type !== 'READBACK_CONFIRMATION'));
    setBlock(prev => prev?.type === 'READBACK_CONFIRMATION' ? null : prev);

    // 1. Contact / Employee Profile Refresh
    if (committedAction === 'update_contact' || committedAction.toLowerCase().includes('contact') || committedAction.toLowerCase().includes('profile')) {
      try {
        const res = await fetch(`${API_BASE}/api/v1/employees/me`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (epoch.current !== currentEpoch) return; // Stale protection: race condition
        if (res.ok) {
          const data = await res.json();
          const updatedEmployee = data.employee;
          if (updatedEmployee) {
            setBlock(prev => {
              if (prev && prev.type === 'EMPLOYEE_PROFILE') {
                const currentEmp = (prev.payload as Record<string, any>)?.employee;
                if (!resourceId || currentEmp?.id === resourceId || currentEmp?.employee_id === resourceId || currentEmp?.id === updatedEmployee.id || currentEmp?.employee_id === updatedEmployee.employee_id) {
                  return { ...prev, payload: { ...prev.payload, employee: { ...currentEmp, ...updatedEmployee } } };
                }
              }
              return prev;
            });
            setAvailableBlocks(prevBlocks =>
              prevBlocks.map(b => {
                if (b.type === 'EMPLOYEE_PROFILE') {
                  const currentEmp = (b.payload as Record<string, any>)?.employee;
                  if (!resourceId || currentEmp?.id === resourceId || currentEmp?.employee_id === resourceId || currentEmp?.id === updatedEmployee.id || currentEmp?.employee_id === updatedEmployee.employee_id) {
                    return { ...b, payload: { ...b.payload, employee: { ...currentEmp, ...updatedEmployee } } };
                  }
                }
                return b;
              })
            );
          }
        } else {
          // Non-fatal: commit succeeded, but subsequent read failed. Preserve valid committed receipt.
          setStatus(prev => ({
            ...prev,
            message: `${prev.message || 'Action committed.'} (Authoritative profile refresh temporarily unavailable.)`,
          }));
        }
      } catch {
        // Non-fatal: network error on subsequent read does NOT invalidate committed write
      }
    }

    // 2. Ticket Refresh & Selection Reconciliation
    if (committedAction === 'update_ticket' || committedAction === 'create_ticket' || committedAction.toLowerCase().includes('ticket')) {
      try {
        const res = await fetch(`${API_BASE}/api/v1/tickets`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (epoch.current !== currentEpoch) return; // Stale response protection
        if (res.ok) {
          const data = await res.json();
          const tickets = data.tickets || (Array.isArray(data) ? data : []);
          setBlock(prev => {
            if (prev && prev.type === 'TICKET_LIST') {
              return { ...prev, payload: { ...prev.payload, tickets, total: data.total ?? tickets.length } };
            }
            return prev;
          });
          setAvailableBlocks(prevBlocks =>
            prevBlocks.map(b => {
              if (b.type === 'TICKET_LIST') {
                return { ...b, payload: { ...b.payload, tickets, total: data.total ?? tickets.length } };
              }
              return b;
            })
          );

          // Reconcile selectedEntity: clear if resolved ticket no longer present in filtered view
          if (selectedEntityRef.current?.type === 'ticket') {
            const selectedId = selectedEntityRef.current.id;
            const stillExists = tickets.some((t: any) => String(t.id || t.ticket_id) === String(selectedId));
            if (!stillExists) {
              setSelectedEntity(null);
              selectedEntityRef.current = null;
            }
          }
        } else {
          // Non-fatal: preserve committed receipt
          setStatus(prev => ({
            ...prev,
            message: `${prev.message || 'Action committed.'} (Authoritative ticket refresh temporarily unavailable.)`,
          }));
        }
      } catch {
        // Non-fatal
      }
    }
  }, []);

  const handleAudio = useCallback(async (blob: Blob, duration: number, givenId?: string) => {
    if (busyRef.current) return;
    if (givenId && submittedTurnsRef.current.has(givenId)) return;
    stopAudio();
    actionSequence.current += 1; actionRequest.current?.abort(); actionRequest.current = null;
    const turnId = givenId || crypto.randomUUID();
    submittedTurnsRef.current.add(turnId);
    if (submittedTurnsRef.current.size > 50) {
      const oldest = Array.from(submittedTurnsRef.current).slice(0, 10);
      oldest.forEach(id => submittedTurnsRef.current.delete(id));
    }
    const messageId = `user-${turnId}`, turnEpoch = epoch.current;
    void duration;
    busyRef.current = true; setBusy(true); setError(null);
    setEvidence('Processing this recording…');
    setStatus({ type: 'verifying', message: 'Verifying your request and identity…' });
    const hadVerifiedSession = sessionRef.current.state === 'VERIFIED';
    const controller = new AbortController(); request.current = controller;
    const timeout = setTimeout(() => controller.abort(), 90000);
    try {
      const form = new FormData();
      const suffix = blob.type.includes('mp4') ? 'm4a' : blob.type.includes('wav') ? 'wav' : 'webm';
      form.append('audio_file', blob, `utterance.${suffix}`);
      form.append('client_turn_id', turnId);
      if (candidate && candidate.trim()) {
        form.append('candidate_employee_id', candidate.trim());
      }
      if (sessionRef.current.sessionId) form.append('session_id', sessionRef.current.sessionId);
      if (block?.id) form.append('active_result_id', block.id);
      if (block?.type) form.append('active_result_type', block.type);
      if (selectedEntityRef.current) {
        form.append('selected_entity_id', selectedEntityRef.current.id);
        form.append('selected_entity_type', selectedEntityRef.current.type);
        if (selectedEntityRef.current.sourceResultId) {
          form.append('selected_source_result_id', selectedEntityRef.current.sourceResultId);
        }
        if (selectedEntityRef.current.name) {
          form.append('selected_entity_name', selectedEntityRef.current.name);
        }
      }
      setMessages(previous => previous.some(value => value.id === messageId) ? previous : [...previous, {
        id: messageId, sender: 'user', text: 'Transcribing…', timestamp: new Date().toLocaleTimeString(), turnId, status: 'pending',
      }]);
      const response = await fetch(`${API_BASE}/api/v1/voice/turn`, { method: 'POST', body: form, signal: controller.signal });
      const data: TurnReply = await response.json();
      if (epoch.current !== turnEpoch) return;

      const code = data.error?.code?.toUpperCase();

      // Check for provider failure
      if (!response.ok && (code === 'PROVIDER_UNAVAILABLE' || code === 'DETECTIF_UNAVAILABLE')) {
        const turnStatus = resolveTurnStatus(data, sessionRef.current);
        const evidenceStr = resolveEvidenceSummary(data, sessionRef.current);
        setStatus(turnStatus);
        setEvidence(evidenceStr);
        setMessages(previous => [
          ...previous.map(v => v.id === messageId ? { ...v, text: data.transcript || v.text, status: 'complete' as const } : v),
          { id: `assistant-${turnId}`, sender: 'assistant', text: data.error?.message || 'Identity verification is temporarily unavailable. Private access cannot continue.',
            timestamp: new Date().toLocaleTimeString(), turnId, status: 'error', errorMessage: data.error?.message },
        ]);
        return;
      }

      if (!response.ok && data.status !== 'denial' && data.status !== 'clarification') {
        throw new Error(data.error?.message || `Voice service returned ${response.status}.`);
      }

      // Authoritative session update: never wipe verified session on an unauthorized denial
      let updated: SessionInfo;
      if (data.session) {
        updated = data.session;
      } else if (hadVerifiedSession && data.status === 'denial' && code !== 'SESSION_EXPIRED' && code !== 'TOKEN_EXPIRED') {
        updated = sessionRef.current;
      } else if (code === 'SESSION_EXPIRED' || code === 'TOKEN_EXPIRED') {
        updated = { state: 'EXPIRED', sessionId: null };
      } else {
        updated = anonymous;
      }

      const isVerified = updated.state === 'VERIFIED';
      setSession(updated); sessionRef.current = updated;

      if (data.session_expires_at) {
        expiresAt.current = Date.parse(data.session_expires_at);
      } else if (!isVerified) {
        expiresAt.current = null;
      }

      if (!isVerified && hadVerifiedSession) {
        stopAudio(); setMessages([welcome()]); setBlock(null); setAvailableBlocks([]); setLastAudio(undefined);
      }

      const turnStatus = resolveTurnStatus(data, updated);
      const evidenceStr = resolveEvidenceSummary(data, updated);
      setEvidence(evidenceStr);
      setStatus(turnStatus);

      const rawBlocks = data.result_blocks && data.result_blocks.length > 0
        ? data.result_blocks
        : (data.result_block ? [data.result_block] : []);
      const { safePrimary, safeBlocks } = resolveSafeResultBlocks(rawBlocks, data.primary_result_id || data.result_block?.id, isVerified);

      setAvailableBlocks(safeBlocks);
      setMessages(previous => [
        ...previous.map(value => {
          const completed = value.id === messageId ? { ...value, text: data.transcript || value.text, status: 'complete' as const, isStreaming: false } : value;
          return safePrimary?.type === 'ACTION_RECEIPT' && completed.resultBlock?.isSensitive
            ? { ...completed, resultBlock: undefined, resultBlockId: undefined } : completed;
        }),
        { id: `assistant-${turnId}`, sender: 'assistant', text: data.assistant_message || data.error?.message || 'No response was returned.',
          timestamp: new Date().toLocaleTimeString(), turnId, status: data.status === 'error' ? 'error' : 'complete',
          resultBlock: safePrimary || undefined, resultBlockId: safePrimary?.id },
      ]);

      if (data.status === 'clarification' && !safePrimary) {
        // preserve existing contextual block during clarification
      } else {
        setBlock(safePrimary);
      }

      if (safePrimary?.type === 'ACTION_RECEIPT') {
        const receipt = (safePrimary.payload as Record<string, any>)?.receipt;
        const statusVal = receipt?.status?.toUpperCase();
        if (statusVal === 'COMMITTED' || statusVal === 'SUCCESS') {
          void refreshAuthoritativeData(receipt?.action || '', receipt?.resource_id || receipt?.target);
        }
      }

      if (data.speech_audio) { setLastAudio(data.speech_audio); await playAudio(data.speech_audio); }
    } catch (cause) {
      if (epoch.current !== turnEpoch) return;
      const message = cause instanceof Error && cause.name === 'AbortError' ? 'The voice request was cancelled or timed out.' : cause instanceof Error ? cause.message : 'Voice request failed.';
      setError(message); setSession(anonymous); sessionRef.current = anonymous; expiresAt.current = null;
      setBlock(null); setAvailableBlocks([]); setLastAudio(undefined); setEvidence('Verification unavailable');
      setMessages(previous => [
        ...previous.map(value => value.id === messageId ? { ...value, text: value.text === 'Transcribing…' ? 'Speech capture error' : value.text, status: 'error' as const } : value),
        { id: crypto.randomUUID(), sender: 'assistant', text: message,
          timestamp: new Date().toLocaleTimeString(), status: 'error', errorMessage: message },
      ]);
      setStatus({ type: 'error', message });
    } finally {
      clearTimeout(timeout);
      if (epoch.current === turnEpoch) { busyRef.current = false; setBusy(false); request.current = null; }
    }
  }, [block, candidate, playAudio, refreshAuthoritativeData, stopAudio]);

  const handleResultAction = useCallback(async (action: string, parameters: Record<string, unknown>) => {
    const token = sessionRef.current.sessionId;
    if (!token || busyRef.current) return;
    const sourceId = parameters.source_result_id;
    if (typeof sourceId !== 'string') return;
    const turnEpoch = epoch.current;
    const actionId = ++actionSequence.current;
    actionRequest.current?.abort();
    const controller = new AbortController();
    actionRequest.current = controller;

    // Handle Proposal Cancellation
    if (action === 'cancel_proposal') {
      setBlock(prev => prev?.id === sourceId || prev?.type === 'READBACK_CONFIRMATION' ? null : prev);
      setAvailableBlocks(prev => prev.filter(b => b.id !== sourceId && b.type !== 'READBACK_CONFIRMATION'));
      setStatus({ type: 'idle' });
      setMessages(previous => [...previous, {
        id: crypto.randomUUID(),
        sender: 'assistant',
        text: 'Action proposal cancelled. The pending change was dismissed without modifying any records.',
        timestamp: new Date().toLocaleTimeString(),
      }]);
      try {
        await fetch(`${API_BASE}/api/v1/voice/result-action`, {
          method: 'POST', signal: controller.signal,
          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'cancel', source_result_id: sourceId }),
        });
      } catch {
        // Graceful catch
      }
      return;
    }

    // Handle Confirm Action with Voice Verification Requirement
    if (action === 'confirm_action') {
      const requiresVoice = Boolean(parameters.requires_voice);
      if (requiresVoice) {
        setStatus({
          type: 'verification_required',
          message: 'Spoken confirmation required: Please speak the exact confirmation readback phrase to authorize this change with biometric verification.',
        });
        setEvidence('Spoken verification required for commit');
        return;
      }
    }

    // Optimistically record selected entity for context
    if (action === 'open_profile' && (parameters.target_id || parameters.id)) {
      const targetId = String(parameters.target_id || parameters.id);
      const name = typeof parameters.name === 'string' ? parameters.name : undefined;
      const newEntity: SelectedEntityContext = {
        type: 'employee',
        id: targetId,
        name,
        sourceResultId: sourceId,
        timestamp: new Date().toISOString(),
      };
      setSelectedEntity(newEntity);
      selectedEntityRef.current = newEntity;
    } else if (action === 'select_ticket' && (parameters.ticket_id || parameters.target_id)) {
      const ticketId = String(parameters.ticket_id || parameters.target_id);
      const newEntity: SelectedEntityContext = {
        type: 'ticket',
        id: ticketId,
        sourceResultId: sourceId,
        timestamp: new Date().toISOString(),
      };
      setSelectedEntity(newEntity);
      selectedEntityRef.current = newEntity;
    }

    const isMutation = action.toLowerCase().includes('commit') || action.toLowerCase().includes('confirm') || action.toLowerCase().includes('save') || action.toLowerCase().includes('update');
    if (isMutation) {
      setStatus({ type: 'executing', message: 'Executing protected action…' });
    } else {
      setStatus({ type: 'reasoning', message: 'Checking the selected result…' });
    }

    try {
      const targetId = parameters.target_id ?? parameters.ticket_id ?? parameters.id;
      const response = await fetch(`${API_BASE}/api/v1/voice/result-action`, {
        method: 'POST', signal: controller.signal,
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, source_result_id: sourceId, target_id: targetId,
          view: parameters.view, group_by: parameters.group_by }),
      });
      if (epoch.current !== turnEpoch || actionSequence.current !== actionId) return;
      const data = await response.json();
      if (epoch.current !== turnEpoch || actionSequence.current !== actionId) return;
      if (response.status === 409) {
        // Stop showing stale proposal as executable
        setBlock(prev => prev?.type === 'READBACK_CONFIRMATION' ? null : prev);
        setAvailableBlocks(prev => prev.filter(b => b.type !== 'READBACK_CONFIRMATION'));
        if (data.status === 'verification_required') {
          setStatus({ type: 'verification_required', message: data.assistant_message || 'Voice verification is required to view details for this person.' });
        } else {
          setStatus({ type: 'clarification', message: data.assistant_message || 'Version conflict detected. The underlying record was modified by another operation. Please request a fresh proposal.' });
          setEvidence('Version conflict · Record modified concurrently');
        }
        return;
      }
      if (!response.ok) throw new Error(data.error?.message || data.detail || 'Result action failed.');
      const result = data.result_block as GenericResultBlock | undefined;
      if (result) {
        setBlock(result);
        setAvailableBlocks(prev => prev.some(b => b.id === result.id) ? prev.map(b => b.id === result.id ? result : b) : [...prev, result]);
      }
      setMessages(previous => [...previous, { id: crypto.randomUUID(), sender: 'assistant',
        text: data.assistant_message || 'Result updated.', timestamp: new Date().toLocaleTimeString(),
        resultBlock: result, resultBlockId: result?.id }]);
      if (result?.type === 'ACTION_RECEIPT') {
        const receipt = (result.payload as Record<string, any>)?.receipt;
        const statusVal = receipt?.status?.toUpperCase();
        if (statusVal === 'COMMITTED' || statusVal === 'SUCCESS') {
          setStatus({ type: 'committed', message: data.assistant_message || 'Action executed and committed successfully.' });
          if (sessionRef.current.actor) {
            setEvidence(`Action committed to database · Actor: ${sessionRef.current.actor.fullName}`);
          }
          void refreshAuthoritativeData(receipt?.action || '', receipt?.resource_id || receipt?.target);
        } else if (statusVal === 'CONFLICT') {
          setStatus({ type: 'clarification', message: 'Version conflict: Record was modified before commit.' });
        } else if (statusVal === 'APPROVAL_REQUIRED') {
          setStatus({ type: 'clarification', message: 'Approval required: Action routed to manager for authorization.' });
        } else if (statusVal === 'DENIED' || statusVal === 'FAILED') {
          setStatus({ type: 'denial', message: 'Action could not be committed.' });
        }
      } else {
        setStatus({ type: 'result_ready' });
      }
    } catch (cause) {
      if (epoch.current !== turnEpoch || actionSequence.current !== actionId) return;
      if (controller.signal.aborted || (cause instanceof Error && cause.name === 'AbortError')) {
        if (isMutation) {
          // Unknown network outcome for protected mutation: retain state, do not claim success or failure
          setStatus({
            type: 'error',
            message: 'Outcome not yet confirmed. A network interruption occurred while executing this change. Please verify record status before retrying.',
          });
          setEvidence('Outcome unconfirmed · Network interruption during execution');
          return;
        }
        return;
      }
      setStatus({ type: 'error', message: cause instanceof Error ? cause.message : 'Result action failed.' });
    } finally {
      if (actionRequest.current === controller) actionRequest.current = null;
    }
  }, [refreshAuthoritativeData]);

  return <AppShell session={session} messages={messages} currentTurnStatus={status}
    activeResultBlock={block} resultBlocks={availableBlocks} isResultLoading={busy && !playing && !block} resultError={error}
    candidateEmployeeId={candidate} onSelectCandidate={value => { clearSession(); setCandidate(value); }}
    evidenceSummary={evidence} captureEpoch={captureEpoch} microphoneDisabled={busy || playing}
    isPlayingAudio={playing} onStopAudio={stopAudio} onReplayAudio={replayAudio}
    hasAudioToReplay={Boolean(lastAudio) && session.state !== 'EXPIRED'} onAudioCaptured={handleAudio} onLiveTranscript={onTranscript}
    onResultAction={handleResultAction} onEndSession={clearSession} onSelectResultBlock={value => {
      if (!value.isSensitive || sessionRef.current.state === 'VERIFIED') setBlock(value);
    }}
    selectedEntity={selectedEntity}
    onClearSelectedEntity={() => {
      setSelectedEntity(null);
      selectedEntityRef.current = null;
    }} />;
}
