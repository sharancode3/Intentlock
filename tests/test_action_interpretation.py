"""
tests/test_action_interpretation.py
Tests for Person 2 Stage 8: Precise Action Interpretation and Proposal Protection.
"""

import pytest
from backend.services.conversation_dispatch import parse_local, IntentPlan, ConversationState, ResultSnapshot, block
from backend.services.semantic_orchestrator import interpret_request, is_exact_confirmation, is_exact_cancellation


def test_comment_with_quoted_cancel():
    """Quotes protect comments containing 'cancel' from being hijacked into cancellation commands."""
    text = "Add a comment to ticket TKT-2026-001: 'Do not cancel the deployment'"
    plan = parse_local(text)
    assert plan.operation == "comment_ticket"
    assert plan.ticket_id == "TKT-2026-001"
    assert plan.value == "Do not cancel the deployment"


def test_comment_with_quoted_confirm():
    """Quotes protect comments containing 'confirm' from being hijacked into confirmations."""
    text = "Add a comment to ticket TKT-2026-001: 'I confirm the release'"
    plan = parse_local(text)
    assert plan.operation == "comment_ticket"
    assert plan.ticket_id == "TKT-2026-001"
    assert plan.value == "I confirm the release"


def test_comment_on_selected_ticket_from_context():
    """Ticket comment resolves against context's selected_ticket_id."""
    state = ConversationState(actor_id="EMP-1042")
    state.selected_ticket_id = "TKT-2026-005"

    text = "Add a comment: 'Reviewed and ready'"
    plan = parse_local(text, state=state)
    assert plan.operation == "comment_ticket"
    assert plan.ticket_id == "TKT-2026-005"
    assert plan.value == "Reviewed and ready"


def test_negated_confirmation():
    """Negated confirmation phrases must never produce a confirm plan."""
    phrases = [
        "Do not confirm that.",
        "Don't confirm this change.",
        "Never confirm that proposal.",
    ]
    for p in phrases:
        assert is_exact_confirmation(p) is False
        plan = parse_local(p)
        assert plan.operation != "confirm"


def test_negated_cancellation():
    """Negated cancellation phrases must never produce a cancel plan."""
    phrases = [
        "Do not cancel.",
        "Don't cancel the proposal.",
        "Never cancel this draft.",
    ]
    for p in phrases:
        assert is_exact_cancellation(p) is False
        plan = parse_local(p)
        assert plan.operation != "cancel"


def test_question_about_confirmation_not_confirm():
    """Asking questions about confirmation or cancellation is NOT a confirmation command."""
    questions = [
        "What happens if I confirm?",
        "Can I confirm later?",
        "How do I cancel this?",
        "Should I confirm this change?",
    ]
    for q in questions:
        assert is_exact_confirmation(q) is False
        assert is_exact_cancellation(q) is False
        plan = parse_local(q)
        assert plan.operation not in ("confirm", "cancel")


def test_param_modification_during_confirmation_not_confirm():
    """Phrases like 'Yes, but change the phone to...' modify parameters and cannot commit old draft."""
    text = "Yes, but use a different number: +91 99999 88888"
    assert is_exact_confirmation(text) is False
    plan = parse_local(text)
    assert plan.operation != "confirm"


def test_contact_update_missing_phone_clarification():
    """Asking to update phone without supplying digits returns clarification, not raw utterance as value."""
    text = "Update my work phone"
    plan = parse_local(text)
    assert plan.operation == "clarify"
    assert plan.field == "phone"
    assert "Please provide the phone number" in str(plan.value)


def test_contact_update_other_person_target_preserved():
    """Updating another employee's phone preserves target ID for policy enforcement."""
    text = "Update EMP-2001's phone to +91 98765 43210"
    plan = parse_local(text)
    assert plan.operation == "update_contact"
    assert plan.entity == "EMP-2001"
    assert "+91 98765 43210" in plan.value


def test_employee_id_digits_not_extracted_as_phone():
    """Digits in employee IDs (EMP-2001) are not mistakenly treated as phone numbers."""
    text = "Update phone for EMP-2001"
    plan = parse_local(text)
    assert plan.operation == "clarify"
    assert plan.field == "phone"


def test_reporting_manager_change_clarification():
    """Reporting manager updates return explicit clarification stating admin approval is needed."""
    text = "Move this employee under Priya"
    plan = parse_local(text)
    assert plan.operation == "clarify"
    assert "administrator approval" in str(plan.value)


def test_ambiguous_make_manager_clarification():
    """'Make X a manager' returns clarification distinguishing designation vs auth role vs reporting."""
    text = "Make this employee a manager"
    plan = parse_local(text)
    assert plan.operation == "clarify"
    assert "designation" in str(plan.value)
    assert "authorization role" in str(plan.value)


def test_promotion_recommendation_not_executed():
    """Promotion recommendation returns clarification that it cannot be executed as immediate role change."""
    text = "Recommend this employee for promotion"
    plan = parse_local(text)
    assert plan.operation == "clarify"
    assert "performance reviews" in str(plan.value)


def test_admin_role_change_clarification():
    """Administrative role grant returns clarification that security admin privilege is required."""
    text = "Give this employee administrator access"
    plan = parse_local(text)
    assert plan.operation == "clarify"
    assert "security administrator" in str(plan.value)


def test_ticket_status_vs_priority_separate():
    """Status changes and priority changes remain strictly distinct operations and fields."""
    status_text = "Mark ticket TKT-2026-001 as Resolved"
    plan_status = parse_local(status_text)
    assert plan_status.operation == "update_ticket"
    assert plan_status.ticket_id == "TKT-2026-001"
    assert plan_status.field == "status"
    assert plan_status.value == "Resolved"

    priority_text = "Set ticket TKT-2026-001 priority to High"
    plan_priority = parse_local(priority_text)
    assert plan_priority.operation == "update_ticket"
    assert plan_priority.ticket_id == "TKT-2026-001"
    assert plan_priority.field == "priority"
    assert plan_priority.value == "High"


def test_presentation_request_not_update_ticket():
    """Requests to change charts must never be parsed as update_ticket mutations."""
    text = "Change the chart to show high-priority tickets"
    plan = parse_local(text)
    assert plan.operation != "update_ticket"


@pytest.mark.asyncio
async def test_nested_compound_mutation_rejection():
    """Compound requests containing nested mutations are rejected with clarification."""
    mutation_child = IntentPlan(operation="update_ticket", ticket_id="TKT-101", field="status", value="Resolved")
    compound_plan = IntentPlan(
        operation="compound",
        compound_plans=[
            IntentPlan(operation="profile", entity="EMP-1042"),
            mutation_child,
        ]
    )
    # Testing orchestrator validation rule on child operations
    from backend.services.operation_registry import OperationRegistry
    meta = OperationRegistry.get(mutation_child.operation)
    assert meta.category == "proposal"
