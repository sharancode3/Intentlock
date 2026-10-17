"""
tests/test_context_and_filters.py
Tests for Person 2 Stage 5: Conversation Context, Selection Lifecycle, and Filter Semantics.
"""

import time
import pytest
from unittest.mock import MagicMock

from backend.services.context_service import (
    ContextService,
    DatasetStatus,
    ContextValidationErrorType,
    OrdinalOutOfRangeError,
    ResourceKindMismatchError,
    MissingRequiredReferenceError,
    SelectionReference,
    apply_filter_transition,
    classify_filter_action,
)
from backend.services.conversation_dispatch import (
    ConversationState,
    ConversationStore,
    ConversationDispatcher,
    ResultSnapshot,
    IntentPlan,
    block,
)


def test_actor_session_isolation():
    """Context for Actor A cannot be validated or reused for Actor B."""
    service = ContextService()
    now = time.time()

    # Valid matching actor and session
    res = service.validate_context(
        actor_id="EMP-1042",
        session_id="sess_123",
        current_actor_id="EMP-1042",
        current_session_id="sess_123",
        last_accessed_at=now,
        now=now,
    )
    assert res.is_valid is True
    assert res.error_code is None

    # Actor mismatch
    res_mismatch = service.validate_context(
        actor_id="EMP-1042",
        session_id="sess_123",
        current_actor_id="EMP-1020",
        current_session_id="sess_123",
        last_accessed_at=now,
        now=now,
    )
    assert res_mismatch.is_valid is False
    assert res_mismatch.error_code == ContextValidationErrorType.ACTOR_MISMATCH

    # Session mismatch
    res_sess_mismatch = service.validate_context(
        actor_id="EMP-1042",
        session_id="sess_123",
        current_actor_id="EMP-1042",
        current_session_id="sess_999",
        last_accessed_at=now,
        now=now,
    )
    assert res_sess_mismatch.is_valid is False
    assert res_sess_mismatch.error_code == ContextValidationErrorType.ACTOR_MISMATCH


def test_context_expiry_and_invalidation():
    """Context older than TTL (300s) fails validation."""
    service = ContextService()
    now = 1000.0
    stale_time = 650.0  # 350s ago (> 300s TTL)

    res = service.validate_context(
        actor_id="EMP-1042",
        session_id="sess_123",
        current_actor_id="EMP-1042",
        current_session_id="sess_123",
        last_accessed_at=stale_time,
        ttl_seconds=300.0,
        now=now,
    )
    assert res.is_valid is False
    assert res.error_code == ContextValidationErrorType.SESSION_EXPIRED


def test_selected_employee_vs_ticket():
    """Selecting a ticket does not satisfy an employee request and vice versa."""
    service = ContextService()
    state = ConversationState(actor_id="EMP-1042")
    state.select_ticket("TCK-101", source_result_id="blk_1")

    # Employee resolution must not return ticket
    target = service.resolve_selection(
        selected_employee=state.selected_employee,
        selected_ticket=state.selected_ticket,
        requested_kind="employee",
    )
    assert target is None

    # Ticket resolution returns the ticket
    ticket_target = service.resolve_selection(
        selected_employee=state.selected_employee,
        selected_ticket=state.selected_ticket,
        requested_kind="ticket",
    )
    assert ticket_target == "TCK-101"

    # Now select an employee
    state.select_employee("EMP-1020", source_result_id="blk_2")
    emp_target = service.resolve_selection(
        selected_employee=state.selected_employee,
        selected_ticket=state.selected_ticket,
        requested_kind="employee",
    )
    assert emp_target == "EMP-1020"


def test_explicit_target_overrides_selection():
    """Explicit target in utterance always overrides stale selection in context."""
    service = ContextService()
    state = ConversationState(actor_id="EMP-1042")
    state.select_employee("EMP-1020", source_result_id="blk_1")

    # User explicitly mentions EMP-4002
    target = service.resolve_selection(
        explicit_target_id="EMP-4002",
        selected_employee=state.selected_employee,
        selected_ticket=state.selected_ticket,
        requested_kind="employee",
    )
    assert target == "EMP-4002"


def test_valid_ordinal_and_out_of_range():
    """1-based ordinal resolution against displayed order, with honest bounds checking."""
    service = ContextService()
    visible_ids = ["TCK-101", "TCK-102", "TCK-103"]

    assert service.resolve_ordinal(visible_ids, 1) == "TCK-101"
    assert service.resolve_ordinal(visible_ids, 2) == "TCK-102"
    assert service.resolve_ordinal(visible_ids, 3) == "TCK-103"

    # Out of range (0 is invalid for 1-based, 4 exceeds length 3)
    with pytest.raises(OrdinalOutOfRangeError) as exc_info:
        service.resolve_ordinal(visible_ids, 0)
    assert "out of range" in str(exc_info.value)

    with pytest.raises(OrdinalOutOfRangeError) as exc_info2:
        service.resolve_ordinal(visible_ids, 5)
    assert exc_info2.value.ordinal == 5
    assert exc_info2.value.total_visible == 3


def test_resource_kind_mismatch_ordinal():
    """Requesting 'second person' on a ticket list raises ResourceKindMismatchError."""
    service = ContextService()
    visible_ids = ["TCK-101", "TCK-102"]

    with pytest.raises(ResourceKindMismatchError) as exc:
        service.resolve_ordinal(
            visible_ids,
            ordinal=1,
            resource_kind="employee",
            active_resource_kind="tickets",
        )
    assert "Cannot resolve employee from active tickets" in str(exc.value)


def test_missing_pronoun_reference_never_falls_back_to_self():
    """Unresolved pronoun raises MissingRequiredReferenceError, never defaults to actor self."""
    service = ContextService()

    with pytest.raises(MissingRequiredReferenceError) as exc:
        service.resolve_selection(
            explicit_target_id=None,
            selected_employee=None,
            selected_ticket=None,
            requested_kind="employee",
            pronoun="their profile",
        )
    assert "No active employee selected" in str(exc.value)

    with pytest.raises(MissingRequiredReferenceError) as exc_tck:
        service.resolve_selection(
            explicit_target_id=None,
            selected_employee=None,
            selected_ticket=None,
            requested_kind="ticket",
            pronoun="this ticket",
        )
    assert "No active ticket selected" in str(exc_tck.value)


def test_empty_base_vs_missing_base():
    """Empty base_rows ([]) is recognized as EMPTY_AUTHORIZED, distinct from None."""
    b = block("TICKET_LIST", "Empty tickets", {"tickets": []})

    # Empty base rows captured
    snap_empty = ResultSnapshot(
        block=b,
        operation="ticket_list",
        visible_ids=[],
        source_rows=[],
        base_rows=[],
    )
    assert snap_empty.dataset_status == DatasetStatus.EMPTY_AUTHORIZED

    # Populated base rows
    snap_pop = ResultSnapshot(
        block=b,
        operation="ticket_list",
        visible_ids=["TCK-1"],
        source_rows=[{"ticket_id": "TCK-1"}],
        base_rows=[{"ticket_id": "TCK-1"}],
    )
    assert snap_pop.dataset_status == DatasetStatus.POPULATED


def test_filter_replacement_high_to_low():
    """Replacing priority from High to Low preserves unrelated filters like status and department."""
    current = {
        "priority": "High",
        "status": "Open",
        "department": "Engineering",
        "from_date": "2026-01-01",
    }
    updated = apply_filter_transition(
        current_filters=current,
        transition_type="replace",
        filter_updates={"priority": "Low"},
    )
    assert updated["priority"] == "Low"
    assert updated["status"] == "Open"
    assert updated["department"] == "Engineering"
    assert updated["from_date"] == "2026-01-01"


def test_clear_priority_preserves_other_filters():
    """Clearing priority only drops priority, keeping department and status intact."""
    current = {
        "priority": "High",
        "status": "Open",
        "department": "Engineering",
    }
    cleared = apply_filter_transition(
        current_filters=current,
        transition_type="clear",
        keys_to_clear=["priority"],
    )
    assert "priority" not in cleared
    assert cleared["status"] == "Open"
    assert cleared["department"] == "Engineering"


def test_refine_status_preserves_person():
    """Refining status adds or narrows status without dropping person or department."""
    current = {
        "person_filter": "EMP-1042",
        "department": "Engineering",
    }
    refined = apply_filter_transition(
        current_filters=current,
        transition_type="refine",
        filter_updates={"status": "Open"},
    )
    assert refined["person_filter"] == "EMP-1042"
    assert refined["department"] == "Engineering"
    assert refined["status"] == "Open"


def test_presentation_only_vs_new_disclosure_classification():
    """Distinguishes harmless presentation reformatting from new data disclosure."""
    delivered_filters = {"priority": "High", "status": "Open"}

    # 1. Pure view reformatting (TABLE -> BAR) on same dataset
    clf_view = classify_filter_action(
        current_filters=delivered_filters,
        requested_filters=delivered_filters,
        delivered_row_count=5,
        is_view_change_only=True,
    )
    assert clf_view.action_type == "presentation_only"
    assert clf_view.is_new_disclosure is False

    # 2. Priority change (High -> Low): Discloses records not delivered earlier
    clf_priority = classify_filter_action(
        current_filters=delivered_filters,
        requested_filters={"priority": "Low", "status": "Open"},
        delivered_row_count=5,
    )
    assert clf_priority.action_type == "new_disclosure_retrieval"
    assert clf_priority.is_new_disclosure is True
    assert clf_priority.dimension_changed == "priority"

    # 3. Clearing a filter (e.g. showing all priorities): Reveals new records
    clf_clear = classify_filter_action(
        current_filters=delivered_filters,
        requested_filters={"status": "Open"},  # priority cleared
        delivered_row_count=5,
    )
    assert clf_clear.action_type == "new_disclosure_retrieval"
    assert clf_clear.is_new_disclosure is True

    # 4. Scope expansion (team -> company)
    clf_scope = classify_filter_action(
        current_filters=delivered_filters,
        requested_filters=delivered_filters,
        delivered_row_count=5,
        scope_widened=True,
    )
    assert clf_scope.action_type == "broader_scope"
    assert clf_scope.is_new_disclosure is True


def test_back_through_bounded_history():
    """Navigation stack supports traversing multiple previous results in sequence."""
    state = ConversationState(actor_id="EMP-1042")

    b1 = block("EMPLOYEE_PROFILE", "Charlie Profile", {"name": "Charlie"})
    b2 = block("TICKET_LIST", "Charlie Tickets", {"total": 3})
    b3 = block("TEAM_METRIC_CHART", "Team SLA", {"metric": "compliance"})

    snap1 = ResultSnapshot(block=b1, operation="profile")
    snap2 = ResultSnapshot(block=b2, operation="ticket_list")
    snap3 = ResultSnapshot(block=b3, operation="ticket_chart")

    state.remember(snap1)
    state.remember(snap2)
    state.remember(snap3)

    assert state.active_id == b3.id

    # First back -> goes to snap2
    prev1 = state.navigate_back()
    assert prev1 is not None
    assert prev1.block.id == b2.id

    # Second back -> goes to snap1
    prev2 = state.navigate_back()
    assert prev2 is not None
    assert prev2.block.id == b1.id

    # Third back -> stack empty, returns None
    prev3 = state.navigate_back()
    assert prev3 is None


def test_context_version_tracking_concurrent_turns():
    """context_version increments on every state transition to detect stale turns."""
    state = ConversationState(actor_id="EMP-1042")
    v0 = state.context_version

    b1 = block("EMPLOYEE_PROFILE", "Profile", {})
    snap1 = ResultSnapshot(block=b1, operation="profile")
    state.remember(snap1)
    assert state.context_version == v0 + 1

    state.select_ticket("TCK-999", source_result_id=b1.id)
    assert state.context_version == v0 + 2

    state.select_employee("EMP-1020", source_result_id=b1.id)
    assert state.context_version == v0 + 3


def test_failed_request_not_becoming_active():
    """Denied/failed operations do not corrupt or overwrite active conversation snapshot."""
    dispatcher = ConversationDispatcher()
    # Attempting to access an unauthorized person (EMP-9999 does not exist/unauthorized)
    res = dispatcher.dispatch("EMP-1042", "sess_test", IntentPlan(operation="profile", entity="Nonexistent Ghost"))
    assert res.is_authorized is False

    # Check store
    from backend.services.conversation_dispatch import conversation_store
    state = conversation_store.get("sess_test", "EMP-1042")
    # Active snapshot must not be set to a failure block
    assert state.active_id is None
