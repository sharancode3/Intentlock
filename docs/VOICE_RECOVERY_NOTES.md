# Voice recovery: local changes and deployment requirements

Changes preserve the workspace layout and existing authorization/executor boundaries.

## Implemented

- Browser activity detection runs independently of the preview socket. A 1.4-second pause sends once, a valid conversation resumes after processing/playback, and 20 seconds without speech discards the recording.
- Cloud speech preview uses one bounded OpenAI transcription stream per utterance. It sends no Detectif requests, avoids transmitting idle silence, and keeps preview text separate from the final original recording.
- Local Silero/Faster-Whisper/Kokoro remain available; cloud imports no longer load their inference runtimes. WebM and MP4 decoding uses PyAV directly.
- Policy selects exactly one Detectif mode/credential. Valid-session reads and presentation reuse need no extra biometric calls. Protected confirmation still requires fresh combined evidence.
- Speaker-only and authenticity-only diagnostics cannot create an employee session.
- Enrollment metadata is checked with the selected verification credential. Definite missing enrollment blocks paid upload; verification-only keys without metadata scope can still verify. Known account/enrollment failures are briefly cached, never retried with another key.
- Official nested results, actual charges and zero-charge replays are parsed. Missing billing data stays unknown. Combined partial failure does not authenticate.
- Concurrent duplicate turns coalesce; failure releases waiters; cached responses are bounded and session validity is rechecked.

## Before deploying

1. Configure `DETECTIF_SPEAKER_API_KEY`, `DETECTIF_DEEPFAKE_API_KEY` and `DETECTIF_COMBINED_API_KEY` on Render using fresh credentials from the account containing the enrolled speakers. Set `DETECTIF_LEGACY_KEY_FALLBACK=0`. Never put these in Vercel/browser variables.
2. Confirm each employee mapping belongs to that same account and references its exact enrolled speaker ID. Do not invent enrollments or infer identity from names. Earlier checks found a test mapping for EMP-1001; recheck that row before repair.
3. Set Render `FRONTEND_ORIGINS` to an explicit JSON list containing `https://intentlock-blue.vercel.app` and any other actual frontend origins. `[*]` is not a WebSocket origin allowlist. The blueprint now contains explicit origins.
4. Keep `SPEECH_PROVIDER=openai`, `ENABLE_CLOUD_PREVIEW=true`, `OPENAI_PREVIEW_MODEL=gpt-live-transcribe`, and the server-side OpenAI key. Preview uses OpenAI audio tokens, never Detectif credits. Model metadata access was verified without uploading audio.
5. Vercel `VITE_API_BASE_URL` must point directly to the real backend, currently `https://intentlock.onrender.com`. Rebuild the frontend after changing build variables. Its WebSocket preview must reach that backend directly.
6. Deploy backend and frontend together, then check microphone permission, live text, pause-to-send, genuine entry, authorized follow-up, failed verification, expiry and protected confirmation with the operator's approved audio and credit budget.

## Verification limits

Final offline backend run: **393 passed, 14 skipped**. Existing frontend contract suites, the real recorder hook regression, production frontend build, and whitespace checks passed. The skipped cases require real speech models or a live Supabase connection.

Normal regression tests use fake providers and isolated SQLite; they do not write to Supabase. No paid Detectif checks were run. The locally configured legacy credential returned an empty enrolled-speaker list; code cannot repair the wrong account credential. Changes have not been pushed or deployed. A physical microphone and real paid verification still require a deployment smoke test.
