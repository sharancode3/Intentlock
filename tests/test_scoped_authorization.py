"""
Unit tests for ScopedAuthorizationService in IntentLock Stage 2.
Verifies self-scope sanitization, manager-scope direct report access,
and strict denial for unauthorized colleague access.
"""

import pytest
from backend.core.scoped_authorization import ScopedAuthorizationService


@pytest.fixture
def auth_service():
    return ScopedAuthorizationService.get_instance()


def test_self_scope_profile_access(auth_service):
    """An employee viewing their own profile gets sanitized, non-leaking data."""
    actor_id = "EMP-1001"  # Aarav Mehta
    result = auth_service.evaluate_and_get_profile(actor_id=actor_id, target_id=None)

    assert result.is_authorized is True
    assert result.status_code == 200
    assert result.result_block is not None
    assert result.result_block.type == "EMPLOYEE_PROFILE"
    assert "Aarav Mehta" in result.spoken_summary

    payload = result.result_block.payload.get("employee", {})
    assert payload["id"] == "EMP-1001"
    assert payload["name"] == "Aarav Mehta"
    assert payload["role"] == "Software Engineer"
    assert payload["department"] == "Engineering"
    assert "Python" in payload["skills"]
    assert "Customer Support Portal" in payload["active_projects"]

    # Verify sensitive internal fields are absent
    assert "security_scope" not in payload
    assert "salary" not in payload
    assert "compensation" not in payload
    assert "performance_rating" not in payload
    assert "system_role" not in payload


def test_self_scope_explicit_target_id(auth_service):
    """An employee explicitly passing their own employee ID gets self-scope profile."""
    actor_id = "EMP-1001"
    result = auth_service.evaluate_and_get_profile(actor_id=actor_id, target_id="EMP-1001")

    assert result.is_authorized is True
    assert result.status_code == 200
    assert result.result_block.payload["employee"]["id"] == "EMP-1001"


def test_manager_scope_direct_report_access(auth_service):
    """A direct reporting manager can view their direct report's profile."""
    manager_id = "EMP-2001"  # Priya Sharma (Manager of Aarav Mehta EMP-1001)
    target_id = "EMP-1001"

    result = auth_service.evaluate_and_get_profile(actor_id=manager_id, target_id=target_id)

    assert result.is_authorized is True
    assert result.status_code == 200
    assert result.result_block is not None
    assert result.result_block.type == "EMPLOYEE_PROFILE"
    assert "Authorized manager view" in result.spoken_summary

    payload = result.result_block.payload.get("employee", {})
    assert payload["id"] == "EMP-1001"
    assert payload["name"] == "Aarav Mehta"
    assert "Customer Support Portal" in payload["active_projects"]


def test_unauthorized_colleague_access_denied(auth_service):
    """An employee cannot inspect a peer/colleague's private record."""
    actor_id = "EMP-1001"   # Aarav Mehta (L1)
    target_id = "EMP-1002"  # Sneha Rao (Peer L1)

    result = auth_service.evaluate_and_get_profile(actor_id=actor_id, target_id=target_id)

    assert result.is_authorized is False
    assert result.status_code == 403
    assert result.result_block is not None
    assert result.result_block.type == "DENIAL_BANNER"
    assert "Access denied" in result.spoken_summary
    assert "UNAUTHORIZED_TARGET" in result.denial_reason

    # Verify no private employee record data leaked in denial payload
    payload = result.result_block.payload
    assert "employee" not in payload
    assert payload["target_requested"] == "EMP-1002"
    assert "Requires verified identity" in payload["policy"]


def test_nonexistent_employee_target(auth_service):
    """Querying a non-existent employee ID returns 404 denial."""
    actor_id = "EMP-1001"
    target_id = "EMP-9999"

    result = auth_service.evaluate_and_get_profile(actor_id=actor_id, target_id=target_id)

    assert result.is_authorized is False
    assert result.status_code == 404
    assert result.denial_reason == "RECORD_NOT_FOUND"
    assert result.result_block.type == "DENIAL_BANNER"
