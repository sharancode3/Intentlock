"""
tests/test_query_facts.py
Tests for Person 2 Stage 6: Authorized Deterministic Queries, Fact Bundles, and Metrics.
"""

from datetime import datetime, timezone, timedelta
import random
import pytest

from backend.services.query_fact_service import (
    QueryFactService,
    NormalizedQuerySpec,
    FactBundle,
)
from backend.core.scoped_authorization import ScopedAuthorizationService


def test_allowlist_ticket_projection():
    """Confidential internal credentials and DB tokens are stripped from ticket projection."""
    service = QueryFactService()
    raw_ticket = {
        "ticket_id": "TCK-412",
        "title": "Monitor flickering",
        "description": "Flickers when USB-C connected",
        "priority": "Critical",
        "status": "Open",
        "category": "hardware",
        "assignee_id": "EMP-1020",
        "requester_id": "EMP-1042",
        "created_at": "2026-10-16T10:00:00Z",
        # Sensitive or internal fields that must be stripped:
        "internal_db_row_id": 9999,
        "auth_token": "secret_token_123",
        "session_hash": "abcde12345",
        "policy_evaluation_log": {"allowed": True},
    }
    projected = service.project_ticket_record(raw_ticket)
    assert projected["ticket_id"] == "TCK-412"
    assert projected["priority"] == "Critical"
    assert "internal_db_row_id" not in projected
    assert "auth_token" not in projected
    assert "session_hash" not in projected
    assert "policy_evaluation_log" not in projected


def test_allowlist_employee_projection():
    """Sensitive salary and auth credentials are stripped from employee projection."""
    service = QueryFactService()
    raw_emp = {
        "identity": {
            "employee_id": "EMP-1042",
            "full_name": "Charlie Davis",
            "work_email": "charlie@intentlock.demo",
            "password_hash": "$2b$12$eXamPLeHaSh",
            "voice_enrolled": True,
        },
        "organization": {
            "title": "Software Engineer",
            "department": "Engineering",
            "location": "Bengaluru",
            "manager_id": "EMP-1020",
            "salary_band": "L4-Private",
            "equity_grants": 5000,
        }
    }
    projected = service.project_employee_record(raw_emp)
    assert projected["employee_id"] == "EMP-1042"
    assert projected["full_name"] == "Charlie Davis"
    assert projected["department"] == "Engineering"
    assert projected["location"] == "Bengaluru"
    assert "password_hash" not in projected
    assert "salary_band" not in projected
    assert "equity_grants" not in projected


def test_sla_injected_clock():
    """SLA overdue calculation changes deterministically based on injected 'now' parameter."""
    service = QueryFactService()
    # Ticket due at 2026-10-16T12:00:00Z
    ticket = {
        "ticket_id": "TCK-1",
        "status": "Open",
        "due_date": "2026-10-16T12:00:00+00:00",
        "sla": {"resolution_target_hours": 24},
    }
    tickets = [ticket]

    # Time before deadline -> Compliant (0% overdue)
    clock_before = datetime(2026, 10, 16, 11, 0, 0, tzinfo=timezone.utc)
    res_before = service.calculate_sla_metrics(tickets, "overdue", now=clock_before)
    assert res_before["overdue_count"] == 0
    assert res_before["compliant_count"] == 1
    assert res_before["rate"] == 0.0

    # Time after deadline -> Overdue (100% overdue)
    clock_after = datetime(2026, 10, 16, 13, 0, 0, tzinfo=timezone.utc)
    res_after = service.calculate_sla_metrics(tickets, "overdue", now=clock_after)
    assert res_after["overdue_count"] == 1
    assert res_after["compliant_count"] == 0
    assert res_after["rate"] == 100.0


def test_sla_zero_denominator_honest_data():
    """When no tickets have an SLA target, rate is None, never falsely reported as 0%."""
    service = QueryFactService()
    tickets_without_sla = [
        {"ticket_id": "TCK-1", "status": "Open"},
        {"ticket_id": "TCK-2", "status": "In Progress"},
    ]
    res = service.calculate_sla_metrics(tickets_without_sla, "compliance")
    assert res["eligible_count"] == 0
    assert res["rate"] is None
    assert res["status"] == "no_eligible_data"
    assert "No eligible SLA targets" in res["rate_percent_str"]


def test_resolution_time_metrics_completed_only():
    """Unresolved tickets are excluded, and negative durations are rejected."""
    service = QueryFactService()
    tickets = [
        # Valid ticket: 4 hours
        {
            "ticket_id": "TCK-1",
            "status": "Resolved",
            "created_at": "2026-10-16T10:00:00Z",
            "resolved_at": "2026-10-16T14:00:00Z",
        },
        # Valid ticket: 6 hours
        {
            "ticket_id": "TCK-2",
            "status": "Closed",
            "created_at": "2026-10-16T08:00:00Z",
            "closed_at": "2026-10-16T14:00:00Z",
        },
        # Unresolved ticket: must be excluded from resolution duration!
        {
            "ticket_id": "TCK-3",
            "status": "Open",
            "created_at": "2026-10-16T08:00:00Z",
        },
        # Corrupt timestamps: resolved_at before created_at -> negative interval rejected!
        {
            "ticket_id": "TCK-4",
            "status": "Resolved",
            "created_at": "2026-10-16T15:00:00Z",
            "resolved_at": "2026-10-16T12:00:00Z",
        }
    ]
    res = service.calculate_resolution_time_metrics(tickets)
    assert res["eligible_count"] == 2
    assert res["unresolved_count"] == 1
    assert res["invalid_negative_count"] == 1
    # Average of 4 and 6 is 5.0 hours
    assert res["avg_hours"] == 5.0
    assert res["median_hours"] == 5.0
    assert res["min_hours"] == 4.0
    assert res["max_hours"] == 6.0


def test_created_date_time_series_not_backlog():
    """Grouped by creation date, sorted ascending, with invalid date count tracked."""
    service = QueryFactService()
    tickets = [
        {"ticket_id": "T1", "created_at": "2026-10-15T09:00:00Z"},
        {"ticket_id": "T2", "created_at": "2026-10-16T10:30:00Z"},
        {"ticket_id": "T3", "created_at": "2026-10-15T14:00:00Z"},
        {"ticket_id": "T4", "created_at": "Not-A-Valid-Date"},
        {"ticket_id": "T5", "created_at": None},
    ]
    series, invalid_count = service.calculate_created_date_time_series(tickets)
    assert invalid_count == 2
    assert len(series) == 2
    assert series[0]["date"] == "2026-10-15"
    assert series[0]["count"] == 2
    assert series[1]["date"] == "2026-10-16"
    assert series[1]["count"] == 1


def test_unknown_office_not_zero_headcount():
    """Querying an unknown/uncovered location returns unknown_location status, not 0 count."""
    service = QueryFactService()
    team = [
        {"identity": {"employee_id": "EMP-1"}, "organization": {"location": "Bengaluru", "department": "Engineering"}},
        {"identity": {"employee_id": "EMP-2"}, "organization": {"location": "Bengaluru", "department": "Engineering"}},
    ]
    # Covered location
    res_bengaluru = service.calculate_team_headcount(team, location_filter="Bengaluru")
    assert res_bengaluru["status"] == "calculated"
    assert res_bengaluru["headcount"] == 2

    # Unknown location (Tulum is not in covered offices)
    res_tulum = service.calculate_team_headcount(team, location_filter="Tulum")
    assert res_tulum["status"] == "unknown_location"
    assert res_tulum["headcount"] is None
    assert "outside known coverage" in res_tulum["explanation"]


def test_ticket_breakdown_with_unknowns():
    """Missing or unrecognized statuses/priorities are tracked explicitly under Unknown."""
    service = QueryFactService()
    tickets = [
        {"ticket_id": "T1", "priority": "urgent"},
        {"ticket_id": "T2", "priority": "High"},
        {"ticket_id": "T3", "priority": "medium"},
        {"ticket_id": "T4", "priority": None},
        {"ticket_id": "T5", "priority": ""},
    ]
    counts, unk = service.calculate_ticket_breakdown(tickets, "priority")
    assert unk == 2
    assert counts["Critical"] == 1  # urgent normalized to Critical
    assert counts["High"] == 1
    assert counts["Medium"] == 1    # medium normalized to Medium
    assert counts["Unknown"] == 2


def test_deterministic_stability_under_input_order():
    """Totals and breakdowns are perfectly identical regardless of list ordering."""
    service = QueryFactService()
    tickets = [
        {"ticket_id": f"T{i}", "priority": ["Low", "Medium", "High", "Critical"][i % 4]}
        for i in range(100)
    ]
    shuffled = list(tickets)
    random.seed(42)
    random.shuffle(shuffled)

    counts_orig, unk_orig = service.calculate_ticket_breakdown(tickets, "priority")
    counts_shuf, unk_shuf = service.calculate_ticket_breakdown(shuffled, "priority")

    assert counts_orig == counts_shuf
    assert unk_orig == unk_shuf


def test_repository_outage_handling():
    """Repository failure sets is_outage_or_error=True and does not produce empty facts."""
    service = QueryFactService()
    spec = NormalizedQuerySpec(
        resource_domain="ticket",
        requested_operation="ticket_list",
    )
    bundle = service.build_fact_bundle(
        query_spec=spec,
        authorized_records=[],
        scope_description="Scope check",
        is_error=True,
        error_message="Postgres connection timeout on Supabase replica",
    )
    assert bundle.is_outage_or_error is True
    assert bundle.error_message == "Postgres connection timeout on Supabase replica"
    assert bundle.aggregates == {}
