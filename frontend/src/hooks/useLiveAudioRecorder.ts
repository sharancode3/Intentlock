import { useCallback, useEffect, useRef, useState } from 'react';
import { previewUrl } from '../utils/voiceClient';
import type { LiveTranscript } from '../utils/voiceClient';
import type { PermissionState } from './useAudioRecorder';
import type { SpeechTimingMetrics } from '../types';
import { TurnDetector } from '../utils/turnDetector';

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
  const submitting = useRef(false);
  const generation = useRef(0);
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
    if (worklet.current) {
      worklet.current.port.onmessage = null;
      worklet.current.port.close();
      worklet.current.disconnect();
    }
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
    if (finalized.current) {
      // Stop Listening must also work while waiting for a response or acquiring the mic.
      if (!keepListening) {
        armed.current = false;
        setArmed(false);
        if (restartTimer.current) clearTimeout(restartTimer.current);
      }
      return;
    }
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
    if (starting.current || submitting.current || recorder.current?.state === 'recording' || latest.current.disabled) return;
    starting.current = true;
    const captureGeneration = ++generation.current;
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
    let detector: TurnDetector;
    let activityAvailable = false;
    const markSpeech = () => {
      detector.markSpeech(Date.now());
      speechStartTime.current ??= performance.now();
      speechEndTime.current = performance.now();
    };

    try {
      const media = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      if (!armed.current || latest.current.disabled || captureGeneration !== generation.current) {
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
      let stopHandled = false;

      capture.ondataavailable = event => {
        if (event.data && event.data.size > 0) chunks.push(event.data);
      };

      capture.onstop = async () => {
        if (stopHandled || captureGeneration !== generation.current) return;
        stopHandled = true;
        submitting.current = true;
        const elapsed = Date.now() - began;
        const discard = cancelled.current;
        if (finalizeStartTime.current) {
          timingMetrics.current.finalizeToSubmissionMs = Math.round(performance.now() - finalizeStartTime.current);
        }
        latest.current.onTimingMetrics?.({ ...timingMetrics.current });
        cleanup();
        setRecording(false);
        setDuration(0);

        try {
        if (discard || !chunks.length || (activityAvailable && !detector.heardSpeech) || elapsed < MIN_SPEECH_DURATION_MS) {
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
        } catch {
          // Do not resubmit an uncertain HTTP result: its turn ID remains consumed.
          setError('The voice turn could not finish. Please try a new request.');
          armed.current = false;
          setArmed(false);
        } finally {
          submitting.current = false;
        }
        if (armed.current && !latest.current.disabled) scheduleRestart();
      };

      capture.start(250);
      timingMetrics.current.micActivationMs = Math.round(performance.now() - micActivationStart);
      began = Date.now();
      detector = new TurnDetector(began);
      setRecording(true);
      latest.current.onLiveTranscript?.({ turnId, text: '', isFinal: false });
      setPreviewStatus('Listening · pause to send · connecting transcript…');

      let clientAnalyser: AnalyserNode | null = null;
      let clientDataArray: Float32Array<ArrayBuffer> | null = null;

      try {
        const audioCtx = context.current || new AudioContext();
        context.current = audioCtx;
        const source = audioCtx.createMediaStreamSource(media);
        clientAnalyser = audioCtx.createAnalyser();
        clientAnalyser.fftSize = 2048;
        source.connect(clientAnalyser);
        clientDataArray = new Float32Array(clientAnalyser.fftSize);
        await audioCtx.resume();
        activityAvailable = true;
      } catch {
        // Fallback gracefully if Web Audio Analyser cannot be created
      }

      if (capture.state !== 'recording' || captureGeneration !== generation.current) return;

      // Start timing before any network/worklet setup. Preview outages cannot disable VAD.
      timer.current = setInterval(() => {
        if (finalized.current) return;
        const now = Date.now();
        setDuration(Math.floor((now - began) / 1000));
        if (clientAnalyser && clientDataArray) {
          clientAnalyser.getFloatTimeDomainData(clientDataArray);
          let sum = 0;
          for (const sample of clientDataArray) sum += sample * sample;
          if (detector.sample(Math.sqrt(sum / clientDataArray.length), now)) markSpeech();
        }
        const decision = detector.decision(now);
        if (decision === 'idle') {
          setPreviewStatus('Microphone stopped after silence');
          finish(false, true);
        } else if (decision === 'submit') {
          finish(true);
        } else if (decision === 'limit') {
          finish(true, activityAvailable && !detector.heardSpeech);
        }
      }, 50);

      if (latest.current.previewEnabled !== false) {
        try {
          const audioContext = context.current || new AudioContext();
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
          const pending: ArrayBuffer[] = [];
          let ready = false;
          const flushPreview = () => {
            if (!ready || ws.readyState !== WebSocket.OPEN) return;
            for (const frame of pending.splice(0)) {
              if (ws.bufferedAmount >= 262144) { ws.close(); return; }
              ws.send(frame);
            }
          };
          const previewTimeout = setTimeout(() => {
            if (!ready) ws.close();
          }, 8000);
          ws.addEventListener('close', () => clearTimeout(previewTimeout), { once: true });

          node.port.onmessage = event => {
            if (activityAvailable && !detector.heardSpeech) {
              // Keep only half a second of pre-roll; do not send idle silence to cloud ASR.
              pending.push(event.data);
              if (pending.length > 8) pending.shift();
              return;
            }
            if (!ready && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
              // Preserve the beginning while the provider connects; bound to eight seconds.
              if (pending.length < 125) pending.push(event.data);
              else ws.close();
            } else if (ready && ws.readyState === WebSocket.OPEN && ws.bufferedAmount < 65536) {
              flushPreview();
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
                ready = true;
                clearTimeout(previewTimeout);
                if (detector.heardSpeech || !activityAvailable) flushPreview();
                setPreviewStatus('Live transcription · pause to send');
              } else if (data.type === 'vad' && data.speech) {
                activityAvailable = true;
                markSpeech();
              } else if (data.type === 'transcript.partial') {
                if (speechStartTime.current && !timingMetrics.current.speechStartToPreviewMs) {
                  timingMetrics.current.speechStartToPreviewMs = Math.round(performance.now() - speechStartTime.current);
                }
                lastTranscriptText.current = data.text;
                latest.current.onLiveTranscript?.({ turnId, text: data.text, isFinal: false });
              } else if (data.type === 'limit') {
                finish(true);
              } else if (data.type === 'unavailable') {
                setPreviewStatus(data.message);
              }
            } catch {
              // Ignore non-JSON preview frames
            }
          };

          ws.onclose = () => {
            pending.length = 0;
            if (!finalized.current) setPreviewStatus('Listening · pause to send · final transcript after submission');
          };
          ws.onerror = () => setPreviewStatus('Listening · pause to send · live transcript unavailable');
        } catch {
          setPreviewStatus('Listening · pause to send · live transcript unavailable');
        }
      }

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
      finish(armed.current, true);
    } else if (!options.disabled && armed.current) {
      scheduleRestart();
    }
  }, [options.disabled, finish, scheduleRestart]);

  useEffect(() => () => {
    generation.current += 1;
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
