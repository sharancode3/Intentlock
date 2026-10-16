import { useState, useRef, useCallback, useEffect } from 'react';

export type PermissionState = 'prompt' | 'granted' | 'denied' | 'unsupported';

interface AudioRecorderOptions {
  onAudioCaptured?: (blob: Blob, durationMs: number) => void;
  maxDurationSeconds?: number;
}

export function useAudioRecorder({
  onAudioCaptured,
  maxDurationSeconds = 180, // 3 minutes ceiling for continuous speech & VAD
}: AudioRecorderOptions = {}) {
  // Check browser audio support during state initialization
  const isSupported = typeof navigator !== 'undefined' && Boolean(navigator.mediaDevices?.getUserMedia);

  const [isRecording, setIsRecording] = useState(false);
  const [duration, setDuration] = useState(0);
  const [permissionState, setPermissionState] = useState<PermissionState>(
    isSupported ? 'prompt' : 'unsupported'
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(
    isSupported ? null : 'Microphone input is not supported in this browser.'
  );

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioStreamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);
  const startTimeRef = useRef<number>(0);
  const isCancelledRef = useRef<boolean>(false);

  const cleanupTracks = useCallback(() => {
    if (audioStreamRef.current) {
      audioStreamRef.current.getTracks().forEach((track) => track.stop());
      audioStreamRef.current = null;
    }
  }, []);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const stopRecording = useCallback(() => {
    clearTimer();
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
  }, [clearTimer]);

  const cancelRecording = useCallback(() => {
    isCancelledRef.current = true;
    stopRecording();
    setDuration(0);
  }, [stopRecording]);

  const startRecording = useCallback(async () => {
    setErrorMessage(null);
    isCancelledRef.current = false;
    chunksRef.current = [];

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setErrorMessage('Microphone capture is unavailable on this device.');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      audioStreamRef.current = stream;
      setPermissionState('granted');

      // Determine supported MIME type for highest fidelity
      let mimeType = 'audio/webm;codecs=opus';
      if (!MediaRecorder.isTypeSupported(mimeType)) {
        if (MediaRecorder.isTypeSupported('audio/webm')) {
          mimeType = 'audio/webm';
        } else if (MediaRecorder.isTypeSupported('audio/mp4')) {
          mimeType = 'audio/mp4';
        } else {
          mimeType = ''; // Let browser default
        }
      }

      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onstop = () => {
        cleanupTracks();
        const elapsedMs = Date.now() - startTimeRef.current;

        if (!isCancelledRef.current && chunksRef.current.length > 0) {
          const finalBlob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
          if (onAudioCaptured) {
            onAudioCaptured(finalBlob, elapsedMs);
          }
        }
        chunksRef.current = [];
        setDuration(0);
      };

      recorder.start(250); // Slice in 250ms chunks
      startTimeRef.current = Date.now();
      setIsRecording(true);
      setDuration(0);

      // Duration counter
      timerRef.current = window.setInterval(() => {
        const elapsedSec = Math.floor((Date.now() - startTimeRef.current) / 1000);
        setDuration(elapsedSec);

        // Auto-stop at max duration ceiling
        if (elapsedSec >= maxDurationSeconds) {
          stopRecording();
        }
      }, 500);

    } catch (err: unknown) {
      cleanupTracks();
      clearTimer();
      setIsRecording(false);

      if (err instanceof DOMException) {
        if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
          setPermissionState('denied');
          setErrorMessage('Microphone permission was denied. Please allow microphone access in your browser to speak.');
        } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
          setErrorMessage('No microphone device was detected on your machine.');
        } else {
          setErrorMessage(`Audio capture error: ${err.message}`);
        }
      } else {
        setErrorMessage('Unable to initialize audio recording.');
      }
    }
  }, [cleanupTracks, clearTimer, maxDurationSeconds, onAudioCaptured, stopRecording]);

  // Clean up on component unmount
  useEffect(() => {
    return () => {
      clearTimer();
      cleanupTracks();
    };
  }, [clearTimer, cleanupTracks]);

  return {
    isRecording,
    duration,
    permissionState,
    errorMessage,
    startRecording,
    stopRecording,
    cancelRecording,
    clearError: () => setErrorMessage(null),
  };
}
