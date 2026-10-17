# IntentLock — Person 2 Stage 3: Structured Semantic Planning & Operation Registry
**Author:** Sharan (Person 2) — Intelligence, Semantic Planning & Results  
**Baseline Commit:** `d189664ddfe789da0b22e1269e5ba0d42fdb4bf6`  
**Date:** 2026-10-17  
**Status:** Implemented Locally & Verified  

---

## 1. Executive Summary & Design Invariants

Stage 3 consolidates all supported helpdesk capabilities into an authoritative, single-source Operation Registry (`backend/services/operation_registry.py`) and introduces a controlled multi-step interpretation pipeline (`backend/services/semantic_orchestrator.py`).

### Key Invariants:
1. **No Authority or Guessed Permissions:** The registry and orchestrator define semantic shapes, required arguments, and category definitions. They never grant permissions or evaluate provider verdicts.
2. **Deterministic Fast Path:** Exact control commands (`help`, `confirm`, `cancel`, `back`) are matched deterministically with strict negation (`"do not confirm"` is never confirm) and quote protection (`"create ticket titled cancel"` is not cancel).
3. **No Private Queries in Public Help:** Commands containing private keywords (`"my"`, `"salary"`, `"profile"`, `"tickets"`) are never misrouted to `PUBLIC_FAQ`.
4. **Safe Allowlisted Context:** `PlannerContext.active_filters` is strictly projected through an allowlist of 12 known filter dimensions. Arbitrary dictionary strings, tokens (`jwt`, `session`, `token`), and credentials (`api_key`, `db_password`) are purged before prompt assembly.
5. **Bounded Compound Execution:** Multi-intent compound requests are bounded to read operations. Compound mutations (e.g. creating a ticket and updating phone in a single step) are rejected.

---

## 2. Supported Operation Registry (`operation_registry.py`)

All 18 operations are indexed with category, parameter contracts, and compatible frontend card renderers:

| Operation | Category | Required Args | Optional Args | Context Prerequisite | Compatible Frontend Blocks |
|---|---|---|---|---|---|
| `help` | Read | None | None | None | `PUBLIC_FAQ` |
| `profile` | Read | None | `entity`, `actor_claim` | None | `EMPLOYEE_PROFILE`, `DENIAL_BANNER` |
| `team_table` | Read | None | `descendants`, `dept`, `loc` | Manager root | `DATA_TABLE`, `DENIAL_BANNER` |
| `team_count` | Read | None | `descendants` | Manager root | `TEAM_METRIC_CHART`, `DENIAL_BANNER` |
| `org_tree` | Read | None | `descendants`, `entity` | Manager root | `ORG_TREE`, `DENIAL_BANNER` |
| `ticket_list` | Read | None | `filters`, `dates`, `person` | None | `TICKET_LIST`, `DENIAL_BANNER` |
| `ticket_chart`| Read | None | `group_by`, `view`, `sla` | None | `TEAM_METRIC_CHART`, `DENIAL_BANNER` |
| `rechart` | Navigation | None | `view`, `group_by`, `filters` | Active ticket result | `TEAM_METRIC_CHART`, `DENIAL_BANNER` |
| `back` | Navigation | None | None | Previous result snapshot | Profile, Table, Tree, Ticket cards |
| `clarify` | Clarification| None | `unresolved_location`, `entity`| None | `PUBLIC_FAQ`, `DENIAL_BANNER` |
| `create_ticket`| Proposal | `value` | `priority_filter` | Verified actor | `READBACK_CONFIRMATION`, `DENIAL_BANNER` |
| `update_ticket`| Proposal | `ticket_id`, `field`, `value`| None | Verified actor | `READBACK_CONFIRMATION`, `DENIAL_BANNER` |
| `comment_ticket`| Proposal| `ticket_id`, `value` | None | Verified actor | `READBACK_CONFIRMATION`, `DENIAL_BANNER` |
| `confirm` | Confirmation| None | None | Active pending draft | `ACTION_RECEIPT`, `DENIAL_BANNER` |
| `cancel` | Cancellation| None | None | None | `PUBLIC_FAQ` |
| `compound` | Compound | None | `entity`, `filters` | None (max depth 3) | `EMPLOYEE_PROFILE`, `TICKET_LIST` |
| `headcount` | Read | None | `scope`, `loc`, `dept` | None | `TEAM_METRIC_CHART`, `DATA_TABLE` |
| `update_contact`| Proposal | `field="phone"`, `value` | `entity` | Self-only actor | `READBACK_CONFIRMATION`, `DENIAL_BANNER` |

---

## 3. Controlled Interpretation Pipeline (`semantic_orchestrator.py`)

```mermaid
flowchart TD
    IN[Raw Utterance & Context] --> VAL[A. Validate & Bound Input (len <= 1000)]
    VAL --> CLAIM[B. Extract & Normalize Actor Claim]
    CLAIM --> EXACT{C. High-Certainty Exact Command?}
    EXACT -->|Help, Confirm, Cancel, Back| DET[Return Deterministic Plan]
    EXACT -->|No / Flexible| PLAN[D. OpenAI Structured Output Plan]
    PLAN --> SAN[E. Allowlisted Context Projection]
    SAN --> BOUNDS[F. Verify Bounds, Registry & Claim Grounding]
    BOUNDS --> OUT[Validated IntentPlan]
```

### Deterministic Exact Matching Rules:
- **`help`**: Triggers ONLY on explicit help queries without private terms. Utterances like *"Help me view EMP-1001's profile"* are routed to semantic planning.
- **`confirm`**: Triggers on exact confirmation utterances. If negated (`"do not confirm"`, `"don't confirm"`), confirmation is rejected.
- **`cancel`**: Triggers on exact cancel utterances. Quotes are stripped before check to prevent `"Create ticket titled 'cancel error'"` from cancelling proposals.
- **`back`**: Triggers on explicit back navigation.

---

## 4. Acceptance Verification & Test Results

All 10 tests in `tests/test_semantic_planning.py` passed offline (`INTENTLOCK_OFFLINE_TESTS=1`):

```text
============================= test session starts =============================
platform win32 -- Python 3.10.11, pytest-8.4.2, pluggy-1.6.0
rootdir: C:\SHARAN PROJECTS\IntentLock
collected 10 items

tests\test_semantic_planning.py ..........                               [100%]

============================= 10 passed in 16.12s =============================
```

### Key Test Outcomes:
- `test_operation_registry_schema_parity`: Confirms all 18 operations are indexed.
- `test_exact_public_help_versus_private_query`: Confirms private requests are never misclassified as public help.
- `test_negated_confirmation_and_cancellation`: Proves negation prevents unintended confirm/cancel execution.
- `test_quoted_content_keyword_protection`: Protects against keyword hijacking inside quoted ticket descriptions.
- `test_context_allowlisting_and_nested_secret_rejection`: Validates that sensitive tokens (`api_key`, `token`, `password`) are purged from context projections.
- `test_no_extra_model_request_for_exact_local_commands`: Confirms exact commands bypass LLM network requests.
- `test_flexible_request_routes_to_planner`: Validates routing of complex requests to structured planner.
- `test_model_refusal_or_provider_failure_returns_clarify`: Safe fail-closed behavior on model timeout or refusal.
- `test_compound_read_versus_disallowed_mutation`: Rejects compound mutations while allowing compound reads.
- `test_claim_grounding_integration_in_orchestrator`: Strips hallucinated claims without utterance grounding.

---

## 5. Gateway Integration Request for Person 1

- **Entrypoint Provided:** `backend/services/semantic_orchestrator.py`:
  ```python
  async def interpret_request(
      utterance: str,
      context: Optional[PlannerContext] = None,
      planner_adapter: Optional[Any] = None,
  ) -> IntentPlan:
  ```
- **Proposed Integration in `main.py`:**
  Replace the two-phase `parse_local(...)` followed by `if plan.operation == "clarify": plan_request(...)` with a single call to `interpret_request(transcript_text, context=ctx, planner_adapter=answer_adapter)`.
- **Wiring Status:** Implemented locally and tested in Person 2 domain; legacy `parse_local` remains 100% backward-compatible.
