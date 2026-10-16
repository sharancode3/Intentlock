"""
IntentLock — Ticket Knowledge & Scoped Authorization Test Suite
Verifies the 20 required tests from Section 27 of the specification,
plus scope enforcement, zero hallucination on unknown tickets, and endpoint security.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.ticket_knowledge_service import TicketKnowledgeService
from backend.services.employee_knowledge_service import EmployeeKnowledgeService
from backend.core.scoped_authorization import ScopedAuthorizationService
from backend.adapters.identity_mapping_store import IdentityMappingStore

@pytest.fixture(scope="module")
def ticket_service():
    return TicketKnowledgeService.get_instance()

@pytest.fixture(scope="module")
def scoped_auth():
    return ScopedAuthorizationService.get_instance()

@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# =============================================================================
# Section 27: The 20 Required Verification Tests
# =============================================================================

def test_01_aarav_tickets(ticket_service, scoped_auth):
    """TEST 1: Show me Aarav's tickets."""
    aarav_tickets = ticket_service.get_scoped_tickets_for_actor("EMP-1001")
    assert len(aarav_tickets) >= 15
    # Verify Aarav is involved in every ticket
    for t in aarav_tickets:
        assert (
            t.get("assignee_id") == "EMP-1001"
            or t.get("requester_id") == "EMP-1001"
            or t.get("created_by") == "EMP-1001"
        )


def test_02_aarav_open_tickets(ticket_service):
    """TEST 2: Show me Aarav's open tickets."""
    aarav_tickets = ticket_service.get_scoped_tickets_for_actor("EMP-1001")
    open_tickets = [t for t in aarav_tickets if t.get("status") in ("Open", "In Progress", "Blocked")]
    assert len(open_tickets) > 0
    filtered = ticket_service.filter_tickets_for_query(aarav_tickets, "open tickets")
    assert any(t["ticket_id"] in ("TKT-2026-001", "TKT-2026-005") for t in filtered)


def test_03_aarav_highest_priority_unresolved(ticket_service):
    """TEST 3: What is Aarav's highest-priority unresolved ticket?"""
    aarav_tickets = ticket_service.get_scoped_tickets_for_actor("EMP-1001")
    unresolved = [t for t in aarav_tickets if t.get("status") not in ("Resolved", "Closed")]
    critical = [t for t in unresolved if t.get("priority") == "Critical"]
    assert len(critical) >= 1
    # TKT-2026-008 is Aarav's Critical unresolved deployment failure ticket
    assert any(t["ticket_id"] == "TKT-2026-008" for t in critical)


def test_04_tickets_escalated_to_priya(ticket_service):
    """TEST 4: What tickets have been escalated to Priya?"""
    escalated = [
        t for t in ticket_service.list_all_tickets()
        if t.get("escalation", {}).get("is_escalated") and t.get("escalation", {}).get("escalated_to") == "EMP-2001"
    ]
    assert len(escalated) >= 4
    tids = {t["ticket_id"] for t in escalated}
    # TKT-2026-001, TKT-2026-007, TKT-2026-008, TKT-2026-012, TKT-2026-015 were escalated to Priya
    assert "TKT-2026-001" in tids or "TKT-2026-007" in tids


def test_05_tickets_requiring_priya_approval(ticket_service):
    """TEST 5: Which tickets require Priya's approval?"""
    requiring_approval = [
        t for t in ticket_service.list_all_tickets()
        if t.get("approval", {}).get("required") and t.get("approval", {}).get("approver_id") == "EMP-2001"
    ]
    assert len(requiring_approval) >= 3
    # Check pending approvals for Priya
    pending_priya = [t for t in requiring_approval if t.get("approval", {}).get("status") == "Pending"]
    assert len(pending_priya) >= 1


def test_06_critical_issues_requiring_arvind_attention(ticket_service):
    """TEST 6: What critical issues require Arvind's attention?"""
    arvind_tickets = ticket_service.get_scoped_tickets_for_actor("EMP-4002", is_executive=True)
    critical_arvind = [
        t for t in arvind_tickets
        if t.get("priority") == "Critical" and (
            t.get("assignee_id") == "EMP-4002"
            or t.get("escalation", {}).get("escalated_to") == "EMP-4002"
            or t.get("approval", {}).get("approver_id") == "EMP-4002"
        )
    ]
    assert len(critical_arvind) >= 5
    tids = {t["ticket_id"] for t in critical_arvind}
    assert "TKT-2026-031" in tids  # SSO Failover Incident
    assert "TKT-2026-032" in tids  # Architecture Sign-off


def test_07_tickets_escalated_to_cto(ticket_service):
    """TEST 7: What tickets have been escalated to the CTO?"""
    escalated_to_cto = [
        t for t in ticket_service.list_all_tickets()
        if t.get("escalation", {}).get("is_escalated") and t.get("escalation", {}).get("escalated_to") == "EMP-4002"
    ]
    assert len(escalated_to_cto) >= 5
    tids = {t["ticket_id"] for t in escalated_to_cto}
    assert "TKT-2026-014" in tids or "TKT-2026-026" in tids or "TKT-2026-031" in tids


def test_08_story_1_authentication_incident(ticket_service):
    """TEST 8: What happened with the Customer Support Portal authentication incident?"""
    tkt_14 = ticket_service.get_ticket_by_id("TKT-2026-014")
    assert tkt_14 is not None
    assert "authentication" in tkt_14["title"].lower()
    assert tkt_14["priority"] == "Critical"
    assert tkt_14["status"] == "Resolved"


def test_09_story_1_priya_role(ticket_service):
    """TEST 9: What did Priya do during that incident?"""
    tkt_14 = ticket_service.get_ticket_by_id("TKT-2026-014")
    assert tkt_14 is not None
    # Priya commented and escalated
    priya_comments = [c for c in tkt_14["comments"] if c["author_id"] == "EMP-2001"]
    assert len(priya_comments) >= 1
    assert "escalated" in priya_comments[0]["comment"].lower() or "arvind" in priya_comments[0]["comment"].lower()


def test_10_story_1_arvind_involvement(ticket_service):
    """TEST 10: Why did Arvind become involved?"""
    tkt_14 = ticket_service.get_ticket_by_id("TKT-2026-014")
    assert tkt_14 is not None
    assert tkt_14["approval"]["required"] is True
    assert tkt_14["approval"]["approver_id"] == "EMP-4002"
    assert tkt_14["approval"]["status"] == "Approved"


def test_11_story_1_root_cause(ticket_service):
    """TEST 11: What was the root cause?"""
    tkt_14 = ticket_service.get_ticket_by_id("TKT-2026-014")
    root_cause = tkt_14.get("resolution", {}).get("root_cause")
    assert root_cause is not None
    assert "replication" in root_cause.lower() or "replica" in root_cause.lower() or "redis" in root_cause.lower()


def test_12_story_1_who_resolved(ticket_service):
    """TEST 12: Who resolved the incident?"""
    tkt_14 = ticket_service.get_ticket_by_id("TKT-2026-014")
    resolved_by = tkt_14.get("resolution", {}).get("resolved_by")
    assert resolved_by == "EMP-1001"  # Aarav Mehta resolved after hotfix deployment


def test_13_compare_workload(ticket_service):
    """TEST 13: Compare Aarav and Priya's open ticket workload."""
    aarav_tickets = ticket_service.get_scoped_tickets_for_actor("EMP-1001")
    aarav_open = [t for t in aarav_tickets if t.get("status") in ("Open", "In Progress", "Blocked")]

    priya_tickets = ticket_service.get_scoped_tickets_for_actor("EMP-2001", direct_report_ids=["EMP-1001", "EMP-1501"])
    priya_open = [t for t in priya_tickets if t.get("status") in ("Open", "In Progress", "Pending", "Blocked")]

    assert len(aarav_open) > 0
    assert len(priya_open) > 0
    # Priya manages more scope including direct report tickets
    assert len(priya_tickets) >= len(aarav_tickets)


def test_14_sla_at_risk_tickets(ticket_service):
    """TEST 14: Show tickets currently at risk of SLA breach."""
    at_risk = [
        t for t in ticket_service.list_all_tickets()
        if t.get("sla", {}).get("resolution_status") == "At Risk"
    ]
    assert len(at_risk) >= 3
    tids = {t["ticket_id"] for t in at_risk}
    assert "TKT-2026-001" in tids or "TKT-2026-007" in tids or "TKT-2026-016" in tids


def test_15_unresolved_authentication_issues(ticket_service):
    """TEST 15: Show unresolved authentication issues."""
    auth_unresolved = [
        t for t in ticket_service.list_all_tickets()
        if "auth" in t.get("category", "").lower() and t.get("status") not in ("Resolved", "Closed")
    ]
    assert len(auth_unresolved) >= 1
    assert any(t["ticket_id"] == "TKT-2026-001" for t in auth_unresolved)


def test_16_pending_approvals(ticket_service):
    """TEST 16: Show pending approvals."""
    pending_apps = [
        t for t in ticket_service.list_all_tickets()
        if t.get("approval", {}).get("status") == "Pending"
    ]
    assert len(pending_apps) >= 4
    # Ensure approver_ids are valid
    for t in pending_apps:
        assert t["approval"]["approver_id"] is not None


def test_17_overdue_or_upcoming_tickets(ticket_service):
    """TEST 17: Which tickets are due soon / overdue?"""
    due_tickets = [t for t in ticket_service.list_all_tickets() if t.get("due_date")]
    assert len(due_tickets) == 42


def test_18_latest_comment_tkt_001(ticket_service):
    """TEST 18: What is the latest comment on TKT-2026-001?"""
    tkt_01 = ticket_service.get_ticket_by_id("TKT-2026-001")
    assert tkt_01 is not None
    comments = tkt_01.get("comments", [])
    assert len(comments) >= 2
    latest = comments[-1]
    assert latest["author_id"] == "EMP-1001"
    assert "PR" in latest["comment"] or "grace" in latest["comment"]


def test_19_activity_history_tkt_001(ticket_service):
    """TEST 19: Show the activity history of TKT-2026-001."""
    tkt_01 = ticket_service.get_ticket_by_id("TKT-2026-001")
    assert tkt_01 is not None
    history = tkt_01.get("activity_history", [])
    assert len(history) >= 3
    event_types = [h["type"] for h in history]
    assert "TICKET_CREATED" in event_types
    assert "ESCALATED" in event_types


def test_20_zero_hallucination_unknown_ticket(scoped_auth):
    """TEST 20: What is TKT-9999? MUST NOT hallucinate a ticket."""
    context = scoped_auth.build_authorized_context_for_llm(
        actor_id="EMP-1001",
        query="What is TKT-9999?",
    )
    assert "ticket_query_result" in context
    res = context["ticket_query_result"]
    assert res["exists"] is False
    assert res["status"] == "NOT_FOUND"
    assert "not exist" in res["message"].lower()


# =============================================================================
# Scoped Authorization & UI Rendering Tests
# =============================================================================

def test_evaluate_and_get_tickets_renders_ticket_list(scoped_auth):
    """Verify ScopedAuthorizationService returns GenericResultBlock of type TICKET_LIST."""
    res = scoped_auth.evaluate_and_get_tickets(actor_id="EMP-1001", query="my tickets")
    assert res.is_authorized is True
    assert res.result_block is not None
    assert res.result_block.type == "TICKET_LIST"
    payload = res.result_block.payload
    assert "tickets" in payload
    assert len(payload["tickets"]) >= 15
    first_ticket = payload["tickets"][0]
    # Check frontend payload compatibility
    assert "ticket_id" in first_ticket
    assert "title" in first_ticket
    assert "priority" in first_ticket
    assert first_ticket["priority"] in ("URGENT", "HIGH", "NORMAL", "LOW")
    assert "status" in first_ticket
    assert first_ticket["status"] in ("OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED")


def test_ticket_api_requires_active_session(client):
    """Protected ticket routes must reject unauthenticated requests."""
    res = client.get("/api/v1/tickets")
    assert res.status_code == 401


def test_ticket_api_with_active_session(client):
    """Protected ticket route returns scoped tickets for authenticated session."""
    store = IdentityMappingStore.get_instance()
    sess = store.create_session(
        session_id="sess_test_aarav_tickets",
        employee_id="EMP-1001",
        full_name="Aarav Mehta",
        role="employee",
        department="Engineering",
        ttl_seconds=300,
    )
    headers = {"Authorization": f"Bearer {sess.session_id}"}
    res = client.get("/api/v1/tickets", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "tickets" in data
    assert len(data["tickets"]) >= 15
