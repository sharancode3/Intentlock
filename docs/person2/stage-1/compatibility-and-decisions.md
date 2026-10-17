# IntentLock — Person 2 Stage 1 Compatibility & Architectural Decisions
**Author:** Sharan (Person 2) — Intelligence, Semantic Planning & Results  
**Baseline Commit:** `d189664ddfe789da0b22e1269e5ba0d42fdb4bf6`  
**Date:** 2026-10-17  

---

## 1. Architectural Decisions Made in Stage 1

### Decision 1: Extend `IntentPlan` In-Place with Optional Fields
- **Change:** Added `actor_claim: Optional[str] = None`, `selected_id: Optional[str] = None`, and `filter_action: Optional[Literal["refine", "replace", "clear"]] = None` directly to `IntentPlan`. Added `"phone"` to `IntentPlan.field` allowed Literals.
- **Rationale:** Moving `IntentPlan` to a new module would risk import churn across `openai_answer_adapter.py`, `conversation_dispatch.py`, and test suites. Keeping it canonical in `backend/services/conversation_dispatch.py` preserves all 100% existing import paths.
- **Backward Compatibility:** All new fields default to `None`. Every existing instantiation (including legacy positional and keyword calls) remains completely valid and passes validation.

### Decision 2: Dual-Signature Support for `OpenAIAnswerAdapter.plan_request`
- **Change:** Updated signature to:
  ```python
  async def plan_request(
      self,
      utterance: str,
      has_current_result: Union[bool, PlannerContext] = False,
      context: Optional[PlannerContext] = None,
  ) -> Optional[IntentPlan]:
  ```
- **Rationale:** The production gateway in `backend/main.py:768` currently calls `plan_request(transcript_text, bool(plan_state and plan_state.active_id))`. By allowing `has_current_result` to accept either a `bool` OR a `PlannerContext` object, the gateway continues to work without modification, while tests and future gateway wiring can supply full context.
- **Security Invariant:** `PlannerContext` excludes database credentials, raw audio, full employee records, and policy overrides. It passes only non-sensitive hint tokens (e.g. `active_result=true`, `source_kind=tree`, `selected_employee=EMP-2001`).

### Decision 3: Add `selected_employee_id` to `ConversationState`
- **Change:** Added `selected_employee_id: Optional[str] = None` to `@dataclass ConversationState`.
- **Rationale:** Clicks on tree nodes (`OrgTreeCard`) and table rows (`DataTableCard`) need to persist an employee selection alongside existing ticket selections (`selected_ticket_id`).
- **Backward Compatibility:** Default value `None` ensures that all existing `ConversationState(actor_id=actor_id)` instantiations behave identically.

---

## 2. Owner Agreement Evidence & Status

| Interface Dimension | Owner | Status | Evidence / Agreement Basis |
|---|---|---|---|
| **`IntentPlan` Extensions** | Person 2 | **Implemented Locally** | Verified via `tests/test_semantic_contracts.py`. 0 regressions on existing 42 Person 2 tests. |
| **`PlannerContext` Schema** | Person 2 | **Implemented Locally** | Verified via `test_openai_plan_request_backward_compatible_signatures`. |
| **Actor Claim Transport** | Person 1 | **Proposed to Person 1** | Documented in `person1-integration-request.md`. Gateway currently uses regex extraction in `main.py:749`. |
| **Tree Click Action Emission** | Person 3 | **Proposed to Person 3** | Documented in `person3-integration-request.md`. Frontend currently handles `select_ticket` only. |
| **Protected Proposal Schema** | Person 1 & 2 | **Agreed & Active** | Established in Supabase Stage 0 remediation (`READBACK_CONFIRMATION` with SHA-256 hash). |
| **Result Block Registry** | Person 2 & 3 | **Agreed & Active** | 10 registered card renderers in `frontend/src/components/renderers/index.ts`. |

---

## 3. Deferred Choices (Explicitly Out-of-Scope for Stage 1)

1. **Full Natural Language Routing Rewrite:**
   - Deferred to **Stage 3**. Stage 1 establishes the schema contract and context foundation; it does NOT replace existing local keyword routing or prompt instructions.
2. **Spoken Identity Extraction Pipeline:**
   - Deferred to **Stage 2**. Decoupling regex logic from `_parse_single` and coordinating with Person 1's gateway will take place in Stage 2.
3. **Frontend Tree Click Event Wiring:**
   - Deferred to **Person 3**. Person 2 has prepared the backend state and mock seam; frontend code in `frontend/src/**` is exclusively owned by Person 3.
4. **Recursive Multi-Tier Tree Traversal:**
   - Deferred to **Person 1 / Stage 4**. Querying arbitrary depth reporting trees requires a helper in `EmployeeKnowledgeService`, which is owned by Person 1.

---

## 4. Why Each Source Change Was Necessary

1. **`conversation_dispatch.py` (Line 45):** Added `"phone"` to `IntentPlan.field` Literal.
   - *Necessity:* `update_contact` proposals pass `field="phone"`. Without `"phone"` in the Literal, schema validation raised `ValidationError` when deserializing valid contact update proposals.
2. **`conversation_dispatch.py` (Lines 55–69):** Added `actor_claim`, `selected_id`, `filter_action`, and `PlannerContext`.
   - *Necessity:* Provides typed structures for upcoming Stage 2 spoken entry and Stage 5 context follow-ups without using untyped dictionaries.
3. **`conversation_dispatch.py` (Line 85):** Added `selected_employee_id` to `ConversationState`.
   - *Necessity:* Provides server-side storage for clicked employee nodes.
4. **`openai_answer_adapter.py` (Lines 70–100):** Dual-signature support for `plan_request`.
   - *Necessity:* Accommodates `PlannerContext` while guaranteeing that existing `main.py` callers with a plain boolean continue to execute without breaking.
