"""
backend/services/context_service.py
Person 2 — Conversation Context, Selection Lifecycle, and Filter Semantics.

Implements bounded structured context for the IntentLock helpdesk:
- Strict actor and session isolation.
- Typed selection references for employees and tickets.
- Cycle-safe and bounds-checked ordinal and pronoun resolution.
- Explicit filter transition semantics: refine, replace, clear, presentation_only.
- Classification of presentation changes (reuse) vs new disclosures (requires evidence).
- Truthful empty-result preservation (empty list is NOT missing data).
- Bounded navigation history.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Tuple, Union


class DatasetStatus(str, Enum):
    """Explicit lifecycle status for query datasets, avoiding truthiness confusion."""
    NONE_CAPTURED = "none_captured"
    EMPTY_AUTHORIZED = "empty_authorized"
    POPULATED = "populated"
    FAILED = "failed"
    DENIED = "denied"
    EXPIRED = "expired"


class ContextValidationErrorType(str, Enum):
    ACTOR_MISMATCH = "actor_mismatch"
    SESSION_EXPIRED = "session_expired"
    RESULT_EVICTED = "result_evicted"
    REVISION_STALE = "revision_stale"
    SELECTION_INVALID = "selection_invalid"


class ContextError(Exception):
    """Base exception for context resolution errors."""
    pass


class ActorMismatchError(ContextError):
    """Raised when context actor does not match current authenticated actor."""
    pass


class SessionExpiredError(ContextError):
    """Raised when conversation context has expired past its TTL."""
    pass


class OrdinalOutOfRangeError(ContextError):
    """Raised when an ordinal reference ('the second person') exceeds visible count."""
    def __init__(self, ordinal: int, total_visible: int, message: Optional[str] = None):
        self.ordinal = ordinal
        self.total_visible = total_visible
        msg = message or f"Ordinal #{ordinal} is out of range; only {total_visible} items are visible."
        super().__init__(msg)


class ResourceKindMismatchError(ContextError):
    """Raised when referring to a resource of a different kind than active."""
    def __init__(self, requested_kind: str, active_kind: str):
        self.requested_kind = requested_kind
        self.active_kind = active_kind
        super().__init__(f"Cannot resolve {requested_kind} from active {active_kind} result.")


class MissingRequiredReferenceError(ContextError):
    """Raised when a pronoun ('their profile') has no active selection in context."""
    def __init__(self, pronoun: str, expected_kind: str):
        self.pronoun = pronoun
        self.expected_kind = expected_kind
        super().__init__(f"No active {expected_kind} selected for reference '{pronoun}'.")


@dataclass
class SelectionReference:
    """Typed selection reference with provenance and source result binding."""
    resource_kind: Literal["employee", "ticket"]
    resource_id: str
    source_result_id: str
    created_at: float = field(default_factory=time.time)
    display_order_index: Optional[int] = None
    label: Optional[str] = None


@dataclass
class ContextValidationResult:
    """Outcome of context validation check before handling an operation."""
    is_valid: bool
    error_code: Optional[ContextValidationErrorType] = None
    error_message: Optional[str] = None


@dataclass
class FilterActionClassification:
    """
    Classifies a filter or rechart request to distinguish harmless presentation changes
    from new data disclosures that require evidence validation.
    """
    action_type: Literal[
        "presentation_only",
        "refilter_delivered",
        "new_disclosure_retrieval",
        "broader_scope",
        "mutation"
    ]
    is_new_disclosure: bool
    explanation: str
    dimension_changed: Optional[str] = None


def apply_filter_transition(
    current_filters: Dict[str, Any],
    transition_type: Literal["refine", "replace", "clear", "clear_all"],
    filter_updates: Optional[Dict[str, Any]] = None,
    keys_to_clear: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Applies precise filter transition semantics:
    - refine: Narrows or adds constraints, preserving existing keys.
    - replace: Replaces specific dimensions (e.g. priority High -> Low) while strictly preserving
      unrelated dimensions (e.g. status, dates, team, department).
    - clear: Removes specified dimension(s) while strictly preserving other filters.
    - clear_all: Resets all active filters.
    """
    result = dict(current_filters)
    updates = filter_updates or {}

    if transition_type == "clear_all":
        return {}

    if transition_type == "clear":
        targets = set(keys_to_clear or [])
        # Also treat None values in updates as clear targets
        for k, v in updates.items():
            if v is None:
                targets.add(k)
        for key in targets:
            result.pop(key, None)
        return result

    if transition_type == "replace":
        # Overwrite only the specified dimensions in updates; leave other dimensions untouched
        for k, v in updates.items():
            if v is None:
                result.pop(k, None)
            else:
                result[k] = v
        return result

    if transition_type == "refine":
        # Intersect or add constraints
        for k, v in updates.items():
            if v is not None:
                result[k] = v
        return result

    return result


def classify_filter_action(
    current_filters: Dict[str, Any],
    requested_filters: Dict[str, Any],
    delivered_row_count: int,
    is_view_change_only: bool = False,
    scope_widened: bool = False,
    is_mutation: bool = False,
) -> FilterActionClassification:
    """
    Determines whether a transition is presentation-only (safe reuse of delivered data)
    or a new disclosure (reveals new private rows, requiring fresh evidence check).
    """
    if is_mutation:
        return FilterActionClassification(
            action_type="mutation",
            is_new_disclosure=True,
            explanation="Protected mutation operation requires step-up evidence and grant.",
        )

    if scope_widened:
        return FilterActionClassification(
            action_type="broader_scope",
            is_new_disclosure=True,
            explanation="Expanding query scope requires fresh authorization check.",
        )

    if is_view_change_only:
        return FilterActionClassification(
            action_type="presentation_only",
            is_new_disclosure=False,
            explanation="Reformatting delivered dataset without changing row selection requires no new evidence.",
        )

    # Check which dimensions changed
    all_keys = set(current_filters.keys()) | set(requested_filters.keys())
    changed_keys = [k for k in all_keys if current_filters.get(k) != requested_filters.get(k)]

    if not changed_keys:
        return FilterActionClassification(
            action_type="presentation_only",
            is_new_disclosure=False,
            explanation="Filters identical; pure presentation transformation.",
        )

    # Check for value replacement or filter clearing
    # E.g., High -> Low priority, or clearing a filter to show more items
    for k in changed_keys:
        curr_val = current_filters.get(k)
        new_val = requested_filters.get(k)

        # If a filter was removed, or value changed to a different partition
        if curr_val is not None and (new_val is None or new_val != curr_val):
            return FilterActionClassification(
                action_type="new_disclosure_retrieval",
                is_new_disclosure=True,
                explanation=f"Changing or clearing filter '{k}' discloses records not present in the delivered set.",
                dimension_changed=k,
            )

    # If all changes are purely adding new constraints (narrowing delivered records)
    # AND we have delivered rows
    if delivered_row_count > 0:
        return FilterActionClassification(
            action_type="refilter_delivered",
            is_new_disclosure=False,
            explanation="Refining existing delivered records to a narrower subset does not disclose new data.",
            dimension_changed=changed_keys[0] if changed_keys else None,
        )

    return FilterActionClassification(
        action_type="new_disclosure_retrieval",
        is_new_disclosure=True,
        explanation="Retrieving records with new constraints requires authorization check.",
        dimension_changed=changed_keys[0] if changed_keys else None,
    )


class ContextService:
    """
    Manages bounded conversation context lifecycle, typed selections, and reference resolution.
    """

    DEFAULT_TTL_SECONDS = 300.0
    MAX_HISTORY_DEPTH = 10

    def validate_context(
        self,
        actor_id: str,
        session_id: str,
        current_actor_id: str,
        current_session_id: str,
        last_accessed_at: float,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        now: Optional[float] = None,
    ) -> ContextValidationResult:
        """
        Validates actor and session binding before allowing context usage.
        Rejects actor mismatches and expired sessions.
        """
        current_time = now if now is not None else time.time()

        if actor_id != current_actor_id:
            return ContextValidationResult(
                is_valid=False,
                error_code=ContextValidationErrorType.ACTOR_MISMATCH,
                error_message=f"Context actor '{actor_id}' does not match authenticated actor '{current_actor_id}'.",
            )

        if session_id != current_session_id:
            return ContextValidationResult(
                is_valid=False,
                error_code=ContextValidationErrorType.ACTOR_MISMATCH,
                error_message="Session ID mismatch.",
            )

        if (current_time - last_accessed_at) > ttl_seconds:
            return ContextValidationResult(
                is_valid=False,
                error_code=ContextValidationErrorType.SESSION_EXPIRED,
                error_message=f"Context has expired past TTL of {ttl_seconds} seconds.",
            )

        return ContextValidationResult(is_valid=True)

    def resolve_ordinal(
        self,
        visible_ids: List[str],
        ordinal: int,
        resource_kind: Optional[str] = None,
        active_resource_kind: Optional[str] = None,
    ) -> str:
        """
        Resolves a 1-based ordinal ('first ticket', 'second person') against visible IDs.
        Raises OrdinalOutOfRangeError or ResourceKindMismatchError.
        """
        if resource_kind and active_resource_kind and resource_kind != active_resource_kind:
            raise ResourceKindMismatchError(
                requested_kind=resource_kind,
                active_kind=active_resource_kind,
            )

        if not visible_ids:
            raise OrdinalOutOfRangeError(ordinal=ordinal, total_visible=0)

        if ordinal < 1 or ordinal > len(visible_ids):
            raise OrdinalOutOfRangeError(ordinal=ordinal, total_visible=len(visible_ids))

        return visible_ids[ordinal - 1]

    def resolve_selection(
        self,
        explicit_target_id: Optional[str] = None,
        selected_employee: Optional[SelectionReference] = None,
        selected_ticket: Optional[SelectionReference] = None,
        requested_kind: Optional[Literal["employee", "ticket"]] = None,
        pronoun: Optional[str] = None,
    ) -> Optional[str]:
        """
        Resolves the active target ID:
        1. Explicit target in current utterance always overrides stale selection.
        2. If requested_kind is employee, returns employee selection (never ticket).
        3. If requested_kind is ticket, returns ticket selection (never employee).
        4. If a pronoun was used ('their profile', 'this ticket') but selection is missing,
           raises MissingRequiredReferenceError (NEVER falls back to actor self!).
        """
        if explicit_target_id:
            return explicit_target_id

        if requested_kind == "employee":
            if selected_employee:
                return selected_employee.resource_id
            if pronoun:
                raise MissingRequiredReferenceError(pronoun=pronoun, expected_kind="employee")
            return None

        if requested_kind == "ticket":
            if selected_ticket:
                return selected_ticket.resource_id
            if pronoun:
                raise MissingRequiredReferenceError(pronoun=pronoun, expected_kind="ticket")
            return None

        # If no specific kind requested, check pronoun requirements
        if pronoun:
            # If pronoun suggests a person ('their', 'he', 'she')
            if pronoun.lower() in ("their", "his", "her", "them"):
                if selected_employee:
                    return selected_employee.resource_id
                raise MissingRequiredReferenceError(pronoun=pronoun, expected_kind="employee")
            # If pronoun suggests a thing ('this', 'it', 'that')
            if selected_ticket:
                return selected_ticket.resource_id
            if selected_employee:
                return selected_employee.resource_id
            raise MissingRequiredReferenceError(pronoun=pronoun, expected_kind="resource")

        return None
