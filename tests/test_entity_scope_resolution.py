"""IntentLock — Person 2 Stage 4 Test Suite: Entity, Relationship and Scope Resolution.

Tests strict resolution precedence, name disambiguation, cycle-safe tree traversal,
truncation honesty, data-driven location coverage, and scope preservation.
Runs strictly offline without provider calls or database writes.
"""

import pytest

from backend.services.entity_scope_resolver import (
    resolve_entity_reference,
    traverse_reporting_tree,
    normalize_location,
    EntityResolutionResult,
    TraversalResult,
    LocationResolutionResult,
)


def test_exact_employee_and_ticket_id_resolution():
    """Explicit canonical IDs resolve directly with highest precedence."""
    visible = [
        {"employee_id": "EMP-2001", "identity": {"full_name": "Bob Miller"}},
        {"employee_id": "EMP-1042", "identity": {"full_name": "Charlie Davis"}},
    ]
    # Explicit employee ID
    emp_res = resolve_entity_reference("EMP-2001", actor_id="EMP-1042", visible_candidates=visible)
    assert emp_res.status == "Resolved"
    assert emp_res.resolved_id == "EMP-2001"
    assert emp_res.target_type == "employee"
    assert emp_res.matched_via == "explicit_employee_id"

    # Explicit ticket ID
    tkt_res = resolve_entity_reference("TKT-2026-009", actor_id="EMP-1042", visible_candidates=visible)
    assert tkt_res.status == "Resolved"
    assert tkt_res.resolved_id == "TKT-2026-009"
    assert tkt_res.target_type == "ticket"
    assert tkt_res.matched_via == "explicit_ticket_id"


def test_duplicate_permitted_names_produce_ambiguity():
    """When multiple employees share a name (e.g. two Priyas), produces Ambiguous clarification."""
    visible = [
        {"employee_id": "EMP-3001", "identity": {"full_name": "Priya Sharma"}},
        {"employee_id": "EMP-3002", "identity": {"full_name": "Priya Patel"}},
    ]
    res = resolve_entity_reference("Show Priya's profile", actor_id="EMP-1042", visible_candidates=visible)
    assert res.status == "Ambiguous"
    assert res.resolved_id is None
    assert len(res.candidates) == 2
    assert "EMP-3001" in res.candidates and "EMP-3002" in res.candidates
    # Proves it does NOT silently choose the first Priya
    assert res.matched_via == "name_match"


def test_explicit_target_overrides_old_selection():
    """An explicit target in the current query overrides an older selected entity."""
    visible = [
        {"employee_id": "EMP-2001", "identity": {"full_name": "Bob Miller"}},
        {"employee_id": "EMP-1001", "identity": {"full_name": "Alice Smith"}},
    ]
    # selected_employee_id is EMP-1001, but speaker asks for EMP-2001
    res = resolve_entity_reference(
        "Show EMP-2001's profile",
        actor_id="EMP-1042",
        visible_candidates=visible,
        selected_employee_id="EMP-1001",
    )
    assert res.status == "Resolved"
    assert res.resolved_id == "EMP-2001"
    assert res.matched_via == "explicit_employee_id"


def test_my_manager_resolution():
    """'my manager' resolves against the verified session actor's reporting structure."""
    def mock_get_manager(eid: str):
        if eid == "EMP-1042":
            return "EMP-2001"
        return None

    res = resolve_entity_reference(
        "Show my manager",
        actor_id="EMP-1042",
        visible_candidates=[],
        get_manager_func=mock_get_manager,
    )
    assert res.status == "Resolved"
    assert res.resolved_id == "EMP-2001"
    assert res.matched_via == "actor_manager_relationship"


def test_selected_person_manager_resolution():
    """'their manager' resolves against the currently selected employee."""
    def mock_get_manager(eid: str):
        if eid == "EMP-2001":
            return "EMP-4002"
        return None

    res = resolve_entity_reference(
        "Who is their manager?",
        actor_id="EMP-1042",
        visible_candidates=[],
        selected_employee_id="EMP-2001",
        get_manager_func=mock_get_manager,
    )
    assert res.status == "Resolved"
    assert res.resolved_id == "EMP-4002"
    assert res.matched_via == "selected_manager_relationship"


def test_missing_selected_entity_returns_missing_reference():
    """'their manager' without a selected employee returns MissingRequiredReference, never defaults to self."""
    res = resolve_entity_reference(
        "Show their manager",
        actor_id="EMP-1042",
        visible_candidates=[],
        selected_employee_id=None,
    )
    assert res.status == "MissingRequiredReference"
    assert res.resolved_id is None


def test_ordinal_stale_context_bounds():
    """Requesting 'fifth person' when only 2 are visible returns StaleContext."""
    res = resolve_entity_reference(
        "Show fifth person",
        actor_id="EMP-1042",
        visible_candidates=[],
        active_visible_ids=["EMP-1001", "EMP-1002"],
    )
    assert res.status == "StaleContext"
    assert res.resolved_id is None


def test_reporting_tree_cycle_detection_and_deduplication():
    """Tree traversal detects cycles (A -> B -> A) and deduplicates members."""
    # Graph: EMP-1 -> [EMP-2], EMP-2 -> [EMP-1, EMP-3] (contains cycle back to EMP-1)
    graph = {
        "EMP-1": [{"employee_id": "EMP-2"}],
        "EMP-2": [{"employee_id": "EMP-1"}, {"employee_id": "EMP-3"}],
        "EMP-3": [],
    }

    result = traverse_reporting_tree(
        root_id="EMP-1",
        get_reports_func=lambda mid: graph.get(mid, []),
        include_root=False,
    )
    assert result.status == "Resolved"
    assert result.is_truncated is False
    # Members should be EMP-2 and EMP-3 without infinite loop
    assert result.member_ids == ["EMP-2", "EMP-3"]
    assert result.total_found == 2


def test_reporting_tree_multi_tier_traversal():
    """Traverses 3 tiers cleanly: CTO -> VP -> Manager -> IC."""
    graph = {
        "CTO": [{"employee_id": "VP-1"}],
        "VP-1": [{"employee_id": "MGR-1"}],
        "MGR-1": [{"employee_id": "IC-1"}, {"employee_id": "IC-2"}],
        "IC-1": [],
        "IC-2": [],
    }

    result = traverse_reporting_tree(
        root_id="CTO",
        get_reports_func=lambda mid: graph.get(mid, []),
        max_depth=5,
    )
    assert result.status == "Resolved"
    assert result.depth_reached == 4
    assert result.member_ids == ["IC-1", "IC-2", "MGR-1", "VP-1"]
    assert result.total_found == 4


def test_reporting_tree_truncation_honesty():
    """When traversal hits max_depth limit, status is TruncatedTraversal and is_truncated is True."""
    # Linear graph of 10 levels
    graph = {f"EMP-{i}": [{"employee_id": f"EMP-{i+1}"}] for i in range(1, 10)}

    result = traverse_reporting_tree(
        root_id="EMP-1",
        get_reports_func=lambda mid: graph.get(mid, []),
        max_depth=3,  # Bounded to 3 levels
    )
    assert result.status == "TruncatedTraversal"
    assert result.is_truncated is True
    assert result.depth_reached == 3
    # Result does NOT pretend to have found everyone
    assert len(result.member_ids) == 3


def test_unknown_location_resolution_preserves_name_and_clarifies():
    """Location 'Tulum' is recognized as unknown coverage, preserved, and clarified honestly."""
    loc_res = normalize_location("Tulum")
    assert loc_res.status == "UnknownCoverage"
    assert loc_res.requested_location == "Tulum"
    assert loc_res.canonical_location is None
    assert loc_res.is_covered is False
    # Honest message pointing to available locations
    assert "Bengaluru" in (loc_res.message or "")


def test_covered_location_alias_normalization():
    """'bangalore' and 'BLR' resolve to canonical covered 'Bengaluru'."""
    assert normalize_location("bangalore").canonical_location == "Bengaluru"
    assert normalize_location("BLR").canonical_location == "Bengaluru"
    assert normalize_location("Bengaluru").is_covered is True


def test_out_of_scope_target_cannot_substitute_actor():
    """Querying an out-of-scope employee returns NotAvailableWithinPermittedScope, never substitutes self."""
    res = resolve_entity_reference(
        "Show EMP-9999's profile",
        actor_id="EMP-1042",
        visible_candidates=[],  # EMP-9999 is NOT visible
    )
    assert res.status == "NotAvailableWithinPermittedScope"
    assert res.resolved_id == "EMP-9999"
    # Never falls back to self actor EMP-1042
    assert res.matched_via != "self_reference"
    assert res.matched_via != "self_default"
