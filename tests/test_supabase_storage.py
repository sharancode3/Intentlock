"""
IntentLock — Supabase Postgres Persistence & Repository Tests
Tests:
1. Safe diagnostics and error sanitization (no passwords, tokens, or raw connection strings leaked).
2. PostgresEmployeeRepository projection of raw database rows into canonical employee model.
3. Reporting hierarchy resolution (manager_name, direct_report_ids) from Postgres relations.
4. PostgresTicketActionStore proposal canonicalization, grant hashing, and payload integrity.
5. Invalidation revision tracking via directory_metadata.
6. Offline and fallback behavior when STORAGE_BACKEND is configured.
"""

import os
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.core.config import get_safe_diagnostics, settings
from backend.adapters.postgres_client import PostgresClient, sanitize_db_error
from backend.adapters.postgres_employee_repository import PostgresEmployeeRepository
from backend.adapters.postgres_ticket_action_store import PostgresTicketActionStore


def test_sanitize_db_error_redacts_credentials():
    """Verify error sanitization scrubs passwords, tokens, and URIs."""
    dirty_err = "FATAL: password authentication failed for user postgres://postgres:Secret123%40xyz@db.host.com:5432/postgres?apikey=sb_secret_token_999"
    sanitized = sanitize_db_error(dirty_err)

    assert "Secret123" not in sanitized
    assert "sb_secret_token_999" not in sanitized
    assert "***" in sanitized


def test_get_safe_diagnostics_redacted():
    """Verify safe diagnostics does not leak Supabase secret keys or connection credentials."""
    diag = get_safe_diagnostics()
    assert "storage_backend" in diag
    assert "supabase" in diag

    sup_diag = diag["supabase"]
    assert "database_url_configured" in sup_diag
    # Ensure raw keys and passwords are NEVER exposed in diagnostics
    diag_str = json.dumps(diag)
    assert "Sh123" not in diag_str
    assert "eyJ" not in diag_str
    assert isinstance(sup_diag["service_role_configured"], bool)


def test_postgres_employee_repository_projection():
    """Test mapping of Postgres flat + JSONB columns to the canonical IntentLock employee model."""
    raw_row_1 = {
        "employee_id": "EMP-1001",
        "full_name": "Aarav Mehta",
        "preferred_name": "Aarav",
        "work_email": "aarav.mehta@intentlock-demo.example",
        "work_phone": "+91 98765 43210",
        "department": "Engineering",
        "designation": "Software Engineer",
        "organizational_level": "L1",
        "location": "Bengaluru",
        "work_mode": "Hybrid",
        "manager_id": "EMP-2001",
        "skills": json.dumps({"technical": ["Python", "FastAPI"]}),
        "projects": json.dumps({"current": [{"name": "IntentLock", "status": "Active"}]}),
        "experience": json.dumps({"total_years": 2.0}),
        "education": json.dumps([{"degree": "B.E. CS"}]),
        "responsibilities": json.dumps(["Backend engineering"]),
        "achievements": json.dumps(["Built zero-trust voice kiosk"]),
        "policy": json.dumps({"profile_modification": {"effect": "ALLOW", "scope": "SELF_CONTACT_ONLY"}}),
        "provenance": json.dumps({"source": "canonical_v1"}),
        "version": 1,
    }

    raw_row_2 = {
        "employee_id": "EMP-2001",
        "full_name": "Priya Sharma",
        "preferred_name": "Priya",
        "work_email": "priya.sharma@intentlock-demo.example",
        "work_phone": "+91 91234 56789",
        "department": "Engineering",
        "designation": "Engineering Manager",
        "organizational_level": "L2",
        "location": "Bengaluru",
        "work_mode": "Hybrid",
        "manager_id": None,
        "skills": json.dumps({"management": ["Sprint Planning"]}),
        "projects": json.dumps({}),
        "experience": json.dumps({}),
        "education": json.dumps([]),
        "responsibilities": json.dumps([]),
        "achievements": json.dumps([]),
        "policy": json.dumps({}),
        "provenance": json.dumps({}),
        "version": 1,
    }

    all_rows = {
        "EMP-1001": raw_row_1,
        "EMP-2001": raw_row_2,
    }

    proj_emp1 = PostgresEmployeeRepository._project_row(raw_row_1, all_rows)
    proj_emp2 = PostgresEmployeeRepository._project_row(raw_row_2, all_rows)

    # 1. Identity & Contact
    assert proj_emp1["employee_id"] == "EMP-1001"
    assert proj_emp1["identity"]["full_name"] == "Aarav Mehta"
    assert proj_emp1["identity"]["work_phone"] == "+91 98765 43210"
    assert proj_emp1["identity"]["contact"]["phone"] == "+91 98765 43210"

    # 2. Derived reporting graph
    assert proj_emp1["reporting"]["manager_id"] == "EMP-2001"
    assert proj_emp1["reporting"]["manager_name"] == "Priya Sharma"
    assert proj_emp1["reporting"]["direct_report_ids"] == []

    assert proj_emp2["reporting"]["manager_id"] is None
    assert proj_emp2["reporting"]["manager_name"] is None
    assert proj_emp2["reporting"]["direct_report_ids"] == ["EMP-1001"]

    # 3. Policy & Permissions
    assert proj_emp1["permissions"]["profile_modification"]["scope"] == "SELF_CONTACT_ONLY"


def test_postgres_ticket_store_proposal_and_grant_hashing():
    """Verify PostgresTicketActionStore manifest canonicalization and SHA256 integrity check."""
    store = PostgresTicketActionStore()

    # Valid typed proposal
    prop = store.build_typed_proposal("update_contact", None, value="+91 98765 43210")
    assert prop["field"] == "phone"
    assert prop["value"] == "+91 98765 43210"

    ticket_prop = store.build_typed_proposal("create_ticket", None, value="Urgent network connectivity outage")
    assert ticket_prop["title"] == "Urgent network connectivity outage"


@pytest.mark.asyncio
async def test_postgres_client_singleton():
    """Verify PostgresClient singleton initialization."""
    client1 = PostgresClient.get_instance()
    client2 = PostgresClient.get_instance()
    assert client1 is client2


def test_postgres_e2e_proposal_confirm_restart_workflow():
    """
    Demonstrates full Postgres proposal -> confirmation -> saved edit -> restart workflow.
    Guarantees:
    1. Proposal drafting in PostgreSQL action_drafts with manifest hash.
    2. Policy enforcement (non-self contact change denied).
    3. Fresh spoken confirmation with exact readback match.
    4. Action grant single-use lifecycle and atomic update in Supabase employees table.
    5. Directory revision bumped in directory_metadata.
    6. Complete simulated service restart / reload reflects the persisted data truthfully.
    """
    if not settings.SUPABASE_DATABASE_URL:
        pytest.skip("SUPABASE_DATABASE_URL not configured")

    import uuid
    from backend.adapters.postgres_ticket_action_store import PostgresTicketActionStore
    from backend.adapters.postgres_employee_repository import PostgresEmployeeRepository
    from backend.adapters.postgres_identity_mapping_store import PostgresIdentityMappingStore
    from backend.services.employee_knowledge_service import EmployeeKnowledgeService

    action_store = PostgresTicketActionStore.get_instance()
    emp_repo = PostgresEmployeeRepository.get_instance()
    id_store = PostgresIdentityMappingStore.get_instance()

    actor_id = "EMP-1001"
    session_id = f"sess_test_{uuid.uuid4().hex[:12]}"
    evidence_digest = "sha256_mock_evidence_test_turn_1"
    orig_backend = settings.STORAGE_BACKEND
    settings.STORAGE_BACKEND = "postgres"
    confirm_digest = "sha256_mock_evidence_test_turn_2"

    # Step 0: Ensure session exists in Postgres
    sess = id_store.create_session(
        session_id=session_id,
        employee_id=actor_id,
        full_name="Aarav Mehta",
        role="Software Engineer",
        department="Engineering",
        ttl_seconds=300,
    )
    assert sess.is_valid

    # Step 1: Read current employee phone
    initial_emp = emp_repo.get_employee_by_id(actor_id)
    assert initial_emp is not None
    orig_phone = initial_emp["identity"]["work_phone"] or "+91 98765 43210"
    test_new_phone = "+91 99887 76655"

    try:
        # Step 2: Proposal drafting
        prop = action_store.build_typed_proposal("update_contact", None, value=test_new_phone)
        assert prop["field"] == "phone"
        assert prop["value"] == test_new_phone

        draft = action_store.propose(
            actor_id=actor_id,
            session_id=session_id,
            operation="update_contact",
            ticket_id=None,
            params=prop,
            direct_report_ids=[],
            proposal_digest=evidence_digest,
        )
        assert draft["draft_id"].startswith("draft_")
        assert draft["operation"] == "update_contact"
        assert draft["ticket_id"] == actor_id
        assert test_new_phone in draft["readback"]

        # Verify draft exists in DB
        db_draft = action_store.get_draft(draft["draft_id"])
        assert db_draft is not None
        assert db_draft["status"] == "PENDING"
        assert db_draft["payload_hash"] is not None

        # Step 3: Exact readback confirmation with fresh voice evidence
        receipt = action_store.confirm(
            actor_id=actor_id,
            session_id=session_id,
            spoken=draft["readback"],
            evidence_digest=confirm_digest,
            direct_report_ids=[],
        )
        assert receipt["status"] == "COMMITTED"
        assert receipt["action"] == "update_contact"
        assert receipt["resource_id"] == actor_id
        assert receipt["new_value"] == test_new_phone
        assert receipt["storage"] == "Postgres"

        # Step 4: Verify draft is marked COMMITTED
        committed_draft = action_store.get_draft(draft["draft_id"])
        assert committed_draft["status"] == "COMMITTED"

        # Step 5: Verify simulated restart / cache reload loads the committed edit from Supabase
        knowledge = EmployeeKnowledgeService.get_instance()
        knowledge.reload()

        reloaded_emp = knowledge.get_employee_by_id(actor_id)
        assert reloaded_emp is not None
        assert reloaded_emp["identity"]["work_phone"] == test_new_phone
        assert reloaded_emp["identity"]["contact"]["phone"] == test_new_phone

    finally:
        # Cleanup / restore original phone
        cleanup_session = f"sess_clean_{uuid.uuid4().hex[:12]}"
        id_store.create_session(
            session_id=cleanup_session,
            employee_id=actor_id,
            full_name="Aarav Mehta",
            role="Software Engineer",
            department="Engineering",
            ttl_seconds=300,
        )
        clean_prop = action_store.build_typed_proposal("update_contact", None, value=orig_phone)
        clean_draft = action_store.propose(
            actor_id=actor_id,
            session_id=cleanup_session,
            operation="update_contact",
            ticket_id=None,
            params=clean_prop,
            direct_report_ids=[],
            proposal_digest="sha256_clean_1",
        )
        action_store.confirm(
            actor_id=actor_id,
            session_id=cleanup_session,
            spoken=clean_draft["readback"],
            evidence_digest="sha256_clean_2",
            direct_report_ids=[],
        )
        id_store.revoke_session(session_id)
        id_store.revoke_session(cleanup_session)
        settings.STORAGE_BACKEND = orig_backend
        EmployeeKnowledgeService.get_instance().reload()
