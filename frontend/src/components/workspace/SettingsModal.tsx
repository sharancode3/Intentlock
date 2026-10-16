import React, { useEffect, useRef } from 'react';
import { X, Sun, Moon, Laptop, Volume2, VolumeX, Eye, Info, Columns, MessageSquare } from 'lucide-react';
import type { WorkspaceSettings, ThemeMode, TextSize, ViewMode } from '../../types';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  settings: WorkspaceSettings;
  onUpdateSettings: (newValues: Partial<WorkspaceSettings>) => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  settings,
  onUpdateSettings,
}) => {
  const dialogRef = useRef<HTMLDivElement | null>(null);

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    if (isOpen) {
      window.addEventListener('keydown', handleKeyDown);
    }
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-none transition-opacity"
      role="dialog"
      aria-modal="true"
      aria-labelledby="settings-dialog-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        className="w-full max-w-md bg-white dark:bg-slate-900 rounded-flat-lg border border-surface-border dark:border-surface-darkBorder p-5 sm:p-6 shadow-none flex flex-col gap-5 transition-colors"
      >
        {/* Header */}
        <div className="flex items-center justify-between pb-3 border-b border-surface-border dark:border-surface-darkBorder">
          <div>
            <h2 id="settings-dialog-title" className="text-base font-bold text-ink-primary dark:text-white">
              Workspace Preferences
            </h2>
            <p className="text-xs text-ink-muted dark:text-slate-400">
              Client-side presentation and accessibility settings
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-flat text-slate-400 hover:text-ink-primary dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors focus:outline-none focus:ring-2 focus:ring-brand-700"
            aria-label="Close settings"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Setting 1: Theme Mode */}
        <div className="flex flex-col gap-2">
          <label className="text-xs font-semibold uppercase tracking-wider text-ink-secondary dark:text-slate-300">
            Interface Theme
          </label>
          <div className="grid grid-cols-3 gap-2">
            {[
              { id: 'light', label: 'Light', icon: Sun },
              { id: 'dark', label: 'Dark', icon: Moon },
              { id: 'system', label: 'System', icon: Laptop },
            ].map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                onClick={() => onUpdateSettings({ theme: id as ThemeMode })}
                className={`py-2 px-3 rounded-flat border text-xs font-medium flex items-center justify-center gap-1.5 transition-colors min-h-[40px] focus:outline-none focus:ring-2 focus:ring-brand-700 ${
                  settings.theme === id
                    ? 'bg-brand-700 text-white border-brand-800'
                    : 'bg-surface-card dark:bg-slate-800 text-ink-primary dark:text-slate-200 border-surface-border dark:border-surface-darkBorder hover:bg-slate-100 dark:hover:bg-slate-700'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Setting 2: Text Size */}
        <div className="flex flex-col gap-2">
          <label className="text-xs font-semibold uppercase tracking-wider text-ink-secondary dark:text-slate-300">
            Text Size Scale
          </label>
          <div className="grid grid-cols-3 gap-2">
            {[
              { id: 'sm', label: 'Compact (14px)' },
              { id: 'md', label: 'Standard (16px)' },
              { id: 'lg', label: 'Large (18px)' },
            ].map(({ id, label }) => (
              <button
                key={id}
                type="button"
                onClick={() => onUpdateSettings({ textSize: id as TextSize })}
                className={`py-2 px-3 rounded-flat border text-xs font-medium text-center transition-colors min-h-[40px] focus:outline-none focus:ring-2 focus:ring-brand-700 ${
                  settings.textSize === id
                    ? 'bg-brand-700 text-white border-brand-800'
                    : 'bg-surface-card dark:bg-slate-800 text-ink-primary dark:text-slate-200 border-surface-border dark:border-surface-darkBorder hover:bg-slate-100 dark:hover:bg-slate-700'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Setting 2.5: Workspace Layout */}
        <div className="flex flex-col gap-2">
          <label className="text-xs font-semibold uppercase tracking-wider text-ink-secondary dark:text-slate-300">
            Workspace Layout
          </label>
          <div className="grid grid-cols-2 gap-2">
            {[
              { id: 'split', label: 'Split Dual-Pane', icon: Columns, desc: 'Chat + Right Inspector' },
              { id: 'feed', label: 'Unified Feed', icon: MessageSquare, desc: 'Cards inline in Chat' },
            ].map(({ id, label, icon: Icon, desc }) => (
              <button
                key={id}
                type="button"
                onClick={() => onUpdateSettings({ viewMode: id as ViewMode })}
                className={`py-2 px-3 rounded-flat border text-xs font-medium flex flex-col items-start gap-1 transition-colors min-h-[48px] focus:outline-none focus:ring-2 focus:ring-brand-700 ${
                  settings.viewMode === id
                    ? 'bg-brand-700 text-white border-brand-800'
                    : 'bg-surface-card dark:bg-slate-800 text-ink-primary dark:text-slate-200 border-surface-border dark:border-surface-darkBorder hover:bg-slate-100 dark:hover:bg-slate-700'
                }`}
              >
                <div className="flex items-center gap-1.5 font-semibold">
                  <Icon className="w-3.5 h-3.5" />
                  <span>{label}</span>
                </div>
                <span className={`text-[10px] ${settings.viewMode === id ? 'text-blue-100' : 'text-ink-muted dark:text-slate-400'}`}>
                  {desc}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Setting 3: Reduced Motion */}
        <div className="flex items-center justify-between p-3 rounded-flat border border-surface-border dark:border-surface-darkBorder bg-surface-card dark:bg-slate-800/60">
          <div className="flex items-start gap-2.5">
            <Eye className="w-4 h-4 text-brand-700 dark:text-blue-400 mt-0.5" />
            <div>
              <span className="text-xs font-semibold text-ink-primary dark:text-white block">
                Reduced Motion
              </span>
              <span className="text-[11px] text-ink-muted dark:text-slate-400">
                Disables animated waveform pulses and smooth scroll
              </span>
            </div>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={settings.reducedMotion}
            onClick={() => onUpdateSettings({ reducedMotion: !settings.reducedMotion })}
            className={`w-10 h-6 rounded-full p-0.5 transition-colors focus:outline-none focus:ring-2 focus:ring-brand-700 ${
              settings.reducedMotion ? 'bg-brand-700' : 'bg-slate-300 dark:bg-slate-600'
            }`}
          >
            <div
              className={`w-5 h-5 rounded-full bg-white transition-transform ${
                settings.reducedMotion ? 'translate-x-4' : 'translate-x-0'
              }`}
            />
          </button>
        </div>

        {/* Setting 4: Voice Playback Preferences */}
        <div className="flex flex-col gap-2.5 p-3 rounded-flat border border-surface-border dark:border-surface-darkBorder bg-surface-card dark:bg-slate-800/60">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {settings.voicePlaybackEnabled ? (
                <Volume2 className="w-4 h-4 text-brand-700 dark:text-blue-400" />
              ) : (
                <VolumeX className="w-4 h-4 text-slate-400" />
              )}
              <span className="text-xs font-semibold text-ink-primary dark:text-white">
                Audio Response Playback
              </span>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={settings.voicePlaybackEnabled}
              onClick={() => onUpdateSettings({ voicePlaybackEnabled: !settings.voicePlaybackEnabled })}
              className={`w-10 h-6 rounded-full p-0.5 transition-colors focus:outline-none focus:ring-2 focus:ring-brand-700 ${
                settings.voicePlaybackEnabled ? 'bg-brand-700' : 'bg-slate-300 dark:bg-slate-600'
              }`}
            >
              <div
                className={`w-5 h-5 rounded-full bg-white transition-transform ${
                  settings.voicePlaybackEnabled ? 'translate-x-4' : 'translate-x-0'
                }`}
              />
            </button>
          </div>

          {settings.voicePlaybackEnabled && (
            <div className="flex flex-col gap-1 pt-1">
              <div className="flex justify-between text-[11px] text-ink-muted dark:text-slate-400">
                <span>Playback Volume</span>
                <span className="font-mono">{Math.round(settings.voiceVolume * 100)}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={settings.voiceVolume}
                onChange={(e) => onUpdateSettings({ voiceVolume: parseFloat(e.target.value) })}
                className="w-full h-1.5 bg-slate-200 dark:bg-slate-700 rounded-lg appearance-none cursor-pointer accent-brand-700"
                aria-label="Voice volume level"
              />
            </div>
          )}

          <div className="text-[10px] text-ink-muted dark:text-slate-500 flex items-center gap-1 mt-1">
            <Info className="w-3 h-3 text-slate-400 shrink-0" />
            <span>Client preference only &bull; Does NOT alter server TTS generation or identity permissions</span>
          </div>
        </div>

        {/* Footer / Done Button */}
        <div className="pt-2 border-t border-surface-border dark:border-surface-darkBorder flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-flat bg-slate-800 hover:bg-slate-900 dark:bg-slate-700 dark:hover:bg-slate-600 text-white text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-brand-700"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};
