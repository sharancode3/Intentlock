# Person 2 — Stage 5: Conversation Context and Filter Semantics

## 1. Baseline and Scope
- **Owner**: Sharan (Person 2)
- **Role**: Semantic understanding, conversation context, selection lifecycle, and filter semantics.
- **Teammate Boundaries**:
  - Person 1 owns session/identity verification, storage, Detectif evidence, and protected actions.
  - Person 3 owns frontend renderers and click-event emission.
- **Preflight Baseline**: Git commit `d189664` with 61 baseline tests passing.

---

## 2. Implemented Architecture & Behaviors

### A. Context is Task State, Not Unlimited Memory
- Context is strictly bounded to task state:
  - Actor and session binding with TTL enforcement (300 seconds).
  - Navigation history stack bounded to 10 entries to prevent infinite growth.
  - Monotonically increasing `context_version` tracking for stale and concurrent turn detection.
  - Typed selection references (`SelectionReference`) for employees and tickets.

### B. Typed Selection & Reference Resolution
- **Separate Resource Selection**:
  - `selected_employee` and `selected_ticket` are maintained independently.
  - An utterance asking for "their profile" evaluates employee selection; asking for "this ticket" evaluates ticket selection. Selecting a ticket never satisfies an employee reference, and vice-versa.
  - If a pronoun is used without an active selection, `MissingRequiredReferenceError` is raised. The system **never falls back to self (`actor_id`)**.
- **Explicit Target Overrides Selection**:
  - When an utterance explicitly mentions an employee (e.g., "EMP-4002"), the explicit target overrides any stale active selection in context.
- **1-Based Ordinal Resolution**:
  - Ordinals ("the first ticket", "the second person") resolve against `visible_ids` of the active result.
  - Bounds checking raises `OrdinalOutOfRangeError` if $1 > \text{ordinal} > N$.
  - Mismatched resource kinds (e.g. asking for "the second person" when active snapshot contains tickets) raises `ResourceKindMismatchError`.

### C. Precise Filter Transition Semantics
- `apply_filter_transition()` implements explicit transition modes:
  - **Refine**: Narrows or adds constraints, merging into existing active filters without dropping active dimensions.
  - **Replace**: Replaces a specific dimension value (e.g. priority High $\to$ Low) while strictly preserving unrelated dimensions (e.g. status, department, dates).
  - **Clear**: Removes a specified dimension (e.g. priority) while strictly preserving other filters (e.g. department, date intervals).
  - **Clear All**: Resets active filters.

### D. Presentation Change vs. New Disclosure
- `classify_filter_action()` explicitly distinguishes harmless presentation changes from new data disclosures:
  - **`presentation_only`** (`is_new_disclosure = False`): Reformatting delivered records (e.g. TABLE $\to$ BAR) on the exact same dataset. Requires no new Detectif evidence.
  - **`refilter_delivered`** (`is_new_disclosure = False`): Narrowing delivered records into a smaller subset without introducing new dimensions.
  - **`new_disclosure_retrieval`** (`is_new_disclosure = True`): Changing a filter partition (e.g. High $\to$ Low priority) or clearing a filter (High $\to$ All). This reveals private rows not present in the delivered set, requiring Person 1 to enforce evidence policy.
  - **`broader_scope`** (`is_new_disclosure = True`): Expanding scope (e.g. team $\to$ company).

### E. Truthful Empty-Result Handling
- Distinguishes `base_rows is None` from `base_rows == []`.
- Empty authorized datasets are tagged with `DatasetStatus.EMPTY_AUTHORIZED`.
- An empty authorized result is preserved truthfulness and does **not** trigger an unrestricted or broader re-query.

---

## 3. Modules Changed & Interfaces
1. **`backend/services/context_service.py`** (New):
   - `DatasetStatus`: Enum (`NONE_CAPTURED`, `EMPTY_AUTHORIZED`, `POPULATED`, `FAILED`, `DENIED`, `EXPIRED`).
   - `SelectionReference`: Dataclass (`resource_kind`, `resource_id`, `source_result_id`, `created_at`, `display_order_index`).
   - `FilterActionClassification`: Dataclass (`action_type`, `is_new_disclosure`, `explanation`, `dimension_changed`).
   - `apply_filter_transition(current_filters, transition_type, filter_updates, keys_to_clear)`.
   - `classify_filter_action(current_filters, requested_filters, delivered_row_count, is_view_change_only, scope_widened, is_mutation)`.
   - `ContextService`: Lifecycle validation, ordinal resolution, and typed selection resolution.
2. **`backend/services/conversation_dispatch.py`** (Modified):
   - Integrated `DatasetStatus` and `__post_init__` into `ResultSnapshot`.
   - Upgraded `ConversationState` with `select_ticket()`, `select_employee()`, `navigate_back()`, and `context_version`.
   - Enhanced `op == "back"` handling to traverse the navigation stack.

---

## 4. Test Verification
- Test file: `tests/test_context_and_filters.py`
- Test count: **15 passed in 0.47s**
- Regression suite: `tests/test_conversation_dispatch.py` (18 passed in 18.69s).
- Total Person 2 test count: **76 passed**.

---

## 5. Handoff Requests & Remaining Dependencies
- **Person 1 (Gateway & Evidence)**:
  - Update `/voice/result-action` and `/voice/turn` to inspect `classify_filter_action().is_new_disclosure`.
  - When `is_new_disclosure is True`, verify voice freshness/Detectif evidence before fetching private data.
  - When `is_new_disclosure is False`, permit re-rendering without step-up authentication.
- **Person 3 (Frontend)**:
  - Emit click events containing `source_result_id` and stable `target_id`.
  - Display ordering should match 1-based ordinal resolution expectations.
