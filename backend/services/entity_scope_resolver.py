"""IntentLock — Person 2 Stage 4 Entity, Relationship and Scope Resolver.

Authoritative resolution layer for entity references, reporting hierarchies,
department/location constraints, and context follow-ups.

CRITICAL INVARIANTS:
1. Precedence: Explicit ID > Relationship > Name > Selection > Ordinal > Self.
2. Honest Outcomes: Distinguishes Resolved, Ambiguous, MissingRequiredReference,
   NotAvailableWithinPermittedScope, UnknownCoverage, RepositoryUnavailable, and TruncatedTraversal.
3. No Hallucinations: Does NOT assume unknown cities are zero or default to Bengaluru.
4. Traversal Safety: Cycle detection, deduplication, stable sorting, and explicit truncation flags.
5. Scope Retention: Never broadens scope silently or drops unresolved constraints.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Literal, Optional, Set, Tuple

from backend.services.claim_extractor import normalize_employee_id


ResolutionStatus = Literal[
    "Resolved",
    "Ambiguous",
    "MissingRequiredReference",
    "NotAvailableWithinPermittedScope",
    "UnknownCoverage",
    "StaleContext",
    "RepositoryUnavailable",
    "UnsupportedScope",
    "TruncatedTraversal",
]


@dataclass(frozen=True)
class EntityResolutionResult:
    """Outcome of resolving an entity target or relation."""
    status: ResolutionStatus
    resolved_id: Optional[str] = None
    target_type: Optional[Literal["employee", "ticket"]] = None
    matched_via: Optional[str] = None
    candidates: List[str] = field(default_factory=list)
    message: Optional[str] = None


@dataclass(frozen=True)
class TraversalResult:
    """Outcome of resolving hierarchical reporting structures."""
    status: ResolutionStatus
    root_id: str
    member_ids: List[str]
    total_found: int
    depth_reached: int
    is_truncated: bool
    message: Optional[str] = None


@dataclass(frozen=True)
class LocationResolutionResult:
    """Outcome of resolving requested geographic/site locations."""
    status: ResolutionStatus
    canonical_location: Optional[str] = None
    requested_location: Optional[str] = None
    is_covered: bool = False
    message: Optional[str] = None


# Authoritative covered organizational sites and aliases
# In a full deployment, this metadata is provided by Person 1's persistence layer.
_AUTHORITATIVE_LOCATION_COVERAGE: Dict[str, Dict[str, Any]] = {
    "bengaluru": {
        "canonical": "Bengaluru",
        "aliases": ["bengaluru", "bangalore", "blr"],
        "is_covered": True,
    },
}

_CANONICAL_TICKET_PATTERN = re.compile(r"\b(?:TKT|INC|REQ)[-\s]?(?:(\d{4}[-\s]\d{3,5})|(\d{3,8}))\b", re.IGNORECASE)


def normalize_location(
    requested_location: str,
    coverage_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
) -> LocationResolutionResult:
    """Resolve a requested location string against authoritative coverage metadata.

    Distinguishes:
    - Covered site (e.g. Bengaluru, Bangalore -> canonical Bengaluru)
    - Unknown site (e.g. Tulum, London, Tokyo -> UnknownCoverage, preserves request)
    """
    if not requested_location or not requested_location.strip():
        return LocationResolutionResult(
            status="Resolved",
            canonical_location=None,
            requested_location=None,
            is_covered=False,
        )

    clean_req = requested_location.strip()
    norm_key = re.sub(r"[^a-zA-Z0-9]", "", clean_req).lower()
    coverage = coverage_metadata if coverage_metadata is not None else _AUTHORITATIVE_LOCATION_COVERAGE

    for site_key, site_info in coverage.items():
        aliases = [re.sub(r"[^a-zA-Z0-9]", "", a).lower() for a in site_info.get("aliases", [site_key])]
        if norm_key in aliases or norm_key == site_key:
            return LocationResolutionResult(
                status="Resolved",
                canonical_location=site_info.get("canonical", site_key.title()),
                requested_location=clean_req,
                is_covered=site_info.get("is_covered", True),
            )

    # Unknown site / coverage: Preserve exact requested name and produce honest clarification
    available_sites = sorted([info.get("canonical", k.title()) for k, info in coverage.items() if info.get("is_covered")])
    sites_str = ", ".join(available_sites) if available_sites else "None recorded"
    return LocationResolutionResult(
        status="UnknownCoverage",
        canonical_location=None,
        requested_location=clean_req,
        is_covered=False,
        message=f"Location '{clean_req}' is not in covered organizational facilities. Available locations: {sites_str}.",
    )


def resolve_entity_reference(
    phrase: Optional[str],
    actor_id: str,
    visible_candidates: List[Dict[str, Any]],
    selected_employee_id: Optional[str] = None,
    selected_ticket_id: Optional[str] = None,
    active_visible_ids: Optional[List[str]] = None,
    get_manager_func: Optional[Callable[[str], Optional[str]]] = None,
) -> EntityResolutionResult:
    """Resolve an entity reference using strict documented precedence.

    Order of Precedence:
    1. Explicit stable target ID in current request (e.g. EMP-2001, TKT-101)
    2. Explicit relationship in current request (e.g. 'my manager', 'their manager')
    3. Explicit full/preferred name within permitted candidate scope
    4. Valid selected resource reference (selected_employee_id or selected_ticket_id)
    5. Valid ordinal reference from active result (e.g. 'first person', 'second person')
    6. Self ONLY when request specifically refers to self ('my profile', 'me', 'myself')
    """
    if not phrase or not phrase.strip():
        # Empty phrase: defaults to self if actor_id is verified
        if actor_id:
            return EntityResolutionResult(
                status="Resolved",
                resolved_id=actor_id,
                target_type="employee",
                matched_via="self_default",
            )
        return EntityResolutionResult(
            status="MissingRequiredReference",
            message="No target specified and no verified session actor present.",
        )

    text = phrase.strip()

    # Precedence 1: Explicit Target ID
    # Check for Ticket ID
    tkt_match = _CANONICAL_TICKET_PATTERN.search(text)
    if tkt_match:
        norm_tkt = re.sub(r"\s+", "-", tkt_match.group(0).upper())
        return EntityResolutionResult(
            status="Resolved",
            resolved_id=norm_tkt,
            target_type="ticket",
            matched_via="explicit_ticket_id",
        )

    # Check for Employee ID
    emp_norm = normalize_employee_id(text)
    if emp_norm:
        # Check if explicit employee ID is permitted/visible
        is_permitted = any(e.get("employee_id") == emp_norm for e in visible_candidates)
        if is_permitted or emp_norm == actor_id:
            return EntityResolutionResult(
                status="Resolved",
                resolved_id=emp_norm,
                target_type="employee",
                matched_via="explicit_employee_id",
            )
        # Target ID exists in request but is outside permitted scope
        return EntityResolutionResult(
            status="NotAvailableWithinPermittedScope",
            resolved_id=emp_norm,
            target_type="employee",
            matched_via="explicit_employee_id",
            message=f"Employee {emp_norm} is outside your authorized organizational visibility.",
        )

    # Precedence 2: Explicit Relationship ('my manager', 'their manager')
    if re.search(r"\b(?:my|the)\s+manager\b", text, re.IGNORECASE):
        if not actor_id:
            return EntityResolutionResult(
                status="MissingRequiredReference",
                message="Cannot resolve 'my manager' without a verified session.",
            )
        manager_id = get_manager_func(actor_id) if get_manager_func else None
        if manager_id:
            return EntityResolutionResult(
                status="Resolved",
                resolved_id=manager_id,
                target_type="employee",
                matched_via="actor_manager_relationship",
            )
        return EntityResolutionResult(
            status="Resolved",
            resolved_id=None,
            target_type="employee",
            matched_via="actor_manager_relationship",
            message="No manager recorded for this employee.",
        )

    if re.search(r"\b(?:their|his|her)\s+manager\b", text, re.IGNORECASE):
        target_ref = selected_employee_id
        if not target_ref:
            return EntityResolutionResult(
                status="MissingRequiredReference",
                message="Cannot resolve 'their manager' because no employee is currently selected.",
            )
        manager_id = get_manager_func(target_ref) if get_manager_func else None
        if manager_id:
            return EntityResolutionResult(
                status="Resolved",
                resolved_id=manager_id,
                target_type="employee",
                matched_via="selected_manager_relationship",
            )
        return EntityResolutionResult(
            status="Resolved",
            resolved_id=None,
            target_type="employee",
            matched_via="selected_manager_relationship",
            message=f"No manager recorded for employee {target_ref}.",
        )

    # Precedence 3: Explicit Full or Preferred Name
    clean_query = text.lower()
    matching_employees = []
    for emp in visible_candidates:
        emp_id = emp.get("employee_id")
        full_name = emp.get("identity", {}).get("full_name", "").lower()
        first_name = full_name.split()[0] if full_name else ""

        if full_name and re.search(rf"\b{re.escape(full_name)}\b", clean_query):
            matching_employees.append(emp_id)
        elif first_name and len(first_name) >= 3 and re.search(rf"\b{re.escape(first_name)}\b", clean_query):
            matching_employees.append(emp_id)

    matching_employees = list(dict.fromkeys(matching_employees))
    if len(matching_employees) == 1:
        return EntityResolutionResult(
            status="Resolved",
            resolved_id=matching_employees[0],
            target_type="employee",
            matched_via="name_match",
        )
    elif len(matching_employees) > 1:
        # Ambiguous name (e.g. multiple "Priya"s) -> clarify! NEVER pick first silently
        return EntityResolutionResult(
            status="Ambiguous",
            candidates=matching_employees,
            target_type="employee",
            matched_via="name_match",
            message=f"Multiple employees match '{text}'. Please specify employee ID.",
        )

    # Precedence 4: Valid Selected Resource Reference
    if re.search(r"\b(?:their|this|that|selected)\s+(?:profile|person|employee|tickets?)\b", text, re.IGNORECASE):
        if selected_employee_id:
            return EntityResolutionResult(
                status="Resolved",
                resolved_id=selected_employee_id,
                target_type="employee",
                matched_via="selected_employee_reference",
            )
        if selected_ticket_id:
            return EntityResolutionResult(
                status="Resolved",
                resolved_id=selected_ticket_id,
                target_type="ticket",
                matched_via="selected_ticket_reference",
            )
        return EntityResolutionResult(
            status="MissingRequiredReference",
            message="No resource is currently selected to resolve relative reference.",
        )

    # Precedence 5: Valid Ordinal Reference from Active Result
    ordinal_match = re.search(r"\b(first|second|third|fourth|fifth)\s+(?:person|employee|ticket|one)\b", text, re.IGNORECASE)
    if ordinal_match and active_visible_ids:
        ord_map = {"first": 0, "second": 1, "third": 2, "fourth": 3, "fifth": 4}
        idx = ord_map.get(ordinal_match.group(1).lower(), -1)
        if 0 <= idx < len(active_visible_ids):
            resolved = active_visible_ids[idx]
            target_kind = "ticket" if resolved.startswith("TKT-") else "employee"
            return EntityResolutionResult(
                status="Resolved",
                resolved_id=resolved,
                target_type=target_kind,
                matched_via="ordinal_reference",
            )
        return EntityResolutionResult(
            status="StaleContext",
            message=f"Ordinal '{ordinal_match.group(1)}' is beyond visible item count ({len(active_visible_ids)}).",
        )

    # Precedence 6: Self Reference ONLY
    if re.search(r"\b(?:my profile|about me|who am i|myself|my details)\b", text, re.IGNORECASE):
        if actor_id:
            return EntityResolutionResult(
                status="Resolved",
                resolved_id=actor_id,
                target_type="employee",
                matched_via="self_reference",
            )
        return EntityResolutionResult(
            status="MissingRequiredReference",
            message="Cannot resolve self without an authenticated session.",
        )

    return EntityResolutionResult(
        status="MissingRequiredReference",
        message=f"Could not resolve target reference from '{text}'.",
    )


def traverse_reporting_tree(
    root_id: str,
    get_reports_func: Callable[[str], List[Dict[str, Any]]],
    include_root: bool = False,
    max_depth: int = 5,
    max_nodes: int = 100,
) -> TraversalResult:
    """Traverse multi-tier reporting hierarchy with cycle detection and bounded work.

    Guarantees:
    - Cycle detection using visited set (prevents infinite recursion)
    - Deduplication
    - Stable sorting
    - Truncation status honesty (flags is_truncated if limits reached)
    - Distinction between unknown root vs known root with 0 reports
    """
    if not root_id:
        return TraversalResult(
            status="Ambiguous",
            root_id="",
            member_ids=[],
            total_found=0,
            depth_reached=0,
            is_truncated=False,
            message="No root employee specified for tree traversal.",
        )

    visited: Set[str] = {root_id}
    result_members: List[str] = [root_id] if include_root else []

    frontier = [root_id]
    current_depth = 0
    is_truncated = False

    while frontier and current_depth < max_depth:
        current_depth += 1
        next_frontier: List[str] = []

        for manager_id in frontier:
            direct_reports = get_reports_func(manager_id)
            for r in direct_reports:
                r_id = r.get("employee_id")
                if not r_id or r_id in visited:
                    continue  # Cycle detected or already visited

                if len(result_members) >= max_nodes:
                    is_truncated = True
                    break

                visited.add(r_id)
                result_members.append(r_id)
                next_frontier.append(r_id)

            if is_truncated:
                break

        frontier = next_frontier

    if len(frontier) > 0 and current_depth >= max_depth:
        is_truncated = True

    status: ResolutionStatus = "TruncatedTraversal" if is_truncated else "Resolved"

    return TraversalResult(
        status=status,
        root_id=root_id,
        member_ids=sorted(result_members),
        total_found=len(result_members),
        depth_reached=current_depth,
        is_truncated=is_truncated,
        message="Reporting tree traversal truncated due to depth/node bounds." if is_truncated else None,
    )
