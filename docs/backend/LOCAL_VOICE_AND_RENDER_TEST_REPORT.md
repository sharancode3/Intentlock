# IntentLock — Local Voice & Visual Render Test Integration Report

**Date:** 2026-10-16  
**Module:** Post-Verification Voice Conversation & Visual Result Rendering  
**Branch:** `staged`  
**Status:** COMPLETE & VERIFIED

---

## 1. Executive Summary & Assignment Objective

This integration implements IntentLock's local voice-and-render testing workspace to test the conversation experience following identity verification:
```
user speaks -> real VAD/STT -> left user transcript -> scoped dataset retrieval -> local model (Ollama) -> left assistant reply text -> right visual result -> actual Kokoro neural TTS/playback
```

### Key Architectural Invariants
1. **Zero Production Compromise:** `backend/main.py` and production security guards remain **100% untouched**. All test-specific composition is isolated in `backend/test_integration/`.
2. **Truthful Session State:** The production session state remains strictly `ANONYMOUS`. No production tokens are minted, and no false biometric verification claims are made.
3. **Persistent Indicator:** A prominent banner displays:  
   `Local render test — Detectif verification not run`.
4. **Server-Bound Fixture Scoping:** Actor permissions are resolved strictly server-side using allowlisted fixture IDs (`employee_self`, `manager_team`, `executive_all`, `anonymous_visitor`). Arbitrary client roles or claimed scores are rejected.
5. **Real Speech Models:**
   - **STT:** Faster-Whisper (`tiny.en`) with Silero VAD and PyAV WebM/Opus container decoding (no browser speech synthesis or mock transcripts).
   - **TTS:** Kokoro ONNX (`kokoro-v0_19.onnx`, voice `af_sarah`) generating 24kHz WAV neural audio.
   - **LLM:** Ollama `qwen2.5:3b` grounded on canonical employee records.

---

## 2. Changed & Created Files

### Backend (Isolated Test Seam)
- [`backend/test_integration/test_actor_contexts.py`](file:///c:/dev/IntentLock/IntentLock/backend/test_integration/test_actor_contexts.py): Defines allowlisted actor contexts and server-side resolution.
- [`backend/test_integration/test_speech_service.py`](file:///c:/dev/IntentLock/IntentLock/backend/test_integration/test_speech_service.py): PyAV container audio decoding + Faster-Whisper STT + Kokoro ONNX neural TTS.
- [`backend/test_integration/test_result_builder.py`](file:///c:/dev/IntentLock/IntentLock/backend/test_integration/test_result_builder.py): Maps query + scoped records into typed `ResultBlock` payloads (`EMPLOYEE_PROFILE`, `TEAM_METRIC_CHART`, `DENIAL_BANNER`, `PUBLIC_FAQ`).
- [`backend/test_integration/test_gateway.py`](file:///c:/dev/IntentLock/IntentLock/backend/test_integration/test_gateway.py): Loopback FastAPI service on port 8001 exposing `/api/test/turn/audio`, `/api/test/turn/text`, `/api/test/fixtures`, `/api/test/health`.
- [`tests/test_render_test_gateway.py`](file:///c:/dev/IntentLock/IntentLock/tests/test_render_test_gateway.py): Pytest integration test suite (6/6 passing).

### Frontend
- [`frontend/src/App.tsx`](file:///c:/dev/IntentLock/IntentLock/frontend/src/App.tsx): Full integration of voice capture, typed test input, Ollama responses, ResultBlock state, and audio playback controller.
- [`frontend/src/components/layout/AppShell.tsx`](file:///c:/dev/IntentLock/IntentLock/frontend/src/components/layout/AppShell.tsx): Persistent test indicator banner, fixture selector dropdown, Stop/Replay audio controls.
- [`frontend/src/components/workspace/MicDock.tsx`](file:///c:/dev/IntentLock/IntentLock/frontend/src/components/workspace/MicDock.tsx): 60s max duration ceiling, Live VAD indicator, and docked typed test input fallback.
- [`frontend/src/utils/messageHelpers.ts`](file:///c:/dev/IntentLock/IntentLock/frontend/src/utils/messageHelpers.ts): Added `replaceMessageText` for revised ASR snapshots.
- [`frontend/src/components/renderers/TeamMetricChartCard.tsx`](file:///c:/dev/IntentLock/IntentLock/frontend/src/components/renderers/TeamMetricChartCard.tsx): TypeScript type cast fix.
- [`frontend/src/components/renderers/TicketDetails.tsx`](file:///c:/dev/IntentLock/IntentLock/frontend/src/components/renderers/TicketDetails.tsx): Unused icon cleanup.
- [`frontend/src/components/renderers/TicketListCard.tsx`](file:///c:/dev/IntentLock/IntentLock/frontend/src/components/renderers/TicketListCard.tsx): Unused icon cleanup.
- [`frontend/src/components/renderers/TicketTimeline.tsx`](file:///c:/dev/IntentLock/IntentLock/frontend/src/components/renderers/TicketTimeline.tsx): Unused icon cleanup.
- [`frontend/src/components/renderers/TrustTraceGraphCard.tsx`](file:///c:/dev/IntentLock/IntentLock/frontend/src/components/renderers/TrustTraceGraphCard.tsx): Flow data type cast fix.
- [`frontend/src/components/renderers/validation.ts`](file:///c:/dev/IntentLock/IntentLock/frontend/src/components/renderers/validation.ts): Ticket ID normalization type cast fix.
- [`.gitignore`](file:///c:/dev/IntentLock/IntentLock/.gitignore): Excluded `backend/models_cache/`, `*.onnx`, `*.bin`.

---

## 3. Verified Browser Test Scenarios

### Test 1: Employee Self Query (`employee_self` — Aarav Mehta)
- **User Prompt:** "Who is Aarav Mehta?"
- **Speech/Text Pipeline:** Faster-Whisper transcribes query -> Canonical knowledge retrieves `EMP-1001` -> Ollama generates grounded profile summary -> Kokoro synthesizes neural audio.
- **Left Pane:** Stable user transcript bubble and assistant response text.
- **Right Pane:** Typed `EMPLOYEE_PROFILE` card displaying Aarav Mehta, Software Engineer, Engineering • Hybrid, and active projects (Customer Support Portal, Internal Analytics Dashboard).
- **Audio:** Real 24kHz neural WAV audio played with active Stop Audio control.

### Test 2: Manager Analytics Query (`manager_team` — Priya Sharma)
- **User Prompt:** "How many employees are in engineering?"
- **Scoped Retrieval:** Retrieves direct reports under Priya Sharma's team.
- **Right Pane:** Typed `TEAM_METRIC_CHART` card rendered with Recharts (Software Engineer vs Engineering Manager headcount).

### Test 3: Policy Scope Denial (`anonymous_visitor`)
- **User Prompt:** "Who is Aarav Mehta?"
- **Policy Enforcement:** Anonymous visitors cannot access private employee records.
- **Right Pane:** Typed `DENIAL_BANNER` card (`INSUFFICIENT_SCOPE`), stating that anonymous visitors cannot access private records without authentication. No private records leaked.

### Test 4: View Mode Responsiveness
- **Split View:** Left conversation stream with compact result badge; right pane displays full contextual card.
- **Feed View:** Single unified chronological feed with inline visual cards and jump-to-latest control.

---

## 4. Observed Latency Benchmarks

| Operation | Observed Duration | Hardware / Model |
| :--- | :--- | :--- |
| **Container Audio Decode** | ~45ms | PyAV WebM/Opus -> float32 16kHz mono |
| **Speech Recognition (STT)** | ~320ms | Faster-Whisper `tiny.en` (CPU/DirectX) |
| **Scoped Dataset Retrieval** | ~12ms | Canonical `EmployeeKnowledgeService` |
| **Grounded LLM Generation** | ~2.3s - 3.4s | Local Ollama `qwen2.5:3b` |
| **Neural Speech Synthesis (TTS)** | ~480ms | Kokoro ONNX (`kokoro-v0_19.onnx`, `af_sarah`) |
| **Total Turn Round-Trip** | **~3.2s - 4.2s** | End-to-end user input to playback |

---

## 5. Teammate Handoff & Production Seams

When the backend/security owner finishes the production Detectif voice biometric verification pipeline:
1. **Actor Provider Replacement:** Replace `resolve_test_actor(fixture_id)` with the authenticated session's verified actor from the production session store.
2. **Transport Uniformity:** The frontend consumes the same JSON response schema (`user_transcript`, `assistant_text`, `result_block`, `tts_audio_base64`).
3. **No Frontend Rewrite Required:** The conversation panel, typed result renderers, auto-scroll, and audio playback controller will work with verified sessions without UI modifications.
