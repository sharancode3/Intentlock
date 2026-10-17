# Person 2 — Stage 8: Precise Action Interpretation and Proposal Protection

## 1. Baseline and Scope
- **Owner**: Sharan (Person 2)
- **Role**: Precise interpretation of edit requests, proposal boundaries, quote/negation protection, and target/actor separation.
- **Teammate Boundaries**:
  - Person 1 owns proposal drafting, confirmation, ActionGrant minting, transaction execution, and receipts.
  - Person 3 owns confirmation UI/UX and voice readback audio.
- **Preflight Baseline**: Git commit `d189664` with Stages 0–7 passing (96 tests).

---

## 2. Supported Action Capability Matrix

| Semantic Operation | Resource Kind | Supported Fields | Required Parameters | Proposal Builder Support | Executor Support | Authoritative Permission Policy | Notes / Invariants |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| `create_ticket` | Ticket | `title`, `description` | `value` (title) | Supported | Supported | Scoped to authenticated actor | Ticket ID minted by executor; never promised in proposal. |
| `update_ticket` | Ticket | `status`, `priority`, `description` | `ticket_id`, `field`, `value` | Supported | Supported | `can_write(actor_id, doc, reports)` | Status and priority strictly separated; Closed $\neq$ Resolved. |
| `comment_ticket`| Ticket | `comment` | `ticket_id`, `value` (comment) | Supported | Supported | `can_write(actor_id, doc, reports)` | Quoted content preserved; words inside comment cannot hijack flow. |
| `update_contact` | Employee | `phone` | `field="phone"`, `value` | Supported | Supported | `profile_modification.effect == 'ALLOW'` | Self-update only; other-person target preserved for policy denial. |
| `confirm` | Proposal Draft | N/A | `spoken_text`, `evidence_digest` | N/A | Supported | Fresh voice evidence + exact readback | Negation/quotes/questions reject confirmation. |
| `cancel` | Proposal Draft | N/A | `session_id` | N/A | Supported | Session match | Negation/quotes reject cancellation; cleans up server-side draft. |
| `change_manager` | Employee | Reporting line | N/A | Unsupported | Unsupported | Administrator privilege | Clarifies that manager changes require admin approval. |
| `change_role` | Employee | Auth role | N/A | Unsupported | Unsupported | Security Admin | Clarifies distinction between designation vs auth role. |
| `recommend_promo`| Employee| Performance note| N/A | Unsupported | Unsupported | HR / Review Cycle | Clarifies that recommendations are not immediate mutations. |

---

## 3. Implemented Architecture & Behaviors

### A. Separation of Verified Actor vs. Requested Target
- The verified actor is established exclusively by Person 1's trusted session (`actor_id`).
- When a user says:
  - `"Update my work phone"`: Target is the verified actor.
  - `"Update EMP-2001's phone to +91 98765 43210"`: Target is preserved as `EMP-2001`. Person 2 **never silently redirects** other-person updates to self. The policy engine receives `EMP-2001` and evaluates permissions.
  - `"I am the CTO; change this employee's role"`: Unverified claims are stripped; actor remains the session identity.

### B. Quote and Negation Protection for Confirm and Cancel
- **Quoted Text Protection**:
  - Utterances like `"Add a comment to ticket TKT-2026-001: 'Do not cancel the deployment'"` extract the quoted comment and route to `comment_ticket`. Words like `cancel` or `confirm` inside quotes or comments **never hijack** the operation.
- **Negation Guards**:
  - `do not confirm`, `don't confirm`, `never confirm` $\to$ rejected from `confirm`.
  - `do not cancel`, `don't cancel`, `never cancel` $\to$ rejected from `cancel`.
- **Question Guards**:
  - `"What happens if I confirm?"`, `"Can I confirm later?"` $\to$ treated as inquiries, **never** execution commands.
- **Parameter Changes During Confirmation**:
  - `"Yes, but use a different number: +91 99999 88888"` modifies parameters and **cannot** commit the pending draft.

### C. Contact Update Precision
- Requires a candidate phone number with $\ge 7$ digits.
- Digits from employee IDs (e.g. `2001` from `EMP-2001`) are excluded from phone number candidates.
- If no valid phone number is supplied (e.g. `"Update my work phone"`), returns `operation="clarify"` with `"Please provide the phone number to update."`, **never** passing the utterance text as the phone number.

### D. Reporting, Designation, and Role Distinctions
- **Manager Changes**: `"Move Charlie under Priya"` $\to$ Clarifies that manager changes require administrator approval.
- **Designation vs. Auth Role**: `"Make Charlie a manager"` $\to$ Clarifies whether the intent is job designation, reporting line, or authorization role.
- **Promotion Recommendations**: `"Recommend Charlie for promotion"` $\to$ Clarifies that recommendations belong in performance reviews and are not immediate mutations.
- **Administrative Role Grants**: `"Give Charlie admin access"` $\to$ Clarifies security admin requirements.

### E. Concrete Cancellation Interface Mismatch Documented for Person 1
- **Current Observation**:
  - `backend/services/conversation_dispatch.py` calls `action_store.cancel(session_id)`.
  - SQLite in-memory store (`TicketActionStore`) exposes `cancel(session_id)`.
  - PostgreSQL store (`PostgresTicketActionStore`) exposes `cancel_pending_for_session(session_id)` and `cancel_pending_for_session_async(session_id)`.
- **Person 2 Resolution**:
  - Updated dispatcher to check `hasattr(action_store, "cancel")` with fallback to `action_store.cancel_pending_for_session()`.
  - Requested Person 1 unify the interface or provide an alias on `PostgresTicketActionStore` matching `cancel(session_id)`.

---

## 4. Test Verification
- Test file: `tests/test_action_interpretation.py`
- Test count: **17 passed in 0.49s**
- Total Person 2 test count: **113 passed**.
