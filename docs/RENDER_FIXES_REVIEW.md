# Review of merged render-fixes changes

Reviewed on 2026-10-16. Local `main` was fast-forwarded from `a5fd2c8` to `c6173f1927936514378c53b8fa45f4c910eb3001` (PR #3, implementation commit `37e0312`). The two existing untracked implementation/handoff prompts were preserved. No application code was changed or pushed during this review.

## Verdict

The merge implements substantial working slices, but it does not finish the requested conversational rendering and protected-action specification. Existing offline tests pass. Additional adversarial and ordinary follow-up examples reproduce defects below. A successful Git merge and passing happy-path tests do not establish correct behavior for these cases.

## Confirmed findings, in recommended fix order

### 1. P1: unresolved/negated status requests return the opposite records

Location: `backend/services/conversation_dispatch.py:160`.

The status parser searches substrings, trying `Resolved` before `Unresolved`. Both "Show unresolved tickets" and "Show not resolved tickets" produce `status_filter='Resolved'`. On the isolated canonical dataset as EMP-2001, each returned five RESOLVED tickets.

Expected: unresolved excludes Resolved and Closed. Parse negation and complete status expressions before positive matches, and clarify contradictory statuses. Add production-route regressions, including "unresolved", "not resolved", "not closed", and mixed filters. The older REST query helper has a similar substring-order defect and should share the corrected typed query semantics.

### 2. P1: follow-up filters can silently disappear while verification is skipped

Locations: `backend/services/conversation_dispatch.py:142`, `backend/services/conversation_dispatch.py:373`.

After a manager ticket list, "Show only high priority tickets as a pie chart instead" becomes `rechart` with no priority filter. The chart contains Critical:10, High:12, Low:5, Medium:8 rather than only High. The early rechart branch also discards requested date/status constraints. This is a factual filtering failure within the actor's authorized snapshot, not evidence that this request crosses the actor's authorization boundary.

Expected: distinguish a presentation-only switch from a filtered query. For a complete, still-valid delivered snapshot, narrower supported filters may be applied to those same rows without obtaining new records. If a request requires new private data, use normal fresh verification and authorization. Preserve filter/group/date state in snapshots and ensure chart totals, narration, and table rows agree.

### 3. P2: natural target and analytic requests still fall into generic outputs

Locations: `backend/services/conversation_dispatch.py:30`, `backend/services/conversation_dispatch.py:195`, `backend/services/conversation_dispatch.py:228`, `backend/main.py:731`, `backend/main.py:933`.

Reproduced offline:

- EMP-2001: "Show my manager profile" returns EMP-2001's own profile. The resolver's generic `my` fallback silently changes the requested target. Resolve the manager relationship and apply policy, or clarify/deny; do not substitute self.
- EMP-2001: "Show EMP-1001 tickets" returns the whole 35-ticket authorized manager scope. The ticket plan has no person-filter field and ignores that employee target. Apply a typed target filter after authorization, or explain that this operation is unsupported.
- "How many overdue tickets?" and "Show ticket SLA compliance" return a generic 35-ticket list, with no overdue/SLA computation or useful unsupported-metric clarification.

OpenAI planning runs only when the local parser returns `clarify`; these incorrectly accepted local plans therefore never reach it. Final voice replies also no longer call the grounded answer generator; they use dispatcher templates such as "Showing N authorized tickets." This preserves deterministic denials but does not fulfill natural, grounded question answering. Keep denials/readbacks/receipts backend-owned; if adding narration, supply only the final authorized result and preserve its scope and facts.

The live dispatcher and existing REST ticket-query helper use different query implementations, so supported filters need one shared validated execution path. A typed plan should reject unsupported modifiers rather than silently drop them. Do not reintroduce a growing substring chain.

### 4. P2: ticket click selection is not shared with voice context

Locations: `frontend/src/components/renderers/TicketListCard.tsx:30`, `frontend/src/components/renderers/TicketListCard.tsx:187`, `backend/services/conversation_dispatch.py:125`.

Ticket detail selection stays in the card's local React state. Unlike the new profile actions, it never informs the backend of the selected ticket. After a multi-ticket result, clicking one ticket and saying "Change this ticket priority to High" cannot resolve that ticket; the parser returns `ticket_list` because the server snapshot still contains many ticket IDs. Context comments also require an explicit ID in the proposal regex even when a single-ticket context exists.

Expected: publish an allowlisted selection reference to server-owned conversation state, validated against the delivered source result. Resolve "this ticket" through that state; still require fresh dual verification, policy, and readback before writes. A click must never itself authorize mutation.

### 5. P2: two pending ticket creations allocate the same ticket ID

Locations: `backend/services/ticket_action_store.py:137`, `backend/services/ticket_action_store.py:211`.

Reproduced using two actor sessions and a temporary SQLite store: both proposals reserved `TKT-2026-043`, since allocation examines committed tickets only. After the first confirmation commits, the second raises uncaught `sqlite3.IntegrityError: UNIQUE constraint failed: tickets.ticket_id`. `ConversationDispatcher` catches `ActionError`, not this failure, so the route can produce a server error.

Expected: allocate/reserve unique IDs transactionally at proposal time, without creating the business ticket before confirmation. Handle conflicts with a safe explicit response and require a fresh readback if a bound target changes. Add a test with two outstanding creates and confirmations.

### 6. P2: the protected-action payload hash is recorded but not verified

Locations: `backend/services/ticket_action_store.py:156`, `backend/services/ticket_action_store.py:188`, `backend/services/ticket_action_store.py:242`.

In an isolated internal tampering test, a draft read back "priority to High". Changing its stored parameters to Low while leaving the readback/hash untouched, then speaking the exact original readback with a different evidence digest, committed Low. `confirm` never recomputes/compares the manifest hash. A consumed grant row is inserted in the same transaction after ticket modification; there is no separate executor validating a grant before applying the write.

This test requires modifying the server's draft database. It does NOT establish that a browser caller can directly edit draft parameters or exploit this remotely. It does establish that the requested parameter-binding invariant and grant-validation boundary are incomplete.

Expected: validate one immutable canonical manifest, hash, actor/session, target, operation, expected version, evidence, expiry, and single-use state before the write; atomically consume authorization with the mutation. Test a changed field/value/target/version, expired/cancelled grants, and duplicate confirmations. Describe the current implementation as SQLite voice-confirmed actions, not a completed independent ActionGrant vault/protected executor.

## Other incomplete requirements

- Backend operations emit one primary block. `LiveApp.tsx:131` selects only that block; other `result_blocks` are not retained in a result selector. Multiple-output conversational requests remain incomplete.
- Profile node clicks deliberately return `verification_required` until that detail was already delivered through a verified voice turn. This is a security choice documented in the handoff, not a broken clickable button; test that the guidance is understandable.
- The structured planner's extracted `field`/`value` are not used for writes: `dispatch` reparses original text with a narrow regex. A correctly interpreted synonym can still fail as a denial rather than a useful clarification. Validate typed parameters through a single proposal path.
- `idempotency_records` stores full responses, including transcript, private result payloads and generated speech audio. Its 120-second lookup cutoff does not delete rows, and session termination does not purge these rows. Bound retention/storage and document it; do not imply that all private response content disappears from backend storage at session expiry. This is generated speech, not storage of the original microphone recording.
- Automated tests do not certify speaker accuracy or explain the previous wrong-speaker incident. The new identity/account checks and diagnostic logs are useful evidence collection, not proof of the root cause.

## What is implemented and supported by inspection/tests

- A production typed dispatcher for own/direct-report profiles, team tables/counts, React Flow reporting trees, ticket lists, BAR/PIE and creation-date LINE/AREA charts.
- Server-bound snapshots and profile click actions, transcript reconciliation, session/error cleanup and asynchronous result guards.
- Public help and presentation-only navigation paths that avoid additional Detectif calls; new private reads and action proposal/confirmation paths still require fresh verification.
- Combined Detectif match/real checks plus mapped speaker/account correspondence; synthetic/inconclusive/mismatch evidence denies private processing in mocked tests.
- CTO ticket access no longer uses the former unconditional all-ticket executive branch; technology scope and explicit involvement are evaluated.
- SQLite ticket persistence, exact readback, different proposal/confirmation audio digests, version checks, atomic write/event/receipt transactions and completed-action replay behavior for tested paths.

## Verification performed

- `python -u -m pytest tests -q --ignore=tests/test_speech_integration.py --tb=short` with `INTENTLOCK_OFFLINE_TESTS=1` and temporary `APP_DB_PATH` / `MAPPING_DB_PATH`: **106 passed, 3 warnings, 37.81 seconds**. The warnings were one collection warning and two deprecated HTTP status references. The sandboxed run was stopped after stalling; the completed run used the host environment.
- `npm run build` in `frontend`: **passed** (TypeScript and Vite). Vite reported the large JavaScript chunk advisory (about 988 kB before gzip).
- `python scripts/validate_employee_graph.py`: **passed**, 31 employees.
- `python scripts/validate_ticket_data.py`: **passed**, 42 seed tickets.
- `git diff --check`: **passed**.
- Additional direct parser/dispatcher/action-store probes reproduced findings 1, 2, 3, 4's unresolved voice context, 5, and 6 using temporary databases. No real employee ticket database was edited by those probes.
- No paid Detectif/OpenAI calls or enrollment operations were made. Real speech integration was excluded from the suite. Local OpenAI SDK exposes `responses.parse`; live model response compatibility was not tested.
- Browser smoke check attempted against the local Vite server on port 5174. Chrome reported `ERR_CONNECTION_TIMED_OUT`; the temporary dev server was stopped. No successful visual, responsive, microphone, or live provider check is claimed.

## Recommended next pass

1. Add regressions for the exact examples above and repair the shared query/filter/target resolution before adding more renderers.
2. Wire selected ticket and view state across clicks/voice; test two-step follow-ups and actor/session resets.
3. Fix ticket-ID reservation and manifest/grant validation before demonstrating concurrent protected writes.
4. Complete multi-result retention and grounded replies from the same authorized result, preserving existing layouts.
5. Run bounded operator-led browser/microphone checks with all three enrolled speakers: match, wrong claim, a different speaker during an active session, expiry, new private reads, chart-only reuse, and exact update confirmation. Correlate UI turns with provider evidence and server policy logs; do not assume that a false acceptance or stale UI is fixed without that evidence.

Implement fixes on a staging branch and review before another main merge. No deployment or production readiness is established by this review.
