"""
IntentLock — Test Actor Contexts
Provides strictly bounded fictional test actor contexts for local downstream
render and voice testing without Detectif biometric verification.

SECURITY INVARIANT:
- Test contexts are resolved strictly server-side from allowlisted fixture IDs.
- Never accepts client-claimed roles, IDs, or claimed verification flags.
- Never mints a production session token.
- Clearly flags all contexts with test_mode=True.
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel

class TestActorContext(BaseModel):
    fixture_id: str
    employee_id: str
    full_name: str
    role: str
    department: Optional[str] = None
    team: Optional[str] = None
    scope_description: str
    permitted_employee_ids: Optional[List[str]] = None
    can_view_team: bool = False
    can_view_all: bool = False
    is_test_mode: bool = True
    security_notice: str = "Local render test — Detectif verification not run"

ALLOWLISTED_TEST_CONTEXTS: Dict[str, TestActorContext] = {
    "employee_self": TestActorContext(
        fixture_id="employee_self",
        employee_id="EMP-1001",
        full_name="Aarav Mehta",
        role="employee",
        department="Engineering",
        team="Application Engineering",
        scope_description="Employee Self Scope — Own profile, assigned projects, and public information only",
        permitted_employee_ids=["EMP-1001"],
        can_view_team=False,
        can_view_all=False,
    ),
    "manager_team": TestActorContext(
        fixture_id="manager_team",
        employee_id="EMP-2001",
        full_name="Priya Sharma",
        role="manager",
        department="Engineering",
        team="Application Engineering",
        scope_description="Engineering Manager Scope — Own profile, 5 direct reports, and team projects",
        permitted_employee_ids=["EMP-2001", "EMP-1001", "EMP-1002", "EMP-1003", "EMP-1004", "EMP-1005"],
        can_view_team=True,
        can_view_all=False,
    ),
    "executive_all": TestActorContext(
        fixture_id="executive_all",
        employee_id="EMP-4002",
        full_name="Arvind Rao (CTO)",
        role="executive",
        department="Technology",
        team="Executive Leadership",
        scope_description="Chief Technology Officer Scope — Technical team organization & aggregate metrics",
        permitted_employee_ids=None,  # All employees accessible at high level
        can_view_team=True,
        can_view_all=True,
    ),
    "anonymous_visitor": TestActorContext(
        fixture_id="anonymous_visitor",
        employee_id="",
        full_name="Anonymous Visitor",
        role="anonymous",
        department=None,
        team=None,
        scope_description="Public Visitor Scope — Zero employee data access. Public FAQs only",
        permitted_employee_ids=[],
        can_view_team=False,
        can_view_all=False,
    ),
}

def resolve_test_actor(fixture_id: Optional[str]) -> TestActorContext:
    """
    Resolve requested fixture ID to an allowlisted server-side test actor context.
    Defaults safely to employee_self if unspecified or unknown.
    """
    if not fixture_id or fixture_id not in ALLOWLISTED_TEST_CONTEXTS:
        return ALLOWLISTED_TEST_CONTEXTS["employee_self"]
    return ALLOWLISTED_TEST_CONTEXTS[fixture_id]
