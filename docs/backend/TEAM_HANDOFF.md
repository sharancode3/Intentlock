# IntentLock — Team Handoff & Ownership Boundaries

This document defines explicit ownership boundaries and integration specifications across the concurrent IntentLock workstreams.

---

## 1. Explicit Workstream Ownership

| Workstream | Owned Paths | Non-Edit Boundary |
| :--- | :--- | :--- |
| **Backend & Speech Integration** (This Agent) | `backend/main.py`<br>`backend/core/**`<br>`backend/adapters/**`<br>`backend/models/**`<br>`backend/requirements.txt`<br>`backend/diagnostic_speech_client.py`<br>`docs/backend/**` | Do not modify `frontend/**`, `data/**`, `backend/data/**`, or `backend/services/**`. |
| **Frontend UI/UX** (Teammate) | `frontend/**` | Do not modify backend gateway or data services. |
| **Data & Knowledge** (Teammate) | `backend/data/**`<br>`backend/services/**`<br>`scripts/build_employee_knowledge_base.py`<br>`data/**` | Do not modify HTTP routing or authentication gateway. |

---

## 2. Handoff to Frontend Owner: Voice Turn & Audio Playback

### A. Submitting Audio Turns
- **Endpoint**: `POST /api/v1/voice/turn`
- **Content-Type**: `multipart/form-data`
- **Fields**:
  - `audio_file`: WebM/Opus, MP4/AAC, or WAV Blob (16kHz or 48kHz; decoded losslessly on backend).
  - `client_turn_id`: Unique UUID generated per turn (used to discard stale/cancelled responses).
  - `session_id`: Current session ID string (optional, defaults to null).
  - `client_timestamp`: ISO 8601 string.

### B. Understanding Response Structure
When speech processing succeeds without Detectif biometric verification, the gateway returns **`HTTP 200 OK`**:
```json
{
  "status": "unavailable",
  "client_turn_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "session_id": null,
  "transcript": "Hello, I need help resetting my password.",
  "spoken_summary": "I heard: \"Hello, I need help resetting my password.\". Voice verification is currently unconfigured, so your session remains anonymous.",
  "speech_audio": {
    "mime_type": "audio/wav",
    "sample_rate": 24000,
    "channels": 1,
    "byte_count": 147456,
    "base64_audio": "UklGRuRwAABXQVZFZm10...",
    "duration_ms": 3072.0
  },
  "speech_timings_ms": {
    "decode_ms": 12.4,
    "vad_ms": 2.1,
    "stt_ms": 234.8,
    "tts_ms": 512.6,
    "total_backend_ms": 765.2
  },
  "session": {
    "state": "ANONYMOUS",
    "authenticated": false,
    "user_id": null,
    "actor_role": "ANONYMOUS"
  },
  "result_block": {
    "type": "status_card",
    "title": "Voice Verification Pending",
    "payload": { ... }
  }
}
```

> [!IMPORTANT]
> **Status Interpretation**:
> - `transcript` contains the real transcribed words from Faster-Whisper.
> - `speech_audio` contains the real synthesized 24kHz WAV from Kokoro-82M.
> - `session.state: "ANONYMOUS"` means voice biometric identity verification (Detectif) has not yet been performed. Private records are blocked. Do not treat `status: "unavailable"` as a failure of the speech pipeline; it indicates that the *protected identity pipeline* is unconfigured.

### C. TypeScript Browser Playback Integration Snippet
To play the synthesized 24kHz WAV in the browser while respecting autoplay restrictions:

```typescript
// frontend/src/utils/audioPlayback.ts

export class SpeechAudioPlayer {
  private currentAudio: HTMLAudioElement | null = null;
  private currentTurnId: string | null = null;

  /**
   * Unlock browser audio playback. Call this directly inside
   * the microphone button's onClick handler before making the turn request.
   */
  public async unlockAudio(): Promise<void> {
    try {
      const dummy = new Audio();
      dummy.src = "data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA";
      await dummy.play();
    } catch {
      // Ignore initial interaction errors
    }
  }

  /**
   * Play base64 WAV payload returned from POST /api/v1/voice/turn
   */
  public async playTurnAudio(base64Audio: string, turnId: string): Promise<void> {
    // 1. Cancel any currently playing turn audio
    this.stop();

    this.currentTurnId = turnId;
    const audioUri = `data:audio/wav;base64,${base64Audio}`;
    const audio = new Audio(audioUri);
    this.currentAudio = audio;

    audio.onended = () => {
      if (this.currentTurnId === turnId) {
        this.currentAudio = null;
        this.currentTurnId = null;
      }
    };

    try {
      await audio.play();
    } catch (err) {
      console.warn("Autoplay blocked or playback cancelled:", err);
    }
  }

  /**
   * Interruption / cancellation handler
   */
  public stop(): void {
    if (this.currentAudio) {
      this.currentAudio.pause();
      this.currentAudio.currentTime = 0;
      this.currentAudio = null;
    }
    this.currentTurnId = null;
  }
}

export const speechPlayer = new SpeechAudioPlayer();
```

---

## 3. Handoff to Data & Knowledge Owner

1. **Dataset Integrity**:
   - The 31 canonical employees in `backend/data/all_employees.json` are validated, unique, and loaded once at startup.
2. **Required Security Refinements in `EmployeeVisibilityService`**:
   - **Explicit Denial**: When an unauthorized caller requests a private employee record, the service currently falls back to a directory view. Please update it to raise or return an explicit denial decision.
   - **Remove ID Prefix Shortcut**: Executive classification currently checks if the ID starts with `EXE-`. Please replace this with explicit verification against canonical roles and security scopes.
   - **Debug Data Sanitization**: Do not return `context_used` or internal `filters_extracted` in production API responses.

---

---

## 4. Stage 2 Frontend Integration Guide: Biometric Identity & Scoped Access

Stage 2 delivers real Detectif voice verification, anti-spoofing dual checks, and scoped employee record reads.

### A. Submitting Candidate Identity Claims
The frontend can claim identity in two supported ways:
1. **Explicit Form Parameter**: Include `candidate_employee_id="EMP-1001"` in the `multipart/form-data` payload of `POST /api/v1/voice/turn`.
2. **Verbal Identity Claim**: The user speaks their ID (e.g. *"Hello, my employee ID is EMP-1001"*). The backend STT automatically extracts `EMP-\d{4}` via regex and verifies the speaker.

### B. Rendering Stage 2 Result Blocks
The response payload contains `result_block` with distinct discriminator types:

1. **`EMPLOYEE_PROFILE`** (`status: "success"`):
   - Render as a personnel card displaying:
     - Name: `payload.employee.name`
     - Role & Department: `payload.employee.role` in `payload.employee.department`
     - Active Projects: List `payload.employee.active_projects` as badges
     - Skills: Top primary skills from `payload.employee.skills`
     - Office Location & Manager Name: `payload.employee.office_location`, `payload.employee.manager_name`
   - Show session state badge: `VERIFIED` with 90s expiration countdown timer based on `session.actor.expiresInSeconds`.

2. **`DENIAL_BANNER`** (`status: "denied"` or `"unverified"`):
   - Render as a prominent warning/denial banner:
     - Reason: `payload.reason` (e.g., synthetic audio warning, speaker mismatch, or unauthorized colleague access)
     - Target: `payload.target_requested`
     - Policy Note: `payload.policy`
   - Session remains `ANONYMOUS`. No employee data is leaked.

### C. Session Management & Termination
- Store `session.sessionId` in frontend state as the active session token.
- Pass this token in subsequent HTTP requests via header `X-Session-Token: <token>` (or `Authorization: Bearer <token>`).
- To provide a "Log out / Terminate Session" button:
```typescript
async function terminateVoiceSession(sessionId: string) {
  await fetch("/api/v1/voice/session/end", {
    method: "POST",
    headers: {
      "X-Session-Token": sessionId,
    },
  });
  // Clear frontend session state
  setSession(null);
}
```
- When the 90-second countdown expires, gracefully clear the active session state and prompt the user to re-verify their voice.

---

## 5. Stage 3 Frontend Integration: Three Personas, Claim Conflicts & Grounded Answers

### A. Three Demonstration Personas
For demo testing with the three consenting participants:
1. **Persona A: Aarav Mehta (`EMP-1001`, Software Engineer)**:
   - Voice verifies Aarav -> displays software developer profile with active projects.
   - Spoken claim like *"Log me in as the CTO"* fails closed (voice mismatch).
   - Asking for peer records or manager files shows a red `DENIAL_BANNER`.
2. **Persona B: Priya Sharma (`EMP-2001`, Engineering Manager)**:
   - Voice verifies Priya -> displays manager profile with direct reports (`EMP-1001`, `EMP-1501`).
   - Querying Aarav or Neha displays their employee profile cards.
   - Querying unrelated engineers (`EMP-1002`) shows a red `DENIAL_BANNER`.
3. **Persona C: Arvind Rao (`EMP-4002`, CTO)**:
   - Voice verifies Arvind -> displays executive technology profile with R&D direct report (`RND-5001`).
   - Querying non-reporting engineers shows a red `DENIAL_BANNER` (role integrity: titles provide no backdoor).

### B. Critical Header Security Rule (No Query Param Tokens)
- Protected endpoints (`/api/v1/employees/me`, `/api/v1/employees/{id}`) **strictly reject** tokens passed in URL query strings (e.g. `?session_id=...` or `?token=...`) with `HTTP 400 Bad Request`.
- Always pass the session token in the request headers:
  ```typescript
  headers: {
    "Authorization": `Bearer ${sessionToken}`,
    // OR: "X-Session-Token": sessionToken,
  }
  ```

### C. Claim Conflict Prevention
- When an active session is in memory, do not send a different `candidate_employee_id` on subsequent turns unless the user explicitly logs out first. Presenting a token for Persona A while claiming Persona B returns `HTTP 400 Bad Request` and terminates the session.

### D. Grounded Spoken Answers (OpenAI Responses API)
- The backend leverages `OpenAI Responses API` (`gpt-5.4-mini`) with `store=False`.
- The assistant's `spoken_summary` and `assistant_message` contain concise, conversational answers strictly grounded in the caller's pre-filtered authorized context.
- The base64 WAV payload in `speech_audio` speaks this exact verified text aloud through Kokoro TTS.

