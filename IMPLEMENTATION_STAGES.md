# IntentLock — Master Implementation Stages & Hackathon Build Plan
**Track 3: UNCLONE AGENTS (UNCLONE Hackathon 2026, BMSCE & DetectifAI)**  
**Document Identity:** `docs/IMPLEMENTATION_STAGES.md`  
**Status:** Authoritative Execution Blueprint & Build Plan  
**Version:** 1.0.0 (Pre-Build Final)  
**Permitted Build Window:** 16 October 2026, ~10:00–18:30 IST (Day 1 Hackathon, 3 Builders)  
**Parent Blueprint:** [`docs/System_Architecture.md`](file:///c:/SHARAN%20PROJECTS/IntentLock/docs/System_Architecture.md)  
**Cross-References:** [`docs/PRD.md`](file:///c:/SHARAN%20PROJECTS/IntentLock/docs/PRD.md) • [`docs/TRD.md`](file:///c:/SHARAN%20PROJECTS/IntentLock/docs/TRD.md) • [`docs/WORKFLOW.md`](file:///c:/SHARAN%20PROJECTS/IntentLock/docs/WORKFLOW.md) • [`docs/UI_UX.md`](file:///c:/SHARAN%20PROJECTS/IntentLock/docs/UI_UX.md) • [`docs/DATABASE_STORAGE.md`](file:///c:/SHARAN%20PROJECTS/IntentLock/docs/DATABASE_STORAGE.md) • [`docs/SECURITY.md`](file:///c:/SHARAN%20PROJECTS/IntentLock/docs/SECURITY.md) • [`docs/Voice_Pipeline_Architecture.md`](file:///c:/SHARAN%20PROJECTS/IntentLock/docs/Voice_Pipeline_Architecture.md) • [`docs/Agent_Identity_and_Trust_Receipt.md`](file:///c:/SHARAN%20PROJECTS/IntentLock/docs/Agent_Identity_and_Trust_Receipt.md) • [`docs/Threat_Model_and_Privacy.md`](file:///c:/SHARAN%20PROJECTS/IntentLock/docs/Threat_Model_and_Privacy.md)

---

## A. One-Page Build Objective

### 1. Problem Statement & User Journey
In typical enterprise AI assistants, conversational models are given direct database access and blind trust: once a user is authenticated (or speaks), the LLM can execute arbitrary tool writes or dump unauthorized internal data. Conversely, voice-enabled kiosks often lack caller verification entirely or rely on static pins.

**IntentLock** solves this by creating a **shared, microphone-first company assistance workspace with no initial login**. An anonymous visitor can walk up to the kiosk and verbally ask public corporate FAQ questions. When an employee requires private ticket data or desires to file a hardware issue, they state their identity claim (e.g., *"I am Charlie Davis, EMP-1001"*). IntentLock evaluates fresh spoken audio through DetectifAI's dual checks (Audio Deepfake Detection + 1:1 Speaker Verification) to establish a short-lived (90s) server-controlled session. The AI agent proposes structured operations, but **cannot grant itself authority or execute writes directly**. A separate, deterministic **Protected Executor** validates user permissions and an exact, parameter-hashed, single-use `ActionGrant` before committing an atomic transaction to Supabase PostgreSQL and returning a truthful trust receipt.

```mermaid
flowchart LR
    Visitor["Anonymous Visitor / Employee"] -->|Spoken Voice Turn| MicKiosk["Shared Mic Kiosk<br>(Zero Initial Login)"]
    
    subgraph PublicFlow ["Public Flow (Zero Auth)"]
        MicKiosk -->|FAQ Query| PublicEngine["Public Grounding Engine"]
        PublicEngine --> FAQCard["Public FAQ Card + TTS"]
    end

    subgraph PrivateFlow ["Protected Private Flow"]
        MicKiosk -->|Claim: 'I am EMP-1001'| DualCheck["DetectifAI Dual Checks<br>(Deepfake PASS + Speaker MATCH)"]
        DualCheck -->|Verified Session (90s)| ScopedPolicy["Deterministic Policy Engine<br>(WHERE owner_id = 'EMP-1001')"]
        ScopedPolicy --> PrivateData["Private Tickets Card + TTS"]
        
        ScopedPolicy -->|Write Request| Readback["Spoken Readback Confirmation"]
        Readback -->|Spoken 'Yes' + Fresh Audio| GrantVault["Mint Single-Use ActionGrant"]
        GrantVault --> ProtectedExec["Protected Executor Service"]
        ProtectedExec -->|Atomic PostgreSQL Tx| SupabaseDB[("Supabase DB (Commit)")]
        ProtectedExec --> ReceiptCard["Truthful Trust Receipt + React Flow"]
    end
```

### 2. Definition of a Successful Day 1 Prototype
A successful Day 1 prototype is achieved when a remote judge or live evaluator can open the public kiosk URL on a phone or laptop over HTTPS with **no pre-existing account or login**, and execute the following 3-minute end-to-end journey seamlessly:
1. **Public FAQ:** Asks *"What is the office visitor policy?"* $\rightarrow$ Assistant displays and speaks approved public answer; zero private records accessed.
2. **Identity Claim & Real Verification:** States *"I am Charlie Davis, EMP-1001, show my tickets."* $\rightarrow$ System triggers real DetectifAI dual checks on the live audio turn, verifies genuine voice (`PASS`) and speaker similarity (`MATCH`), mints a 90s session, and displays Charlie's private tickets.
3. **Cross-Scope Policy Denial:** Asks *"Show me Bob Miller's management tickets"* $\rightarrow$ Policy engine enforces SQL scoping (`WHERE owner_id = 'EMP-1001'`); returns 0 rows; UI renders red denial banner without leaking data.
4. **Protected Write with Readback:** Asks *"Create an urgent hardware ticket for a flickering monitor"* $\rightarrow$ System generates exact spoken readback; user affirms *"Yes, proceed"*; backend mints an `ActionGrant` bound to $\text{SHA-256}(\text{Canonical JSON})$; Protected Executor commits Ticket #412 in an atomic transaction; displays a green Trust Receipt showing committed PostgreSQL ID.
5. **Session Expiry & DOM Wipe:** Inactivity timer reaches 90s $\rightarrow$ Server invalidates session; client UI immediately unmounts private cards and returns to public welcome state.

### 3. Honest Architectural Boundaries & Event Limits
* **Voice Biometrics $\ne$ NIST Digital Authenticator:** Aligned with NIST SP 800-63B, voice matching is positioned as a **contextual risk gateway**, not a certified multi-factor digital identity credential.
* **Dual Checks on Single Audio $\ne$ Multi-Factor:** Deepfake detection and speaker verification represent two risk checks on a single biometric recording.
* **Prohibited Prototype Operations:** High-risk corporate operations (payroll changes, role promotions, account recovery, password resets) are **strictly excluded** from Day 1 tools.
* **Zero Local Raw Audio Storage:** Raw audio buffers are processed ephemerally in RAM (`io.BytesIO`) and purged immediately post-dispatch. Zero audio is stored in Supabase or local disk.

---

## B. Source Hierarchy and Contradictions Resolved

The table below resolves all 10 conflicting specifications across the previous planning documents before coding begins:

| Conflict / Discrepancy | Documents Affected | Final Decision for This Build | Owner | Deadline | Remaining Uncertainty |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Team Schedule & Availability** | TRD, UI/UX, System Arch | **Locked:** A works solo 10:00–11:00 (FastAPI, Supabase, API kit smoke test). B & C arrive at 11:00. Replace all older 10:00 all-hands schedules. | Team Lead (A) | Oct 16, 09:30 | Organizer schedule adjustments. |
| **2. Fictional Employee IDs & Personas** | PRD, TRD, UI/UX, Workflow | **Locked:** Standardize on official organizational dataset: `EMP-1001` (Charlie Davis, L1 Eng), `EMP-2001` (Bob Miller, L3 Manager), `EMP-3001` (Alice Vance, Helpdesk), `EMP-4002` (CTO). Teammates consent to enroll their voices as these disclosed demo personas. | Backend (A) | Oct 16, 10:30 | Official persona names in Word docs. |
| **3. Duplicate `EMP-4002` Record** | CTO Doc vs. L5 Exec Doc | **Locked:** `EMP-4002` represents **one individual** (Chief Technology Officer). Collapse into a single Supabase `employees` row (`role: 'executive'`). | Backend (A) | Oct 16, 10:45 | None. Resolved. |
| **4. Canonical API Turn Path** | TRD (`/voice/turn`) vs. UI_UX (`/kiosk/turn`) | **Locked:** Freeze single canonical endpoint: `POST /api/v1/voice/turn`. All client audio turns route here. | Backend (A) | Oct 16, 11:00 | None. Contract frozen. |
| **5. Org Hierarchy vs. Demo Policy** | Org Docs (L1–L5) vs. DB Roles | **Locked:** Implement a 4-tier demo policy model: `employee` (own-scope), `manager` (team-scope), `helpdesk` (queue-scope), `executive` (aggregate-scope). No blanket access based on "executive" string alone. | Backend (A) | Oct 16, 11:15 | None. Scoping rules locked. |
| **6. PRD FR-01–FR-14 vs. Build Window** | PRD vs. 6–8h build limit | **Locked:** Focus 100% of Day 1 on a single complete vertical slice (`query_faq`, `get_my_tickets`, `create_ticket`). P1/P2 features cut if time demands. | Product (B) | Oct 16, 11:00 | Velocity during afternoon. |
| **7. "Immutable" & "Cryptographic" Claims** | Security, Database, UI/UX | **Locked:** Use accurate language: "Backend audit ledger" and "Transaction-backed trust receipt" backed by PostgreSQL atomic commits, not public blockchain or PKI. | Backend (A) | Oct 16, 10:00 | None. Language corrected. |
| **8. Replay & Biometric Defenses** | Voice Arch, Security | **Locked:** DetectifAI provides acoustic deepfake checks; dynamic spoken readbacks defeat static replays. Live neural relays are honestly documented as residual risks. | Speech (C) | Oct 16, 10:30 | DetectifAI kit score semantics. |
| **9. Enrollment Timing** | Voice Arch (claimed pre-event) | **Locked:** In-event enrollment strictly during permitted hours (11:30–12:00) using consenting teammate voices after kit validation. Zero pre-event biometric data. | Speech (C) | Oct 16, 11:30 | DetectifAI enrollment API contract. |
| **10. Local Model Contention (Qwen3 4B)** | TRD vs. Machine Resources | **Locked:** Benchmark installed Qwen3 4B at 11:15. If inference > 1.8s or structured JSON fails, fall back to tested local Qwen-2.5 or OpenAI dormant adapter. | Speech (C) | Oct 16, 11:30 | Local GPU VRAM availability. |

---

## C. Locked P0 Architecture and Contract Freeze

```mermaid
flowchart TD
    subgraph ClientLayer ["1. Frontend Client Layer (Teammate B)"]
        Browser["React 19 / Vite / Tailwind UI"] --> WebAudio["Web Audio VAD & 16kHz Recorder"]
        Browser --> ResultView["Typed ResultBlock Renderer (Cards, Tables, Charts, Trace)"]
    end

    subgraph TransportGateway ["2. Transport & Ingress Gateway (Teammate A)"]
        WebAudio -->|POST /api/v1/voice/turn<br>(multipart/form-data: audio + session_id)| Ingress["FastAPI Ingress Router"]
        Ingress --> SessionVault[("In-Memory Session Vault<br>(sess_<uuid4>, 90s Sliding TTL)")]
        Ingress --> RAMBuffer["Ephemeral RAM Audio Buffer<br>(io.BytesIO)"]
    end

    subgraph SpeechIntelligence ["3. Speech & Conversational Pipeline (Teammate C)"]
        RAMBuffer --> LocalSTT["faster-whisper INT8 (CTranslate2)"]
        LocalSTT -->|Transcript| LLMAdapter["Sandboxed LLM Adapter (Qwen3 4B / OpenAI)"]
        LLMAdapter -->|Emits Structured ToolProposal JSON| ProposalContract["Proposal Schema Validator"]
        ProposalContract --> LocalTTS["Kokoro-82M TTS Generator (24kHz WAV)"]
        LocalTTS --> Browser
    end

    subgraph SecurityCore ["4. Authoritative Security & Policy Core (Teammate A)"]
        RAMBuffer -->|Ephemeral Dispatch| DetectifAI["DetectifAI API Gateway<br>(Deepfake PASS + Speaker MATCH)"]
        DetectifAI --> SessionVault
        
        ProposalContract --> PolicyEngine["Deterministic Policy Engine"]
        SessionVault --> PolicyEngine
        PolicyEngine --> GrantVault[("action_grants Table<br>(SHA-256 Hash, TTL 30s)")]
        GrantVault --> ProtectedExec["Protected Executor Service<br>(Holds asyncpg DB Pool)"]
    end

    subgraph StorageLayer ["5. Authoritative Storage Layer (Teammate A)"]
        ProtectedExec -->|Atomic PostgreSQL Tx| SupabaseDB[("Supabase PostgreSQL DB<br>(Port 6543 Pooler, RLS Deny)")]
        SupabaseDB --> T_Tickets["tickets"]
        SupabaseDB --> T_Audit["audit_events (Append-Only)"]
    end
```

### 1. Canonical Turn Request/Response Contract (`POST /api/v1/voice/turn`)
* **Request (Multipart/form-data):**
  * `audio_file`: Binary 16kHz mono PCM WAV.
  * `session_id`: Optional string (`sess_<uuid4>` or null).
  * `client_timestamp`: ISO 8601 string.
* **Response (Application/JSON):**
```json
{
  "request_id": "req_9812a4b8-2c31-489e-9d22-7711aa55dd88",
  "session_id": "sess_4410a2f9-7711-48a2-b992-cc118822ee44",
  "session_state": "VERIFIED_ACTIVE",
  "session_expires_in_seconds": 88.4,
  "transcript": "Create an urgent hardware ticket for flickering monitor",
  "spoken_summary": "I have created hardware ticket number 412 for your flickering monitor.",
  "tts_audio_base64": "UklGRi...",
  "result_block": {
    "type": "ACTION_RECEIPT",
    "receipt_id": "rcpt_9812a4b8_412",
    "status": "COMMITTED",
    "title": "Hardware Support Ticket #412",
    "actor_id": "EMP-1001",
    "action_name": "create_ticket",
    "details": {
      "ticket_id": 412,
      "category": "hardware",
      "priority": "urgent",
      "status": "open"
    },
    "audit_event_id": 88192
  },
  "trust_trace_events": [
    {"node": "node_audio", "status": "PASSED"},
    {"node": "node_deepfake", "status": "PASSED"},
    {"node": "node_speaker", "status": "PASSED"},
    {"node": "node_policy", "status": "PASSED"},
    {"node": "node_confirm", "status": "PASSED"},
    {"node": "node_grant", "status": "PASSED"},
    {"node": "node_mutate", "status": "COMMITTED"}
  ]
}
```

### 2. Unified Frontend-Backend Typed Card Union
The frontend React workspace renders strictly authorized DTOs conforming to this discriminated union:
1. `FAQ_CARD`: Grounded public answer with source document badge.
2. `EMPLOYEE_PROFILE_CARD`: Caller name, department, role, active project summary.
3. `TICKET_TABLE`: Array of ticket rows scoped strictly by verified ownership.
4. `TEAM_QUEUE_CHART`: Recharts bar chart of open ticket counts by priority (manager scope).
5. `CONFIRMATION_MODAL`: Exact readback parameters with affirmative/cancel status.
6. `DENIAL_BANNER`: Red alert stating exact policy or biometric reason; 0 records shown.
7. `ACTION_RECEIPT`: Green card showing committed ticket ID, audit ID, and transaction hash.
8. `TRUST_TRACE_DAG`: Live `@xyflow/react` node states (`PASSED`, `FAILED`, `NOT_REACHED`).

---

## D. P0 Feature Inventory and Demo Traceability

| PRD Ref | Feature Capability | Implementation Stage | Primary Owner | Critical Dependency | Observable Live Demo Test |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **FR-01** | Zero-Login Public Assistance | Stage 3 | Teammate B (UI) / A (BE) | FastAPI Ingress | Visitor asks FAQ; receives grounded answer; no login prompt. |
| **FR-02** | Ephemeral Voice Capture | Stage 1, 3 | Teammate B (Mic) / C (VAD) | Web Audio API | Mic captures audio; buffers strictly in RAM; 0 files on disk. |
| **FR-03** | Local Speech-to-Text | Stage 3 | Teammate C | faster-whisper | Spoken audio transcribes locally with <800ms latency. |
| **FR-04** | Grounded Intent Reasoning | Stage 3, 6 | Teammate C | Local Qwen / OpenAI | Intent correctly maps to allowlisted `ToolProposal` verbs. |
| **FR-05** | Real DetectifAI Deepfake Check | Stage 5 | Teammate A | DetectifAI API Kit | Live turn evaluated for synthetic artifacts; flags clone audio. |
| **FR-06** | Real DetectifAI Speaker Match | Stage 5 | Teammate A | DetectifAI API Kit | Voice matched 1:1 against enrolled reference key. |
| **FR-07** | Sliding Session Vault (90s) | Stage 2, 5 | Teammate A | In-Memory Cache | Active session clears after 90s; DOM purges sensitive cards. |
| **FR-08** | Deterministic Scoping Engine | Stage 4, 7 | Teammate A | Supabase PostgreSQL | `EMP-1001` cannot read `EMP-2001` tickets (WHERE filter). |
| **FR-09** | Spoken Readback Confirmation | Stage 6, 8 | Teammate C / B | Policy Engine | Assistant speaks exact ticket parameters; waits for "yes". |
| **FR-10** | Single-Use ActionGrant Issuer | Stage 8 | Teammate A | SHA-256 Hashing | Grant bound to $\text{params\_hash}$; expires in 30 seconds. |
| **FR-11** | Protected Executor Atomic Tx | Stage 8 | Teammate A | PostgreSQL `asyncpg` | Grant consumption + ticket insert + audit write in 1 SQL tx. |
| **FR-12** | Truthful Trust Receipt Card | Stage 8 | Teammate B | Committed Result DTO | Green card displays real committed PostgreSQL `ticket_id: 412`. |
| **FR-13** | React Flow Trust Trace | Stage 7, 8 | Teammate B | `@xyflow/react` | 9-node DAG displays live verification verdicts truthfully. |
| **FR-14** | Local Text-to-Speech Output | Stage 3, 6 | Teammate C | Kokoro-82M Local | Assistant speaks concise summaries with <600ms first audio. |
| **FR-15** | Manager Team Scope View | Stage 7 | Teammate A / B | `teams` SQL Join | `EMP-2001` views Team Eng A tickets; Eng B blocked. |
| **FR-16** | Replay & Concurrency Guard | Stage 8, 9 | Teammate A | SQL Row-Level Lock | Replayed grant updates 0 rows; returns HTTP 409 Conflict. |
| **FR-17** | Private PDF Preview View | **P1 Cut Line** | Teammate B | Signed URL Endpoint | Deferred if time is short; fallback to typed table view. |
| **FR-18** | Local 1:N Biometric Ranking | **P2 Deferred** | Deferred | Supabase pgvector | **CUT FOR DAY 1:** Strictly Option A zero local embeddings. |
| **FR-19** | Full Multi-Factor Auth (NFA) | **Post-Hackathon**| Deferred | WebAuthn / FIDO2 | Future enterprise evolution outside hackathon scope. |

---

## E. Stage-by-Stage Implementation Plan

### Stage 0: Pre-Build Planning & Architecture Freeze (09:00–10:00)
* **Goal:** Align team, receive official DetectifAI API kit, freeze presentation storyline, and prepare the 10:00 start.
* **Owner:** Teammate A (on-site at 09:00), with B & C remote review.
* **Inputs:** Approved architecture documents, official API kit, hackathon rulebook.
* **Actions:**
  1. Teammate A collects API credentials, endpoint documentation, and quota limits.
  2. Confirm permitted build start at ~10:00.
  3. Prepare Stage 2 handoff packet for B & C (arriving at 11:00).
* **Exit Gate:** API credentials verified; zero feature code written prior to 10:00.

---

### Stage 1: Frontend Workspace Foundation (11:00–12:30)
* **Goal:** Deliver a responsive, single-page kiosk workspace with mic capture, settings, and typed card slots.
* **Owner:** Teammate B (Product / Frontend Lead).
* **Key Components:** React 19, Tailwind CSS, shadcn/ui, Web Audio API.
* **Touched Interfaces:** `frontend/src/components/workspace/*`, `frontend/src/hooks/useAudioRecorder.ts`.
* **Deliverables:**
  * Clean layout: Header with status pill, central conversation timeline, bottom mic dock, right-side contextual result pane.
  * Settings drawer: Theme toggle, text size, volume slider (client-side only; zero privilege impact).
  * State visualizers: Idle, Listening, Verifying, Authorized, Denied, Confirmation Awaiting, Action Committed.
* **Integration Gate:** Browser captures 16kHz WAV from microphone, visualizes audio wave, and renders mock `FAQ_CARD` and `DENIAL_BANNER` from typed props.

---

### Stage 2: Backend Core & DetectifAI Groundwork (10:00–11:00 — A Solo)
* **Goal:** Establish FastAPI server, Supabase connection pool, environment isolation, and DetectifAI client smoke test.
* **Owner:** Teammate A (Backend & Security Lead).
* **Key Components:** FastAPI, `asyncpg`, `pydantic-v2`, `httpx`.
* **Touched Interfaces:** `backend/main.py`, `backend/core/config.py`, `backend/services/detectifai_client.py`.
* **Deliverables:**
  * FastAPI server running on port `8000` with `/health` and `/api/v1/voice/turn` stubs.
  * Supabase PostgreSQL connection verified over port `6543` connection pooler.
  * DetectifAI API client written and smoke-tested with Teammate A's own consented voice audio.
  * Canonical contract frozen for Teammate B & C arrival at 11:00.
* **Integration Gate:** `curl http://localhost:8000/health` returns `status: "healthy"`, DB pool connected, DetectifAI API ping successful.

---

### Stage 3: First Integrated Public Voice Turn (11:00–12:30)
* **Goal:** Connect frontend mic $\rightarrow$ speech pipeline $\rightarrow$ public FAQ retrieval $\rightarrow$ visual card + spoken TTS.
* **Owners:** Teammate C (STT/TTS/LLM) + Teammate B (UI Dock) + Teammate A (Ingress).
* **Key Components:** `faster-whisper` INT8, `Kokoro-82M`, Qwen3 4B, `faqs` Supabase table.
* **Sequence:**
  1. Teammate B captures audio blob on button release, POSTs to `/api/v1/voice/turn`.
  2. Teammate C runs local Whisper transcription, routes text to Qwen3 4B.
  3. Qwen emits `ToolProposal(verb="query_faq", params={"query": "visitor policy"})`.
  4. Teammate A queries Supabase `faqs WHERE visibility = 'public'`.
  5. Teammate C synthesizes summary audio via Kokoro-82M.
  6. Teammate B displays `FAQ_CARD` and plays audio response.
* **Integration Gate (Checkpoint 1 — 12:30):** Speaking *"What is the visitor policy?"* into the browser renders the approved FAQ answer and speaks it with $<2.2\text{s}$ total turn latency.

---

### Stage 4: Structured Persona Ingestion & Scoped Data (12:30–13:30)
* **Goal:** Seed Supabase with clean fictional employee data, team hierarchies, and support tickets.
* **Owner:** Teammate A (Backend Lead).
* **Key Components:** Supabase SQL migration script, Python seed script.
* **Seeded Dataset:**
  * `employees`: `EMP-1001` (Charlie Davis, L1 Eng), `EMP-2001` (Bob Miller, L3 Mgr), `EMP-3001` (Alice Vance, Helpdesk), `EMP-4002` (Evelyn Reed, CTO — unified record).
  * `teams`: `team_eng_a` (Managed by `EMP-2001`, contains `EMP-1001`), `team_eng_b`.
  * `tickets`: Ticket #101 (Bob Miller, Server Migration), Ticket #205 (Team Eng B), Ticket #412 seed placeholder.
  * `enrollment_refs`: Provider reference keys mapped to consenting team members.
* **Integration Gate:** Parameterized SQL queries enforce `WHERE owner_id = 'EMP-1001'`; query returns exactly Charlie's tickets and 0 rows for Bob Miller.

---

### Stage 5: Multi-Stage Voice Impersonation Defense & Identity (13:30–15:00)
* **Goal:** Wire genuine DetectifAI dual checks into the turn pipeline to govern session creation.
* **Owner:** Teammate A (API Gateway & Policy) + Teammate C (Audio Normalization).
* **The 14-Step Enforcement Protocol:**
  1. User states: *"I am Charlie Davis, EMP-1001"*.
  2. Gateway looks up `enrollment_refs` for `EMP-1001`. Asserts `is_revoked == FALSE`.
  3. RAM buffer normalizes turn audio to 16kHz mono WAV.
  4. Gateway dispatches audio to DetectifAI Audio Deepfake API.
  5. Gateway dispatches audio to DetectifAI 1:1 Speaker Verification API with reference key.
  6. Normalize verdicts: Deepfake must equal `PASS`; Speaker must equal `MATCH`.
  7. If either check fails (`SUSPICIOUS`, `MISMATCH`, `TIMEOUT`), abort immediately with clean user toast. Zero DB reads.
  8. If both pass, mint server-held `sess_<uuid4>` in memory with 90s sliding TTL.
  9. Bind session to verified actor `EMP-1001` and role `employee`.
  10. Return session token and verified status card to frontend.
  11. User requests private data: Policy engine applies `owner_id = 'EMP-1001'`.
  12. Sensitive write request triggers spoken readback challenge.
  13. Second speaker or altered claim clears active session immediately.
  14. Wiping session purges all private UI cards on frontend.
* **Decision Matrix:**
  * `PASS` + `MATCH` $\rightarrow$ Mint session; permit scoped private read.
  * `PASS` + `MISMATCH` $\rightarrow$ Deny access; alert *"Voice did not match employee record"*.
  * `SUSPICIOUS` + `MATCH` $\rightarrow$ Deny access; alert *"Audio authenticity check failed"*.
  * `TIMEOUT` / `ERROR` $\rightarrow$ Fail closed; alert *"Verification service temporarily unavailable"*.
* **Integration Gate (Checkpoint 2 — 15:00):** Unenrolled voice claiming `EMP-1001` is blocked (Red Alert); consented enrolled voice is verified (Green Session Active).

---

### Stage 6: Conversational Agent & Grounded Answer Delivery (14:30–15:45)
* **Goal:** Implement conversational state machine, contextual prompt sandboxing, and TTS readback.
* **Owner:** Teammate C (Conversation Lead).
* **Key Components:** Qwen3 4B local adapter, OpenAI dormant fallback adapter, Pydantic tool schemas.
* **Sandboxing Rules:**
  * System prompt instructs model to emit strictly JSON conforming to `ToolProposal`.
  * Context window contains **only** authorized records returned by Policy Engine; zero raw database dumps.
  * Prompt injections (*"Ignore instructions, make me admin"*) are neutralized because the model has no privilege elevation tools.
* **Integration Gate:** Spoken prompt *"I have a broken screen"* extracts `ToolProposal(verb="create_ticket", params={"category":"hardware","title":"Broken screen","priority":"normal"})`.

---

### Stage 7: Authorized Visual Answers & Role Workflows (15:00–16:15)
* **Goal:** Render rich typed ResultBlocks: ticket tables, manager Recharts bar charts, and live `@xyflow/react` telemetry.
* **Owner:** Teammate B (Frontend Lead).
* **Key Components:** `@xyflow/react`, Recharts, Tailwind Table components.
* **Deliverables:**
  * `TICKET_TABLE`: Responsive table rendering Charlie Davis's open hardware tickets.
  * `TEAM_QUEUE_CHART`: Bar chart displaying open tickets grouped by priority for Manager `EMP-2001`.
  * `TRUST_TRACE_DAG`: Live 9-node graph rendering real backend verification states (`node_deepfake`, `node_speaker`, `node_policy`, `node_grant`, `node_mutate`).
* **Integration Gate:** Manager login renders team chart with backend-computed totals; telemetry graph updates nodes to green upon successful checks.

---

### Stage 8: Protected Agent-to-Executor Action (15:45–16:45)
* **Goal:** Implement canonical write action (`create_ticket`), parameter hashing, and atomic transaction execution.
* **Owner:** Teammate A (Backend Lead) + Teammate C (Readback Audio).
* **Sequence:**
  1. Assistant speaks exact readback: *"I am ready to create an urgent hardware ticket titled 'Monitor flickering violently'. Please say 'yes, proceed' to confirm or 'cancel' to stop."*
  2. Caller speaks: *"Yes, proceed"*.
  3. Backend verifies affirmation, computes $\text{params\_hash} = \text{SHA-256}(\text{Canonical JSON})$, mints `ActionGrant` (30s TTL).
  4. Protected Executor opens PostgreSQL transaction (`READ COMMITTED`):
     ```sql
     BEGIN;
     UPDATE action_grants SET is_consumed=TRUE WHERE grant_id=:id AND is_consumed=FALSE;
     -- Assert rowcount == 1
     INSERT INTO tickets (title, category, priority, status, owner_id, team_id) 
     VALUES ('Monitor flickering violently', 'hardware', 'urgent', 'open', 'EMP-1001', 'team_eng_a')
     RETURNING ticket_id;
     INSERT INTO audit_events (action, result, grant_id, actor_id, details) VALUES (...);
     COMMIT;
     ```
  5. UI displays green `ACTION_RECEIPT` with Ticket #412; TTS announces *"Ticket 412 has been created."*
* **Integration Gate (Checkpoint 3 — 16:45):** Spoken ticket creation commits atomically to Supabase; replaying the same request fails with HTTP 409 Conflict; parameters tampered post-readback abort with 0 rows mutated.

---

### Stage 9: Security & Operational Hardening (16:45–17:30)
* **Goal:** Execute negative test suite, verify error recovery, validate secret isolation, and confirm zero raw audio on disk.
* **Owners:** Teammate A, B, and C collectively.
* **Checks Executed:**
  * Cross-scope ticket query returns 0 rows (`TC-TMP-05`).
  * Replayed `ActionGrant` fails atomic lock (`TC-TMP-12`).
  * Inactivity timer at 90s purges server session and wipes client DOM (`TC-TMP-15`).
  * Host file system inspection confirms zero `.wav` files saved to disk.
  * Vite bundle inspection confirms zero Supabase service keys or DetectifAI tokens exposed.
* **Integration Gate:** Full 17-test security acceptance matrix passes without regressions.

---

### Stage 10: External Access, Demo Rehearsal & Submission (17:30–18:30)
* **Goal:** Expose kiosk via public HTTPS tunnel, rehearse live presentation, and submit 5-slide deck.
* **Owners:** Teammate B (Kiosk Host / Slides) + Teammate A & C (Live Rehearsal).
* **Deliverables:**
  * Cloudflare Tunnel or ngrok endpoint running over HTTPS with working microphone permissions on remote mobile/laptop devices.
  * 5-Slide Deck finalized in exact mandated order:
    1. **Problem:** Vulnerability of shared voice AI kiosks lacking verification and separation of reasoning from execution.
    2. **Solution:** IntentLock zero-login helpdesk with DetectifAI dual checks and parameter-bound action grants.
    3. **DetectifAI:** Live integration architecture with Audio Deepfake Detection and 1:1 Speaker Verification.
    4. **Impact:** Neutralizing prompt injections, preventing cross-employee leaks, protecting enterprise database state.
    5. **Scale:** Roadmap to air-gapped microservices (Option A), multi-modal biometric gating, and enterprise ITSM integration.
  * Two complete dry-run rehearsals executed without resetting the database manually.
* **Exit Gate:** Public link accessible to judges without login; 5-slide PDF submitted to hackathon portal before deadline.

---

### Stage 11: Day 2 Finalist Extensions (Conditional — Post-Day 1)
* **Scope:** Enhancements built only if the team advances to Day 2 finals:
  1. Secondary action: `update_ticket_status` with optimistic locking version checks.
  2. Protected PDF preview viewer with 30s signed streaming endpoints.
  3. Advanced voice barge-in / acoustic echo cancellation tuning.
  4. Rigorous evaluation of Option B local embeddings with explicit consent manifests.
* **Invariant:** No Stage 11 feature may be added on Day 1 at the expense of demo stability.

---

## F. Master Day 1 Schedule & Parallel Workstreams

```mermaid
gantt
    title IntentLock Day 1 Implementation Schedule (16 October 2026)
    dateFormat HH:mm
    axisFormat %H:%M

    section Teammate A (Backend/Security)
    API Kit & Inauguration          :done,    09:00, 10:00
    FastAPI & Supabase Groundwork   :active,  10:00, 11:00
    Public Turn & Persona Seeding   :         11:00, 13:30
    DetectifAI Dual Checks Core     :         13:30, 15:00
    Protected Executor Atomic Tx    :         15:45, 16:45
    Security Tests & Hardening      :         16:45, 17:30

    section Teammate B (Product/Frontend)
    Transit & Arrival               :done,    09:00, 11:00
    Kiosk Workspace UI Foundation   :active,  11:00, 12:30
    Lunch & Contract Alignment      :         12:30, 13:00
    Typed Result Blocks & Recharts  :         13:00, 15:00
    React Flow Telemetry Canvas     :         15:00, 16:15
    UI Polish, Rehearsal, Slides    :         16:45, 18:30

    section Teammate C (Speech/AI)
    Transit & Arrival               :done,    09:00, 11:00
    Speech Pipeline & Qwen Benchmark:active,  11:00, 12:30
    Public Voice Turn Integration   :         12:30, 13:30
    Voice Enrollment & Normalization:         13:30, 14:30
    LLM Intent Parser & Readback    :         14:30, 15:45
    TTS Feedback & Audio Tuning     :         15:45, 16:45
    Demo Rehearsal & Presentation   :         17:30, 18:30
```

### Critical Synchronization Checkpoints
1. **Checkpoint 0 (11:00):** Contract Freeze. A delivers API contracts, DB connection strings, and DetectifAI formats to B & C.
2. **Checkpoint 1 (12:30):** First Public Voice Turn. Browser mic captures voice $\rightarrow$ Whisper transcribes $\rightarrow$ FAQ retrieved $\rightarrow$ Kokoro speaks.
3. **Checkpoint 2 (15:00):** Biometric Identity Gate. Real DetectifAI dual checks gate session creation; wrong voice blocked; genuine voice creates 90s session.
4. **Checkpoint 3 (16:45):** Protected Write Complete. Exact readback confirmed $\rightarrow$ single-use grant minted $\rightarrow$ atomic commit in PostgreSQL $\rightarrow$ receipt rendered.
5. **Checkpoint 4 (17:30):** Feature Freeze. Zero new code. External Cloudflare tunnel verified; dry run rehearsal on secondary laptop/phone.

---

## G. Critical-Path Dependency Graph

```mermaid
flowchart TD
    Kit["09:00: API Kit Received (A)"] --> Bootstrap["10:00: FastAPI & DB Bootstrap (A)"]
    
    Arrival["11:00: B & C Arrive"] --> ContractFreeze["11:00: Contract Freeze Checkpoint"]
    Bootstrap --> ContractFreeze
    
    ContractFreeze --> UI_Foundation["11:00: React Workspace (B)"]
    ContractFreeze --> Speech_Setup["11:00: Whisper + Qwen3 Setup (C)"]
    
    UI_Foundation & Speech_Setup --> PublicTurn["12:30: Checkpoint 1 - Public Voice Turn"]
    
    PublicTurn --> PersonaSeed["12:30: Seed Org Personas (A)"]
    PublicTurn --> DualBiometrics["13:30: DetectifAI Integration (A + C)"]
    
    PersonaSeed & DualBiometrics --> BiometricGate["15:00: Checkpoint 2 - Biometric Session Gate"]
    
    BiometricGate --> ScopedUI["15:00: Scoped Tables & Recharts (B)"]
    BiometricGate --> AgentReadback["15:00: Spoken Readback Guard (C)"]
    
    ScopedUI & AgentReadback --> ProtectedWrite["16:45: Checkpoint 3 - Protected Write & Receipt (A)"]
    
    ProtectedWrite --> SecurityHarden["16:45: Security Test Suite (All)"]
    SecurityHarden --> FeatureFreeze["17:30: Feature Freeze & Tunnel Launch"]
    FeatureFreeze --> Rehearsal["17:30-18:30: Rehearsal & Deck Submission"]
```

---

## H. Scope-Cut Matrix and Contingency Fallbacks

If development encounters delays, the team executes these pre-agreed scope cuts without debating during build hours:

| Trigger Condition | Delayed Capability | Fallback Action & Treatment | Decision Owner | Cut Deadline |
| :--- | :--- | :--- | :--- | :--- |
| Local Qwen3 4B inference $>1.8\text{s}$ or corrupts JSON. | Local LLM Intent Parsing | Switch immediately to dormant OpenAI `gpt-4o-mini` adapter. Audio stays local; prompts stripped of PII. | Speech Lead (C) | 12:00 |
| `@xyflow/react` node layout has rendering bugs. | Interactive Dynamic DAG | Downgrade to static vertical CSS timeline card; **preserve real backend event data**. | Product Lead (B) | 16:00 |
| Supabase connection latency spikes $>800\text{ms}$. | Multi-table joins | Flatten demo queries to single-table lookup; keep SQL scoping intact. | Backend Lead (A) | 14:00 |
| Time is past 16:00 and Protected Write is incomplete. | Secondary Actions & Status Updates | **CUT ENTIRELY:** Drop ticket updates; implement strictly 1 canonical action (`create_ticket`). | Team Lead (A) | 16:00 |
| Venue Wi-Fi drops external tunnel connections. | Remote Cloudflare Tunnel | Switch presentation to local laptop screen; present judges with local browser instance. | Product Lead (B) | 17:30 |
| DetectifAI API rate limit reaches 80% of quota. | Real-time turn checks | Conserve remaining calls strictly for live judging turns; use labeled dev stubs during testing. | Backend Lead (A) | 15:30 |

---

## I. Resource, Hardware, and API Budget Management

### 1. API Quota & Cost Guardrails
* **DetectifAI APIs (Deepfake & Speaker Verification):**
  * Exact quota is `TBD — Official API Kit` (received at 09:00).
  * Strategy: Zero redundant calls during development. Developer unit tests run against local labeled mock responses (`mock_detectifai.py`).
  * Real DetectifAI calls reserved strictly for Stage 2 smoke test (1 call), Stage 5 integration (3 calls), Stage 9 validation (5 calls), and live judge demonstration (~4 calls).
* **OpenAI API Credit Budget:**
  * Strict ceiling: **USD $15.00 total spend**.
  * Use local Qwen3 4B for all development turns.
  * Enable OpenAI only if local model fails latency benchmark, configured with minimal token bounds (`max_tokens: 150`).

### 2. Demonstration Laptop Resource Allocation
* **Host Machine:** Dedicated Windows development laptop (RTX GPU, 16GB+ RAM).
* **VRAM Apportionment:**
  * `faster-whisper` INT8 (CTranslate2): ~1.2 GB VRAM.
  * `Kokoro-82M` TTS Engine: ~0.8 GB VRAM.
  * Local Qwen3 4B: ~3.2 GB VRAM.
  * Total Allocated: ~5.2 GB VRAM (well within 8GB/16GB GPU ceiling).
* **Contention Invariant:** Whisper STT, Qwen inference, and Kokoro TTS execute in strict sequential turn phases; they never run concurrent matrix multiplications on the GPU.

---

## J. Traceability and Requirements Matrix

| PRD Req ID | PRD Title | Stage | Component Owner | Implementation Proof | Live Demonstration Test |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **FR-01** | Zero-Login Public Mode | Stage 3 | Teammate B / A | `PolicyEngine.evaluate(role='public')` | Visitor asks public FAQ; zero login prompt shown. |
| **FR-02** | Ephemeral Audio Capture | Stage 1, 3 | Teammate B / C | RAM Buffer `io.BytesIO` | File system check confirms zero audio files on disk. |
| **FR-03** | Local Speech Recognition | Stage 3 | Teammate C | faster-whisper CTranslate2 | Spoken prompt transcribes accurately in <800ms. |
| **FR-04** | Grounded Conversational AI | Stage 6 | Teammate C | Pydantic Schema Validator | Model emits structured `ToolProposal`; no arbitrary SQL. |
| **FR-05** | Real Deepfake Detection | Stage 5 | Teammate A | DetectifAI Audio Deepfake API | Cloned voice flagged as `SUSPICIOUS`; session denied. |
| **FR-06** | Real Speaker Verification | Stage 5 | Teammate A | DetectifAI 1:1 Speaker API | Enrolled voice matches (`MATCH`); wrong voice rejected. |
| **FR-07** | Sliding Session Vault | Stage 5 | Teammate A | In-Memory TTL Dict | Session expires after 90s; DOM purges private cards. |
| **FR-08** | Scoped Resource Queries | Stage 4, 7 | Teammate A | Parameterized SQL `WHERE` | Charlie views own tickets; Bob Miller tickets hidden. |
| **FR-09** | Spoken Readback Guard | Stage 6, 8 | Teammate C / B | Policy Confirmation Hook | Assistant speaks exact parameters; waits for "yes". |
| **FR-10** | Single-Use Action Grants | Stage 8 | Teammate A | `action_grants` SHA-256 Table | Replayed grant fails; tampered parameters abort. |
| **FR-11** | Protected Atomic Write | Stage 8 | Teammate A | PostgreSQL `asyncpg` Tx | Grant consumed + ticket inserted + audit logged in 1 tx. |
| **FR-12** | Truthful Trust Receipt | Stage 8 | Teammate B | ResultBlock Component | Green card displays real committed PostgreSQL `ticket_id`. |
| **FR-13** | Live Trust Trace DAG | Stage 7, 8 | Teammate B | `@xyflow/react` Canvas | Node states update live from server-sent event stream. |
| **FR-14** | Local Speech Synthesis | Stage 3, 6 | Teammate C | Kokoro-82M TTS Engine | Assistant speaks concise conversational summaries. |

---

## K. Truthful Demonstration Checklist & Evidence Guide

During live judging, the team proves each architectural claim using observable system evidence:

| Claim Made to Judges | How We Prove It Live | What Judges Observe on Screen | What Backend Logs Prove |
| :--- | :--- | :--- | :--- |
| **1. "No Initial Login Required"** | Open fresh incognito window. | Clean public kiosk welcome screen; zero password boxes. | Ingress log: `session_id: null`, `actor: anonymous`. |
| **2. "Real DetectifAI Dual Voice Checks"** | Unenrolled team member speaks claimed ID `EMP-1001`. | Red Alert: *"Biometric Verification Failed — Voice Mismatch"*. | Server logs real DetectifAI JSON response: `speaker_verdict: "MISMATCH"`. |
| **3. "Genuine Voice Authenticates"** | Consented enrolled member speaks `EMP-1001`. | Green Status Pill: *"Session Active: Charlie Davis (EMP-1001)"*. | Server logs real DetectifAI JSON response: `deepfake: "PASS", speaker: "MATCH"`. |
| **4. "Strict Horizontal Data Isolation"** | Charlie Davis asks for Bob Miller's ticket. | Muted Card: *"No tickets found in your assigned scope"*. | SQL query log: `SELECT * FROM tickets WHERE owner_id = 'EMP-1001'`. 0 rows. |
| **5. "No LLM Direct Database Access"** | Inspect source code with judges. | `LLMAdapter` imports zero database packages; emits JSON only. | Code inspection confirms zero SQL strings in model prompt. |
| **6. "Exact-Action Readback Binding"** | Assistant speaks proposed ticket parameters. | Confirmation Modal displaying title, category, priority. | Backend computes $\text{params\_hash} = \text{SHA-256}(\text{Canonical JSON})$. |
| **7. "Atomic Transaction & Truthful Receipt"** | User affirms *"Yes"*; kiosk commits. | Green Trust Receipt Card displaying Ticket #412 and Audit #88192. | Supabase Table Editor: Ticket #412 inserted; `action_grants.is_consumed = TRUE`. |
| **8. "Replay & Tamper Resistance"** | Re-submit consumed grant via curl. | Kiosk displays HTTP 409 Conflict: *"Grant Already Consumed"*. | PostgreSQL log: `UPDATE action_grants` affected 0 rows; tx aborted. |
| **9. "Zero Local Audio Storage"** | Run `ls -la` on server `/tmp` directory. | Zero `.wav` or audio files present on local machine. | Code inspection: RAM buffer wiped via `buffer.truncate(0)`. |
| **10. "Automatic Session Expiry"** | Wait 90 seconds without speaking. | Screen wipes private ticket card; resets to Public Welcome. | Ingress log: subsequent request returns `HTTP 401 Unauthorized`. |

---

## L. Open Questions Matrix

The following operational questions must be finalized upon receiving the API kit at 09:00:

| Priority | Question / Uncertainty | Source of Answer | Impact on Build | Default Assumption Until Resolved |
| :--- | :--- | :--- | :--- | :--- |
| **1 (Urgent)** | What are the exact HTTP endpoints, auth headers, and audio format requirements for DetectifAI? | Official API Kit (09:00) | Determines `detectifai_client.py` payload construction. | Assume 16kHz WAV multipart upload with Bearer token. |
| **2 (Urgent)** | What is our exact API call quota for deepfake detection and speaker verification? | Official API Kit / Organizers | Dictates test call budgeting and caching strategy. | Assume tight quota ($\le 50$ calls); use mock stubs in dev. |
| **3 (High)** | What is the exact registered Track 3 use-case title from event registration (Rule 3.7)? | Team Lead / Portal | Ensures slides and demo match registered submission. | Marked **OPEN**; align title on Slide 1 before submission. |
| **4 (High)** | Does DetectifAI provide an enrollment API, or are reference profiles pre-provisioned via a portal? | Official API Kit | Determines whether Stage 5 executes API enrollment or uses static keys. | Assume API enrollment endpoint taking audio sample + ID. |
| **5 (Medium)** | Does the venue Wi-Fi block outbound Cloudflare Tunnels or WebSocket ports? | Venue Network Test (10:00) | Determines external judge link reachability. | Fall back to mobile hotspot or ngrok HTTP tunnel. |
| **6 (Medium)** | What is the official deadline for final slide deck and link submission? | Organizer Briefing | Determines feature freeze and rehearsal buffer. | Assume 18:00 IST submission cutoff. |

---

## M. Final "First Actions Tomorrow Morning" Checklist

*Read this 60-second checklist at 08:50 IST before opening laptops:*

### Teammate A (Backend & Security Lead — Arrives 09:00)
1. **09:00–10:00:** Receive API kit; record endpoint URLs, auth tokens, audio constraints, and quota limits in `.env.local`.
2. **10:00–10:30:** Bootstrap FastAPI repo; configure Supabase connection pooler (`port 6543`); verify `SELECT 1`.
3. **10:30–11:00:** Execute minimal DetectifAI live smoke test using own consented voice; freeze canonical API contract for B & C.

### Teammate B (Product & Frontend Lead — Arrives 11:00)
1. **11:00–11:15:** Pull repo; review frozen API contract; verify Vite dev server starts on port `5173`.
2. **11:15–12:30:** Build responsive kiosk workspace shell: mic dock, state pills, and typed result component slots.
3. **12:30–13:00:** Integrate Checkpoint 1: Wire browser mic audio POST to `/api/v1/voice/turn` and verify mock FAQ card renders.

### Teammate C (Speech & AI Lead — Arrives 11:00)
1. **11:00–11:15:** Pull repo; benchmark local `faster-whisper` and Qwen3 4B; record turn latency on presentation machine.
2. **11:15–12:30:** Wire Web Audio capture handoff to local Whisper STT and Kokoro-82M TTS audio player.
3. **12:30–13:00:** Integrate Checkpoint 1: Verify spoken FAQ query outputs audible TTS response agreeing with UI card.
