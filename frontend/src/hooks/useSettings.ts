import { useState, useEffect, useCallback } from 'react';
import type { WorkspaceSettings, ThemeMode, TextSize, ViewMode } from '../types';

const STORAGE_KEY = 'intentlock_ui_preferences_v1';

const DEFAULT_SETTINGS: WorkspaceSettings = {
  theme: 'system',
  textSize: 'md',
  reducedMotion: false,
  voicePlaybackEnabled: true,
  voiceVolume: 0.8,
  viewMode: 'split',
};

export function useSettings() {
  const [settings, setSettings] = useState<WorkspaceSettings>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        return { ...DEFAULT_SETTINGS, ...parsed };
      }
    } catch {
      // Fallback to defaults if localStorage is restricted
    }
    return DEFAULT_SETTINGS;
  });

  // Apply Theme to DOM
  useEffect(() => {
    const root = document.documentElement;
    const isDark =
      settings.theme === 'dark' ||
      (settings.theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);

    if (isDark) {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
  }, [settings.theme]);

  // Apply Text Size to DOM
  useEffect(() => {
    document.documentElement.setAttribute('data-text-size', settings.textSize);
  }, [settings.textSize]);

  // Apply Reduced Motion to DOM
  useEffect(() => {
    if (settings.reducedMotion) {
      document.documentElement.classList.add('reduced-motion');
    } else {
      document.documentElement.classList.remove('reduced-motion');
    }
  }, [settings.reducedMotion]);

  const updateSettings = useCallback((newValues: Partial<WorkspaceSettings>) => {
    setSettings((prev) => {
      const updated = { ...prev, ...newValues };
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      } catch {
        // Silently ignore storage failures
      }
      return updated;
    });
  }, []);

  const setTheme = useCallback((theme: ThemeMode) => updateSettings({ theme }), [updateSettings]);
  const setTextSize = useCallback((textSize: TextSize) => updateSettings({ textSize }), [updateSettings]);
  const setReducedMotion = useCallback((reducedMotion: boolean) => updateSettings({ reducedMotion }), [updateSettings]);
  const setVoicePlayback = useCallback((voicePlaybackEnabled: boolean) => updateSettings({ voicePlaybackEnabled }), [updateSettings]);
  const setVoiceVolume = useCallback((voiceVolume: number) => updateSettings({ voiceVolume }), [updateSettings]);
  const setViewMode = useCallback((viewMode: ViewMode) => updateSettings({ viewMode }), [updateSettings]);

  return {
    settings,
    updateSettings,
    setTheme,
    setTextSize,
    setReducedMotion,
    setVoicePlayback,
    setVoiceVolume,
    setViewMode,
  };
}
