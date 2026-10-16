export const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

export function previewUrl() {
  const url = new URL(`${API_BASE}/api/v1/voice/preview`, window.location.origin);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}

export interface LiveTranscript {
  turnId: string;
  text: string;
  cancelled?: boolean;
}
