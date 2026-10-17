"""IntentLock — Person 2 Stage 3 Single Supported-Operation Registry.

Authoritative metadata registry for all 18 supported operations in IntentLock.
Describes semantic purpose, execution category, parameter contracts, context
dependencies, and compatible result cards.

CRITICAL INVARIANTS:
1. No Authority: Contains NO guessed user permissions, role rules, or provider verdicts.
2. No Executable Code: Contains NO SQL strings, arbitrary callbacks, or direct writes.
3. Aligned: 100% matched with IntentPlan, ConversationDispatcher, and Card Renderers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Set


OperationCategory = Literal[
    "read",
    "navigation",
    "proposal",
    "confirmation",
    "cancellation",
    "clarification",
    "compound",
]


@dataclass(frozen=True)
class OperationMetadata:
    """Immutable metadata contract for a supported helpdesk operation."""
    name: str
    semantic_purpose: str
    category: OperationCategory
    required_args: List[str] = field(default_factory=list)
    optional_args: List[str] = field(default_factory=list)
    requires_active_result: bool = False
    requires_selected_resource: Optional[Literal["ticket", "employee"]] = None
    compatible_result_blocks: List[str] = field(default_factory=list)
    is_implemented: bool = True
    notes: Optional[str] = None


# Authoritative definition of all 18 supported operations
_SUPPORTED_OPERATIONS: Dict[str, OperationMetadata] = {
    "help": OperationMetadata(
        name="help",
        semantic_purpose="Public kiosk help and capability overview",
        category="read",
        compatible_result_blocks=["PUBLIC_FAQ"],
        notes="Bypasses biometric and session checks.",
    ),
    "profile": OperationMetadata(
        name="profile",
        semantic_purpose="Retrieve authorized profile details for self or visible employee",
        category="read",
        optional_args=["entity", "actor_claim"],
        compatible_result_blocks=["EMPLOYEE_PROFILE", "DENIAL_BANNER"],
    ),
    "team_table": OperationMetadata(
        name="team_table",
        semantic_purpose="List authorized direct reports or department team members in a table",
        category="read",
        optional_args=["descendants", "department", "location"],
        compatible_result_blocks=["DATA_TABLE", "DENIAL_BANNER"],
    ),
    "team_count": OperationMetadata(
        name="team_count",
        semantic_purpose="Show direct report count as a KPI metric bar chart",
        category="read",
        optional_args=["descendants"],
        compatible_result_blocks=["TEAM_METRIC_CHART", "DENIAL_BANNER"],
    ),
    "org_tree": OperationMetadata(
        name="org_tree",
        semantic_purpose="Render reporting hierarchy tree for authorized scope",
        category="read",
        optional_args=["descendants", "entity"],
        compatible_result_blocks=["ORG_TREE", "DENIAL_BANNER"],
    ),
    "ticket_list": OperationMetadata(
        name="ticket_list",
        semantic_purpose="Query and filter authorized support tickets",
        category="read",
        optional_args=["ticket_id", "status_filter", "priority_filter", "from_date", "to_date", "person_filter"],
        compatible_result_blocks=["TICKET_LIST", "DENIAL_BANNER"],
    ),
    "ticket_chart": OperationMetadata(
        name="ticket_chart",
        semantic_purpose="Aggregate authorized tickets into a visual chart",
        category="read",
        optional_args=["group_by", "view", "status_filter", "priority_filter", "from_date", "to_date", "sla_metric"],
        compatible_result_blocks=["TEAM_METRIC_CHART", "DENIAL_BANNER"],
    ),
    "rechart": OperationMetadata(
        name="rechart",
        semantic_purpose="Change visual representation or dimension of active ticket dataset",
        category="navigation",
        optional_args=["view", "group_by", "priority_filter", "status_filter", "filter_action"],
        requires_active_result=True,
        compatible_result_blocks=["TEAM_METRIC_CHART", "DENIAL_BANNER"],
    ),
    "back": OperationMetadata(
        name="back",
        semantic_purpose="Navigate back to previous authorized result block in conversation state",
        category="navigation",
        requires_active_result=True,
        compatible_result_blocks=["EMPLOYEE_PROFILE", "DATA_TABLE", "ORG_TREE", "TICKET_LIST", "TEAM_METRIC_CHART"],
    ),
    "clarify": OperationMetadata(
        name="clarify",
        semantic_purpose="Ask user for clarification when request is ambiguous, contradictory, or missing required parameters",
        category="clarification",
        optional_args=["entity", "unresolved_location", "value"],
        compatible_result_blocks=["PUBLIC_FAQ", "DENIAL_BANNER"],
    ),
    "create_ticket": OperationMetadata(
        name="create_ticket",
        semantic_purpose="Propose creation of a new support ticket (two-phase commit proposal)",
        category="proposal",
        required_args=["value"],  # description / title
        optional_args=["priority_filter"],
        compatible_result_blocks=["READBACK_CONFIRMATION", "DENIAL_BANNER"],
    ),
    "update_ticket": OperationMetadata(
        name="update_ticket",
        semantic_purpose="Propose modification of an existing ticket's field (status, priority, description)",
        category="proposal",
        required_args=["ticket_id", "field", "value"],
        compatible_result_blocks=["READBACK_CONFIRMATION", "DENIAL_BANNER"],
    ),
    "comment_ticket": OperationMetadata(
        name="comment_ticket",
        semantic_purpose="Propose adding a comment to an existing support ticket",
        category="proposal",
        required_args=["ticket_id", "value"],
        compatible_result_blocks=["READBACK_CONFIRMATION", "DENIAL_BANNER"],
    ),
    "confirm": OperationMetadata(
        name="confirm",
        semantic_purpose="Confirm a pending proposal with fresh spoken verification",
        category="confirmation",
        requires_active_result=True,
        compatible_result_blocks=["ACTION_RECEIPT", "DENIAL_BANNER"],
    ),
    "cancel": OperationMetadata(
        name="cancel",
        semantic_purpose="Cancel an active pending proposal or clear current proposal draft",
        category="cancellation",
        compatible_result_blocks=["PUBLIC_FAQ"],
    ),
    "compound": OperationMetadata(
        name="compound",
        semantic_purpose="Execute bounded sequence of authorized read operations (max depth 3)",
        category="compound",
        optional_args=["entity", "status_filter", "priority_filter"],
        compatible_result_blocks=["EMPLOYEE_PROFILE", "TICKET_LIST", "TEAM_METRIC_CHART"],
        notes="Writes/mutations in compound plans are strictly unsupported.",
    ),
    "headcount": OperationMetadata(
        name="headcount",
        semantic_purpose="Query authorized employee headcount across department, location, or team scope",
        category="read",
        optional_args=["scope", "location", "department", "unresolved_location"],
        compatible_result_blocks=["TEAM_METRIC_CHART", "DATA_TABLE", "PUBLIC_FAQ"],
    ),
    "update_contact": OperationMetadata(
        name="update_contact",
        semantic_purpose="Propose updating verified actor's own contact phone number (two-phase proposal)",
        category="proposal",
        required_args=["field", "value"],  # field="phone"
        optional_args=["entity"],
        compatible_result_blocks=["READBACK_CONFIRMATION", "DENIAL_BANNER"],
        notes="Policy restricts updates to self only.",
    ),
}


class OperationRegistry:
    """Registry query interface for semantic planners and validators."""

    @classmethod
    def get(cls, op_name: str) -> Optional[OperationMetadata]:
        return _SUPPORTED_OPERATIONS.get(op_name.lower().strip() if op_name else "")

    @classmethod
    def all_operations(cls) -> Dict[str, OperationMetadata]:
        return dict(_SUPPORTED_OPERATIONS)

    @classmethod
    def is_supported(cls, op_name: str) -> bool:
        return op_name.lower().strip() in _SUPPORTED_OPERATIONS

    @classmethod
    def get_by_category(cls, category: OperationCategory) -> List[OperationMetadata]:
        return [op for op in _SUPPORTED_OPERATIONS.values() if op.category == category]
