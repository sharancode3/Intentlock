"""
IntentLock — Person 2 Stage 1 Semantic Contracts & Foundation Tests
Tests backward compatibility, contract boundaries, PlannerContext encapsulation,
fixture validation, and non-execution guarantees under isolated offline execution.
"""

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from backend.services.conversation_dispatch import (
    IntentPlan,
    PlannerContext,
    ConversationState,
    ConversationStore,
    ResultSnapshot,
    ConversationDispatcher,
    block,
)
from backend.adapters.openai_answer_adapter import OpenAIAnswerAdapter
from backend.models.turn import GenericResultBlock, VoiceTurnResponse


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "person2"


def test_intent_plan_backward_compatibility():
    """Verify that existing legacy IntentPlan instantiations remain 100% valid."""
    legacy_plan = IntentPlan(operation="profile", entity="EMP-1001")
    assert legacy_plan.operation == "profile"
    assert legacy_plan.entity == "EMP-1001"
    assert legacy_plan.actor_claim is None
    assert legacy_plan.selected_id is None
    assert legacy_plan.filter_action is None

    # Verify agreed extensions are optional and typed
    extended_plan = IntentPlan(
        operation="profile",
        actor_claim="EMP-4002",
        entity="EMP-2001",
        selected_id="EMP-1001",
        filter_action="replace",
    )
    assert extended_plan.actor_claim == "EMP-4002"
    assert extended_plan.entity == "EMP-2001"
    assert extended_plan.selected_id == "EMP-1001"
    assert extended_plan.filter_action == "replace"


def test_planner_context_encapsulation():
    """Verify PlannerContext holds only bounded, non-sensitive context hints."""
    ctx = PlannerContext(
        has_active_result=True,
        source_kind="tickets",
        selected_ticket_id="TKT-2026-001",
        selected_employee_id="EMP-1001",
        active_filters={"priority": "High"},
    )
    assert ctx.has_active_result is True
    assert ctx.source_kind == "tickets"
    assert ctx.selected_ticket_id == "TKT-2026-001"
    assert ctx.selected_employee_id == "EMP-1001"

    # Context must NOT accept arbitrary credential or auth override fields
    data = ctx.model_dump()
    assert "auth_token" not in data
    assert "password" not in data
    assert "database_url" not in data


@pytest.mark.asyncio
async def test_openai_plan_request_backward_compatible_signatures():
    """Verify plan_request works with legacy boolean AND new PlannerContext."""
    adapter = OpenAIAnswerAdapter(api_key="test-key", model="gpt-5.4-mini")

    mock_client = MagicMock()
    mock_responses = MagicMock()
    mock_parsed_result = MagicMock()
    mock_parsed_result.output_parsed = IntentPlan(operation="help")
    mock_responses.parse = AsyncMock(return_value=mock_parsed_result)
    mock_client.responses = mock_responses

    with patch.object(adapter, "_get_client", return_value=mock_client):
        # 1. Legacy call: boolean has_current_result
        res1 = await adapter.plan_request("help", has_current_result=True)
        assert res1.operation == "help"
        call_args_1 = mock_responses.parse.call_args[1]
        assert "active_result=true" in call_args_1["input"]

        # 2. Legacy call: boolean False
        res2 = await adapter.plan_request("help", has_current_result=False)
        assert res2.operation == "help"
        call_args_2 = mock_responses.parse.call_args[1]
        assert "none" in call_args_2["input"]

        # 3. New call: PlannerContext passed as context kwarg
        ctx = PlannerContext(
            has_active_result=True,
            source_kind="tree",
            selected_employee_id="EMP-2001",
        )
        res3 = await adapter.plan_request("show their tickets", context=ctx)
        assert res3.operation == "help"
        call_args_3 = mock_responses.parse.call_args[1]
        assert "source_kind=tree" in call_args_3["input"]
        assert "selected_employee=EMP-2001" in call_args_3["input"]


def test_actor_claim_does_not_override_identity():
    """Semantic plan's actor_claim is a candidate claim, NOT a verified identity."""
    plan = IntentPlan(operation="profile", actor_claim="EMP-4002", entity="EMP-1001")
    # Entity represents query target; actor_claim represents spoken claim
    assert plan.actor_claim == "EMP-4002"
    assert plan.entity == "EMP-1001"

    # Runtime verification: Dispatching with empty actor_id denies access regardless of actor_claim
    mock_scoped = MagicMock()
    mock_scoped.build_denial_result_block.return_value = block("DENIAL_BANNER", "Denied", {"message": "unauth"})
    dispatcher = ConversationDispatcher(scoped=mock_scoped)
    result = dispatcher.dispatch(actor_id="", session_id="sess_guest", plan=plan)
    assert result.is_authorized is False
    mock_scoped.evaluate_and_get_profile.assert_not_called()


def test_conversation_state_selection_separation():
    """Verify ConversationState separates selected_ticket_id and selected_employee_id."""
    state = ConversationState(actor_id="EMP-1001")
    assert state.selected_ticket_id is None
    assert state.selected_employee_id is None

    state.selected_ticket_id = "TKT-2026-005"
    state.selected_employee_id = "EMP-2001"

    assert state.selected_ticket_id == "TKT-2026-005"
    assert state.selected_employee_id == "EMP-2001"
    assert state.actor_id == "EMP-1001"


def test_all_17_fixtures_are_valid_and_schema_compliant():
    """Validate all 17 JSON fixtures in tests/fixtures/person2/ against current schemas."""
    fixture_files = list(FIXTURES_DIR.glob("*.json"))
    assert len(fixture_files) == 17, f"Expected 17 fixtures, found {len(fixture_files)}"

    for fpath in fixture_files:
        with open(fpath, "r", encoding="utf-8") as fp:
            data = json.load(fp)

        # Invariant checks across all fixtures
        assert "contract_status" in data, f"{fpath.name} missing contract_status"
        assert data["contract_status"] in ("Existing contract", "Agreed extension", "Proposed only")
        assert "category" in data, f"{fpath.name} missing category"
        assert "input" in data, f"{fpath.name} missing input"
        assert "plan" in data, f"{fpath.name} missing plan"
        assert "expected_output" in data, f"{fpath.name} missing expected_output"

        # Validate that the fixture plan deserializes cleanly into IntentPlan
        plan_dict = data["plan"]
        plan_obj = IntentPlan(**plan_dict)
        assert plan_obj.operation == plan_dict["operation"]


def test_mutation_plan_does_not_execute_write():
    """Interpreting a mutation request must never execute a database write."""
    # Person 2 dispatcher only constructs proposals or delegates to action_store
    mock_action_store = MagicMock()
    mock_action_store.propose.return_value = {
        "draft_id": "draft_test_123",
        "ticket_id": "EMP-1001",
        "readback": "I confirm update contact for EMP-1001: phone to +91 98765 43210",
        "expires_at": "2026-10-17T12:00:00Z",
    }
    mock_action_store.build_typed_proposal.return_value = {"field": "phone", "value": "+91 98765 43210"}

    mock_scoped_auth = MagicMock()
    mock_scoped_auth.ticket_service.store = mock_action_store
    mock_scoped_auth.knowledge.get_employee_by_id.return_value = {
        "employee_id": "EMP-1001",
        "permissions": {"profile_modification": {"effect": "ALLOW"}},
        "reporting": {"direct_report_ids": []},
    }

    dispatcher = ConversationDispatcher(scoped=mock_scoped_auth)
    plan = IntentPlan(operation="update_contact", entity=None, field="phone", value="+91 98765 43210")

    result = dispatcher.dispatch(
        actor_id="EMP-1001",
        session_id="sess_test",
        plan=plan,
        spoken_text="Update my phone to +91 98765 43210",
    )

    # Dispatched proposal must NOT call confirm() or execute a mutation
    mock_action_store.confirm.assert_not_called()
    assert result.is_authorized is True
    assert result.result_block is not None
    assert result.result_block.type == "READBACK_CONFIRMATION"
    assert "draft" in result.result_block.payload
