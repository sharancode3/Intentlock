import { useCallback, useEffect, useRef, useState } from 'react';
import { previewUrl } from '../utils/voiceClient';
import type { LiveTranscript } from '../utils/voiceClient';
import type { PermissionState } from './useAudioRecorder';

interface Options {
  onAudioCaptured: (blob: Blob, duration: number, turnId?: string) => void | Promise<void>;
  onLiveTranscript?: (event: LiveTranscript) => void;
  disabled?: boolean;
  previewEnabled?: boolean;
}

/** Continuous conversation, bounded individual recordings, local server VAD/ASR preview. */
export function useLiveAudioRecorder(options: Options) {
  const supported = typeof navigator.mediaDevices?.getUserMedia === 'function' && typeof MediaRecorder !== 'undefined';
  const [isRecording, setRecording] = useState(false);
  const [isArmed, setArmed] = useState(false);
  const [duration, setDuration] = useState(0);
  const [permissionState, setPermission] = useState<PermissionState>(supported ? 'prompt' : 'unsupported');
  const [errorMessage, setError] = useState<string | null>(null);
  const [previewStatus, setPreviewStatus] = useState('');
  const latest = useRef(options);
  useEffect(() => { latest.current = options; });
  const armed = useRef(false);
  const starting = useRef(false);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const socket = useRef<WebSocket | null>(null);
  const context = useRef<AudioContext | null>(null);
  const worklet = useRef<AudioWorkletNode | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const restartTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancelled = useRef(false);
  const startRef = useRef<() => Promise<void>>(async () => {});

  const cleanup = useCallback(() => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    if (socket.current) {
      socket.current.onmessage = null;
      socket.current.onclose = null;
      socket.current.close();
      socket.current = null;
    }
    worklet.current?.disconnect();
    worklet.current = null;
    void context.current?.close().catch(() => {});
    context.current = null;
    stream.current?.getTracks().forEach(track => track.stop());
    stream.current = null;
  }, []);

  const finish = useCallback((keepListening: boolean, discard = false) => {
    armed.current = keepListening;
    setArmed(keepListening);
    cancelled.current = discard;
    if (restartTimer.current) clearTimeout(restartTimer.current);
    if (recorder.current?.state === 'recording') recorder.current.stop();
    else cleanup();
    setRecording(false);
  }, [cleanup]);

  const scheduleRestart = useCallback(() => {
    if (restartTimer.current) clearTimeout(restartTimer.current);
    restartTimer.current = setTimeout(() => {
      if (armed.current && !latest.current.disabled) void startRef.current();
    }, 350);
  }, []);

  const start = useCallback(async () => {
    if (starting.current || recorder.current?.state === 'recording' || latest.current.disabled) return;
    starting.current = true;
    armed.current = true;
    setArmed(true);
    setError(null);
    cancelled.current = false;
    const turnId = crypto.randomUUID();
    let began = 0;
    let lastSpeech = Date.now();
    let heardSpeech = false;
    let vadAvailable = false;
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: {
        channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true,
      } });
      if (!armed.current || latest.current.disabled) {
        media.getTracks().forEach(track => track.stop());
        return;
      }
      stream.current = media;
      setPermission('granted');
      const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find(value => MediaRecorder.isTypeSupported(value));
      const capture = new MediaRecorder(media, mime ? { mimeType: mime } : undefined);
      recorder.current = capture;
      const chunks: Blob[] = [];
      capture.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      capture.onstop = async () => {
        const elapsed = Date.now() - began;
        const discard = cancelled.current;
        cleanup();
        setRecording(false);
        setDuration(0);
        if (discard || !chunks.length || (vadAvailable && !heardSpeech)) {
          latest.current.onLiveTranscript?.({ turnId, text: '', cancelled: true });
        } else {
          await latest.current.onAudioCaptured(new Blob(chunks, { type: capture.mimeType || 'audio/webm' }), elapsed, turnId);
        }
        if (armed.current && !latest.current.disabled) scheduleRestart();
      };
      capture.start(250);
      began = Date.now();
      lastSpeech = began;
      setRecording(true);
      latest.current.onLiveTranscript?.({ turnId, text: '' });
      setPreviewStatus(latest.current.previewEnabled === false ? 'Record, then submit' : 'Connecting live local transcription…');

      if (latest.current.previewEnabled !== false) {
        try {
          const audioContext = new AudioContext();
          context.current = audioContext;
          await audioContext.audioWorklet.addModule('/pcm-capture.worklet.js');
          if (capture.state !== 'recording') return;
          const node = new AudioWorkletNode(audioContext, 'pcm-capture');
          worklet.current = node;
          audioContext.createMediaStreamSource(media).connect(node);
          // The worklet outputs silence; connecting keeps the processing graph alive.
          node.connect(audioContext.destination);
          await audioContext.resume();
          const ws = new WebSocket(previewUrl());
          socket.current = ws;
          node.port.onmessage = event => {
            if (ws.readyState === WebSocket.OPEN && ws.bufferedAmount < 65536) ws.send(event.data);
            else if (ws.bufferedAmount >= 65536) {
              setPreviewStatus('Preview is behind; final transcript will follow submission');
              ws.close();
            }
          };
          ws.onmessage = event => {
            if (capture.state !== 'recording') return;
            const data = JSON.parse(event.data);
            if (data.type === 'ready') {
              vadAvailable = true;
              setPreviewStatus('Live local transcription · pause to send');
            } else if (data.type === 'vad' && data.speech) {
              heardSpeech = true;
              lastSpeech = Date.now();
            } else if (data.type === 'transcript.partial') {
              latest.current.onLiveTranscript?.({ turnId, text: data.text });
            } else if (data.type === 'limit') finish(true);
            else if (data.type === 'unavailable') setPreviewStatus(data.message);
          };
          ws.onclose = () => {
            vadAvailable = false;
            setPreviewStatus('Preview offline · use Done to submit for transcription');
          };
          ws.onerror = () => setPreviewStatus('Preview offline · use Done to submit');
        } catch {
          setPreviewStatus('Live preview unavailable · use Done to submit');
        }
      }
      timer.current = setInterval(() => {
        const now = Date.now();
        setDuration(Math.floor((now - began) / 1000));
        if (vadAvailable && now - lastSpeech >= 20000) {
          setPreviewStatus('Microphone stopped after 20 seconds without speech');
          finish(false, !heardSpeech);
        } else if (vadAvailable && heardSpeech && now - lastSpeech >= 1400) {
          finish(true);
        } else if (now - began >= 55000) finish(true);
      }, 200);
    } catch (error) {
      cleanup();
      armed.current = false;
      setArmed(false);
      setRecording(false);
      if (error instanceof DOMException && error.name === 'NotAllowedError') setPermission('denied');
      setError(error instanceof Error ? error.message : 'Microphone could not start.');
    } finally {
      starting.current = false;
    }
  }, [cleanup, finish, scheduleRestart]);
  useEffect(() => { startRef.current = start; }, [start]);

  useEffect(() => {
    if (options.disabled && recorder.current?.state === 'recording') finish(true, true);
    else if (!options.disabled && armed.current) scheduleRestart();
  }, [options.disabled, finish, scheduleRestart]);
  useEffect(() => () => {
    armed.current = false;
    cancelled.current = true;
    if (restartTimer.current) clearTimeout(restartTimer.current);
    if (recorder.current?.state === 'recording') recorder.current.stop();
    cleanup();
  }, [cleanup]);

  return { isRecording, isArmed, duration, permissionState, errorMessage, previewStatus,
    startRecording: start, stopRecording: () => finish(false),
    cancelRecording: () => finish(false, true), clearError: () => setError(null) };
}
