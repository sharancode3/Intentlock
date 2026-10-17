"""IntentLock — Person 2 Stage 3 Test Suite: Structured Semantic Planning.

Tests operation registry parity, context allowlisting, deterministic exact commands,
negation protection, quoted keyword protection, model planning pipeline, refusal handling,
and compound request bounds under strictly offline conditions.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from backend.adapters.openai_answer_adapter import OpenAIAnswerAdapter
from backend.services.conversation_dispatch import IntentPlan, PlannerContext, Operation
from backend.services.operation_registry import OperationRegistry, OperationMetadata
from backend.services.semantic_orchestrator import (
    interpret_request,
    is_exact_public_help,
    is_exact_confirmation,
    is_exact_cancellation,
    is_exact_back,
)


def test_operation_registry_schema_parity():
    """Verify that all 18 supported operations exist in OperationRegistry, IntentPlan, and Dispatcher."""
    all_ops = OperationRegistry.all_operations()
    assert len(all_ops) == 18

    # Check key expected operations
    expected = [
        "help", "profile", "team_table", "team_count", "org_tree",
        "ticket_list", "ticket_chart", "rechart", "back", "clarify",
        "create_ticket", "update_ticket", "comment_ticket", "confirm", "cancel",
        "compound", "headcount", "update_contact",
    ]
    for op in expected:
        assert OperationRegistry.is_supported(op), f"Missing {op} in registry"
        # Verify valid in IntentPlan
        plan = IntentPlan(operation=op)
        assert plan.operation == op


def test_exact_public_help_versus_private_query():
    """'help' is public help, but 'Help me with my private record' is NOT public help."""
    assert is_exact_public_help("help") is True
    assert is_exact_public_help("what can I ask?") is True
    assert is_exact_public_help("Helpdesk options") is True

    # Private queries containing 'help' must NOT be classified as public help
    assert is_exact_public_help("Help me with my private record") is False
    assert is_exact_public_help("Help me view EMP-1001's profile") is False
    assert is_exact_public_help("Help me update my phone") is False
    assert is_exact_public_help("Help with ticket #123") is False


def test_negated_confirmation_and_cancellation():
    """'do not confirm' is NOT confirm; 'don't cancel' is NOT cancel."""
    assert is_exact_confirmation("confirm") is True
    assert is_exact_confirmation("I confirm") is True
    assert is_exact_confirmation("yes, confirm") is True
    assert is_exact_confirmation("do not confirm") is False
    assert is_exact_confirmation("I don't confirm this") is False

    assert is_exact_cancellation("cancel") is True
    assert is_exact_cancellation("abort") is True
    assert is_exact_cancellation("do not cancel") is False
    assert is_exact_cancellation("don't cancel") is False


def test_quoted_content_keyword_protection():
    """'Create a ticket titled \"cancel account error\"' must not become operation='cancel'."""
    utterance = 'Create a ticket titled "cancel account error"'
    assert is_exact_cancellation(utterance) is False


def test_context_allowlisting_and_nested_secret_rejection():
    """Ensure context projection allowlists recognized keys and strips credentials/tokens."""
    adapter = OpenAIAnswerAdapter(api_key="test-key")

    dirty_context = PlannerContext(
        has_active_result=True,
        source_kind="tickets",
        selected_ticket_id="TKT-101",
        active_filters={
            "priority": "urgent",
            "api_key": "sk-1234567890",
            "db_password": "supersecretpassword",
            "token": "eyJhbGciOi...",
            "status": "open",
        },
    )

    with patch.object(adapter, "_get_client") as mock_client:
        mock_parse = AsyncMock()
        mock_parse.output_parsed = IntentPlan(operation="ticket_list", priority_filter="Critical")
        mock_client.return_value.responses.parse = mock_parse

        # Run planning
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(adapter.plan_request("filter to urgent", context=dirty_context))
        finally:
            loop.close()

        call_args = mock_parse.call_args[1]
        input_str = call_args["input"]

        # Legitimate keys present
        assert "priority=urgent" in input_str
        assert "status=open" in input_str
        assert "source_kind=tickets" in input_str

        # Sensitive keys stripped!
        assert "api_key" not in input_str
        assert "supersecretpassword" not in input_str
        assert "eyJhbGci" not in input_str


@pytest.mark.asyncio
async def test_no_extra_model_request_for_exact_local_commands():
    """High-certainty deterministic commands (help, confirm, cancel, back) bypass model calls."""
    mock_adapter = MagicMock()
    mock_adapter.plan_request = AsyncMock()

    # Exact Help
    plan_help = await interpret_request("help", planner_adapter=mock_adapter)
    assert plan_help.operation == "help"
    mock_adapter.plan_request.assert_not_called()

    # Exact Confirm
    plan_confirm = await interpret_request("confirm", planner_adapter=mock_adapter)
    assert plan_confirm.operation == "confirm"
    mock_adapter.plan_request.assert_not_called()

    # Exact Cancel
    plan_cancel = await interpret_request("cancel", planner_adapter=mock_adapter)
    assert plan_cancel.operation == "cancel"
    mock_adapter.plan_request.assert_not_called()

    # Exact Back
    plan_back = await interpret_request("go back", planner_adapter=mock_adapter)
    assert plan_back.operation == "back"
    mock_adapter.plan_request.assert_not_called()


@pytest.mark.asyncio
async def test_flexible_request_routes_to_planner():
    """Flexible queries route to the structured model planner."""
    mock_adapter = MagicMock()
    mock_adapter.plan_request = AsyncMock(return_value=IntentPlan(operation="ticket_chart", view="PIE"))

    plan = await interpret_request("Show my team tickets as a pie chart", planner_adapter=mock_adapter)
    assert plan.operation == "ticket_chart"
    assert plan.view == "PIE"
    mock_adapter.plan_request.assert_called_once()


@pytest.mark.asyncio
async def test_model_refusal_or_provider_failure_returns_clarify():
    """Provider failure or refusal safely falls back without crashing or faking success."""
    mock_adapter = MagicMock()
    mock_adapter.plan_request = AsyncMock(side_effect=RuntimeError("OpenAI API rate limit"))

    plan = await interpret_request("Arbitrary complex request", planner_adapter=mock_adapter)
    assert plan.operation in ("clarify", "help")


@pytest.mark.asyncio
async def test_compound_read_versus_disallowed_mutation():
    """Compound reads are allowed; compound mutations are rejected."""
    mock_adapter = MagicMock()
    # Legitimate compound read
    mock_adapter.plan_request = AsyncMock(return_value=IntentPlan(operation="compound", entity="EMP-1001"))
    read_plan = await interpret_request("Show profile and tickets", planner_adapter=mock_adapter)
    assert read_plan.operation == "compound"

    # Compound containing mutation fields is rejected
    mock_adapter.plan_request = AsyncMock(return_value=IntentPlan(
        operation="compound",
        field="phone",
        value="+1234567890",
    ))
    mutation_plan = await interpret_request("Show profile and update phone", planner_adapter=mock_adapter)
    assert mutation_plan.operation == "clarify"


@pytest.mark.asyncio
async def test_claim_grounding_integration_in_orchestrator():
    """Model-invented claims without spoken grounding are stripped by orchestrator."""
    mock_adapter = MagicMock()
    # Model hallucinated actor_claim="EMP-4002"
    mock_adapter.plan_request = AsyncMock(return_value=IntentPlan(
        operation="profile",
        actor_claim="EMP-4002",
        entity="EMP-1001",
    ))

    # Utterance does NOT contain an explicit claim to be EMP-4002
    plan = await interpret_request("Show EMP-1001's profile", planner_adapter=mock_adapter)
    assert plan.operation == "profile"
    assert plan.actor_claim is None  # Stripped!
