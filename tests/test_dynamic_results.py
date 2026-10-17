"""
tests/test_dynamic_results.py
Tests for Person 2 Stage 7: Dynamic Structured Outputs, Renderer Selection, and Agreement.
"""

from datetime import datetime, timezone
import pytest

from backend.services.query_fact_service import (
    QueryFactService,
    NormalizedQuerySpec,
    FactBundle,
)
from backend.services.result_generator import (
    ResultGenerator,
    PresentationDecision,
)
from backend.models.turn import GenericResultBlock


def test_single_metric_headcount():
    """Single headcount metric renders as TEAM_METRIC_CHART with agreement in spoken text."""
    q_service = QueryFactService()
    r_generator = ResultGenerator()

    team = [
        {"identity": {"employee_id": "EMP-1", "full_name": "Dev 1"}, "organization": {"department": "Engineering", "location": "Bengaluru"}},
        {"identity": {"employee_id": "EMP-2", "full_name": "Dev 2"}, "organization": {"department": "Engineering", "location": "Bengaluru"}},
        {"identity": {"employee_id": "EMP-3", "full_name": "Dev 3"}, "organization": {"department": "Engineering", "location": "Bengaluru"}},
    ]
    spec = NormalizedQuerySpec(
        resource_domain="team",
        requested_operation="headcount",
        metric="headcount",
        filters={"department": "Engineering"},
    )
    bundle = q_service.build_fact_bundle(spec, team, "Engineering direct team")
    block, spoken = r_generator.generate_result(bundle)

    assert block.type == "TEAM_METRIC_CHART"
    assert block.payload["unit"] == "people"
    assert block.payload["data"][0]["count"] == 3
    assert "3 people" in spoken
    assert "Engineering" in spoken


def test_employee_profile_block():
    """Single employee query maps to EMPLOYEE_PROFILE with allowlisted fields."""
    q_service = QueryFactService()
    r_generator = ResultGenerator()

    emp = [{
        "employee_id": "EMP-1042",
        "full_name": "Charlie Davis",
        "title": "Software Engineer",
        "department": "Engineering",
        "location": "Bengaluru",
        "work_email": "charlie@intentlock.demo",
        # Sensitive fields
        "salary": 150000,
        "raw_token": "token_abc",
    }]
    spec = NormalizedQuerySpec(
        resource_domain="employee",
        requested_operation="profile",
        root_target_id="EMP-1042",
    )
    bundle = q_service.build_fact_bundle(spec, emp, "Self profile")
    block, spoken = r_generator.generate_result(bundle)

    assert block.type == "EMPLOYEE_PROFILE"
    assert block.title == "Charlie Davis"
    assert block.payload["employee_id"] == "EMP-1042"
    assert "salary" not in block.payload
    assert "raw_token" not in block.payload
    assert "Charlie Davis" in spoken


def test_employee_table_block():
    """Multiple employees map to DATA_TABLE with columns and rows."""
    q_service = QueryFactService()
    r_generator = ResultGenerator()

    team = [
        {"employee_id": "EMP-1", "full_name": "Alice", "title": "Lead", "department": "Eng", "location": "BLR"},
        {"employee_id": "EMP-2", "full_name": "Bob", "title": "Engineer", "department": "Eng", "location": "BLR"},
    ]
    spec = NormalizedQuerySpec(
        resource_domain="employee",
        requested_operation="team_table",
    )
    bundle = q_service.build_fact_bundle(spec, team, "Direct reports table")
    block, spoken = r_generator.generate_result(bundle)

    assert block.type == "DATA_TABLE"
    assert len(block.payload["rows"]) == 2
    assert block.payload["total_count"] == 2
    assert "columns" in block.payload


def test_ticket_list_block():
    """Ticket query maps to TICKET_LIST block with tickets array."""
    q_service = QueryFactService()
    r_generator = ResultGenerator()

    tickets = [
        {"ticket_id": "TCK-101", "title": "VPN issue", "priority": "High", "status": "Open", "category": "IT"},
        {"ticket_id": "TCK-102", "title": "Keycard access", "priority": "Low", "status": "Closed", "category": "Facilities"},
    ]
    spec = NormalizedQuerySpec(
        resource_domain="ticket",
        requested_operation="ticket_list",
    )
    bundle = q_service.build_fact_bundle(spec, tickets, "My tickets")
    block, spoken = r_generator.generate_result(bundle)

    assert block.type == "TICKET_LIST"
    assert block.payload["total_count"] == 2
    assert len(block.payload["tickets"]) == 2
    assert "Showing 2 authorized tickets" in spoken


def test_category_bar_and_pie_compatibility():
    """Pie chart requires at least 2 non-zero categories; single category falls back to BAR."""
    q_service = QueryFactService()
    r_generator = ResultGenerator()

    # Case A: 2 categories -> PIE supported
    tickets_multi = [
        {"ticket_id": "T1", "priority": "High"},
        {"ticket_id": "T2", "priority": "Low"},
    ]
    spec_multi = NormalizedQuerySpec(
        resource_domain="ticket",
        requested_operation="ticket_chart",
        grouping="priority",
        requested_presentation="PIE",
    )
    bundle_multi = q_service.build_fact_bundle(spec_multi, tickets_multi, "Tickets by priority")
    block_multi, _ = r_generator.generate_result(bundle_multi, requested_view="PIE")
    assert block_multi.payload["chart_type"] == "PIE"

    # Case B: 1 category -> PIE incompatible, falls back to BAR with explanation
    tickets_single = [
        {"ticket_id": "T1", "priority": "High"},
        {"ticket_id": "T2", "priority": "High"},
    ]
    bundle_single = q_service.build_fact_bundle(spec_multi, tickets_single, "Tickets by priority")
    block_single, spoken_single = r_generator.generate_result(bundle_single, requested_view="PIE")
    assert block_single.payload["chart_type"] == "BAR"
    assert "falling back to Bar chart" in block_single.payload["coverage_note"]
    assert "falling back to Bar chart" in spoken_single


def test_incompatible_view_line_on_non_temporal_data():
    """Requesting LINE on non-temporal priority breakdown falls back to BAR without inventing dates."""
    q_service = QueryFactService()
    r_generator = ResultGenerator()

    tickets = [
        {"ticket_id": "T1", "priority": "Critical"},
        {"ticket_id": "T2", "priority": "Medium"},
    ]
    spec = NormalizedQuerySpec(
        resource_domain="ticket",
        requested_operation="ticket_chart",
        grouping="priority",
        requested_presentation="LINE",
    )
    bundle = q_service.build_fact_bundle(spec, tickets, "Priority breakdown")
    block, spoken = r_generator.generate_result(bundle, requested_view="LINE")

    assert block.payload["chart_type"] == "BAR"
    assert "Cannot render non-temporal data as a LINE chart" in block.payload["coverage_note"]
    assert "Cannot render non-temporal data as a LINE chart" in spoken


def test_incompatible_view_chart_on_single_profile():
    """Requesting BAR on single employee profile falls back to EMPLOYEE_PROFILE card."""
    q_service = QueryFactService()
    r_generator = ResultGenerator()

    emp = [{"employee_id": "EMP-1042", "full_name": "Charlie Davis", "title": "Engineer"}]
    spec = NormalizedQuerySpec(
        resource_domain="employee",
        requested_operation="profile",
        root_target_id="EMP-1042",
        requested_presentation="BAR",
    )
    bundle = q_service.build_fact_bundle(spec, emp, "Profile")
    block, spoken = r_generator.generate_result(bundle, requested_view="BAR")

    assert block.type == "EMPLOYEE_PROFILE"
    assert "cannot be rendered as a chart" in spoken


def test_empty_dataset_rendering():
    """Empty ticket result renders cleanly as TICKET_LIST with count 0."""
    q_service = QueryFactService()
    r_generator = ResultGenerator()

    spec = NormalizedQuerySpec(
        resource_domain="ticket",
        requested_operation="ticket_list",
    )
    bundle = q_service.build_fact_bundle(spec, [], "Empty tickets")
    block, spoken = r_generator.generate_result(bundle)

    assert block.type == "TICKET_LIST"
    assert block.payload["total_count"] == 0
    assert len(block.payload["tickets"]) == 0
    assert "No tickets match the requested criteria" in spoken


def test_compound_results_mixed_outcomes():
    """Compound query retains individual outcomes: permitted profile and outage error."""
    q_service = QueryFactService()
    r_generator = ResultGenerator()

    # Bundle 1: Valid employee profile
    spec1 = NormalizedQuerySpec(resource_domain="employee", requested_operation="profile", root_target_id="EMP-1042")
    bundle1 = q_service.build_fact_bundle(spec1, [{"employee_id": "EMP-1042", "full_name": "Charlie Davis"}], "Self")

    # Bundle 2: Outage error
    spec2 = NormalizedQuerySpec(resource_domain="ticket", requested_operation="ticket_list")
    bundle2 = q_service.build_fact_bundle(spec2, [], "Tickets", is_error=True, error_message="Database replica timeout")

    compound_results = r_generator.generate_compound_results([bundle1, bundle2])
    assert len(compound_results) == 2

    # Result 1: EMPLOYEE_PROFILE
    block1, summary1 = compound_results[0]
    assert block1.type == "EMPLOYEE_PROFILE"
    assert "Charlie Davis" in summary1

    # Result 2: DENIAL_BANNER with error
    block2, summary2 = compound_results[1]
    assert block2.type == "DENIAL_BANNER"
    assert block2.payload["denial_reason"] == "SERVICE_ERROR"
    assert "Database replica timeout" in summary2


def test_fact_payload_text_agreement():
    """Numbers in spoken_summary strictly agree with payload data and bundle aggregates."""
    q_service = QueryFactService()
    r_generator = ResultGenerator()

    tickets = [
        {"ticket_id": "T1", "priority": "Critical"},
        {"ticket_id": "T2", "priority": "Critical"},
        {"ticket_id": "T3", "priority": "High"},
    ]
    spec = NormalizedQuerySpec(
        resource_domain="ticket",
        requested_operation="ticket_chart",
        grouping="priority",
    )
    bundle = q_service.build_fact_bundle(spec, tickets, "Priority breakdown")
    block, spoken = r_generator.generate_result(bundle)

    data_map = {item["label"]: item["count"] for item in block.payload["data"]}
    assert data_map["Critical"] == 2
    assert data_map["High"] == 1
    assert bundle.aggregates["breakdown"]["Critical"] == 2
    assert bundle.aggregates["breakdown"]["High"] == 1

    # Text must contain exact numbers
    assert "3 authorized tickets" in spoken
    assert "2 Critical" in spoken
    assert "1 High" in spoken
