"""IntentLock — Person 2 Stage 2 Explicit Actor-Claim Extraction.

Extracts, normalizes, and grounds explicit self-identifications from spoken utterances,
distinguishing candidate actor claims from query targets, role mentions, negated IDs,
quoted text, questions, and conflicting multiple claims.

CRITICAL INVARIANTS:
1. Untrusted: A candidate claim is NEVER an authentication decision or verified actor.
2. Grounded: Model-generated claims must be grounded in explicit self-identification.
3. No Session: This module never mints sessions, checks biometrics, or queries private DBs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Tuple


ClaimDisposition = Literal[
    "valid_claim",
    "role_only",
    "negated",
    "question",
    "quoted",
    "conflict",
    "none",
]


@dataclass(frozen=True)
class ClaimExtractionResult:
    """Internal provenance and semantic breakdown of identity mentions in an utterance."""
    raw_mention: Optional[str]
    claimed_id: Optional[str]
    normalized_id: Optional[str]
    role_claim: Optional[str]
    confidence: float
    is_negated: bool
    is_question: bool
    is_quoted: bool
    is_conflicted: bool
    disposition: ClaimDisposition
    clarification_reason: Optional[str] = None


# Canonical employee ID regex: EMP-XXXX or emp xxxx or empXXXX
_CANONICAL_EMP_PATTERN = re.compile(
    r"\b(?:emp|employee)[-\s]?(\d{3,6})\b",
    re.IGNORECASE,
)

# Common roles in organizational context
_ROLE_PATTERNS = [
    (re.compile(r"\b(?:i\s+am|i'm|as)\s+(?:the\s+)?cto\b", re.IGNORECASE), "CTO"),
    (re.compile(r"\b(?:i\s+am|i'm|as)\s+(?:the\s+)?ceo\b", re.IGNORECASE), "CEO"),
    (re.compile(r"\b(?:i\s+am|i'm|as)\s+(?:the\s+)?cfo\b", re.IGNORECASE), "CFO"),
    (re.compile(r"\b(?:i\s+am|i'm|as)\s+(?:the\s+)?vp\b", re.IGNORECASE), "VP"),
    (re.compile(r"\b(?:i\s+am|i'm|as)\s+(?:a\s+|the\s+)?(?:engineering\s+)?manager\b", re.IGNORECASE), "Manager"),
    (re.compile(r"\b(?:i\s+am|i'm|as)\s+(?:a\s+|the\s+)?(?:lead|senior\s+)?engineer\b", re.IGNORECASE), "Engineer"),
    (re.compile(r"\b(?:i\s+am|i'm|as)\s+(?:a\s+|the\s+)?team\s+lead\b", re.IGNORECASE), "Team Lead"),
]

# Patterns indicating explicit self-identification
_SELF_IDENTIFICATION_PREFIXES = [
    re.compile(r"\b(?:my\s+(?:employee\s+)?id\s+is|my\s+id\s+is|this\s+is|i\s+am|i'm)\s+([a-z0-9\-\s]+)", re.IGNORECASE),
]

# Negation indicators preceding self identification
_NEGATION_PATTERNS = [
    re.compile(r"\b(?:i\s+am\s+not|i'm\s+not|not\s+(?:emp|employee))\b", re.IGNORECASE),
]

# Question indicators
_QUESTION_PATTERNS = [
    re.compile(r"^(?:am\s+i|is\s+my\s+id|could\s+i\s+be)\b", re.IGNORECASE),
]

# Quoted content patterns (single or double quotes)
_QUOTED_PATTERNS = [
    re.compile(r"['\"]([^'\"]+)['\"]"),
    re.compile(r"\b(?:ticket|comment|description|notes?)\s+(?:says?|contains?|states?)\s+['\"]?([^'\"\n]+)['\"]?", re.IGNORECASE),
]


def normalize_employee_id(raw_id: str) -> Optional[str]:
    """Conservative normalization for employee IDs.

    Normalizes case, removes redundant spacing and hyphens into standard EMP-XXXX format.
    Never invents missing digits.
    """
    if not raw_id:
        return None
    cleaned = raw_id.strip().upper()
    match = _CANONICAL_EMP_PATTERN.search(cleaned)
    if match:
        digits = match.group(1)
        return f"EMP-{digits}"
    return None


def extract_actor_claim(utterance: str) -> ClaimExtractionResult:
    """Extract an explicit candidate actor claim from untrusted user utterance.

    Strictly separates:
    - Candidate actor claim (speaker claiming who they are)
    - Query target (e.g. 'Show EMP-2001's profile')
    - Role claim (e.g. 'I am the CTO' -> role_claim='CTO', claimed_id=None)
    - Negations ('I am not EMP-4002' -> is_negated=True)
    - Questions ('Am I EMP-4002?' -> is_question=True)
    - Quoted text ('The ticket says "I am EMP-4002"')
    - Multiple conflicting claims ('My ID is EMP-4002, actually EMP-2001')
    """
    if not utterance or not utterance.strip():
        return ClaimExtractionResult(
            raw_mention=None,
            claimed_id=None,
            normalized_id=None,
            role_claim=None,
            confidence=0.0,
            is_negated=False,
            is_question=False,
            is_quoted=False,
            is_conflicted=False,
            disposition="none",
        )

    text = utterance.strip()

    # 1. Detect Quoted Content
    quoted_spans = []
    for q_pattern in _QUOTED_PATTERNS:
        for q_match in q_pattern.finditer(text):
            quoted_spans.append((q_match.start(), q_match.end(), q_match.group(0)))

    # 2. Check for Role-only Claims
    role_claim: Optional[str] = None
    for pattern, role_name in _ROLE_PATTERNS:
        if pattern.search(text):
            role_claim = role_name
            break

    # 3. Detect Questions
    is_question = bool(text.endswith("?") or any(qp.search(text) for qp in _QUESTION_PATTERNS))

    # 4. Detect Negation
    is_negated = bool(any(np.search(text) for np in _NEGATION_PATTERNS))

    # 5. Extract all mentions of employee IDs and evaluate their syntactic context
    # We look for explicit self-identification anchors like "my id is...", "i am EMP...", "this is EMP..."
    emp_matches = list(_CANONICAL_EMP_PATTERN.finditer(text))

    if not emp_matches:
        if role_claim:
            return ClaimExtractionResult(
                raw_mention=role_claim,
                claimed_id=None,
                normalized_id=None,
                role_claim=role_claim,
                confidence=0.8,
                is_negated=is_negated,
                is_question=is_question,
                is_quoted=False,
                is_conflicted=False,
                disposition="role_only",
                clarification_reason="ROLE_CLAIM_REQUIRES_EMPLOYEE_ID",
            )
        return ClaimExtractionResult(
            raw_mention=None,
            claimed_id=None,
            normalized_id=None,
            role_claim=None,
            confidence=0.0,
            is_negated=is_negated,
            is_question=is_question,
            is_quoted=False,
            is_conflicted=False,
            disposition="none",
        )

    # Filter out matches that appear entirely inside quoted spans
    unquoted_matches = []
    quoted_matches = []
    for m in emp_matches:
        m_start, m_end = m.start(), m.end()
        is_in_quote = any(q_start <= m_start and m_end <= q_end for q_start, q_end, _ in quoted_spans)
        if is_in_quote:
            quoted_matches.append(m)
        else:
            unquoted_matches.append(m)

    if not unquoted_matches and quoted_matches:
        # All ID mentions were inside quotes (e.g. The ticket says 'I am EMP-4002')
        return ClaimExtractionResult(
            raw_mention=quoted_matches[0].group(0),
            claimed_id=None,
            normalized_id=None,
            role_claim=role_claim,
            confidence=0.0,
            is_negated=is_negated,
            is_question=is_question,
            is_quoted=True,
            is_conflicted=False,
            disposition="quoted",
            clarification_reason="QUOTED_TEXT_NOT_CLAIM",
        )

    # Evaluate unquoted matches for explicit self-identification vs target queries
    self_identified_ids: List[Tuple[str, str]] = []  # (raw, normalized)
    target_only_ids: List[Tuple[str, str]] = []

    for m in unquoted_matches:
        raw_token = m.group(0)
        norm_id = normalize_employee_id(raw_token)
        if not norm_id:
            continue

        # Look at preceding characters within the immediate clause
        start_idx = max(0, m.start() - 40)
        preceding = text[start_idx:m.start()].lower()
        # Bound preceding to the immediate clause after punctuation like . ! ? ;
        clause = re.split(r"[.?!;]", preceding)[-1].strip()

        # Check for questioned identity
        is_clause_question = any(qp in clause for qp in ["am i", "could i be", "is my id", "is my employee id"])
        if is_clause_question or (is_question and any(qp in text.lower() for qp in ["am i", "could i be", "is my id"])):
            return ClaimExtractionResult(
                raw_mention=raw_token,
                claimed_id=None,
                normalized_id=None,
                role_claim=role_claim,
                confidence=0.0,
                is_negated=is_negated,
                is_question=True,
                is_quoted=False,
                is_conflicted=False,
                disposition="question",
                clarification_reason="QUESTION_NOT_ASSERTED_IDENTITY",
            )

        # Check for self-identification phrasing in the immediate clause
        is_self = any(prefix in clause for prefix in [
            "my employee id is", "my id is", "i am", "i'm", "this is", "myself", "speaking is"
        ])

        # Explicit target indicators
        is_target_marker = any(marker in clause for marker in [
            "profile for", "profile of", "show", "view", "about", "manages", "reports to", "under", "for employee", "for emp", "tickets for"
        ])

        if is_self and not is_target_marker:
            self_identified_ids.append((raw_token, norm_id))
        elif is_target_marker:
            target_only_ids.append((raw_token, norm_id))
        else:
            # Standalone match without clear prefix
            if text.strip().upper() == norm_id:
                self_identified_ids.append((raw_token, norm_id))
            else:
                target_only_ids.append((raw_token, norm_id))

    # Evaluate multiple claims for conflict
    distinct_self_ids = list(dict.fromkeys([nid for _, nid in self_identified_ids]))

    if len(distinct_self_ids) > 1:
        # User said e.g. "My ID is EMP-4002, actually EMP-2001"
        return ClaimExtractionResult(
            raw_mention=f"{distinct_self_ids[0]}, {distinct_self_ids[1]}",
            claimed_id=None,
            normalized_id=None,
            role_claim=role_claim,
            confidence=0.0,
            is_negated=is_negated,
            is_question=is_question,
            is_quoted=False,
            is_conflicted=True,
            disposition="conflict",
            clarification_reason="CONFLICTING_IDENTITY_CLAIMS",
        )

    if not self_identified_ids:
        # There was an employee ID in the utterance, but it was a query target, not a self-identification
        if role_claim:
            return ClaimExtractionResult(
                raw_mention=role_claim,
                claimed_id=None,
                normalized_id=None,
                role_claim=role_claim,
                confidence=0.8,
                is_negated=is_negated,
                is_question=is_question,
                is_quoted=False,
                is_conflicted=False,
                disposition="role_only",
                clarification_reason="ROLE_CLAIM_REQUIRES_EMPLOYEE_ID",
            )
        return ClaimExtractionResult(
            raw_mention=None,
            claimed_id=None,
            normalized_id=None,
            role_claim=None,
            confidence=0.0,
            is_negated=is_negated,
            is_question=is_question,
            is_quoted=False,
            is_conflicted=False,
            disposition="none",
        )

    raw_token, norm_id = self_identified_ids[0]

    # Handle Negation
    if is_negated:
        return ClaimExtractionResult(
            raw_mention=raw_token,
            claimed_id=None,
            normalized_id=None,
            role_claim=role_claim,
            confidence=0.0,
            is_negated=True,
            is_question=is_question,
            is_quoted=False,
            is_conflicted=False,
            disposition="negated",
            clarification_reason="NEGATED_IDENTITY_CLAIM",
        )

    # Handle Questions
    if is_question:
        return ClaimExtractionResult(
            raw_mention=raw_token,
            claimed_id=None,
            normalized_id=None,
            role_claim=role_claim,
            confidence=0.0,
            is_negated=False,
            is_question=True,
            is_quoted=False,
            is_conflicted=False,
            disposition="question",
            clarification_reason="QUESTION_NOT_ASSERTED_IDENTITY",
        )

    # Valid grounded claim
    return ClaimExtractionResult(
        raw_mention=raw_token,
        claimed_id=norm_id,
        normalized_id=norm_id,
        role_claim=role_claim,
        confidence=0.95,
        is_negated=False,
        is_question=False,
        is_quoted=False,
        is_conflicted=False,
        disposition="valid_claim",
    )


def validate_plan_claim_grounding(utterance: str, plan_actor_claim: Optional[str]) -> Optional[str]:
    """Validate that a model-generated actor_claim is grounded in explicit self-identification.

    If the LLM outputs actor_claim='EMP-4002' when the user never claimed that ID,
    this function rejects the claim and returns None.
    If the utterance contains a valid grounded self-identification, it returns the normalized ID.
    """
    if not plan_actor_claim:
        return None

    extraction = extract_actor_claim(utterance)
    if extraction.disposition == "valid_claim" and extraction.normalized_id:
        norm_plan_claim = normalize_employee_id(plan_actor_claim)
        if norm_plan_claim == extraction.normalized_id:
            return extraction.normalized_id

    # Model hallucinated or ungrounded claim -> discard it
    return None
