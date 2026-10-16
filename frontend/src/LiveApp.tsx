import { useCallback, useEffect, useRef, useState } from 'react';
import { AppShell } from './components/layout/AppShell';
import { useSettings } from './hooks/useSettings';
import { API_BASE } from './utils/voiceClient';
import type { LiveTranscript } from './utils/voiceClient';
import type { ConversationMessage, GenericResultBlock, SessionInfo, TurnStatusNotice } from './types';

interface TurnReply {
  transcript?: string; assistant_message?: string; status: string; session?: SessionInfo;
  session_expires_at?: string; result_block?: GenericResultBlock | null;
  result_blocks?: GenericResultBlock[]; primary_result_id?: string | null;
  speech_audio?: { base64_audio: string; mime_type: string };
  trust_evidence?: { speaker_decision?: string; authenticity_verdict?: string };
  error?: { message?: string };
}
const anonymous: SessionInfo = { state: 'ANONYMOUS', sessionId: null };
const welcome = (): ConversationMessage => ({ id: crypto.randomUUID(), sender: 'assistant',
  text: 'Choose the employee ID you are claiming, then start speaking. Your voice must match that enrollment. Pause to send a question; transcripts appear here as you speak.', timestamp: 'Ready' });

export default function LiveApp() {
  const { settings } = useSettings();
  const [session, setSession] = useState<SessionInfo>(anonymous);
  const [candidate, setCandidate] = useState('EMP-1001');
  const [messages, setMessages] = useState<ConversationMessage[]>([welcome()]);
  const [status, setStatus] = useState<TurnStatusNotice>({ type: 'idle' });
  const [block, setBlock] = useState<GenericResultBlock | null>(null);
  const [availableBlocks, setAvailableBlocks] = useState<GenericResultBlock[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [lastAudio, setLastAudio] = useState<TurnReply['speech_audio']>(undefined);
  const [evidence, setEvidence] = useState('Voice verification required');
  const [captureEpoch, setCaptureEpoch] = useState(0);
  const epoch = useRef(0);
  const request = useRef<AbortController | null>(null);
  const actionRequest = useRef<AbortController | null>(null);
  const actionSequence = useRef(0);
  const sessionRef = useRef(session);
  useEffect(() => { sessionRef.current = session; }, [session]);
  const expiresAt = useRef<number | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioDone = useRef<(() => void) | null>(null);
  const busyRef = useRef(false);

  const stopAudio = useCallback(() => {
    audioRef.current?.pause(); audioRef.current = null;
    audioDone.current?.(); audioDone.current = null; setPlaying(false);
  }, []);
  const playAudio = useCallback(async (payload: NonNullable<TurnReply['speech_audio']>) => {
    stopAudio();
    if (!settings.voicePlaybackEnabled) return;
    await new Promise<void>(resolve => {
      const audio = new Audio(`data:${payload.mime_type};base64,${payload.base64_audio}`);
      audioRef.current = audio; audioDone.current = resolve;
      audio.volume = Math.max(0, Math.min(1, settings.voiceVolume));
      const done = () => {
        if (audioRef.current === audio) { audioRef.current = null; audioDone.current = null; setPlaying(false); }
        resolve();
      };
      audio.onended = done; audio.onerror = done; setPlaying(true);
      void audio.play().catch(() => { setError('Audio playback was blocked. Use Replay Audio.'); done(); });
    });
  }, [settings.voicePlaybackEnabled, settings.voiceVolume, stopAudio]);

  const clearSession = useCallback(() => {
    const token = sessionRef.current.sessionId;
    epoch.current += 1; actionSequence.current += 1;
    request.current?.abort(); request.current = null;
    actionRequest.current?.abort(); actionRequest.current = null; stopAudio();
    expiresAt.current = null; setSession(anonymous); sessionRef.current = anonymous;
    setBlock(null); setAvailableBlocks([]); setMessages([welcome()]); setLastAudio(undefined);
    setEvidence('Voice verification required'); setBusy(false); busyRef.current = false;
    setStatus({ type: 'idle' }); setError(null); setCaptureEpoch(value => value + 1);
    if (token) void fetch(`${API_BASE}/api/v1/voice/session/end`, {
      method: 'POST', headers: { Authorization: `Bearer ${token}` },
    }).catch(() => setError('Backend session termination could not be confirmed. Local private content was cleared.'));
  }, [stopAudio]);
  useEffect(() => {
    const timer = setInterval(() => {
      if (expiresAt.current === null) return;
      const remaining = Math.max(0, Math.ceil((expiresAt.current - Date.now()) / 1000));
      if (!remaining) clearSession();
      else setSession(value => value.actor ? { ...value, actor: { ...value.actor, expiresInSeconds: remaining } } : value);
    }, 1000);
    return () => clearInterval(timer);
  }, [clearSession]);
  useEffect(() => () => { request.current?.abort(); actionRequest.current?.abort(); stopAudio(); }, [stopAudio]);

  const onTranscript = useCallback(({ turnId, text, cancelled }: LiveTranscript) => {
    const id = `user-${turnId}`;
    setMessages(previous => {
      if (cancelled) return previous.filter(message => message.id !== id);
      const message: ConversationMessage = { id, sender: 'user', text: text || 'Listening…',
        timestamp: new Date().toLocaleTimeString(), turnId, status: 'streaming', isStreaming: true };
      return previous.some(value => value.id === id) ? previous.map(value => value.id === id ? message : value) : [...previous, message];
    });
  }, []);

  const handleAudio = useCallback(async (blob: Blob, duration: number, givenId?: string) => {
    if (busyRef.current) return;
    actionSequence.current += 1; actionRequest.current?.abort(); actionRequest.current = null;
    const turnId = givenId || crypto.randomUUID();
    const messageId = `user-${turnId}`, turnEpoch = epoch.current;
    void duration;
    busyRef.current = true; setBusy(true); setError(null);
    setEvidence('Processing this recording…');
    setStatus({ type: 'transcribing', message: 'Finalizing your request…' });
    const hadVerifiedSession = sessionRef.current.state === 'VERIFIED';
    const controller = new AbortController(); request.current = controller;
    const timeout = setTimeout(() => controller.abort(), 90000);
    try {
      const form = new FormData();
      const suffix = blob.type.includes('mp4') ? 'm4a' : blob.type.includes('wav') ? 'wav' : 'webm';
      form.append('audio_file', blob, `utterance.${suffix}`);
      form.append('client_turn_id', turnId); form.append('candidate_employee_id', candidate);
      if (sessionRef.current.sessionId) form.append('session_id', sessionRef.current.sessionId);
      setMessages(previous => previous.some(value => value.id === messageId) ? previous : [...previous, {
        id: messageId, sender: 'user', text: 'Transcribing…', timestamp: new Date().toLocaleTimeString(), turnId, status: 'pending',
      }]);
      const response = await fetch(`${API_BASE}/api/v1/voice/turn`, { method: 'POST', body: form, signal: controller.signal });
      const data: TurnReply = await response.json();
      if (epoch.current !== turnEpoch) return;
      if (!response.ok) throw new Error(data.error?.message || `Voice service returned ${response.status}.`);
      const updated = data.session || anonymous;
      setSession(updated); sessionRef.current = updated;
      expiresAt.current = data.session_expires_at ? Date.parse(data.session_expires_at) : null;
      if (updated.state !== 'VERIFIED' && hadVerifiedSession) {
        stopAudio(); setMessages([]); setBlock(null); setAvailableBlocks([]); setLastAudio(undefined);
      }
      const trust = data.trust_evidence;
      setEvidence(trust ? `Speaker: ${trust.speaker_decision || 'reused session'} · Authenticity: ${trust.authenticity_verdict || 'reused session'}` : data.status === 'success' ? 'No voice verification needed for this request' : 'Verification incomplete; private access restricted');
      const primary = data.result_blocks?.find(value => value.id === data.primary_result_id) || data.result_block || null;
      const allBlocks = data.result_blocks && data.result_blocks.length > 0 ? data.result_blocks : (primary ? [primary] : []);
      setAvailableBlocks(allBlocks);
      setMessages(previous => [
        ...previous.map(value => {
          const completed = value.id === messageId ? { ...value, text: data.transcript || value.text, status: 'complete' as const, isStreaming: false } : value;
          return primary?.type === 'ACTION_RECEIPT' && completed.resultBlock?.isSensitive
            ? { ...completed, resultBlock: undefined, resultBlockId: undefined } : completed;
        }),
        { id: `assistant-${turnId}`, sender: 'assistant', text: data.assistant_message || data.error?.message || 'No response was returned.',
          timestamp: new Date().toLocaleTimeString(), turnId, status: 'complete',
          resultBlock: primary || undefined, resultBlockId: primary?.id },
      ]);
      if (primary) setBlock(primary);
      setStatus({ type: data.status === 'success' ? 'result_ready' : data.status === 'clarification' ? 'clarification' : 'denial', message: data.error?.message });
      if (data.speech_audio) { setLastAudio(data.speech_audio); await playAudio(data.speech_audio); }
    } catch (cause) {
      if (epoch.current !== turnEpoch) return;
      const message = cause instanceof Error && cause.name === 'AbortError' ? 'The voice request was cancelled or timed out.' : cause instanceof Error ? cause.message : 'Voice request failed.';
      setError(message); setSession(anonymous); sessionRef.current = anonymous; expiresAt.current = null;
      setBlock(null); setAvailableBlocks([]); setLastAudio(undefined); setEvidence('Verification unavailable');
      setMessages([{ id: crypto.randomUUID(), sender: 'assistant', text: message,
        timestamp: new Date().toLocaleTimeString(), status: 'error', errorMessage: message }]);
      setStatus({ type: 'error', message });
    } finally {
      clearTimeout(timeout);
      if (epoch.current === turnEpoch) { busyRef.current = false; setBusy(false); request.current = null; }
    }
  }, [candidate, playAudio, stopAudio]);

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
    setStatus({ type: 'reasoning', message: 'Checking the selected result…' });
    try {
      const response = await fetch(`${API_BASE}/api/v1/voice/result-action`, {
        method: 'POST', signal: controller.signal,
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, source_result_id: sourceId, target_id: parameters.target_id,
          view: parameters.view, group_by: parameters.group_by }),
      });
      if (epoch.current !== turnEpoch || actionSequence.current !== actionId) return;
      const data = await response.json();
      if (epoch.current !== turnEpoch || actionSequence.current !== actionId) return;
      if (response.status === 409) {
        setStatus({ type: 'clarification', message: data.assistant_message });
        return;
      }
      if (!response.ok) throw new Error(data.error?.message || data.detail || 'Result action failed.');
      const result = data.result_block as GenericResultBlock | undefined;
      if (result) setBlock(result);
      setMessages(previous => [...previous, { id: crypto.randomUUID(), sender: 'assistant',
        text: data.assistant_message || 'Result updated.', timestamp: new Date().toLocaleTimeString(),
        resultBlock: result, resultBlockId: result?.id }]);
      setStatus({ type: 'result_ready' });
    } catch (cause) {
      if (epoch.current !== turnEpoch || actionSequence.current !== actionId || controller.signal.aborted) return;
      setStatus({ type: 'error', message: cause instanceof Error ? cause.message : 'Result action failed.' });
    } finally {
      if (actionRequest.current === controller) actionRequest.current = null;
    }
  }, []);

  return <AppShell session={session} messages={messages} currentTurnStatus={status}
    activeResultBlock={block} resultBlocks={availableBlocks} isResultLoading={busy && !playing && !block} resultError={error}
    candidateEmployeeId={candidate} onSelectCandidate={value => { clearSession(); setCandidate(value); }}
    evidenceSummary={evidence} captureEpoch={captureEpoch} microphoneDisabled={busy || playing}
    isPlayingAudio={playing} onStopAudio={stopAudio} onReplayAudio={() => { if (lastAudio) void playAudio(lastAudio); }}
    hasAudioToReplay={Boolean(lastAudio)} onAudioCaptured={handleAudio} onLiveTranscript={onTranscript}
    onResultAction={handleResultAction} onEndSession={clearSession} onSelectResultBlock={value => {
      if (!value.isSensitive || sessionRef.current.state === 'VERIFIED') setBlock(value);
    }} />;
}
