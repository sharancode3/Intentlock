# IntentLock — Person 2 Stage 2: Actor-Claim Separation & Grounding
**Author:** Sharan (Person 2) — Intelligence, Semantic Planning & Results  
**Baseline Commit:** `d189664ddfe789da0b22e1269e5ba0d42fdb4bf6`  
**Date:** 2026-10-17  
**Status:** Implemented Locally & Verified  

---

## 1. Executive Summary & Design Invariants

In Stage 2, Person 2 establishes a dedicated, bounded claim-extraction module: `backend/services/claim_extractor.py`.  
This module decouples **untrusted spoken identity claims** from **authorized query targets** and **role mentions**.

### Critical Security Invariants:
1. **Untrusted Input:** A candidate claim (`plan.actor_claim` or `ClaimExtractionResult.claimed_id`) is strictly untrusted input. It **never** constitutes authentication or verified authority.
2. **Deterministic Actor Separation:** `dispatcher.dispatch` continues to enforce `actor_id` established by Person 1's gateway and Detectif checks. Even if an untrusted user claims `"I am EMP-4002"`, the dispatcher denies access if `actor_id == ""`.
3. **No Session or Biometric Calls:** Claim extraction executes synchronously, entirely in-memory, without calling Detectif, Supabase, or issuing session tokens.
4. **Model Grounding:** Model-generated `actor_claim` fields from OpenAI structured planning are verified against explicit self-identification in the utterance text via `validate_plan_claim_grounding()`. If an LLM hallucinates an identity claim, it is stripped.

---

## 2. Capabilities Implemented in `claim_extractor.py`

| Capability | Spoken Utterance Example | Extraction Result | Provenance Disposition |
|---|---|---|---|
| **Explicit Self-Identification** | *"My employee ID is EMP-4002"* | `claimed_id="EMP-4002"`, `normalized_id="EMP-4002"` | `valid_claim` |
| **Query Target Only** | *"Show EMP-4002's profile"* | `claimed_id=None`, target untouched | `none` |
| **Actor & Target in One Utterance** | *"I am EMP-4002. Show EMP-2001's profile"* | `claimed_id="EMP-4002"` (actor), target `EMP-2001` separate | `valid_claim` |
| **Role-Only Claim** | *"I am the CTO"* | `role_claim="CTO"`, `claimed_id=None` (no inferred ID) | `role_only` (`ROLE_CLAIM_REQUIRES_EMPLOYEE_ID`) |
| **Negated Identity** | *"I am not EMP-4002"* | `claimed_id=None`, `is_negated=True` | `negated` (`NEGATED_IDENTITY_CLAIM`) |
| **Questioned Identity** | *"Am I EMP-4002?"* | `claimed_id=None`, `is_question=True` | `question` (`QUESTION_NOT_ASSERTED_IDENTITY`) |
| **Quoted Text** | *'The ticket says "I am EMP-4002"'* | `claimed_id=None`, `is_quoted=True` | `quoted` (`QUOTED_TEXT_NOT_CLAIM`) |
| **Conflicting Multiple Claims** | *"My ID is EMP-4002, actually EMP-2001"* | `claimed_id=None`, `is_conflicted=True` | `conflict` (`CONFLICTING_IDENTITY_CLAIMS`) |
| **Normalization** | *"emp 4002"*, *"emp-4002"*, *"EMP4002"* | `normalized_id="EMP-4002"` (standard uppercase hyphenated) | `valid_claim` |
| **Model Grounding** | Model outputs `actor_claim="EMP-4002"` for *"Show EMP-4002"* | Rejected by `validate_plan_claim_grounding` $\rightarrow$ `None` | `none` |

---

## 3. Acceptance Verification & Test Results

All 13 tests in `tests/test_claim_extraction.py` passed offline (`INTENTLOCK_OFFLINE_TESTS=1`):

```text
============================= test session starts =============================
platform win32 -- Python 3.10.11, pytest-8.4.2, pluggy-1.6.0
rootdir: C:\SHARAN PROJECTS\IntentLock
collected 13 items

tests\test_claim_extraction.py .............                             [100%]

============================= 13 passed in 0.51s ==============================
```

### Verified Behaviors:
- `test_explicit_actor_id_extraction`: Confirms extraction of `EMP-4002`.
- `test_explicit_target_only_does_not_assert_actor`: Target query does not produce candidate claim.
- `test_actor_and_target_in_single_utterance_remain_distinct`: Utterance clause isolation prevents target ID from bleeding into candidate claim.
- `test_role_only_claim_does_not_infer_employee_id`: CTO claim does not guess an employee ID.
- `test_negated_claim_does_not_assert_identity`: Negation flag prevents claim assertion.
- `test_questioned_claim_does_not_assert_identity`: Questions do not assert identity.
- `test_quoted_claim_does_not_assert_identity`: Quoted spans do not assert identity.
- `test_conflicting_multiple_claims_produce_clarification`: Multiple claims reject silent choice.
- `test_normalization_variations`: Normalizes spacing, casing, and prefixes without inventing missing digits.
- `test_compound_claim_with_relationship`: Correctly extracts claim while leaving relationship for Stage 4 resolution.
- `test_model_invented_claim_grounding_rejection`: Un-grounded model outputs are purged.
- `test_authenticated_actor_unchanged_by_candidate_claim`: Runtime proof that `dispatcher.dispatch` denies unverified guests and isolates verified actor IDs from plan claims.
- `test_zero_session_or_provider_calls`: Strictly pure semantic parsing.

---

## 4. Gateway Integration Request for Person 1

- **Module Provided:** `backend/services/claim_extractor.py` (`extract_actor_claim`, `validate_plan_claim_grounding`).
- **Current Gateway Implementation:** `backend/main.py:749` currently uses a simple regex:
  ```python
  emp_match = _EXTRACT_EMP_REGEX.search(transcript_text)
  ```
- **Proposed Integration in `main.py`:**
  ```python
  from backend.services.claim_extractor import extract_actor_claim

  claim_res = extract_actor_claim(transcript_text)
  if claim_res.disposition == "valid_claim" and claim_res.normalized_id:
      candidate_emp_id = claim_res.normalized_id
  elif claim_res.disposition == "conflict":
      # Return explicit clarification for conflicting claims
      return VoiceTurnResponse(status="clarification", clarification_reason=claim_res.clarification_reason, ...)
  ```
- **Wiring Status:** Implemented locally and tested in Person 2 domain; gateway integration in `main.py` is pending Person 1 adoption.
