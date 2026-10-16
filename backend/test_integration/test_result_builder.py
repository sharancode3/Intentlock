"""
IntentLock — Test Result Builder
Maps user query, resolved TestActorContext, and scoped canonical employee data
into strongly typed ResultBlock envelopes matching frontend contracts.

Supported Result Types:
- EMPLOYEE_PROFILE: Single employee details and active projects.
- TEAM_METRIC_CHART: Headcount / role distribution / department aggregate metrics.
- DENIAL_BANNER: Explicit policy rejection when query exceeds actor's permitted scope.
- PUBLIC_FAQ: General corporate FAQ and assistance grounding.
"""

from typing import Dict, Any, List, Optional
import datetime
from backend.test_integration.test_actor_contexts import TestActorContext

def build_result_block_for_query(
    query: str,
    actor: TestActorContext,
    retrieved_employees: List[Dict[str, Any]],
    answer_text: str,
    is_denied: bool = False,
    denial_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build a typed ResultBlock matching the frontend registry contracts.
    """
    now_str = datetime.datetime.now().strftime("%I:%M %p")

    # 1. Scope Denial Path
    if is_denied or actor.role == "anonymous" and any(w in query.lower() for w in ["employee", "salary", "who is", "profile", "report", "project"]):
        return {
            "id": f"blk-denial-{int(datetime.datetime.now().timestamp())}",
            "type": "DENIAL_BANNER",
            "title": "Access Denied by IntentLock Policy",
            "timestamp": now_str,
            "isSensitive": False,
            "payload": {
                "message": (
                    denial_reason
                    or f"Access to private employee data is restricted for your test scope ({actor.full_name})."
                ),
                "code": "INSUFFICIENT_SCOPE",
                "reason": f"Active test profile is bound to: {actor.scope_description}",
                "next_step": "Switch test profile to a Manager or Executive context using the top test selector.",
            },
        }

    q_lower = query.lower()

    # 2. Aggregate / Headcount / Chart Request
    if any(k in q_lower for k in ["how many", "count", "headcount", "distribution", "breakdown", "statistics", "chart"]):
        # Compute real deterministic counts from retrieved records
        role_counts: Dict[str, int] = {}
        for emp in retrieved_employees:
            r = emp.get("employment", {}).get("designation", "Staff")
            role_counts[r] = role_counts.get(r, 0) + 1

        chart_data = [{"name": role, "value": count} for role, count in role_counts.items()]
        chart_type = "PIE" if "distribution" in q_lower or "pie" in q_lower else "BAR"

        return {
            "id": f"blk-chart-{int(datetime.datetime.now().timestamp())}",
            "type": "TEAM_METRIC_CHART",
            "title": "Scoped Team Personnel Breakdown",
            "timestamp": now_str,
            "isSensitive": True,
            "payload": {
                "chart_type": chart_type,
                "title": f"Headcount for {actor.department or 'Organization'} ({len(retrieved_employees)} Members)",
                "unit": "members",
                "team_id": actor.team or "ENG_TEAM_A",
                "time_range": "Current Org Hierarchy",
                "kpis": {
                    "total_tickets": len(retrieved_employees),
                    "open_tickets": sum(1 for e in retrieved_employees if e.get("employment", {}).get("employment_type") == "Full-time"),
                    "resolved_tickets": 0,
                    "avg_resolution_time": "Real-time sync",
                    "sla_compliance_pct": 100.0,
                },
                "data": chart_data if chart_data else [{"name": "Scoped Members", "value": len(retrieved_employees)}],
            },
        }

    # 3. Single Employee Profile Path
    if retrieved_employees and len(retrieved_employees) >= 1:
        emp = retrieved_employees[0]
        # Extract active projects list
        current_projs = emp.get("projects", {}).get("current", [])
        proj_names: List[str] = []
        for p in current_projs:
            if isinstance(p, dict):
                p_name = p.get("name") or p.get("title") or "Internal Initiative"
                if p.get("role"):
                    p_name += f" ({p['role']})"
                proj_names.append(p_name)
            elif isinstance(p, str):
                proj_names.append(p)

        return {
            "id": f"blk-profile-{emp.get('employee_id', 'unknown')}",
            "type": "EMPLOYEE_PROFILE",
            "title": f"Employee Profile: {emp.get('identity', {}).get('full_name', 'Employee')}",
            "timestamp": now_str,
            "isSensitive": True,
            "payload": {
                "employee": {
                    "id": emp.get("employee_id", "EMP-0000"),
                    "name": emp.get("identity", {}).get("full_name", "Unknown Name"),
                    "role": emp.get("employment", {}).get("designation", "Employee"),
                    "department": emp.get("employment", {}).get("department", "General"),
                    "team": emp.get("employment", {}).get("work_arrangement", "Hybrid"),
                    "email": emp.get("identity", {}).get("email", ""),
                    "active_projects": proj_names if proj_names else ["Core Operations & Development"],
                    "status": emp.get("employment", {}).get("employment_type", "Active Full-time"),
                }
            },
        }

    # 4. Default Grounded Public FAQ
    return {
        "id": f"blk-faq-{int(datetime.datetime.now().timestamp())}",
        "type": "PUBLIC_FAQ",
        "title": "IntentLock Grounded Company Information",
        "timestamp": now_str,
        "isSensitive": False,
        "payload": {
            "question": query,
            "answer": answer_text,
            "category": "Corporate Helpdesk Knowledge",
            "source_document": "IntentLock_Canonical_Dataset.json",
        },
    }
