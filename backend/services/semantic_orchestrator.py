"""IntentLock — Person 2 Stage 3 Semantic Interpretation Orchestrator.

Implements the controlled multi-step interpretation pipeline:
A. Validate & bound user input.
B. Extract explicit actor claim separately (via claim_extractor).
C. Recognize high-certainty deterministic exact commands (with negation, quoting & privacy checks).
D. Route flexible commands through structured model planner (OpenAI structured outputs).
E. Enforce semantic bounds, operation registry checks, grounding validation, and compound restrictions.

CRITICAL INVARIANTS:
1. Exact command matching respects negation (e.g. 'do not confirm' is never confirm).
2. Quotes are protected ('create ticket titled cancel' is not cancel).
3. Private queries are never misrouted to public help.
4. Model-invented actor claims without utterance grounding are stripped.
5. Compound mutations are strictly disallowed.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from backend.services.claim_extractor import extract_actor_claim, validate_plan_claim_grounding
from backend.services.conversation_dispatch import IntentPlan, PlannerContext, parse_local
from backend.services.operation_registry import OperationRegistry


# High-certainty exact command patterns
_EXACT_HELP_PATTERNS = [
    re.compile(r"^(?:help|what can i ask|what are the options|helpdesk options|show help|menu)\??$", re.IGNORECASE),
]

_EXACT_CONFIRM_PATTERNS = [
    re.compile(r"^(?:(?:i\s+)?confirm(?:\s+(?:action|proposal|this|ticket|update))?|yes(?:,\s*confirm)?)\.?$", re.IGNORECASE),
    re.compile(r"^i\s+confirm\s+(?:update|create|comment)\b.*$", re.IGNORECASE),
]

_EXACT_CANCEL_PATTERNS = [
    re.compile(r"^(?:(?:i\s+)?cancel(?:\s+(?:action|proposal|this|draft))?|abort|nevermind)\.?$", re.IGNORECASE),
]

_EXACT_BACK_PATTERNS = [
    re.compile(r"^(?:go\s+)?back(?:\s+to\s+previous)?\.?$", re.IGNORECASE),
]

# Negation indicators preventing confirm/cancel misclassification
_NEGATED_CONFIRM = re.compile(r"\b(?:do\s+not|don't|not)\s+confirm\b", re.IGNORECASE)
_NEGATED_CANCEL = re.compile(r"\b(?:do\s+not|don't|not)\s+cancel\b", re.IGNORECASE)

# Private context terms that disqualifies classification as public help
_PRIVATE_TERMS = re.compile(
    r"\b(?:my|myself|private|profile|ticket|tickets|salary|contact|phone|manager|team|reports|performance|emp-\d{3,6})\b",
    re.IGNORECASE,
)

# Quoted content detector
_QUOTED_CONTENT = re.compile(r"['\"]([^'\"]+)['\"]")


def is_exact_public_help(utterance: str) -> bool:
    """True if utterance is purely requesting public kiosk help without private references."""
    clean = utterance.strip()
    if _PRIVATE_TERMS.search(clean):
        # User said e.g. "Help me with my private record" -> NOT public help
        return False
    return any(p.match(clean) for p in _EXACT_HELP_PATTERNS)


def is_exact_confirmation(utterance: str) -> bool:
    """True if utterance is an unambiguous confirmation of a pending proposal."""
    clean = utterance.strip()
    if _NEGATED_CONFIRM.search(clean):
        return False
    # If quoted content contains confirm, ignore it
    unquoted = _QUOTED_CONTENT.sub("", clean).strip()
    return any(p.match(unquoted) for p in _EXACT_CONFIRM_PATTERNS)


def is_exact_cancellation(utterance: str) -> bool:
    """True if utterance is an unambiguous cancellation of a pending proposal."""
    clean = utterance.strip()
    if _NEGATED_CANCEL.search(clean):
        return False
    # If phrase has "create ticket" or "ticket titled", don't treat as cancel
    if re.search(r"\b(?:create|update|open|log)\s+(?:a\s+)?ticket\b", clean, re.IGNORECASE):
        return False
    unquoted = _QUOTED_CONTENT.sub("", clean).strip()
    return any(p.match(unquoted) for p in _EXACT_CANCEL_PATTERNS)


def is_exact_back(utterance: str) -> bool:
    """True if utterance is an unambiguous back-navigation command."""
    clean = utterance.strip()
    return any(p.match(clean) for p in _EXACT_BACK_PATTERNS)


async def interpret_request(
    utterance: str,
    context: Optional[PlannerContext] = None,
    planner_adapter: Optional[Any] = None,
    state: Optional[Any] = None,
) -> IntentPlan:
    """Orchestrate end-to-end semantic interpretation of an untrusted user command.

    Follows the 6-step interpretation pipeline with strict boundaries and zero hallucination.
    """
    # Step A: Validate and bound input
    if not utterance or not utterance.strip():
        return IntentPlan(operation="clarify")

    clean_text = utterance.strip()
    if len(clean_text) > 1000:
        # Long input: reject rather than silently truncating trailing negation or constraints
        return IntentPlan(operation="clarify")

    # Step B: Extract candidate actor claim separately
    claim_extraction = extract_actor_claim(clean_text)

    # Step C: High-certainty deterministic exact commands
    if is_exact_public_help(clean_text):
        return IntentPlan(operation="help")

    if is_exact_confirmation(clean_text):
        return IntentPlan(operation="confirm")

    if is_exact_cancellation(clean_text):
        return IntentPlan(operation="cancel")

    if is_exact_back(clean_text):
        return IntentPlan(operation="back")

    # Step D: Route flexible requests through model planner or local parser
    plan: Optional[IntentPlan] = None
    if planner_adapter and hasattr(planner_adapter, "plan_request"):
        try:
            plan = await planner_adapter.plan_request(clean_text, context=context)
        except Exception:
            plan = None

    # Deterministic local fallback if model planner did not produce a valid plan
    if plan is None:
        plan = parse_local(clean_text, state=state)

    # Step E: Validate semantic consistency & boundaries
    # 1. Operation must be supported in the OperationRegistry
    if not OperationRegistry.is_supported(plan.operation):
        return IntentPlan(operation="clarify")

    # 2. Actor claim grounding
    if plan.actor_claim:
        grounded_id = validate_plan_claim_grounding(clean_text, plan.actor_claim)
        if not grounded_id:
            # Model hallucinated actor_claim without explicit self-identification
            plan.actor_claim = None

    # If planner didn't extract actor_claim but step B found a valid explicit claim, wire it
    if not plan.actor_claim and claim_extraction.disposition == "valid_claim" and claim_extraction.normalized_id:
        plan.actor_claim = claim_extraction.normalized_id

    # 3. Compound request boundaries (examining both root and child plans)
    if plan.operation == "compound":
        # Disallow compound mutations (e.g. create_ticket in compound)
        # Person 2 compound queries are strictly read-only
        if plan.field or plan.value or plan.ticket_id:
            return IntentPlan(operation="clarify")
        if plan.compound_plans:
            if len(plan.compound_plans) > 3:
                return IntentPlan(operation="clarify")
            for sub in plan.compound_plans:
                meta = OperationRegistry.get(sub.operation)
                if meta and meta.category in ("proposal", "confirmation", "cancellation"):
                    return IntentPlan(operation="clarify")

    return plan
