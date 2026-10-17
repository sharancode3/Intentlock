# Local completion recheck — 2026-10-17

Reviewed local branch `render-fixes`, HEAD `8211f87`, following the agent's supplied completion report. Changes include `8420428` and `8211f87` after the previously reviewed main merge `c6173f1`. This review did not change application code, push, merge, deploy, enroll voices, or use paid providers. Existing local prompt files were preserved.

## Conclusion

Several of the original reproductions are repaired. The claim that the entire implementation specification is complete is premature. The new tests cover useful individual examples but miss conversational sequences, metric filter semantics, compound outputs, and parts of the protected-executor contract.

## Confirmed progress

Direct offline probes against production parser/dispatcher with temporary SQLite state now show:

- `Show unresolved tickets` uses Unresolved, returning 25 scoped nonterminal manager tickets in the isolated seed.
- `Show my manager profile` is denied by policy instead of silently substituting self.
- `Show EMP-1001 tickets` filters the authorized manager scope to 16 involved tickets.
- A full ticket list followed by `Show only high priority tickets as a pie chart instead` correctly returns 12 High rows in the isolated seed.

Code inspection also confirms the ticket-click selection endpoint, inclusion of pending drafts in ticket-ID allocation, recomputed manifest-hash comparison, frontend result-pill scaffolding, and expired idempotency cleanup on writes. These changes should be preserved.

The numbers above describe the isolated seed and policy, not constants for production or test expectations.

## Remaining defects and incomplete requirements

### 1. Changing filters within the conversation returns false empty results

`backend/services/conversation_dispatch.py:527` starts each rechart from `active.source_rows`, which already contains only the previous filtered result.

Reproduction:

1. Manager: `Show my tickets`.
2. `Show only high priority tickets as a pie chart instead` -> 12 High rows.
3. `Show only low priority tickets as a pie chart instead` -> zero rows.

The original full authorized snapshot contains five Low tickets. The second filter is applied to the High-only rows. It must either use a still-valid retained authorized source covering Low, or request fresh evidence/retrieval if the available source is insufficient. Do not silently report zero. Preserve both source bounds and current view/filter state; define replace versus intersect semantics explicitly.

### 2. SLA/overdue output drops query constraints and makes unsupported classifications

`backend/services/conversation_dispatch.py:453` and `:485` retrieve all actor-scoped tickets directly instead of applying the typed person/status/priority/date query first.

Reproduction: `Show only High priority overdue tickets` produces a plan with priority High, but the metric reports over all 35 manager tickets. The same bypass exists for person and date filters when routed to the metric branches.

Additional code findings:

- Deadline comparison uses the hard-coded string `2026-10-16`, not an injected/current as-of time.
- Every ticket outside the overdue bucket is labeled `Within SLA`, including tickets whose compliance was not established by that calculation.
- Missing `sla.resolution_status` is defaulted to `Within SLA`, turning unknown into success.
- A status distribution is labeled SLA compliance without a precise eligible denominator/rate definition.

Filter authorized rows first, compute a clearly defined metric from trustworthy fields, preserve unknown/excluded states, and label recorded SLA status distinctly from a reconstructed deadline or compliance percentage. Use a clock and explicit timezone rules, or return a useful unavailable explanation.

### 3. Routing still accepts incomplete interpretations

Reproduced:

- `Show EMP-1001 SLA compliance` becomes an employee profile because the early employee-ID branch does not recognize SLA as ticket context.
- `Show tickets that are not high priority` becomes priority High, the opposite meaning.
- With a selected ticket, `Change this chart to a pie chart` becomes update_ticket for that ticket, rather than a presentation switch.

The new parser still consists of early keyword branches; OpenAI is invoked only after local `clarify`, so incorrectly accepted plans bypass fallback. Use complete validated operation/constraint interpretation. The selected ticket must not capture unrelated uses of the verb "change." Unsupported negation must clarify instead of invert.

### 4. Multiple outputs remain frontend-only scaffolding

ResultHost has a pill selector, but the production voice response still emits `result_blocks=[result_block]` in `backend/main.py:1064`. The plan still describes one operation.

Reproduction: `Show my profile and my tickets` returns only the ticket list. There is no second profile result for the new selector to expose. Implement bounded compound reads, per-operation policy/outcomes, and retained multi-result conversation references before marking this complete.

### 5. Other requested boundaries remain incomplete

- Final grounded narration is still absent from the voice path; the dispatcher owns all replies. Do not restore an LLM override of policy, denial, readback, or receipts, but provide useful grounded answers from the final authorized result as specified.
- Mutation parameters are still reparsed from original text rather than using one validated typed proposal path.
- Hash recomputation now checks parameter tampering, but the manifest still excludes expiry and the confirmation readback is an independent stored string. Authorization rows are still inserted as consumed after business modification rather than validated by the planned executor boundary before execution.
- Readback normalization still removes all nonalphanumeric characters, including potentially meaningful signs/decimal separators.
- Private response retention cleanup only runs when another idempotency record is written. A quiet terminated session can leave cached private payloads/transcripts/generated audio on disk. Session-bound cleanup and bounded abandoned conversation-state cleanup remain needed.
- Concurrent in-flight duplicate turn requests are explicitly still uncoalesced in the implementation ledger.

These are specification-completion gaps; the internal tampering test does not demonstrate a remote browser exploit. Live wrong-speaker behavior also remains unverified.

## Verification

- Frontend `npm run build`: passed in this recheck; Vite reports the existing large-chunk advisory (about 989 kB before gzip).
- Employee graph and 42-ticket seed validators: passed.
- `git diff --check`: passed.
- Direct parser/dispatcher probes above: completed offline using temporary ticket state.
- Independent offline suite: **112 passed, 3 warnings in 37.60 seconds**, using `INTENTLOCK_OFFLINE_TESTS=1`, temporary identity/ticket stores, and `python -u -m pytest tests/ -q --ignore=tests/test_speech_integration.py --tb=short`. The sandboxed attempt stalled and was stopped; the completed host run used the same isolated/offline setup. The warnings were one collection warning and two deprecated HTTP status references.
- No successful browser layout, microphone, full speech, live Detectif/OpenAI, or kiosk-handoff validation is claimed.

Keep the fixes local until these remaining points and the manual demo matrix have been reviewed. No push or deployment is authorized by this recheck.
