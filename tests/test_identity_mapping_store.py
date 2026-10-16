"""
IntentLock — Identity Mapping & Session Store Tests
Tests the local SQLite persistence for speaker mappings, enrollment status,
and short-lived opaque voice sessions.
"""

import os
import tempfile
import pytest
from backend.adapters.identity_mapping_store import IdentityMappingStore


@pytest.fixture
def temp_store():
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as f:
        temp_path = f.name
    store = IdentityMappingStore(db_path=temp_path)
    yield store
    if os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except Exception:
            pass


def test_upsert_and_retrieve_speaker_mapping(temp_store):
    mapping = temp_store.upsert_mapping(
        employee_id="EMP-1001",
        provider_speaker_id="emp_1001_aarav",
        account_alias="primary_account",
        display_name="Aarav Mehta",
        enrollment_status="PENDING",
    )
    assert mapping.employee_id == "EMP-1001"
    assert mapping.provider_speaker_id == "emp_1001_aarav"
    assert mapping.enrollment_status == "PENDING"

    # Retrieve by employee ID
    by_eid = temp_store.get_mapping_by_employee_id("EMP-1001")
    assert by_eid is not None
    assert by_eid.display_name == "Aarav Mehta"

    # Retrieve by speaker ID
    by_sid = temp_store.get_mapping_by_speaker_id("emp_1001_aarav")
    assert by_sid is not None
    assert by_sid.employee_id == "EMP-1001"


def test_update_enrollment_status(temp_store):
    temp_store.upsert_mapping(
        employee_id="EMP-1001",
        provider_speaker_id="emp_1001_aarav",
        display_name="Aarav Mehta",
    )
    ok = temp_store.update_enrollment_status("EMP-1001", "ENROLLED", sample_count=2)
    assert ok is True

    updated = temp_store.get_mapping_by_employee_id("EMP-1001")
    assert updated.enrollment_status == "ENROLLED"
    assert updated.sample_count == 2


def test_voice_session_lifecycle(temp_store):
    temp_store.upsert_mapping("EMP-1001", "emp_1001_aarav")

    # Create active session with 90s TTL
    sess = temp_store.create_session(
        session_id="sess_test_123",
        employee_id="EMP-1001",
        full_name="Aarav Mehta",
        role="Software Engineer",
        department="Engineering",
        team_id="team_core",
        ttl_seconds=90,
    )

    assert sess.session_id == "sess_test_123"
    assert sess.is_valid is True
    assert sess.seconds_remaining > 0

    # Retrieve session
    retrieved = temp_store.get_session("sess_test_123")
    assert retrieved is not None
    assert retrieved.employee_id == "EMP-1001"
    assert retrieved.is_valid is True

    # Revoke session
    temp_store.revoke_session("sess_test_123")
    revoked = temp_store.get_session("sess_test_123")
    assert revoked.is_revoked is True
    assert revoked.is_valid is False


def test_expired_session_fails(temp_store):
    temp_store.upsert_mapping("EMP-1001", "emp_1001_aarav")

    # Create session with -1s TTL (already expired)
    sess = temp_store.create_session(
        session_id="sess_expired",
        employee_id="EMP-1001",
        full_name="Aarav Mehta",
        role="Software Engineer",
        department="Engineering",
        ttl_seconds=-1,
    )

    assert sess.is_expired is True
    assert sess.is_valid is False
    assert sess.seconds_remaining == 0


def test_idempotency_records(temp_store):
    res_payload = {"status": "success", "session_id": "sess_1"}
    temp_store.save_idempotency_record(
        operation_key="op_turn_99",
        audio_digest="sha256_mock_hash",
        employee_id="EMP-1001",
        response_dict=res_payload,
    )

    saved = temp_store.get_idempotency_record("op_turn_99")
    assert saved == res_payload

    missing = temp_store.get_idempotency_record("non_existent_key")
    assert missing is None
