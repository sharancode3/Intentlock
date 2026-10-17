# IntentLock — Person 2 Integration Requests for Person 1 (Trust, Persistence & Gateway Owner)
**Author:** Sharan (Person 2) — Intelligence, Semantic Planning & Results  
**Baseline Commit:** `d189664ddfe789da0b22e1269e5ba0d42fdb4bf6`  
**Date:** 2026-10-17  
**Status:** Stage 1 Contract Alignment  

---

## Overview

Person 2 owns semantic parsing, natural language intent modeling, conversation context state, and structured result block generation.  
Person 1 owns the gateway (`backend/main.py`), actor authentication, session management, authorization policies, and Supabase persistence.

To prepare for Person 2 Stage 2 (Identity Claim Decoupling) and Stage 5 (Context Follow-ups) without breaking existing production routes, Person 2 requests the following three backward-compatible integration updates from Person 1.

---

## Request 1: Accept `plan.actor_claim` in Voice Gateway for Candidate Identity Resolution

### 1. Concrete Need
Currently, the voice gateway extracts employee IDs using a strict regex: `_EXTRACT_EMP_REGEX = re.compile(r"(?:emp|employee)[-\s]?(\d{4})", re.IGNORECASE)`.  
If a user says *"I am EMP 4002 and I want to see my tickets"* or *"This is Charlie Davis from engineering"*, regex extraction works only if the literal pattern matches.  
In Person 2 Stage 2, `IntentPlan` exposes a typed `actor_claim: Optional[str] = None` field. The gateway should allow `plan.actor_claim` to serve as a candidate identity for Detectif verification when no session token is present.

### 2. Current Call in `backend/main.py` (Line 749 & 863)
```python
# main.py:749
emp_match = _EXTRACT_EMP_REGEX.search(transcript_text)
if emp_match:
    candidate_emp_id = f"EMP-{emp_match.group(1)}"
```

### 3. Proposed Signature & Logic
```python
# Proposed update in main.py turn handling:
candidate_emp_id = None
if emp_match:
    candidate_emp_id = f"EMP-{emp_match.group(1)}"
elif plan and plan.actor_claim:
    # Use the decoupled semantic actor claim as a candidate for verification
    candidate_emp_id = plan.actor_claim.strip().upper()

# Gateway continues deterministic Detectif speaker check before minting any session
```

### 4. Error Semantics
- If `plan.actor_claim` is formatted incorrectly or does not map to an enrolled employee:
  - Gateway returns `VoiceTurnResponse(status="clarification", clarification_reason="UNKNOWN_IDENTITY", message="Employee ID not recognized.")`.
- If `plan.actor_claim` is present but audio fails Detectif speaker verification:
  - Gateway rejects with `VoiceTurnResponse(status="denied", message="Voice verification failed. Please try speaking again.")`.

### 5. Contract Fixture Reference
- `tests/fixtures/person2/explicit_actor_claim_vs_target.json`
  - Demonstrates decoupling where `actor_claim = "EMP-4002"` (CTO) while `entity = "EMP-2001"` (target employee whose profile is queried).

### 6. What Remains Mocked
In Person 2 tests, the gateway caller and Detectif verification service are mocked. Person 2 never verifies voice authenticity or creates session tokens.

### 7. Dependency
Required for **Person 2 Stage 2** (Spoken Identity Claim Decoupling and Candidate Handoff).

---

## Request 2: Pass `PlannerContext` into `plan_request` in `backend/main.py`

### 1. Concrete Need
The LLM planner in `OpenAIAnswerAdapter.plan_request` requires contextual hints (e.g. active source kind, selected resource ID, active filter summary) to resolve follow-up utterances like *"now filter to only high priority"* or *"show their tickets"*.  
Currently, `main.py:768` passes only a single boolean `has_current_result`.  
Person 2 has implemented a dual-compatible signature in `backend/adapters/openai_answer_adapter.py` that accepts either a `bool` or a `PlannerContext` object.

### 2. Current Call in `backend/main.py` (Line 768)
```python
plan = await answer_adapter.plan_request(
    transcript_text,
    bool(plan_state and plan_state.active_id)
)
```

### 3. Proposed Signature & Invocation
```python
# Construct safe, non-sensitive context hints using canonical state access
from backend.services.conversation_dispatch import PlannerContext

active_snap = plan_state.snapshots.get(plan_state.active_id) if (plan_state and plan_state.active_id) else None

ctx = PlannerContext(
    has_active_result=bool(active_snap is not None),
    source_kind=active_snap.source_kind if active_snap else None,
    selected_ticket_id=plan_state.selected_ticket_id if plan_state else None,
    selected_employee_id=getattr(plan_state, "selected_employee_id", None),
    active_filters=active_snap.filter_state if active_snap else {},
)

plan = await answer_adapter.plan_request(
    transcript_text,
    context=ctx
)
```

### 4. Error Semantics
- If `context` is omitted or `None`, `plan_request` falls back safely to `PlannerContext(has_active_result=False)`.
- If context is corrupted or contains stale IDs, planner defaults to standalone intent classification without failing.

### 5. Contract Fixture Reference
- `tests/fixtures/person2/selected_ticket_followup.json` (resolves relative follow-up against `selected_ticket_id`).
- `tests/fixtures/person2/priority_filter_replacement.json` (replaces priority filter while preserving base dataset).

### 6. What Remains Mocked
In Person 2 unit tests, OpenAI API network calls are mocked; prompt string assembly is validated offline (`test_planner_context_encapsulation`).

### 7. Dependency
Required for **Person 2 Stage 5** (Context-Aware Follow-Up & Filter Refinement).

---

## Request 3: Recursive Reporting Tree Traversal Helper in `EmployeeKnowledgeService`

### 1. Concrete Need
When an authorized manager or executive asks *"Show everyone in my reporting organization"* or *"What is the headcount under EMP-4002?"*, multi-tier descendants must be retrieved.  
Currently, `EmployeeKnowledgeService` only queries direct reports (`manager_id == target_id`), missing 2nd and 3rd level reports.

### 2. Current Call in `backend/services/employee_knowledge_service.py` (Line 126)
```python
reports = [e for e in all_employees if e.get("manager_id") == manager_id]
```

### 3. Proposed Helper Signature
```python
# In EmployeeKnowledgeService (backend/services/employee_knowledge_service.py):
def get_all_descendant_ids(self, manager_id: str, max_depth: int = 5) -> List[str]:
    """Recursively collects all direct and indirect report IDs under manager_id.
    Includes cycle detection to guard against circular reporting graphs.
    """
    descendants = set()
    frontier = [manager_id]
    depth = 0
    while frontier and depth < max_depth:
        depth += 1
        next_frontier = []
        for mid in frontier:
            direct_reports = [e["employee_id"] for e in self.get_direct_reports(mid)]
            for r_id in direct_reports:
                if r_id not in descendants:
                    descendants.add(r_id)
                    next_frontier.append(r_id)
        frontier = next_frontier
    return sorted(list(descendants))
```

### 4. Error Semantics
- Returns empty list `[]` if `manager_id` does not exist or has no reports.
- Bounds recursion to `max_depth` (default 5) to guarantee fast deterministic responses.

### 5. Contract Fixture Reference
- `tests/fixtures/person2/team_descendant_request.json`

### 6. What Remains Mocked
In Person 2 tests, tree traversal is tested using in-memory dictionary hierarchies.

### 7. Dependency
Required for **Person 2 Stage 4** (Recursive Reporting Tree Queries & Grounded Facts).
