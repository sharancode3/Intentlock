# IntentLock — Person 2 Proposed Contracts & Interfaces
**Author:** Sharan (Person 2)  
**Target Stakeholders:** Person 1 (Trust, Persistence & Gateway), Person 3 (Frontend & Speech)  
**Date:** 2026-10-17  
**Status:** PROPOSED & READY FOR COORDINATION (No Code Mutations)

---

## 1. Overview & Architectural Principles

To ensure zero merge conflicts and seamless integration across teammates:
1. **Backward Compatibility:** All existing field names and discriminators are preserved. Additions are strictly optional with conservative fallbacks.
2. **Explicit Trust Boundaries:** No model-generated code, SQL, or permission elevations. Person 1 owns authentication and authorization; Person 2 owns semantics and query interpretation; Person 3 owns presentation.
3. **Four Canonical Response States for Every Contract:**
   - **Success (`200 OK`)**: Authorized payload delivered with matching spoken summary.
   - **Clarification (`200 OK`, `clarification_reason`)**: Amber guidance without misleading success or false-empty records.
   - **Denial (`403 Forbidden` / `denied`)**: Explicit policy denial with honest reasoning.
   - **Proposal / Receipt**: Two-phase protected modification lifecycle.

---

## 2. Contract Specifications

### Contract 1: Explicit Spoken Identity Claim vs. Query Target
* **Owner & Location:** Person 1 (`backend/main.py:749, 863-872`) and Person 2 (`backend/services/conversation_dispatch.py:32-54`)
* **Current Signature:**
  - Transport: `candidate_employee_id: Optional[str]` via multipart form field.
  - Regex in `main.py`: `re.search(r"\b(?:i am|my employee id is|this is)\s+((?:EMP|RND|EXE)[-_ ]?\d{4})\b")`.
  - Schema: `IntentPlan.entity: Optional[str]`.
* **Current Consumers:** `VoiceGateway.handle_voice_turn()`, `ConversationDispatcher.dispatch()`.
* **Desired Behavior:** Clean separation of actor claim (spoken employee ID) from requested query targets (e.g. *"Show EMP-2001's tickets"*), preventing target entities from hijacking the authenticated actor.
* **Minimal Proposed Extension:**
  Add optional `actor_claim: Optional[str]` to `IntentPlan` while keeping `entity` strictly for query target references:
  ```python
  class IntentPlan(BaseModel):
      operation: Operation
      actor_claim: Optional[str] = Field(default=None, description="Explicit employee ID claimed by speaker, e.g. EMP-4002")
      entity: Optional[str] = Field(default=None, description="Target entity ID or name referenced in query, e.g. EMP-2001")
      ...
  ```
* **Compatibility:** Backward compatible; if `actor_claim` is absent, gateway falls back to existing regex extraction.
* **Other Owner Action:** Person 1 reads `plan.actor_claim` in `main.py` when evaluating candidate identity.
* **Status:** Proposed.

---

### Contract 2: Planner Context Input & IntentPlan Output
* **Owner & Location:** Person 2 (`backend/adapters/openai_answer_adapter.py:70-101`)
* **Current Signature:**
  `plan_request(utterance: str, has_current_result: bool) -> Optional[IntentPlan]`
* **Current Consumers:** `backend/main.py:768`
* **Desired Behavior:** Provide the planner with compact conversational context so follow-ups like *"Show their projects"* or *"Open the second ticket"* understand active references without fragile regexes.
* **Minimal Proposed Extension:**
  ```python
  class PlannerContext(BaseModel):
      has_active_result: bool = False
      source_kind: Optional[Literal["tickets", "employees", "profile", "tree"]] = None
      selected_ticket_id: Optional[str] = None
      selected_employee_id: Optional[str] = None
      active_filters: Dict[str, Any] = Field(default_factory=dict)

  async def plan_request(utterance: str, context: Optional[PlannerContext] = None) -> Optional[IntentPlan]:
  ```
* **Compatibility:** Default `context=None` maintains full backward compatibility with current `has_current_result` callers.
* **Other Owner Action:** Person 1 passes `PlannerContext` built from `ConversationState` in `main.py`.
* **Status:** Proposed.

---

### Contract 3: Authorized Entity & Scope Resolution
* **Owner & Location:** Person 2 (`backend/services/conversation_dispatch.py:414-440`)
* **Current Signature:**
  `_resolve_profile_target(actor_id: str, phrase: Optional[str], state: ConversationState) -> Optional[str]`
* **Current Consumers:** `ConversationDispatcher.dispatch()` for `profile`, `tickets`, `headcount`.
* **Desired Behavior:** Resolves target references (`"my manager"`, `"first person"`, name queries) strictly within permitted scope. Rejects out-of-scope targets with honest denials.
* **Minimal Proposed Extension:**
  Refactor into a dedicated `EntityResolver` module supporting employee and ticket ordinals:
  ```python
  class EntityResolutionResult(BaseModel):
      resolved_id: Optional[str]
      resolution_kind: Literal["self", "manager", "direct_report", "ordinal", "explicit", "unresolved"]
      error_message: Optional[str] = None
  ```
* **Status:** Proposed for Person 2 internal module in Stage 4.

---

### Contract 4: Grounded Query & Metric Facts Object
* **Owner & Location:** Person 2 (`backend/services/conversation_dispatch.py:133-138`)
* **Current Signature:**
  `block(kind: str, title: str, payload: dict, sensitive: bool = True) -> GenericResultBlock`
* **Current Consumers:** Person 3 (`frontend/src/types/payloads.ts`)
* **Desired Behavior:** Strict alignment of facts between visual payloads, assistant narration, and speech audio.
* **Minimal Proposed Extension:**
  Standardize `kpis` and `summary` schema in `GenericResultBlock.payload`:
  ```typescript
  // Shared contract representation
  interface GroundedMetricPayload {
    chart_type: 'BAR' | 'PIE' | 'LINE' | 'AREA';
    title: string;
    unit: string;
    data: Array<{ label: string; count: number }>;
    kpis: {
      total_evaluated: number;
      items: Array<{ label: string; value: number | string }>;
    };
  }
  ```
* **Status:** Already available and matching frontend `TeamMetricChartPayload`.

---

### Contract 5: Selected-Entity & Click Feedback Action
* **Owner & Location:** Person 3 (`frontend/src/LiveApp.tsx`) and Person 2 (`backend/services/conversation_dispatch.py:68-89`)
* **Current Signature:**
  - Frontend: `handleResultAction("select_ticket", { ticket_id })`
  - Backend: `ConversationState.selected_ticket_id`
* **Desired Behavior:** Support clicking tree nodes or table rows to select an employee so voice follow-ups (*"Show their profile"*, *"Show their tickets"*) resolve that clicked person.
* **Minimal Proposed Extension:**
  Add `selected_employee_id: Optional[str] = None` to `ConversationState`:
  ```python
  @dataclass
  class ConversationState:
      actor_id: str
      snapshots: Dict[str, ResultSnapshot] = field(default_factory=dict)
      active_id: Optional[str] = None
      previous_id: Optional[str] = None
      selected_ticket_id: Optional[str] = None
      selected_employee_id: Optional[str] = None
      last_accessed: float = field(default_factory=time.time)
  ```
* **Other Owner Action:**
  - Person 3 wires tree node click to emit `onAction("select_employee", { employee_id })`.
  - Person 1 routes `action` submissions in `main.py` to update `selected_employee_id`.
* **Status:** Awaiting agreement with Person 1 and Person 3.

---

### Contract 6: Protected Action Proposal & Readback
* **Owner & Location:** Person 1 (`TicketActionStore.propose()`) and Person 2 (`conversation_dispatch.py:578-595`)
* **Current Signature:**
  `propose(actor_id, session_id, operation, ticket_id, params, report_ids, audio_digest) -> dict`
* **Current Consumers:** `dispatch()` for `create_ticket`, `update_ticket`, `comment_ticket`, `update_contact`.
* **Desired Behavior:** Exact parameter readback, SHA-256 manifest hash generation, single-use action grant insertion, and `READBACK_CONFIRMATION` payload generation.
* **Status:** Already established and verified in Stage 0 remediation.

---

### Contract 7: Multi-Result Response Block Delivery
* **Owner & Location:** Person 1 (`backend/models/turn.py:VoiceTurnResponse`), Person 2 (`conversation_dispatch.py:532`), Person 3 (`frontend/src/components/workspace/ResultHost.tsx`)
* **Current Signature:**
  ```python
  class VoiceTurnResponse(BaseModel):
      primary_result_id: Optional[str] = None
      result_block: Optional[GenericResultBlock] = None
      result_blocks: Optional[List[GenericResultBlock]] = None
  ```
* **Current Consumers:** `frontend/src/components/workspace/ResultHost.tsx:31-70` (renders tab bar when `result_blocks.length > 1`).
* **Desired Behavior:** Preserve all authorized blocks generated during compound queries and allow seamless tab switching.
* **Status:** Already available and verified in `test_compound_query_emits_multiple_result_blocks`.

---

## 3. Representative Contract Examples

### Example A: Successful Query (`team_count`)
```json
{
  "status": "success",
  "transcript": "How many direct reports do I have?",
  "assistant_message": "Arvind Rao has 3 direct reports.",
  "spoken_summary": "Arvind Rao has 3 direct reports.",
  "primary_result_id": "blk_a1b2c3d4",
  "result_block": {
    "id": "blk_a1b2c3d4",
    "type": "TEAM_METRIC_CHART",
    "title": "Direct reports",
    "payload": {
      "chart_type": "BAR",
      "title": "Direct reports",
      "unit": "people",
      "data": [{ "label": "Direct reports", "count": 3 }],
      "kpis": { "items": [{ "label": "Direct reports", "value": 3 }] }
    }
  }
}
```

### Example B: Clarification Query (Unknown Location)
```json
{
  "status": "clarification",
  "transcript": "How many employees are in Tulum?",
  "assistant_message": "I heard 'Tulum' as the location. Our demo directory only covers Bengaluru. Would you like the headcount for Bengaluru?",
  "spoken_summary": "I heard 'Tulum' as the location. Our demo directory only covers Bengaluru. Would you like the headcount for Bengaluru?",
  "result_block": null,
  "clarification_reason": "UNRESOLVED_LOCATION"
}
```

### Example C: Policy Denial (Non-Executive Headcount)
```json
{
  "status": "denied",
  "transcript": "Show total company headcount",
  "assistant_message": "Access denied. Organization-wide headcount is restricted to executive leadership.",
  "spoken_summary": "Access denied. Organization-wide headcount is restricted to executive leadership.",
  "result_block": {
    "id": "blk_denial_987",
    "type": "DENIAL_BANNER",
    "title": "Access Denied",
    "payload": {
      "reason": "ACCESS_DENIED",
      "message": "Access denied. Organization-wide headcount is restricted to executive leadership."
    }
  }
}
```

### Example D: Mutation Proposal & Committed Receipt
```json
// 1. Proposal Readback:
{
  "status": "success",
  "transcript": "Update my phone to +91 98765 43210",
  "assistant_message": "No change has been made. Please review and speak exactly: I confirm update contact for EMP-1001: phone to +91 98765 43210",
  "result_block": {
    "id": "blk_draft_1122",
    "type": "READBACK_CONFIRMATION",
    "title": "Contact update readback",
    "payload": {
      "confirmation_id": "draft_abc123",
      "draft": {
        "action": "update_contact",
        "target": "EMP-1001",
        "params": { "field": "phone", "value": "+91 98765 43210" },
        "summary_readback": "I confirm update contact for EMP-1001: phone to +91 98765 43210"
      },
      "requires_voice_confirmation": true
    }
  }
}

// 2. Committed Receipt:
{
  "status": "success",
  "transcript": "I confirm update contact for EMP-1001: phone to +91 98765 43210",
  "assistant_message": "The change to EMP-1001 was committed as event evt_7788.",
  "result_block": {
    "id": "blk_receipt_4455",
    "type": "ACTION_RECEIPT",
    "title": "Committed contact change",
    "payload": {
      "receipt": {
        "event_id": "evt_7788",
        "action": "update_contact",
        "resource_id": "EMP-1001",
        "storage": "Postgres",
        "committed_at": "2026-10-17T09:30:00Z"
      }
    }
  }
}
```
