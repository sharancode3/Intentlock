# IntentLock live integration handoff

## Scope and data coverage

The production path is `final audio/transcript -> typed intent -> identity evidence -> canonical policy -> scoped knowledge or ticket transaction -> typed result -> existing renderer/TTS`. The local parser handles clear requests; OpenAI Responses structured output is a bounded interpretation fallback for unclear phrasing. Its plan never supplies actor, permission, computed facts, or a receipt. All personnel/ticket rows are from the 31-employee/42-ticket fictional seed or the SQLite ticket store after a committed edit.

| Request example | Live result | Scope/evidence |
| --- | --- | --- |
| “Show my profile and projects” | `EMPLOYEE_PROFILE` with approved optional projects/skills | Actor self; fresh dual voice verification |
| “How many direct reports?” / “Show my team” | Count chart / `DATA_TABLE` | Manager direct reports; fresh verification |
| “Show my reporting tree” | `ORG_TREE` | Manager direct reports, or CTO's explicit R&D summary subtree; fresh verification |
| “Open the second person” / “Open EMP-1001 details” | `EMPLOYEE_PROFILE` | Resolved only from authorized visible people; fresh verification |
| “Show my tickets by priority” | `TICKET_LIST` or BAR/PIE | Authorized tickets filtered before aggregation; fresh verification |
| “Only unresolved tickets since 2026-10-12 as a line chart” | Real creation-date LINE/AREA buckets | Scoped tickets; fresh verification |
| “Show those as a pie by status” / “table instead” / “back to the tree” | Reuses a bounded delivered snapshot | Valid session/snapshot; no new Detectif call |
| “What can you do?” | `PUBLIC_FAQ` | Public; no Detectif call |
| “Change TKT-2026-001 priority to Critical” | `READBACK_CONFIRMATION` | Permitted ticket; fresh dual verification; zero writes |
| Speak the displayed exact confirmation phrase | `ACTION_RECEIPT` | Fresh dual evidence from a different recording; one SQLite transaction |

Unknown fields, unsupported operations, ambiguous targets, inaccessible resources, and unsupported chart history yield clarification or denial. Historical backlog, payroll, performance, and SLA percentages are not fabricated.

## Policy

| Actor | Summary | Private detail | Ticket writes |
| --- | --- | --- | --- |
| Anonymous | Approved help only | None | None |
| Employee | Own approved profile and scoped tickets | Self | Self-involved tickets; self ticket creation |
| Manager | Direct-report names/titles/counts/tree; scoped team tickets | Self and direct reports | Own or directly delegated/involved tickets |
| CTO (`EMP-4002`) | Own data, one direct report, and three permitted R&D descendants as summary; bounded technology tickets | Self/direct report under the same detail policy; no general descendant detail | Same explicit involvement/delegation rules |

The dropdown is a claim. The provider's mapped speaker/account and real-authenticity verdict must correspond to it. An employee ID in a requested target is not a self-claim. Detail and mutation decisions run server-side; a visible node is not authorization to reveal its private fields. Existing public ticket and employee endpoints continue to use the canonical policy facade.

## Persistence and setup

`APP_DB_PATH` defaults to `backend/data/app_state.sqlite3` and holds canonical tickets, versions, drafts, grants, and events. On first initialization it seeds only when the `tickets` table is empty. Keep this file on persistent storage in deployment; deleting it loses edits and reimports the JSON seed. Existing `MAPPING_DB_PATH` is separate and its enrollment IDs/voices are unchanged. Its session schema adds nullable `last_verified_at` in place. Back up both stores before moving a deployed instance. Do not ship either SQLite file in Git.

From the repository root, install Python dependencies with `python -m pip install -r requirements.txt` and run `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`. In `frontend`, run `npm ci` and `npm run dev`. The Vite proxy is development only; production frontend hosting needs its configured backend API URL and CORS origin. Real voice use requires the configured Detectif key/account, enrolled mapping database, OpenAI key for ambiguous requests, local speech models/system audio dependencies, and enough startup memory. `INTENTLOCK_OFFLINE_TESTS=1` is only for offline tests and disables real provider/speech startup.

Offline verification from the root uses `python scripts/validate_employee_graph.py`, `python scripts/validate_ticket_data.py`, and `python -m pytest tests -q --ignore=tests/test_speech_integration.py --tb=short` with `INTENTLOCK_OFFLINE_TESTS=1` and temporary `APP_DB_PATH`/`MAPPING_DB_PATH`. The frontend build is `npm run build` in `frontend`. On this Windows host the asyncio test suite required running outside the filesystem sandbox; its final result was 106 passed with one collection warning. Build passed with Vite's large-chunk advisory.

## Call-count evidence and five-minute demo

Offline injected providers show: public help = 0 Detectif calls; first manager ticket list plus BAR and PIE switches = 1 total; manager tree plus new profile detail = 2 total; proposal plus exact confirmation = 2 calls and one committed event. These are mock counts, not a claim about live network reliability or billing retries. The production adapter retains a stable provider idempotency key for bounded retries.

1. Choose `EMP-1001`. Speak a full phrase: “Show my profile and projects.” Show the profile card and speech/text agreement.
2. Choose `EMP-2001`. Ask for the reporting tree (Priya -> Aarav and Neha), then “Open the first person.” A fresh verified turn shows Aarav's permitted detail. Click that already delivered person to revisit the same result.
3. Ask for team tickets, then “Show those as a bar chart,” “pie by status instead,” and “table instead.” These presentation turns reuse the same authorized snapshot.
4. Choose `EMP-4002`. Ask “Show everyone reporting to me.” Show one direct report and three people in the permitted R&D tree. Ask for another manager's private detail and show denial.
5. Return to `EMP-1001`. Propose “Change TKT-2026-001 priority to Critical.” Verify no change before readback. Speak the displayed complete confirmation phrase in a new recording; show committed receipt and refreshed ticket value.

## Unverified and deployment limits

The earlier wrong-speaker/cross-role observation has no retained end-to-end evidence proving a cause. The new redacted `voice_trace` and `voice_policy` logs expose the selected claim, explicit self-claim, mapped/provider identity, actual scores/thresholds/verdicts, evidence freshness, policy outcome, and renderer without logging audio, API keys, or entire records. A live incident still needs correlated provider/operator evidence; these offline tests cannot certify biometric performance.

Browser visual/microphone checks were not completed: Windows computer-use halted on uncertain browser URL state. Live Detectif/OpenAI calls were intentionally not made because credits are limited. Concurrent in-flight duplicate turns are not coalesced, although completed exact retries are replay-safe. Session evidence does not authorize every new private query; the shared kiosk still has a handoff risk until an operator tests speaker changes and timeout behavior in its real environment. Multiple result fields are accepted but current operations return one primary block. No staging branch deployment or production security certification is implied.
