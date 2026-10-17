export const API_BASE = (typeof import.meta !== 'undefined' && import.meta?.env?.VITE_API_BASE_URL) || '';

export function previewUrl() {
  const origin = typeof window !== 'undefined' && window.location?.origin ? window.location.origin : 'http://localhost:5173';
  const url = new URL(`${API_BASE}/api/v1/voice/preview`, origin);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}

export interface LiveTranscript {
  turnId: string;
  text: string;
  isFinal?: boolean;
  cancelled?: boolean;
}

