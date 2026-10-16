# IntentLock implementation ledger

Branch: `render-fixes`, created from `origin/main` at `a5fd2c8`. No remote staging ref existed at the initial fetch.

## Verified root causes

- `backend/main.py` previously selected tickets with broad keywords, otherwise self profile; it did not route to target profiles, reporting, or charts. Result status could be success after biometric verification even when policy denied the operation.
- `frontend/src/LiveApp.tsx` read only one result, did not wire result actions, cleared the active card at request start, and blocked every recording below 4.2 seconds.
- `TicketKnowledgeService` returned all 42 raw tickets to an executive flag. The live ticket scope is now bounded to involvement, direct reports, and the configured technology domain.
- Profile target IDs were previously mixed with identity claims. Selected identity and explicit spoken self-claim are now checked independently of requested target references.
- Unresolved/negated status requests inverted filters due to substring order testing "resolved" inside "unresolved"; fixed to check compound/negated statuses first across dispatcher and ticket knowledge service.
- Follow-up presentation recharting discarded requested priority, status, and date filters; fixed to retain and apply narrower filters to existing snapshots.
- Natural target expressions ("my manager") previously fell back to caller ID; fixed to resolve `reporting.manager_id` and apply policy denial rather than substituting self.
- Employee ticket requests ("Show EMP-1001 tickets") lacked a person filter and returned all scoped tickets; added `person_filter` in `IntentPlan` and filtered accordingly.
- Overdue and SLA queries dumped all tickets; added explicit SLA breakdown and overdue metrics calculation with truthful KPIs and narration.
- Clicking ticket rows only updated local React state; wired `select_ticket` action to `ConversationState.selected_ticket_id` so subsequent turns resolve "this ticket".
- Concurrent ticket creation proposals previously allocated identical IDs; now queries both committed tickets and pending drafts in SQLite.
- Protected-action manifest hash was stored but unverified at confirmation; recomputes canonical manifest SHA-256 and rejects modifications before mutation.

## Completed slices

- Typed bounded local/OpenAI intent plan, production dispatcher, scoped profile/reporting/ticket outputs, filters, chart switches, server-owned result snapshots and click actions.
- Typed frontend table/tree/time chart registration inside the existing workspace design; transcript reconciliation and private-history cleanup.
- Public/help and cached presentation paths without Detectif; fresh dual verification for new private reads and ticket proposals/confirmations; exact completed delivery replay and evidence freshness metadata.
- SQLite canonical ticket store seeded once from the existing 42-ticket JSON, versioned drafts/events, readback, fresh exact voice confirmation, atomic commits, and truthful receipts.
- Redacted identity/policy traces, employee graph validator, and offline production-route tests.
- Multi-result block retention in frontend with tab/pill switcher in `ResultHost`.
- Bounded retention on `idempotency_records` in `IdentityMappingStore` (expired entries purged past 120s).

## Verification

- Offline Python suite: **112 passed, 25 warnings** across all test modules (`tests/test_conversation_dispatch.py`, `tests/test_ticket_knowledge.py`, etc.); real speech integration tests excluded to avoid model downloads and paid providers.
- Frontend `npm run build`: **passed** (TypeScript and Vite production build).
- `python scripts/validate_employee_graph.py`: **passed** (31 employees).
- `python scripts/validate_ticket_data.py`: **passed** (42 tickets).
- `git diff --check`: **passed**.
- Additional direct tests: Verified status negation, filtered recharting, manager target policy denial, employee ticket scoping, SLA metrics, click selection context, concurrent creation ID reservation, and manifest tampering rejection.

## Remaining checks and limitations

- OVERRIDING HUMAN INSTRUCTION: Remote push is withheld; all verified changes remain purely on local branch `render-fixes`.
- Live Detectif/OpenAI, full local speech, responsive browser layouts, and actual kiosk handoff remain unverified. The reported wrong-speaker incident is not reproduced or attributed to a provider model.
- Exact completed network replay is deduplicated; concurrent in-flight duplicate deliveries are not yet coalesced.
- Voice selection of new private detail requires a fresh recording. Clicking a newly visible tree/table member asks for that voice request; already verified delivered detail can be revisited by click.

See `INTENTLOCK_LIVE_HANDOFF.md` for capability/policy matrix, setup, demo, and runtime blockers.
