# IntentLock — Person 2 Stage 9: Grounded Narration and Model Budget Optimization

**Role**: Person 2 (Sharan) — Semantic understanding, conversation context, queries, and backend result generation.  
**Date**: October 2026  
**Status**: Completed and Verified

---

## 1. Overview and Core Philosophy

In a high-security voice helpdesk, the model must **never be an authoritative decision-maker or an ungrounded storyteller**. The primary source of truth is always the deterministic policy-governed data retrieved by Person 1's authorization service and Person 2's query engines.

Stage 9 formalizes three non-negotiable operational principles for all LLM interaction:
1. **Strict Truthfulness**: An LLM must never claim that missing records were accessed or invent employees, metrics, or tickets. Blank outputs or refusals fail closed into deterministic fallbacks.
2. **Model Call Minimization**: High-frequency, deterministic tasks (lookups, counts, confirmations, cancellations, public help, and offline tests) bypass the LLM entirely, saving latency and cost.
3. **Bounded Context & Privacy**: Context passed to external models is stripped of internal credentials, raw database secrets, and unbound data. Exception logs never leak caller queries or private tokens.

---

## 2. Truthfulness & Grounding Verification

In `backend/adapters/openai_answer_adapter.py`, the `OpenAIAnswerAdapter` implements post-generation grounding verification via `verify_grounding(clean_output, authorized_context)`:

### A. Blank and Empty Output Rejection
* **Risk**: Previous behavior or dummy fallback returned generic phrases like *"I have accessed your authorized records..."* even when the model output was empty or timed out. In `main.py:1013`, any returned string with `is_available=True` overwrites the deterministic summary.
* **Guarantee**: When the model returns empty or whitespace-only text, `generate_answer()` sets `is_available=False`, `grounded=False`, `error_message="EMPTY_OUTPUT"`, and `answer_text=""`. This guarantees `main.py` preserves the accurate deterministic `spoken_summary`.

### B. Model Refusal Handling
* **Risk**: Generic model refusals (e.g., *"I cannot assist with that request"*) look like successful answers if unchecked.
* **Guarantee**: The adapter tests for refusal patterns (`re.search(r"^(?:i cannot assist|i am unable to help|i cannot fulfill|i am sorry, but i cannot)\b", clean, re.I)`). If triggered, the response is marked `is_available=False`, `grounded=False`, and `error_message="UNGROUNDED: MODEL_REFUSAL"`.

### C. Metric Contradiction Guard
* **Risk**: An LLM may hallucinate counts (e.g. claiming *"You have 15 open tickets"* when the authorized payload contains only 3).
* **Guarantee**: `verify_grounding` extracts numerical assertions and checks them against `payload.total_count`. If a discrepancy is detected, the LLM response is rejected (`is_available=False, grounded=False`), preventing user misinformation over the voice channel.

---

## 3. Deterministic Fast Paths & Offline Guarantees

Model calls are skipped entirely for all operations where deterministic results are sufficient:

| Operation / Path | Fast Path Implementation | LLM Invocation |
| :--- | :--- | :--- |
| **Public Help** (`help`) | Pre-compiled static help FAQ | **Skipped** |
| **Confirm Action** (`confirm`) | Exact cryptographic/action draft confirmation | **Skipped** |
| **Cancel Action** (`cancel`) | Exact draft state cancellation | **Skipped** |
| **Team Count** (`team_count`) | Direct SQL/in-memory count aggregation | **Skipped** |
| **Headcount** (`headcount`) | Deterministic org tree traversal & scope filtering | **Skipped** |
| **Back Navigation** (`back`) | Conversation snapshot stack pop | **Skipped** |
| **Single Entity Lookup** | Deterministic profile/ticket row presentation | **Skipped** |
| **Offline Testing** | `INTENTLOCK_OFFLINE_TESTS=1` environment guard | **Strictly Skipped** (Zero API Spend) |

---

## 4. Compound Query Narration Preservation

When a compound request is dispatched (e.g., *"Show my profile and my team's tickets"*):
- Both plans execute independently under their respective authorization rules.
- In `backend/services/conversation_dispatch.py`, `_dispatch_compound()` combines both spoken summaries:
  ```python
  combined_spoken = f"{res1.spoken_summary} Additionally, {res2.spoken_summary}"
  ```
- Both visual blocks are returned in `result_blocks: [block1, block2]`, preventing either query from being swallowed or replaced by a single ungrounded LLM summary.

---

## 5. Token and Latency Budgeting

To ensure sub-second voice turnaround and minimal API expense:
1. **Bounded Planning Context**:
   `plan_request()` strictly allowlists filter keys (`priority`, `status`, `from_date`, etc.) and strips any sensitive tokens (`key`, `secret`, `password`, `token`, `cred`, `jwt`, `auth`, `session`).
2. **Output Token Capping**:
   - `plan_request`: Capped at `max_output_tokens=350`.
   - `generate_answer`: Capped at `max_output_tokens=settings.OPENAI_MAX_OUTPUT_TOKENS` (default 250).
3. **Timeouts**:
   Configured with `OPENAI_TIMEOUT_SECONDS` (default 3.0s). Any timeout triggers `openai.APITimeoutError` which immediately fails closed (`error_message="TIMEOUT"`).

---

## 6. Telemetry & Observability

Every adapter call records structured telemetry while maintaining strict caller privacy:
- **Telemetry Metrics**: `correlation_id`, `model`, `latency_ms`, `words_count`, `tokens_used` (from `response.usage.total_tokens`), and `grounded=True/False`.
- **Sanitized Exception Logging**: In `generate_answer()`, exceptions are logged solely as:
  ```python
  logger.error(f"OpenAI generation error on {correlation_id}: {err_type}")
  ```
  Neither the caller's spoken question nor the internal employee payload is ever logged in cleartext exception traces, preventing credential and PII leakage.

---

## 7. Verification Matrix

The Stage 9 implementation is verified by `tests/test_answer_adapter_truthfulness.py`:

| Test Name | Verified Invariant | Result |
| :--- | :--- | :--- |
| `test_unconfigured_adapter_fails_closed` | Missing API key returns `is_available=False` without mocks | **PASSED** |
| `test_empty_model_output_marks_unavailable_no_fabrication` | Blank model text returns `is_available=False, error_message=EMPTY_OUTPUT` | **PASSED** |
| `test_refusal_model_output_fails_grounding` | Model refusals fail grounding and are marked unavailable | **PASSED** |
| `test_metric_contradiction_fails_grounding` | Hallucinated counts (15 vs 3) fail grounding verification | **PASSED** |
| `test_grounded_truthful_narration_succeeds` | Grounded facts agreeing with context return valid answer & token telemetry | **PASSED** |
| `test_rate_limit_error_handled_gracefully` | Rate limits return clean `RATE_LIMIT_EXCEEDED` error | **PASSED** |
| `test_timeout_error_handled_gracefully` | API timeouts return clean `TIMEOUT` error | **PASSED** |
| `test_privacy_in_exception_logging` | Exceptions log only error type and turn ID; no query/context PII | **PASSED** |
| `test_plan_request_strips_sensitive_filter_keys` | Non-allowlisted / sensitive keys are stripped from planning input hints | **PASSED** |
