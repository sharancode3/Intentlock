# IntentLock — Stage 1 API Contract & Gateway Specification

This document specifies the authoritative HTTP API contract for IntentLock's Stage 1 gateway foundation.

---

## 1. Diagnostics & Health Endpoints

### `GET /health/live` & `GET /api/v1/health/live`
- **Purpose**: Liveness probe. Indicates if the process is up and responding.
- **Success Code**: `200 OK`
- **Response**:
```json
{
  "status": "live",
  "project": "IntentLock Backend",
  "version": "1.0.0",
  "timestamp": "2026-10-16T12:00:00.000000+00:00"
}
```

### `GET /health/ready` & `GET /api/v1/health/ready`
- **Purpose**: Readiness probe. Evaluates if all required pipeline dependencies are operational.
- **Stage 1 Status**: `503 Service Unavailable` (Truthfully reflects that speech and voice evidence pipelines are unconfigured).
- **Response**:
```json
{
  "status": "not_ready",
  "project": "IntentLock Backend",
  "components": {
    "dataset": "ready",
    "ollama": "unreachable",
    "speech_service": "unavailable",
    "voice_evidence": "unconfigured"
  },
  "reason": "Voice processing and speaker verification pipelines are not connected."
}
```

---

## 2. Voice Turn Ingress Route

### `POST /api/v1/voice/turn`
- **Content-Type**: `multipart/form-data`
- **Headers**:
  - `X-Request-Id`: Optional client correlation ID (max 64 chars); server generates `req_<hex>` if omitted.
- **Form Fields**:
  - `audio_file`: Binary speech recording (Required). Max size: 8 MiB (`MAX_AUDIO_BYTES`).
  - `client_turn_id`: Non-empty string (Required, max 128 chars). Used by frontend to correlate retries.
  - `session_id`: Optional opaque session reference (Max 128 chars). Untrusted; does not grant authority.
  - `client_timestamp`: Optional ISO timestamp string (Diagnostic only).

### Allowed Audio MIME Types
Parameters such as `;codecs=opus` are normalized to base media types:
- `audio/webm`
- `audio/mp4`
- `audio/wav`, `audio/x-wav`
- `audio/ogg`
- `audio/mpeg`
- `audio/aac`
- `audio/m4a`, `audio/x-m4a`

### Stage 1 Unavailable Response (`503 Service Unavailable`)
```json
{
  "api_version": "1",
  "request_id": "req_51e8ec452b76",
  "client_turn_id": "turn-uuid-1234-abcd",
  "status": "unavailable",
  "session": {
    "state": "ANONYMOUS",
    "sessionId": null,
    "actor": null
  },
  "session_expires_at": null,
  "transcript": null,
  "assistant_message": null,
  "spoken_summary": null,
  "result_block": null,
  "trust_evidence": null,
  "error": {
    "code": "VOICE_PIPELINE_NOT_READY",
    "message": "Voice processing is not connected yet. Please try again when the service is ready.",
    "retryable": false
  }
}
```

### Response Headers
- `X-Request-Id`: Matching server correlation ID.
- `Cache-Control`: `no-store, no-cache, must-revalidate`

---

## 3. Security Boundary & Private Route Protection

All private employee directory and knowledge routes require an authenticated, verified session.

| Endpoint | Method | Unauthenticated Behavior | Forged Client Claims Behavior |
| --- | --- | --- | --- |
| `/api/v1/employees` | GET | `401 Unauthorized` | `403 Forbidden` |
| `/api/v1/employees/{id}` | GET | `401 Unauthorized` | `403 Forbidden` |
| `/api/v1/employees/search` | GET | `401 Unauthorized` | `403 Forbidden` |
| `/api/v1/employees/{id}/reporting` | GET | `401 Unauthorized` | `403 Forbidden` |
| `/api/v1/knowledge/query` | POST | `401 Unauthorized` | `403 Forbidden` |

### Safe Error Envelope
```json
{
  "api_version": "1",
  "request_id": "req_6dcbc14495a2",
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Authentication required. Unauthenticated access to private employee records is denied. Voice verification required via /api/v1/voice/turn.",
    "retryable": false
  }
}
```

---

---

## 4. Stage 2 Dual-Verification Voice Turn Response

When voice processing and Detectif biometric verification execute on `POST /api/v1/voice/turn`:

### A. Dual Verification Success (`HTTP 200 OK`)
Requires `decision == "match"` AND `authenticity_verdict == "real"`.
```json
{
  "api_version": "1",
  "request_id": "req_51e8ec452b76",
  "client_turn_id": "turn-test-pass-001",
  "status": "success",
  "session": {
    "state": "VERIFIED",
    "sessionId": "sess_482b8a07f3de49989a3f9bb8c49e2954",
    "actor": {
      "employeeId": "EMP-1001",
      "fullName": "Aarav Mehta",
      "role": "Software Engineer",
      "department": "Engineering",
      "teamId": "Application Engineering",
      "expiresInSeconds": 90
    }
  },
  "session_expires_at": "2026-10-16T12:01:30.000000+00:00",
  "transcript": "Who am I? My employee ID is EMP-1001",
  "assistant_message": "Identity verified as Aarav Mehta, Software Engineer in Engineering. Displaying your authorized employee profile.",
  "spoken_summary": "Identity verified as Aarav Mehta, Software Engineer in Engineering. Displaying your authorized employee profile.",
  "speech_audio": {
    "mime_type": "audio/wav",
    "sample_rate": 24000,
    "channels": 1,
    "byte_count": 147456,
    "base64_audio": "UklGRuRwAABXQVZFZm10...",
    "duration_ms": 3072.0
  },
  "speech_timings_ms": {
    "stt_ms": 234.8,
    "detectif_ms": 120.4,
    "tts_ms": 512.6,
    "total_backend_ms": 867.8
  },
  "result_block": {
    "id": "blk_profile_EMP-1001_1760611800",
    "type": "EMPLOYEE_PROFILE",
    "title": "Employee Profile: Aarav Mehta (EMP-1001)",
    "timestamp": "12:00 PM",
    "isSensitive": true,
    "payload": {
      "employee": {
        "id": "EMP-1001",
        "name": "Aarav Mehta",
        "role": "Software Engineer",
        "department": "Engineering",
        "team": "Application Engineering",
        "email": "aarav.mehta@intentlock-demo.example",
        "active_projects": ["Customer Support Portal", "Internal Analytics Dashboard"],
        "status": "Active",
        "office_location": "Bengaluru",
        "manager_name": "Priya Sharma",
        "skills": ["Python", "JavaScript", "TypeScript", "React", "FastAPI"]
      }
    }
  },
  "trust_evidence": {
    "speaker_decision": "match",
    "similarity_score": 0.92,
    "similarity_threshold": 0.75,
    "authenticity_verdict": "real",
    "deepfake_score": 0.08,
    "deepfake_threshold": 0.50,
    "speaker_id": "spk_aarav_001",
    "is_dual_verified": true,
    "timestamp": "2026-10-16T12:00:00+00:00"
  },
  "error": null
}
```

### B. Dual Verification Rejection (`HTTP 200 OK`, `status: "denied"`)
Triggered when speaker does not match (`decision == "no_match"`) OR synthetic audio detected (`deepfake.verdict in ("fake", "not_sure")`).
```json
{
  "api_version": "1",
  "request_id": "req_62ab10998f32",
  "client_turn_id": "turn-test-fake-001",
  "status": "denied",
  "session": {
    "state": "ANONYMOUS",
    "sessionId": null,
    "actor": null
  },
  "session_expires_at": null,
  "transcript": "My employee ID is EMP-1001",
  "assistant_message": "Voice authentication denied: potential synthetic audio detected (fake).",
  "spoken_summary": "Voice authentication denied: potential synthetic audio detected (fake).",
  "result_block": {
    "id": "blk_denial_1760611800",
    "type": "DENIAL_BANNER",
    "title": "Access Restricted: Policy Authorization Boundary",
    "timestamp": "12:00 PM",
    "isSensitive": false,
    "payload": {
      "reason": "Voice authentication denied: potential synthetic audio detected (fake).",
      "target_requested": "EMP-1001",
      "policy": "Requires verified identity with self-viewing scope or direct reporting manager authorization."
    }
  },
  "trust_evidence": {
    "speaker_decision": "match",
    "similarity_score": 0.91,
    "similarity_threshold": 0.75,
    "authenticity_verdict": "fake",
    "deepfake_score": 0.96,
    "deepfake_threshold": 0.50,
    "speaker_id": "spk_aarav_001",
    "is_dual_verified": false,
    "timestamp": "2026-10-16T12:00:00+00:00"
  },
  "error": null
}
```

---

## 5. Protected Scoped Routes & Session Termination

### `POST /api/v1/voice/session/end`
- **Purpose**: Explicitly revoke active session and wipe cached context.
- **Headers**: `X-Session-Token: <token>` or `Authorization: Bearer <token>`
- **Response**:
```json
{
  "status": "session_terminated",
  "session": {
    "state": "ANONYMOUS",
    "sessionId": null
  },
  "message": "Session explicitly terminated. All private context wiped."
}
```

### `GET /api/v1/employees/me`
- **Purpose**: Retrieve authenticated caller's own scoped profile.
- **Headers**: `X-Session-Token: <token>` or `Authorization: Bearer <token>`
- **Response (`200 OK`)**:
```json
{
  "employee": {
    "id": "EMP-1001",
    "name": "Aarav Mehta",
    "role": "Software Engineer",
    "department": "Engineering",
    "team": "Application Engineering",
    "email": "aarav.mehta@intentlock-demo.example",
    "active_projects": ["Customer Support Portal", "Internal Analytics Dashboard"],
    "status": "Active",
    "office_location": "Bengaluru",
    "manager_name": "Priya Sharma",
    "skills": ["Python", "JavaScript", "TypeScript", "React", "FastAPI"]
  }
}
```

### `GET /api/v1/employees/{employee_id}`
- **Purpose**: Scoped employee lookup.
- **Rules**:
  - Direct manager querying report -> `200 OK` with direct report details.
  - Peer querying colleague -> `403 Forbidden` with `DENIAL_BANNER` block.
  - Target does not exist -> `404 Not Found`.

---

## 6. Stage 3 Contract Additions: Role Integrity, Claim Conflicts & OpenAI Responses

### A. Three Canonical Personas
1. **Persona A: EMP-1001 (Aarav Mehta, L1 Software Engineer)**:
   - Self-profile and assigned projects only.
   - Denied access to peers (`EMP-1002`), manager files (`EMP-2001`), and compensation.
2. **Persona B: EMP-2001 (Priya Sharma, L3 Engineering Manager)**:
   - Self-profile and direct reports (`EMP-1001`, `EMP-1501`) profiles and project summaries.
   - Denied access to unrelated engineering peers (`EMP-1002`).
3. **Persona C: EMP-4002 (Arvind Rao, L5 CTO)**:
   - Self-profile, executive technology authority, and R&D direct report (`RND-5001`).
   - Strict role integrity: Denied access to private personnel records of non-reporting employees (`EMP-1002`). Executive titles provide no backdoor.

### B. Security Invariants
1. **Header-Only Authentication**:
   - All protected routes reject session tokens passed in URL query strings (`?session_id=` or `?token=`) with `HTTP 400 Bad Request`.
   - Only `Authorization: Bearer <token>` and `X-Session-Token: <token>` are permitted.
2. **Caller Claim Conflict Rejection**:
   - In `POST /api/v1/voice/turn`, presenting an active session for Actor A while declaring `candidate_employee_id` for Actor B returns `HTTP 400 Bad Request` and revokes the active session.
3. **Anti-Resurrection Protection**:
   - Revoked sessions permanently transition to `is_revoked = 1`. Any attempt to resurrect a revoked session token raises a validation error.

### C. OpenAI Responses API (`gpt-5.4-mini`) Answer Generation
When `LLM_PROVIDER=openai`:
- Context is strictly pre-filtered by `ScopedAuthorizationService.build_authorized_context_for_llm` before transmission.
- Provider executes `AsyncOpenAI.responses.create` with `store=False`, `max_output_tokens=1024`, and grounding instructions.
- Approved concise output is spoken aloud via Kokoro TTS synthesis.

