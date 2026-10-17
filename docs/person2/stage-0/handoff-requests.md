# IntentLock — Person 2 Cross-Owner Coordination & Handoff Requests
**Author:** Sharan (Person 2)  
**Date:** 2026-10-17  
**Status:** Audit & Interface Requests for Stages 1–5

---

## 1. Requests for Person 1 (Trust, Persistence, Authorization & Gateway)

### Request 1.1: Standardized Spoken Identity Claim in Gateway Transport
- **Concrete Need:** Pass explicit spoken employee ID claims (e.g. *"My employee ID is EMP-4002"*) directly to the gateway's candidate identity evaluation without relying on loose regex matching in `main.py`.
- **Existing Interface:**
  - `POST /api/v1/voice/turn` accepts `candidate_employee_id: Optional[str]` via multipart form.
  - Regex in `backend/main.py:749`: `explicit_self_claim = re.search(r"\b(?:i am|my employee id is|this is)\s+((?:EMP|RND|EXE)[-_ ]?\d{4})\b", text, re.I)`.
- **Proposed Input / Output:**
  - `IntentPlan` produces `actor_claim: Optional[str] = "EMP-4002"`.
  - Person 1's gateway checks `plan.actor_claim` before falling back to regex.
- **Why Needed:** Guarantees that target employee queries (e.g. *"Show EMP-2001's profile"*) are never confused with actor identity claims by the transport layer.
- **What Person 2 Can Do with a Mock While Waiting:** Person 2 can parse and validate `actor_claim` vs `entity` within `IntentPlan` and test against mock gateway fixtures.

### Request 1.2: Enriched Planner Context from Gateway
- **Concrete Need:** Provide `plan_request()` with active snapshot metadata (`source_kind`, `selected_ticket_id`, `selected_employee_id`, and `filter_state`).
- **Existing Interface:**
  `OpenAIAnswerAdapter.plan_request(utterance: str, has_current_result: bool) -> Optional[IntentPlan]` (`openai_answer_adapter.py:70`).
- **Proposed Input / Output:**
  ```python
  class PlannerContext(BaseModel):
      has_active_result: bool
      source_kind: Optional[str]
      selected_ticket_id: Optional[str]
      selected_employee_id: Optional[str]
      filter_state: Dict[str, Any]

  async def plan_request(utterance: str, context: Optional[PlannerContext] = None) -> Optional[IntentPlan]
  ```
- **Why Needed:** Enables the model planner to resolve pronoun and contextual follow-ups (*"Show their projects"*, *"Only urgent ones"*) without guessing.
- **What Person 2 Can Do with a Mock While Waiting:** Person 2 can implement `PlannerContext` internally within `backend/adapters/openai_answer_adapter.py` with backward-compatible defaults (`context=None`).

### Request 1.3: Dynamic Multi-Level Reporting Tree Resolution
- **Concrete Need:** Expose a method in `EmployeeKnowledgeService` that returns all recursive reporting descendants for an actor rather than hardcoding `EMP-4002` special casing.
- **Existing Interface:**
  `EmployeeKnowledgeService.get_direct_reports(employee_id)` returns only 1 level. `conversation_dispatch.py:441` contains hardcoded `actor_id == "EMP-4002"` logic.
- **Proposed Input / Output:**
  `EmployeeKnowledgeService.get_all_descendant_ids(employee_id: str) -> List[str]`
- **Why Needed:** Allows any manager with sub-managers to view their complete permitted organization tree accurately and without code duplication.
- **What Person 2 Can Do with a Mock While Waiting:** Person 2 can mock `get_all_descendant_ids` in tests to develop Stage 4 entity and tree resolution.

---

## 2. Requests for Person 3 (Frontend, Renderers & Speech)

### Request 2.1: Tree Node and Table Employee Row Click Action Dispatch
- **Concrete Need:** Emit a standardized `select_employee` event when a user clicks a node in `OrgTreeCard` or a row in `DataTableCard`.
- **Existing Interface:**
  - `TicketListCard` emits `onAction("select_ticket", { ticket_id })`.
  - `OrgTreeCard` currently only toggles local React view state.
- **Proposed Input / Output:**
  - In `OrgTreeCard.tsx` / `DataTableCard.tsx`:
    `onAction("select_employee", { employee_id: node.id })`
  - Person 1's gateway records this into `ConversationState.selected_employee_id`.
- **Why Needed:** Makes clicks and speech seamlessly continuous. A user can click a person in the tree and speak *"Show their profile"* or *"Show their tickets"*.
- **What Person 2 Can Do with a Mock While Waiting:** Person 2 can simulate `ConversationState(selected_employee_id="EMP-1001")` in backend dispatch tests.

### Request 2.2: Consistent Error & Clarification Badge Presentation
- **Concrete Need:** Render clarification responses (status code 200 with `clarification_reason`) with an amber indicator and clear prompt text, rather than a green success checkmark or blank panel.
- **Existing Interface:**
  `VoiceTurnResponse` emits `status: "clarification"`, `assistant_message`, and `spoken_summary`.
- **Proposed Input / Output:**
  Frontend header / status pill displays amber `Clarification Needed` badge when `response.status === "clarification"`.
- **Why Needed:** Prevents user confusion when an out-of-scope location (e.g. *"Tulum"*) or unsupported request asks for clarification.
- **What Person 2 Can Do with a Mock While Waiting:** Person 2 already emits `status="clarification"` and verifies it in backend regression tests (`test_headcount_and_routing.py`).

---

## 3. Plan for Person 2's Next Stage (Stage 1 & Stage 2)

### Stage 1: Contract Agreement & Shared Fixture Alignment
1. **Define Schema Artifacts:**
   - Formalize `IntentPlan` field additions (`actor_claim`, `selected_id`).
   - Create mock fixtures in `tests/fixtures/` covering the 4 canonical states (Success, Clarification, Denial, Proposal/Receipt).
2. **Offline Unit Verification:**
   - Write unit tests for proposed contracts using mocked gateway and repository fixtures.

### Stage 2: Spoken Identity Claim Decoupling
1. **Decouple Actor Claim from Query Entity:**
   - Update `_parse_single()` in `conversation_dispatch.py` to populate `actor_claim` when an explicit employee ID is stated as identity (*"My employee ID is EMP-4002"*).
   - Ensure query targets (*"Show EMP-2001"*) strictly populate `entity` and leave `actor_claim` null.
2. **Prevent Role Elevation:**
   - Ensure role claims (*"I am the CTO"*) do not set `actor_claim` and route safely to identity clarification.
3. **Regression Guard:**
   - Validate that all existing 161 offline tests continue to pass with 0 regressions.
