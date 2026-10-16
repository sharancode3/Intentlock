import React from 'react';
import { Mic, Square, X, AlertCircle } from 'lucide-react';
import { useLiveAudioRecorder } from '../../hooks/useLiveAudioRecorder';
import type { LiveTranscript } from '../../utils/voiceClient';

interface MicDockProps {
  onAudioCaptured: (audioBlob: Blob, durationMs: number, turnId?: string) => void | Promise<void>;
  onLiveTranscript?: (event: LiveTranscript) => void;
  previewEnabled?: boolean;
  onTextSubmitted?: (text: string) => void;
  disabled?: boolean;
  disabledReason?: string;
  className?: string;
}

export const MicDock: React.FC<MicDockProps> = ({
  onAudioCaptured,
  onTextSubmitted,
  onLiveTranscript, previewEnabled = true,
  disabled = false,
  disabledReason,
  className = '',
}) => {
  const [typedInput, setTypedInput] = React.useState('');

  const {
    isRecording,
    isArmed,
    previewStatus,
    duration,
    permissionState,
    errorMessage,
    startRecording,
    stopRecording,
    cancelRecording,
    clearError,
  } = useLiveAudioRecorder({
    onAudioCaptured,
    onLiveTranscript, previewEnabled, disabled,
  });

  const minutes = Math.floor(duration / 60);
  const seconds = duration % 60;
  const formattedTime = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;

  return (
    <div className={`w-full bg-white dark:bg-surface-darkBg border-t border-surface-border dark:border-surface-darkBorder p-3 sm:p-4 shrink-0 transition-colors ${className}`}>
      <div className="max-w-2xl mx-auto flex flex-col items-center gap-2">
        {/* Permission / Capture Error Alert */}
        {errorMessage && (
          <div className="w-full mb-1 p-2.5 rounded-flat bg-state-dangerBg border border-state-dangerBorder text-state-danger text-xs sm:text-sm flex items-start justify-between gap-2">
            <div className="flex items-start gap-2">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{errorMessage}</span>
            </div>
            <button
              type="button"
              onClick={clearError}
              className="text-xs font-semibold underline shrink-0 hover:opacity-80"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Active Recording State: Waveform Bars + Timer + Stop / Cancel Actions */}
        {isRecording ? (
          <div className="w-full flex items-center justify-between gap-3 p-3 rounded-flat bg-brand-50 dark:bg-blue-950/40 border border-brand-200 dark:border-blue-800 animate-pulse-subtle">
            {/* Visual Waveform bars (CSS driven, zero heavy dependencies) */}
            <div className="flex items-center gap-1.5 pl-2" aria-hidden="true">
              <span className="w-1.5 bg-brand-700 dark:bg-blue-400 rounded-full animate-wave-bar" style={{ animationDelay: '0.0s' }} />
              <span className="w-1.5 bg-brand-700 dark:bg-blue-400 rounded-full animate-wave-bar" style={{ animationDelay: '0.2s' }} />
              <span className="w-1.5 bg-brand-700 dark:bg-blue-400 rounded-full animate-wave-bar" style={{ animationDelay: '0.4s' }} />
              <span className="w-1.5 bg-brand-700 dark:bg-blue-400 rounded-full animate-wave-bar" style={{ animationDelay: '0.1s' }} />
              <span className="w-1.5 bg-brand-700 dark:bg-blue-400 rounded-full animate-wave-bar" style={{ animationDelay: '0.3s' }} />
            </div>

            {/* Recording Timer & Label */}
            <div className="flex flex-col items-center">
              <span className="text-xs font-medium text-brand-900 dark:text-blue-200">
                Listening · pause to send
              </span>
              <span className="font-mono text-sm font-bold text-brand-700 dark:text-blue-400">
                {formattedTime}
              </span>
            </div>

            {/* Stop & Cancel Controls */}
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={cancelRecording}
                className="p-2 rounded-flat text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-white border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors text-xs font-medium flex items-center gap-1 min-h-[40px] focus:outline-none focus:ring-2 focus:ring-slate-400"
                aria-label="Cancel recording"
              >
                <X className="w-4 h-4" />
                <span className="hidden sm:inline">Cancel</span>
              </button>

              <button
                type="button"
                onClick={stopRecording}
                className="px-3.5 py-2 rounded-flat bg-state-danger hover:bg-red-700 text-white text-xs sm:text-sm font-semibold flex items-center gap-1.5 transition-colors shadow-none focus:outline-none focus:ring-2 focus:ring-red-500 min-h-[40px]"
                aria-label="Finish speaking and submit"
              >
                <Square className="w-4 h-4 fill-white" />
                <span>Done</span>
              </button>
            </div>
          </div>
        ) : (
          /* Idle Action: Prominent High-Contrast Primary Mic Button */
          <div className="w-full flex flex-col items-center gap-2">
            <button
              type="button"
              disabled={disabled || permissionState === 'unsupported'}
              onClick={() => { if (isArmed) cancelRecording(); else void startRecording(); }}
              className={`w-full sm:w-auto px-6 py-2.5 rounded-flat-lg font-semibold text-sm sm:text-base flex items-center justify-center gap-2.5 transition-all shadow-none min-h-[46px] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-brand-700 ${
                disabled || permissionState === 'unsupported'
                  ? 'bg-slate-100 text-slate-400 border border-slate-200 cursor-not-allowed dark:bg-slate-800 dark:text-slate-500 dark:border-slate-700'
                  : 'bg-brand-700 hover:bg-brand-800 active:bg-brand-900 text-white border border-brand-800'
              }`}
              aria-label={disabled ? disabledReason || 'Microphone unavailable' : 'Tap to speak into kiosk microphone'}
            >
              <Mic className="w-5 h-5 shrink-0" aria-hidden="true" />
              <span>{disabled ? disabledReason || 'Microphone Unavailable' : isArmed ? 'Stop Listening' : 'Start Conversation'}</span>
            </button>

            {/* Typed Test Input Fallback */}
            {onTextSubmitted && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (typedInput.trim()) {
                    onTextSubmitted(typedInput.trim());
                    setTypedInput('');
                  }
                }}
                className="w-full flex items-center gap-2 max-w-xl"
              >
                <input
                  type="text"
                  value={typedInput}
                  onChange={(e) => setTypedInput(e.target.value)}
                  placeholder="Typed test input (e.g. 'Who is Aarav Mehta?' or 'Show my direct reports')..."
                  className="flex-1 px-3 py-1.5 text-xs bg-slate-50 dark:bg-slate-900 border border-surface-border dark:border-surface-darkBorder rounded-flat text-ink-primary dark:text-white placeholder:text-ink-muted dark:placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-brand-700"
                />
                <button
                  type="submit"
                  disabled={!typedInput.trim()}
                  className="px-3 py-1.5 text-xs font-semibold rounded-flat bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-ink-primary dark:text-slate-200 border border-slate-300 dark:border-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
                >
                  Send (Typed Test)
                </button>
              </form>
            )}

            <span className="text-[11px] text-ink-muted dark:text-slate-400 tracking-tight text-center">
              {previewStatus || 'Start once to converse. A short pause sends your question; 20 seconds of silence stops the microphone.'}
            </span>
          </div>
        )}
      </div>
    </div>
  );
};
