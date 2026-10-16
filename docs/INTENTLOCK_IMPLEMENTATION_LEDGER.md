# IntentLock implementation ledger

Branch: `render-fixes`, created from `origin/main` at `a5fd2c8`. No remote staging ref existed at the initial fetch.

## Verified root causes

- `backend/main.py` previously selected tickets with broad keywords, otherwise self profile; it did not route to target profiles, reporting, or charts. Result status could be success after biometric verification even when policy denied the operation.
- `frontend/src/LiveApp.tsx` read only one result, did not wire result actions, cleared the active card at request start, and blocked every recording below 4.2 seconds.
- `TicketKnowledgeService` returned all 42 raw tickets to an executive flag. The live ticket scope is now bounded to involvement, direct reports, and the configured technology domain.
- Profile target IDs were previously mixed with identity claims. Selected identity and explicit spoken self-claim are now checked independently of requested target references.

## Completed slices

- Typed bounded local/OpenAI intent plan, production dispatcher, scoped profile/reporting/ticket outputs, filters, chart switches, server-owned result snapshots and click actions.
- Typed frontend table/tree/time chart registration inside the existing workspace design; transcript reconciliation and private-history cleanup.
- Public/help and cached presentation paths without Detectif; fresh dual verification for new private reads and ticket proposals/confirmations; exact completed delivery replay and evidence freshness metadata.
- SQLite canonical ticket store seeded once from the existing 42-ticket JSON, versioned drafts/events, readback, fresh exact voice confirmation, atomic commits, and truthful receipts.
- Redacted identity/policy traces, employee graph validator, and offline production-route tests.

## Verification

- Offline Python suite: 106 passed, 1 existing PytestCollectionWarning (`test_app` callable); real speech integration tests excluded to avoid model downloads and paid providers.
- Frontend `npm run build`: passed; Vite reports a large-chunk advisory.
- `python scripts/validate_employee_graph.py`: passed (31 employees).
- `python scripts/validate_ticket_data.py`: passed (42 tickets).
- `git diff --check`: passed before final staging review.
- Browser visual check: blocked. Windows computer-use stopped because it could not establish the browser URL safely; no visual or microphone behavior is claimed as verified.

## Remaining checks and limitations

- Live Detectif/OpenAI, full local speech, responsive browser layouts, and actual kiosk handoff remain unverified. The reported wrong-speaker incident is not reproduced or attributed to a provider model.
- Exact completed network replay is deduplicated; concurrent in-flight duplicate deliveries are not yet coalesced.
- Voice selection of new private detail requires a fresh recording. Clicking a newly visible tree/table member asks for that voice request; already verified delivered detail can be revisited by click.
- Client supports the multi-result response envelope but the current dispatcher emits one primary block per operation.

See `INTENTLOCK_LIVE_HANDOFF.md` for capability/policy matrix, setup, demo, and runtime blockers.
