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
- Filter switching previously operated strictly on `active.source_rows` (the filtered subset of the previous turn); now retains `base_rows` across snapshots and applies dimension-replacement semantics (e.g., High to Low filter transition maintains the full authorized candidate pool).
- SLA and overdue calculations previously bypassed typed plan filters (`priority`, `person`, `status`, `dates`) and defaulted missing SLA records to "Within SLA"; now applies filters first, uses real UTC as-of time, and preserves `Unknown / No SLA` states.
- Routing previously converted `EMP-1001 SLA compliance` to profile view, inverted priority negation to positive, and captured presentation changes as `update_ticket` on selected tickets; now routes SLA to tickets, clarifies on priority negation, and guards presentation changes.
- Compound queries (e.g. "Show my profile and my tickets") previously only returned a single result block; now executes both sub-plans, registers both snapshots in `ConversationState`, and emits multiple `result_blocks` in `VoiceTurnResponse`.
- Planned executor boundary now inserts single-use `action_grants` prior to mutation and marks them `consumed_at` upon successful commit. Manifest hash verification includes `expires_at` and `readback`. Readback normalization preserves numbers, decimals, and signs while stripping speech punctuation.
- In-flight duplicate turn requests are now coalesced via an async lock and event (`_in_flight_turns`), preventing concurrent duplicate biometric queries.
- Periodic cleanup of expired idempotency records (`cleanup_expired_records`) runs on turn ingress and session revocation.
- Default frontend theme set to `'light'`.

## Completed slices

- Typed bounded local/OpenAI intent plan, production dispatcher, scoped profile/reporting/ticket outputs, filters, chart switches, server-owned result snapshots and click actions.
- Typed frontend table/tree/time chart registration inside the existing workspace design; transcript reconciliation and private-history cleanup.
- Public/help and cached presentation paths without Detectif; fresh dual verification for new private reads and ticket proposals/confirmations; exact completed delivery replay, evidence freshness metadata, and concurrent in-flight request coalescing.
- SQLite canonical ticket store seeded once from the existing 42-ticket JSON, versioned drafts/events, readback, fresh exact voice confirmation, atomic commits, and truthful receipts with single-use action grants.
- Grounded factual narration from authorized payload for safe queries, strictly protecting policy denials, readbacks, and receipts from model override.
- Bounded retention on `idempotency_records` in `IdentityMappingStore` (expired entries purged past 120s; session revocation cleans up actor records) and bounded `ConversationStore` (64 states, 300s TTL).
- Multi-result block retention in frontend with tab/pill switcher in `ResultHost` backed by multi-result backend `result_blocks`.

## Verification

- Offline Python suite: **124 passed, 3 warnings in 35.36s** across all test modules (`tests/test_conversation_dispatch.py`, `tests/test_ticket_knowledge.py`, `tests/test_render_fixes_recheck.py`, etc.); real speech integration tests excluded to avoid model downloads and paid providers.
- Dedicated Recheck Regression Suite (`tests/test_render_fixes_recheck.py`): **12 passed, 0 failures**:
  1. `test_filter_switching_retains_base_rows_without_false_empty` (12 High -> 5 Low -> 5 Table)
  2. `test_sla_overdue_filters_scope_to_typed_constraints_first` (High priority overdue evaluates 12 High tickets, not 35)
  3. `test_sla_compliance_metric_honest_classification` (honest separation of SLA categories, no defaulting)
  4. `test_routing_sla_compliance_is_ticket_context_not_profile` (SLA routes to ticket metric)
  5. `test_routing_priority_negation_fails_safely_to_clarify` (negation fails safely to clarify)
  6. `test_routing_presentation_switch_with_selected_ticket_does_not_update_ticket` (selected ticket does not hijack chart switch)
  7. `test_compound_query_emits_multiple_result_blocks` (returns both profile and ticket blocks)
  8. `test_manifest_tampering_of_expiry_and_readback_rejected` (expiry and readback tamper rejection)
  9. `test_planned_executor_grant_inserted_and_consumed` (single-use grant verification)
  10. `test_speech_tolerant_readback_normalization` (preserves decimals and signs)
  11. `test_concurrent_inflight_turn_coalescing` (concurrent duplicate calls coalesce to 1 biometric check)
  12. `test_session_revocation_purges_idempotency` (private idempotency records purged on session revoke)
- Frontend `npm run build`: **passed** (TypeScript and Vite production build, 0 errors).
- `python scripts/validate_employee_graph.py`: **passed** (31 employees).
- `python scripts/validate_ticket_data.py`: **passed** (42 tickets).
- `git diff --check`: **passed**.

## Semantic Routing, Identity Entry, Headcount, and Misleading FAQ Fallback Fix (2026-10-17)

### Changes
- **Genuine Public Help Decoupled from Private Clarification**: Only genuine public help inquiries (`"What can you do?"`, `"Help"`) return `PUBLIC_FAQ` with `status="success"` and 0 Detectif calls. Unrecognized private requests or unresolved constraints route through identity verification and return `status="clarification"` (amber) without misleading green success badges or canned FAQs.
- **Biometric Session Verification on Candidate Entry**: Claiming candidate identities (e.g. `EMP-4002 — Arvind Rao (CTO)`) triggers voice verification via Detectif and creates a verified session, keeping the user identity badge and header properly visible.
- **Typed Headcount Capability**: Added typed `headcount` operation to `IntentPlan` supporting scopes (`company`, `direct_reports`, `reporting_tree`, `department`, `location`).
- **Organization-Level Access Control**: Executive-only restriction (EMP-4002) for company-wide aggregate metrics without leaking individual employee IDs. Direct reports and reporting tree counts available to managers for their respective structures.
- **Truthful Location Scope Handling**: Preserved out-of-scope locations (e.g. "Tulum") as explicit unresolved constraints, prompting for clarification without guessing the count or returning zero. Recognized office locations with 0 directory records accurately report 0 recorded employees.
- **OpenAI Narration Adapter Protocol**: Realigned `generate_answer(question, authorized_context, correlation_id)` protocol and ensured `assistant_message`, `spoken_summary`, and TTS synthesis all agree.
- **Frontend Workforce Analytics Support**: Added `category` field support to `TeamMetricChartPayload` and `TeamMetricChartCard.tsx` with workforce RBAC annotations.

### Verification
- **Dedicated Regression Suite (`tests/test_headcount_and_routing.py`)**: **12 passed, 0 failures**:
  1. `test_1_screenshot_exact_utterance_with_candidate_cto` (verified session for EMP-4002, Tulum clarification, no PUBLIC_FAQ)
  2. `test_2_permitted_scoped_headcount_bengaluru` (CTO permitted company aggregate count of 31 employees)
  3. `test_3_direct_reports_count_not_company_headcount` (direct reports vs company headcount separation)
  4. `test_4_company_headcount_denied_for_non_executive` (EMP-1001 denied org-wide headcount)
  5. `test_5_i_am_the_cto_without_candidate_identity` (prompts for employee ID, zero Detectif calls)
  6. `test_6_selected_cto_identity_with_another_speaker` (mismatched speaker fails closed, no private count)
  7. `test_7_what_can_you_do_public_help_zero_detectif` (genuine help returns PUBLIC_FAQ with zero Detectif calls)
  8. `test_8_unknown_phrasing_for_supported_count_resolved` (fallback to structured planner resolves count)
  9. `test_9_planner_unavailable_returns_honest_clarification` (unavailable planner returns honest clarification)
  10. `test_10_unknown_location_vs_recognized_zero_matches` (Tulum vs London distinct honest outcomes)
  11. `test_11_narration_adapter_contract_and_text_agreement` (adapter contract and 3-way text agreement verified)
  12. `test_12_existing_ticket_and_tree_workflows_preserved` (profiles, tickets, org trees preserved)
- **Full Pytest Suite**: **136 passed, 13 skipped, 0 failed** in 41.84s across 149 test items.
- **Frontend Build**: `npm run build` completed with 0 errors.
- **Running Services**: Backend on `http://127.0.0.1:8000`, Frontend dev on `http://localhost:5173`.

## Supabase PostgreSQL Persistence & Protected Contact Update (2026-10-17)

### Changes
- **PostgreSQL Connection Layer (`backend/adapters/postgres_client.py`)**: Bounded connection pooling with `asyncpg`, command timeouts, transaction isolation with `SET LOCAL intentlock.actor_id = $1` context for row-level security, and credential-sanitizing error handling (`sanitize_db_error`).
- **Additive DDL & RLS Migration (`backend/migrations/001_initial_schema.sql`)**: Defined 10 tables (`schema_migrations`, `directory_metadata`, `employees`, `tickets`, `speaker_mappings`, `voice_sessions`, `action_drafts`, `action_grants`, `action_events`, `idempotency_records`). Row-Level Security (RLS) enabled across all tables, with direct access revoked from `anon` and `authenticated` roles.
- **Migration & Data Importer (`scripts/migrate_to_postgres.py`)**: Safe advisory-locked (`pg_advisory_lock(0x494E5445)`) migration and idempotent import tool. Migrated 31 canonical employees, 42 authoritative tickets, and 3 enrolled speaker mappings into Supabase project `ahprvdydzjebbpampyhz` (ap-northeast-2). Old drafts and expired voice sessions were strictly excluded.
- **Postgres Repositories (`backend/adapters/postgres_*`)**:
  - `PostgresEmployeeRepository`: Canonical projections, relational hierarchy resolution (`manager_name`, `direct_report_ids`), directory revision tracking via `directory_metadata`.
  - `PostgresTicketActionStore`: Authoritative ticket operations, draft proposal manifests, SHA256 integrity digests, single-use `action_grants`, atomic commits, and audit event logs (`action_events`).
  - `PostgresIdentityMappingStore`: Speaker mappings, short-lived sessions, and TTL-bounded idempotency cache.
- **Dual-Storage Routing & Dynamic Invalidation**: Supported `STORAGE_BACKEND="postgres"` vs `"sqlite"` (default for offline test parity). `EmployeeKnowledgeService.refresh_if_stale()` automatically polls `directory_metadata.revision` and reloads in-memory indexes when mutations occur.
- **Protected Self-Contact Edit (`update_contact`)**:
  - Recognized from voice utterances ("update my phone to +91 98765 43210").
  - RBAC policy enforced: `SELF_CONTACT_ONLY` strictly guarded; attempts to modify other employees' details are denied.
  - Spoken readback: `"I confirm update contact for EMP-XXXX: phone to <number>"`.
  - Confirmation requires fresh voice evidence; replaying previous audio hash is rejected.
  - Atomic commit updates employee row, increments version, bumps directory revision, marks grant consumed, logs audit event, and returns `ACTION_RECEIPT` (`"storage": "Postgres"`).
- **Frontend Profile Integration**: Added optional `phone` field to `EmployeeRecord` in `payloads.ts`, validated in `validation.ts`, and rendered with Lucide `Phone` icon in `EmployeeProfileCard.tsx`.

### Verification
- **Supabase Target Verified Live**:
  - Applied migration `001_initial_schema.sql` via session pooler (`aws-0-ap-northeast-2.pooler.supabase.com:5432`).
  - 31 employees, 42 tickets, 3 speaker mappings confirmed in Supabase database.
  - Direct HTTP REST access with `anon` key confirmed denied (HTTP 401 unauthorized).
- **Dedicated Test Suites (`tests/test_contact_update.py` and `tests/test_supabase_storage.py`)**: **11 passed, 0 failures**:
  1. `test_parse_update_contact` (Intent parsing for self and targeted contact updates)
  2. `test_build_typed_proposal_validation` (Validation of phone digit counts and formats)
  3. `test_update_contact_propose_and_confirm_lifecycle` (Propose, readback, confirmation, and receipt)
  4. `test_update_contact_non_self_denied` (Strict policy denial of non-self contact modification)
  5. `test_profile_displays_updated_phone` (Profile query displays updated phone number)
  6. `test_full_contact_update_route_turn_by_turn` (End-to-end multi-turn voice turn API execution)
  7. `test_sanitize_db_error_redacts_credentials` (Password and token redaction from db error messages)
  8. `test_get_safe_diagnostics_redacted` (Safe diagnostics never exposes raw secrets or tokens)
  9. `test_postgres_employee_repository_projection` (Row projection and reporting hierarchy derivation)
  10. `test_postgres_ticket_store_proposal_and_grant_hashing` (Typed proposal creation and grant hashing)
  11. `test_postgres_client_singleton` (Async client singleton pool initialization)
- **Full Pytest Suite**: **147 passed, 13 skipped, 0 failed** in 72.36s across all test modules.
- **Frontend Build**: `npm run build` passed cleanly with 0 TypeScript/Vite errors.
- **Git diff check**: `git diff --check` passed cleanly with 0 whitespace issues.

## Supabase PostgreSQL Remediation & Hardening (2026-10-17)

### Remediated Issues (Code Review Findings P1/P2)
1. **[P1] Postgres Identity Adapter Method Parity**:
   - `PostgresIdentityMappingStore` implemented missing methods called by `VoiceGateway`: `cleanup_expired_records(cutoff_seconds=120)`, `refresh_session(session_id, ttl_seconds, verified)`, `save_idempotency_record(operation_key, audio_digest, employee_id, response_dict)`, `get_idempotency_record(operation_key)`, and `update_enrollment_status(employee_id, status, sample_count)`.
   - Routed all synchronous adapter operations safely through `self.client.run(...)` on the persistent worker loop thread.
2. **[P1] Dedicated Event Loop Worker & Connection Pool Lifecycle**:
   - Eliminated ad-hoc `asyncio.run()` and `ThreadPoolExecutor` calls across repository wrappers that previously caused asyncpg connection pool corruption and event loop deadlocks.
   - Built a dedicated persistent worker thread (`IntentLock-Postgres-Worker`) with a single event loop inside `PostgresClient`.
   - Added thread-safe execution helpers: `run(coro)` for synchronous callers via `asyncio.run_coroutine_threadsafe(...).result(...)` and `run_async(coro)` for async callers via `asyncio.wrap_future(...)`.
3. **[P1] Consistent Timestamp Typing & Manifest Verification**:
   - Updated `propose_async` in `PostgresTicketActionStore` to pass timezone-aware Python `datetime` objects with `.replace(microsecond=0)` into PostgreSQL `TIMESTAMPTZ` columns (`expires_at`, `created_at`), while generating a stable canonical ISO-8601 string for SHA-256 manifest hashing.
   - Updated `confirm_async` to dynamically accept both Python `datetime` objects and ISO strings without raising `TypeError`, and pass Python `datetime` objects for `grant_exp_dt`.
4. **[P1] Full Employee Data Fidelity & Importer Alignment**:
   - Fixed data loss in `scripts/migrate_to_postgres.py` where `identity.contact.email` was read instead of `identity.work_email`.
   - Restored missing schema columns via migration `002_schema_enhancements.sql`: `employment_status`, `employment_type`, `date_of_joining`, `sub_department`, `research_level`, `security_scope`, `voice_authority`, `recent_activity`, `extra_data`.
   - Updated `PostgresEmployeeRepository._project_row()` to project all 14 canonical fields.
   - Added `--repair` mode in `migrate_to_postgres.py` and executed safe, non-destructive repair across all 31 employee records in the live Supabase development database.
5. **[P1] Actor-Aware Row-Level Security (RLS) Policies**:
   - Replaced permissive `USING (true) WITH CHECK (true)` policies with strict actor-checked policies via migration `003_actor_rls_policies.sql`.
   - Policies inspect `current_setting('intentlock.actor_id', true)` for user-scoped tables (`action_drafts`, `action_grants`, `action_events`, `voice_sessions`, `idempotency_records`).
6. **[P1] Safe, Transactional Migration Importer**:
   - Implemented strict read-only dry-run verification: checks table existence using `information_schema.tables` without creating `schema_migrations` or executing DDL/DML.
   - Wrapped entire data import in a single database transaction (`async with conn.transaction():`) with automatic rollback on error.
   - Parameterized all paths to use application settings (`settings.DATA_PATH`, `settings.APP_DB_PATH`, `settings.MAPPING_DB_PATH`).
7. **[P1] Dependency Manifest Updates**:
   - Added `asyncpg>=0.29.0` to root `requirements.txt` and `backend/requirements.txt`.
8. **[P2] Cache Freshness Before Reads & Explicit RBAC Policy Checks**:
   - Added `self.refresh_if_stale()` before directory reads in `EmployeeKnowledgeService` (`list_all_employees`, `get_employee_by_id`, `find_employee_by_name`, `search_employees`) to eliminate stale cached reads.
   - Enforced `permissions.profile_modification.effect == "ALLOW"` in `ConversationDispatcher` and in both `PostgresTicketActionStore` and `TicketActionStore` before creating contact proposals or executing confirmations.

### Verification
- **End-to-End Proposal -> Confirmation -> DB Commit -> Restart Test**:
  - Added `test_postgres_e2e_proposal_confirm_restart_workflow` to `tests/test_supabase_storage.py`.
  - Simulates proposing a contact update on Supabase Postgres, verifying manifest hash, confirming with fresh voice evidence, committing to the database, simulating process restart by re-initializing repository instances, and asserting persisted state in the fresh instance.
- **Supabase Target Verified Live**:
  - Migrations `001_initial_schema.sql`, `002_schema_enhancements.sql`, and `003_actor_rls_policies.sql` applied cleanly.
  - 31 employees repaired with 100% data parity in Supabase database.
- **Full Offline Pytest Suite**: **161 passed, 0 failed** in 82.44s across all test modules in `tests/`.
- **Frontend Build**: `npm run build` passed cleanly with 0 TypeScript/Vite errors.
- **Git diff check**: `git diff --check` passed cleanly with 0 whitespace issues.

## Remaining checks and limitations

- OVERRIDING HUMAN INSTRUCTION: Remote push is withheld; all verified changes remain purely on local branch `render-fixes`.
- Live Detectif/OpenAI, full local speech, responsive browser layouts, and actual kiosk handoff remain unverified. The reported wrong-speaker incident is not reproduced or attributed to a provider model.
- Exact completed network replay is deduplicated; concurrent in-flight duplicate deliveries are now coalesced via async event synchronization.
- Voice selection of new private detail requires a fresh recording. Clicking a newly visible tree/table member asks for that voice request; already verified delivered detail can be revisited by click.

See `INTENTLOCK_LIVE_HANDOFF.md` for capability/policy matrix, setup, demo, and runtime blockers.
