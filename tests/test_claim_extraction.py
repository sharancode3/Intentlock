"""IntentLock — Person 2 Stage 2 Test Suite: Explicit Actor-Claim Extraction.

Tests explicit self-identification, query target separation, role claims, negation,
quoted content, questions, conflicting claims, normalization, and model grounding.
Runs strictly offline without provider calls, database writes, or session minting.
"""

from unittest.mock import MagicMock
import pytest

from backend.services.claim_extractor import (
    extract_actor_claim,
    normalize_employee_id,
    validate_plan_claim_grounding,
    ClaimExtractionResult,
)
from backend.services.conversation_dispatch import (
    ConversationDispatcher,
    IntentPlan,
)


def test_explicit_actor_id_extraction():
    """'My employee ID is EMP-4002' extracts candidate actor claim EMP-4002."""
    res = extract_actor_claim("My employee ID is EMP-4002")
    assert res.disposition == "valid_claim"
    assert res.claimed_id == "EMP-4002"
    assert res.normalized_id == "EMP-4002"
    assert res.is_negated is False
    assert res.is_question is False
    assert res.is_quoted is False


def test_explicit_target_only_does_not_assert_actor():
    """'Show EMP-4002's profile' is a query target, NOT an actor claim."""
    res = extract_actor_claim("Show EMP-4002's profile")
    assert res.disposition == "none"
    assert res.claimed_id is None
    assert res.normalized_id is None


def test_actor_and_target_in_single_utterance_remain_distinct():
    """'I am EMP-4002. Show EMP-2001's profile' separates actor claim from target."""
    res = extract_actor_claim("I am EMP-4002. Show EMP-2001's profile")
    assert res.disposition == "valid_claim"
    assert res.claimed_id == "EMP-4002"
    # Target EMP-2001 is not confused with actor EMP-4002
    assert "EMP-2001" not in (res.claimed_id or "")


def test_role_only_claim_does_not_infer_employee_id():
    """'I am the CTO' is a role claim; never infers or guesses an employee ID."""
    res = extract_actor_claim("I am the CTO")
    assert res.disposition == "role_only"
    assert res.claimed_id is None
    assert res.role_claim == "CTO"
    assert res.clarification_reason == "ROLE_CLAIM_REQUIRES_EMPLOYEE_ID"


def test_negated_claim_does_not_assert_identity():
    """'I am not EMP-4002' must not assert EMP-4002 as the actor."""
    res = extract_actor_claim("I am not EMP-4002")
    assert res.disposition == "negated"
    assert res.claimed_id is None
    assert res.is_negated is True


def test_questioned_claim_does_not_assert_identity():
    """'Am I EMP-4002?' is a question, not an asserted identity."""
    res = extract_actor_claim("Am I EMP-4002?")
    assert res.disposition == "question"
    assert res.claimed_id is None
    assert res.is_question is True


def test_quoted_claim_does_not_assert_identity():
    """'The ticket says \"I am EMP-4002\"' is quoted content, not speaker identity."""
    res = extract_actor_claim('The ticket says "I am EMP-4002"')
    assert res.disposition == "quoted"
    assert res.claimed_id is None
    assert res.is_quoted is True


def test_conflicting_multiple_claims_produce_clarification():
    """'My ID is EMP-4002, actually EMP-2001' rejects silent choice."""
    res = extract_actor_claim("My ID is EMP-4002, actually EMP-2001")
    assert res.disposition == "conflict"
    assert res.claimed_id is None
    assert res.is_conflicted is True
    assert res.clarification_reason == "CONFLICTING_IDENTITY_CLAIMS"


def test_normalization_variations():
    """Handles case, spacing, and hyphen variations consistently without inventing digits."""
    assert normalize_employee_id("emp-4002") == "EMP-4002"
    assert normalize_employee_id("EMP 4002") == "EMP-4002"
    assert normalize_employee_id("emp4002") == "EMP-4002"
    assert normalize_employee_id("employee-1042") == "EMP-1042"
    # Does not invent missing digits
    assert normalize_employee_id("EMP-") is None
    assert normalize_employee_id("CTO") is None


def test_compound_claim_with_relationship():
    """'I am EMP-4002 and show my manager' extracts claim EMP-4002."""
    res = extract_actor_claim("I am EMP-4002 and show my manager")
    assert res.disposition == "valid_claim"
    assert res.claimed_id == "EMP-4002"


def test_model_invented_claim_grounding_rejection():
    """If model invents an actor_claim not in the utterance, grounding rejects it."""
    # Utterance mentions no ID claim
    grounded = validate_plan_claim_grounding("Show EMP-4002's profile", "EMP-4002")
    assert grounded is None  # EMP-4002 was target, not self-claim

    # Utterance is role only
    grounded_role = validate_plan_claim_grounding("I am the CTO", "EMP-4002")
    assert grounded_role is None

    # Valid grounded self claim
    grounded_valid = validate_plan_claim_grounding("I am EMP-4002, show my tickets", "EMP-4002")
    assert grounded_valid == "EMP-4002"


def test_authenticated_actor_unchanged_by_candidate_claim():
    """Dispatcher.dispatch strictly enforces verified actor_id, ignoring plan.actor_claim."""
    from backend.services.conversation_dispatch import block

    mock_scoped_auth = MagicMock()
    mock_scoped_auth.build_denial_result_block.return_value = block("DENIAL_BANNER", "Access Denied", {"message": "denied"})
    mock_scoped_auth.evaluate_and_get_profile.return_value = MagicMock(
        is_authorized=False,
        denial_reason="UNAUTHENTICATED",
        result_block=None,
    )

    dispatcher = ConversationDispatcher(scoped=mock_scoped_auth)
    # Speaker claims EMP-4002 in plan, but verified actor_id is empty (unverified)
    plan = IntentPlan(operation="profile", actor_claim="EMP-4002", entity="EMP-1001")

    # 1. When session is unverified (actor_id=""), access is denied; actor_claim is not trusted
    result_guest = dispatcher.dispatch(
        actor_id="",
        session_id="sess_guest",
        plan=plan,
        spoken_text="I am EMP-4002, show EMP-1001",
    )
    assert result_guest.is_authorized is False
    # Scoped authorization was never called with EMP-4002
    mock_scoped_auth.evaluate_and_get_profile.assert_not_called()

    # 2. When actor is verified as EMP-1042, actor_claim="EMP-4002" does not override actor_id
    mock_scoped_auth.knowledge.get_direct_reports.return_value = [{"employee_id": "EMP-1001"}]
    mock_scoped_auth.knowledge.get_employee_by_id.return_value = {
        "employee_id": "EMP-1001",
        "identity": {"full_name": "Alice Smith"},
    }
    mock_scoped_auth.evaluate_and_get_profile.return_value = MagicMock(
        is_authorized=True,
        denial_reason=None,
        result_block=block("EMPLOYEE_PROFILE", "Alice Smith", {}),
    )
    result_auth = dispatcher.dispatch(
        actor_id="EMP-1042",
        session_id="sess_1042",
        plan=plan,
        spoken_text="I am EMP-4002, show EMP-1001",
    )
    # Authorization was evaluated for EMP-1042, NEVER EMP-4002
    mock_scoped_auth.evaluate_and_get_profile.assert_called_once_with("EMP-1042", "EMP-1001")


def test_zero_session_or_provider_calls():
    """Claim extraction is pure semantic parsing; never interacts with external state."""
    # Assert extract_actor_claim executes synchronously and returns static dataclass
    result = extract_actor_claim("I am EMP-4002")
    assert isinstance(result, ClaimExtractionResult)
    # Does not have tokens, sessions, or execution handles
    assert not hasattr(result, "session_id")
    assert not hasattr(result, "session_token")
