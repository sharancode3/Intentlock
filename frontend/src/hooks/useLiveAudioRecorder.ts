import { useCallback, useEffect, useRef, useState } from 'react';
import { previewUrl } from '../utils/voiceClient';
import type { LiveTranscript } from '../utils/voiceClient';
import type { PermissionState } from './useAudioRecorder';
import type { SpeechTimingMetrics } from '../types';

export const PAUSE_TO_SUBMIT_MS = 1400; // Natural post-speech pause threshold before finalization
export const IDLE_TIMEOUT_MS = 20000;    // Timeout when no speech is detected at all
export const MAX_RECORDING_DURATION_MS = 55000; // Ceiling matching backend max preview
export const MIN_SPEECH_DURATION_MS = 300; // Guard against accidental empty clicks

interface Options {
  onAudioCaptured: (blob: Blob, duration: number, turnId?: string) => void | Promise<void>;
  onLiveTranscript?: (event: LiveTranscript) => void;
  onTimingMetrics?: (metrics: SpeechTimingMetrics) => void;
  disabled?: boolean;
  previewEnabled?: boolean;
}

/**
 * Continuous conversation, bounded individual recordings, local server VAD/ASR preview.
 * Strictly guarantees exactly one submission per logical turn and reliable resource cleanup.
 */
export function useLiveAudioRecorder(options: Options) {
  const supported = typeof navigator !== 'undefined' &&
    typeof navigator.mediaDevices?.getUserMedia === 'function' &&
    typeof MediaRecorder !== 'undefined';

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
  const currentTurnId = useRef<string | null>(null);
  const submittedTurns = useRef<Set<string>>(new Set());
  const finalized = useRef(false);
  const lastTranscriptText = useRef('');

  const timingMetrics = useRef<SpeechTimingMetrics>({});
  const speechStartTime = useRef<number | null>(null);
  const speechEndTime = useRef<number | null>(null);
  const finalizeStartTime = useRef<number | null>(null);

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
      socket.current.onerror = null;
      socket.current.close();
      socket.current = null;
    }
    worklet.current?.disconnect();
    worklet.current = null;
    void context.current?.close().catch(() => {});
    context.current = null;
    if (stream.current) {
      stream.current.getTracks().forEach(track => {
        track.onended = null;
        track.stop();
      });
      stream.current = null;
    }
  }, []);

  const finish = useCallback((keepListening: boolean, discard = false) => {
    if (finalized.current) return;
    finalized.current = true;
    finalizeStartTime.current = performance.now();
    if (speechEndTime.current && !timingMetrics.current.speechEndToFinalizeMs) {
      timingMetrics.current.speechEndToFinalizeMs = Math.round(performance.now() - speechEndTime.current);
    }
    armed.current = keepListening;
    setArmed(keepListening);
    cancelled.current = discard;
    if (restartTimer.current) clearTimeout(restartTimer.current);

    if (recorder.current && recorder.current.state === 'recording') {
      try {
        recorder.current.stop();
      } catch {
        cleanup();
      }
    } else {
      cleanup();
    }
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
    finalized.current = false;
    lastTranscriptText.current = '';

    // Stop any dangling tracks before re-acquiring
    if (stream.current) {
      stream.current.getTracks().forEach(track => track.stop());
      stream.current = null;
    }

    const turnId = crypto.randomUUID();
    currentTurnId.current = turnId;
    const micActivationStart = performance.now();
    timingMetrics.current = {};
    speechStartTime.current = null;
    speechEndTime.current = null;
    finalizeStartTime.current = null;
    let began = 0;
    let lastSpeech = Date.now();
    let heardSpeech = false;
    let vadAvailable = false;

    try {
      const media = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      if (!armed.current || latest.current.disabled) {
        media.getTracks().forEach(track => track.stop());
        return;
      }

      // Handle physical disconnection of the microphone
      media.getAudioTracks().forEach(track => {
        track.onended = () => {
          setError('Your microphone disconnected. Please reconnect it.');
          finish(false, true);
        };
      });

      stream.current = media;
      setPermission('granted');

      const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find(value => MediaRecorder.isTypeSupported(value));
      const capture = new MediaRecorder(media, mime ? { mimeType: mime } : undefined);
      recorder.current = capture;
      const chunks: Blob[] = [];

      capture.ondataavailable = event => {
        if (event.data && event.data.size > 0) chunks.push(event.data);
      };

      capture.onstop = async () => {
        const elapsed = Date.now() - began;
        const discard = cancelled.current;
        if (finalizeStartTime.current) {
          timingMetrics.current.finalizeToSubmissionMs = Math.round(performance.now() - finalizeStartTime.current);
        }
        latest.current.onTimingMetrics?.({ ...timingMetrics.current });
        cleanup();
        setRecording(false);
        setDuration(0);

        if (discard || !chunks.length || (vadAvailable && !heardSpeech) || elapsed < MIN_SPEECH_DURATION_MS) {
          latest.current.onLiveTranscript?.({ turnId, text: '', cancelled: true });
        } else {
          if (!submittedTurns.current.has(turnId)) {
            submittedTurns.current.add(turnId);
            if (submittedTurns.current.size > 50) {
              const oldest = submittedTurns.current.values().next().value;
              if (oldest) submittedTurns.current.delete(oldest);
            }
            latest.current.onLiveTranscript?.({
              turnId,
              text: lastTranscriptText.current,
              isFinal: true,
            });
            const finalBlob = new Blob(chunks, { type: capture.mimeType || 'audio/webm' });
            await latest.current.onAudioCaptured(finalBlob, elapsed, turnId);
          }
        }
        if (armed.current && !latest.current.disabled) scheduleRestart();
      };

      capture.start(250);
      timingMetrics.current.micActivationMs = Math.round(performance.now() - micActivationStart);
      began = Date.now();
      lastSpeech = began;
      setRecording(true);
      latest.current.onLiveTranscript?.({ turnId, text: '', isFinal: false });
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
          node.connect(audioContext.destination);
          await audioContext.resume();

          const ws = new WebSocket(previewUrl());
          socket.current = ws;

          node.port.onmessage = event => {
            if (ws.readyState === WebSocket.OPEN && ws.bufferedAmount < 65536) {
              ws.send(event.data);
            } else if (ws.bufferedAmount >= 65536) {
              setPreviewStatus('Preview is behind; final transcript will follow submission');
              ws.close();
            }
          };

          ws.onmessage = event => {
            if (capture.state !== 'recording') return;
            try {
              const data = JSON.parse(event.data);
              if (data.type === 'ready') {
                vadAvailable = true;
                setPreviewStatus('Live local transcription · pause to send');
              } else if (data.type === 'vad' && data.speech) {
                heardSpeech = true;
                lastSpeech = Date.now();
                if (!speechStartTime.current) {
                  speechStartTime.current = performance.now();
                }
                speechEndTime.current = performance.now();
              } else if (data.type === 'transcript.partial') {
                if (speechStartTime.current && !timingMetrics.current.speechStartToPreviewMs) {
                  timingMetrics.current.speechStartToPreviewMs = Math.round(performance.now() - speechStartTime.current);
                }
                lastTranscriptText.current = data.text;
                latest.current.onLiveTranscript?.({ turnId, text: data.text, isFinal: false });
              } else if (data.type === 'limit') {
                finish(false);
              } else if (data.type === 'unavailable') {
                setPreviewStatus(data.message);
              }
            } catch {
              // Ignore non-JSON preview frames
            }
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
        if (vadAvailable && now - lastSpeech >= IDLE_TIMEOUT_MS) {
          setPreviewStatus('Microphone stopped after silence');
          finish(false, !heardSpeech);
        } else if (vadAvailable && heardSpeech && now - lastSpeech >= PAUSE_TO_SUBMIT_MS) {
          finish(false);
        } else if (now - began >= MAX_RECORDING_DURATION_MS) {
          finish(false);
        }
      }, 200);

    } catch (error) {
      cleanup();
      armed.current = false;
      setArmed(false);
      setRecording(false);

      if (error instanceof DOMException) {
        if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
          setPermission('denied');
          setError('Microphone access was denied. Allow microphone access in your browser settings and try again.');
        } else if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
          setPermission('unsupported');
          setError('No microphone was detected. Connect a microphone and retry.');
        } else if (error.name === 'NotReadableError' || error.name === 'TrackStartError') {
          setError('Microphone is currently unavailable or in use by another application.');
        } else if (error.name === 'OverconstrainedError') {
          setError('Microphone does not satisfy required audio constraints.');
        } else {
          setError(`Microphone error: ${error.message}`);
        }
      } else {
        setError(error instanceof Error ? error.message : 'Microphone could not start.');
      }
    } finally {
      starting.current = false;
    }
  }, [cleanup, finish, scheduleRestart]);

  useEffect(() => { startRef.current = start; }, [start]);

  useEffect(() => {
    if (options.disabled && recorder.current?.state === 'recording') {
      finish(false, true);
    } else if (!options.disabled && armed.current) {
      scheduleRestart();
    }
  }, [options.disabled, finish, scheduleRestart]);

  useEffect(() => () => {
    armed.current = false;
    cancelled.current = true;
    if (restartTimer.current) clearTimeout(restartTimer.current);
    if (recorder.current?.state === 'recording') recorder.current.stop();
    cleanup();
  }, [cleanup]);

  return {
    isRecording,
    isArmed,
    duration,
    permissionState,
    errorMessage,
    previewStatus,
    startRecording: start,
    stopRecording: () => finish(false),
    cancelRecording: () => finish(false, true),
    clearError: () => setError(null),
  };
}
