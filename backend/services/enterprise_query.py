"""
IntentLock — Deterministic Enterprise Query Engine
Executes validated read queries against canonical datasets:
all_employees.json, all_tickets.json, teams.json, projects.json, departments.json.

Produces structured results matching frontend result contracts:
profile, table, chart, tree, comparison, summary, compound, clarification, not_found, proposal, error.
"""

from typing import Any, Dict, List, Literal, Optional, Tuple, Union
import copy

from backend.services.enterprise_data import EnterpriseDataRepository, normalize_text
from backend.services.entity_resolver import EntityResolver, ResolutionResult


class EnterpriseQueryEngine:
    def __init__(
        self,
        repo: Optional[EnterpriseDataRepository] = None,
        resolver: Optional[EntityResolver] = None,
    ):
        self.repo = repo or EnterpriseDataRepository.get_instance()
        self.resolver = resolver or EntityResolver(self.repo)

    # ---------------------------------------------------------
    # Employee Queries
    # ---------------------------------------------------------
    def get_employee_profile(self, employee_id: str) -> Dict[str, Any]:
        emp = self.repo.employees_by_id.get(employee_id)
        if not emp:
            return {"status": "not_found", "result_type": "not_found", "entity_type": "employee", "query": employee_id}

        mgr_id = emp.get("reporting", {}).get("manager_id")
        mgr = self.repo.employees_by_id.get(mgr_id) if mgr_id else None

        team_id = emp.get("employment", {}).get("team_id")
        team = self.repo.teams_by_id.get(team_id) if team_id else None

        dept_id = emp.get("employment", {}).get("department_id")
        dept = self.repo.departments_by_id.get(dept_id) if dept_id else None

        lead = None
        if team and team.get("team_lead_id"):
            lead = self.repo.employees_by_id.get(team["team_lead_id"])

        current_projects = []
        for prj_ref in emp.get("projects", {}).get("current", []):
            pid = prj_ref.get("project_id")
            p = self.repo.projects_by_id.get(pid)
            current_projects.append({
                "project_id": pid,
                "name": prj_ref.get("name") or (p["name"] if p else pid),
                "allocation_percent": prj_ref.get("allocation_percent", 0),
                "description": p.get("description") if p else None,
                "status": p.get("status") if p else None,
            })

        direct_reports = self.repo.employees_by_manager.get(employee_id, [])

        return {
            "status": "success",
            "result_type": "profile",
            "entity_type": "employee",
            "entity_id": employee_id,
            "data": {
                "employee_id": emp["employee_id"],
                "name": emp.get("identity", {}).get("full_name"),
                "preferred_name": emp.get("identity", {}).get("preferred_name"),
                "email": emp.get("identity", {}).get("work_email"),
                "phone": emp.get("identity", {}).get("work_phone"),
                "designation": emp.get("employment", {}).get("designation"),
                "department": dept["name"] if dept else emp.get("employment", {}).get("department"),
                "department_id": dept_id,
                "team": team["name"] if team else None,
                "team_id": team_id,
                "team_lead": lead.get("identity", {}).get("full_name") if lead else None,
                "team_lead_id": team.get("team_lead_id") if team else None,
                "manager": mgr.get("identity", {}).get("full_name") if mgr else None,
                "manager_id": mgr_id,
                "department_head": (
                    self.repo.employees_by_id.get(dept["head_id"], {}).get("identity", {}).get("full_name")
                    if dept and dept.get("head_id") else None
                ),
                "department_head_id": dept.get("head_id") if dept else None,
                "executive_owner": (
                    self.repo.employees_by_id.get(dept["executive_owner_id"], {}).get("identity", {}).get("full_name")
                    if dept and dept.get("executive_owner_id") else None
                ),
                "executive_owner_id": dept.get("executive_owner_id") if dept else None,
                "location": emp.get("employment", {}).get("location"),
                "work_mode": emp.get("employment", {}).get("work_mode"),
                "date_of_joining": emp.get("employment", {}).get("date_of_joining"),
                "skills": emp.get("skills", {}),
                "current_projects": current_projects,
                "direct_reports_count": len(direct_reports),
                "direct_reports": [
                    {"employee_id": dr["employee_id"], "name": dr.get("identity", {}).get("full_name")}
                    for dr in direct_reports
                ],
            },
            "context_updates": {
                "selected_employee_id": employee_id,
                "selected_team_id": team_id,
                "selected_department_id": dept_id,
            }
        }

    def get_employee_manager(self, employee_id: str) -> Dict[str, Any]:
        emp = self.repo.employees_by_id.get(employee_id)
        if not emp:
            return {"status": "not_found", "result_type": "not_found", "entity_type": "employee", "query": employee_id}

        mgr_id = emp.get("reporting", {}).get("manager_id")
        if not mgr_id:
            return {
                "status": "success",
                "result_type": "summary",
                "message": f"{emp.get('identity', {}).get('full_name')} does not have a reporting manager.",
                "data": {"manager": None, "manager_id": None},
                "context_updates": {"selected_employee_id": employee_id}
            }

        mgr = self.repo.employees_by_id.get(mgr_id)
        return {
            "status": "success",
            "result_type": "profile",
            "entity_type": "employee",
            "entity_id": mgr_id,
            "message": f"{emp.get('identity', {}).get('full_name')}'s manager is {mgr.get('identity', {}).get('full_name')} ({mgr_id}).",
            "data": {
                "manager_id": mgr_id,
                "manager_name": mgr.get("identity", {}).get("full_name"),
                "designation": mgr.get("employment", {}).get("designation"),
                "department": mgr.get("employment", {}).get("department"),
            },
            "context_updates": {
                "selected_employee_id": mgr_id,
                "prior_employee_id": employee_id,
            }
        }

    def get_direct_reports(self, employee_id: str) -> Dict[str, Any]:
        emp = self.repo.employees_by_id.get(employee_id)
        if not emp:
            return {"status": "not_found", "result_type": "not_found", "entity_type": "employee", "query": employee_id}

        reports = self.repo.employees_by_manager.get(employee_id, [])
        return {
            "status": "success",
            "result_type": "table",
            "title": f"Direct Reports of {emp.get('identity', {}).get('full_name')}",
            "entity_type": "employee",
            "entity_id": employee_id,
            "count": len(reports),
            "columns": ["Employee ID", "Full Name", "Designation", "Department", "Team"],
            "rows": [
                [
                    r["employee_id"],
                    r.get("identity", {}).get("full_name"),
                    r.get("employment", {}).get("designation"),
                    r.get("employment", {}).get("department"),
                    r.get("employment", {}).get("team_id") or "N/A"
                ]
                for r in reports
            ],
            "context_updates": {
                "selected_employee_id": employee_id,
                "first_report_id": reports[0]["employee_id"] if reports else None,
            }
        }

    def get_employee_projects(self, employee_id: str) -> Dict[str, Any]:
        emp = self.repo.employees_by_id.get(employee_id)
        if not emp:
            return {"status": "not_found", "result_type": "not_found", "entity_type": "employee", "query": employee_id}

        projects = []
        for prj_ref in emp.get("projects", {}).get("current", []):
            pid = prj_ref.get("project_id")
            p = self.repo.projects_by_id.get(pid)
            projects.append({
                "project_id": pid,
                "name": prj_ref.get("name") or (p["name"] if p else pid),
                "allocation_percent": prj_ref.get("allocation_percent", 0),
                "status": p.get("status") if p else "Active",
                "owning_team_id": p.get("owning_team_id") if p else None,
                "owning_department_id": p.get("owning_department_id") if p else None,
            })

        return {
            "status": "success",
            "result_type": "table",
            "title": f"Projects for {emp.get('identity', {}).get('full_name')}",
            "entity_type": "employee",
            "entity_id": employee_id,
            "count": len(projects),
            "columns": ["Project ID", "Project Name", "Allocation", "Status", "Owning Team", "Department"],
            "rows": [
                [
                    p["project_id"],
                    p["name"],
                    f"{p['allocation_percent']}%",
                    p["status"],
                    p["owning_team_id"] or "N/A",
                    p["owning_department_id"] or "N/A"
                ]
                for p in projects
            ],
            "context_updates": {
                "selected_employee_id": employee_id,
                "selected_project_id": projects[0]["project_id"] if projects else None,
            }
        }

    # ---------------------------------------------------------
    # Team Queries
    # ---------------------------------------------------------
    def get_team_profile(self, team_id: str) -> Dict[str, Any]:
        team = self.repo.teams_by_id.get(team_id)
        if not team:
            return {"status": "not_found", "result_type": "not_found", "entity_type": "team", "query": team_id}

        lead = self.repo.employees_by_id.get(team.get("team_lead_id")) if team.get("team_lead_id") else None
        mgr = self.repo.employees_by_id.get(team.get("manager_id")) if team.get("manager_id") else None
        dept = self.repo.departments_by_id.get(team.get("department_id")) if team.get("department_id") else None

        members = [self.repo.employees_by_id[m] for m in team.get("member_ids", []) if m in self.repo.employees_by_id]
        projects = [self.repo.projects_by_id[p] for p in team.get("project_ids", []) if p in self.repo.projects_by_id]

        return {
            "status": "success",
            "result_type": "profile",
            "entity_type": "team",
            "entity_id": team_id,
            "data": {
                "team_id": team_id,
                "name": team["name"],
                "department": dept["name"] if dept else team.get("department"),
                "department_id": team.get("department_id"),
                "lead": lead.get("identity", {}).get("full_name") if lead else None,
                "lead_id": team.get("team_lead_id"),
                "manager": mgr.get("identity", {}).get("full_name") if mgr else None,
                "manager_id": team.get("manager_id"),
                "headcount": len(members),
                "members": [
                    {"employee_id": m["employee_id"], "name": m.get("identity", {}).get("full_name"), "designation": m.get("employment", {}).get("designation")}
                    for m in members
                ],
                "projects": [
                    {"project_id": p["project_id"], "name": p["name"], "status": p.get("status")}
                    for p in projects
                ],
            },
            "context_updates": {
                "selected_team_id": team_id,
                "selected_department_id": team.get("department_id"),
            }
        }

    # ---------------------------------------------------------
    # Department Queries
    # ---------------------------------------------------------
    def get_department_profile(self, department_id: str) -> Dict[str, Any]:
        dept = self.repo.departments_by_id.get(department_id)
        if not dept:
            return {"status": "not_found", "result_type": "not_found", "entity_type": "department", "query": department_id}

        head = self.repo.employees_by_id.get(dept.get("head_id")) if dept.get("head_id") else None
        exec_owner = self.repo.employees_by_id.get(dept.get("executive_owner_id")) if dept.get("executive_owner_id") else None

        teams = [self.repo.teams_by_id[t] for t in dept.get("team_ids", []) if t in self.repo.teams_by_id]
        members = [self.repo.employees_by_id[m] for m in dept.get("member_ids", []) if m in self.repo.employees_by_id]
        owned_prjs = [p for p in self.repo.projects if p.get("owning_department_id") == department_id and p.get("status") == "Active"]
        tickets = [t for t in self.repo.tickets if t.get("department_id") == department_id]
        open_tickets = [t for t in tickets if t.get("status") in ["Open", "In Progress"]]

        return {
            "status": "success",
            "result_type": "profile",
            "entity_type": "department",
            "entity_id": department_id,
            "data": {
                "department_id": department_id,
                "name": dept["name"],
                "aliases": dept.get("aliases", []),
                "description": dept.get("description"),
                "status": dept.get("status"),
                "department_type": dept.get("department_type"),
                "head": head.get("identity", {}).get("full_name") if head else None,
                "head_id": dept.get("head_id"),
                "executive_owner": exec_owner.get("identity", {}).get("full_name") if exec_owner else None,
                "executive_owner_id": dept.get("executive_owner_id"),
                "headcount": len(members),
                "teams_count": len(teams),
                "teams": [{"team_id": t["team_id"], "name": t["name"]} for t in teams],
                "active_projects_count": len(owned_prjs),
                "active_projects": [{"project_id": p["project_id"], "name": p["name"]} for p in owned_prjs],
                "total_tickets_count": len(tickets),
                "open_tickets_count": len(open_tickets),
            },
            "context_updates": {
                "selected_department_id": department_id,
            }
        }

    # ---------------------------------------------------------
    # Project Queries
    # ---------------------------------------------------------
    def get_project_profile(self, project_id: str) -> Dict[str, Any]:
        prj = self.repo.projects_by_id.get(project_id)
        if not prj:
            return {"status": "not_found", "result_type": "not_found", "entity_type": "project", "query": project_id}

        own_team = self.repo.teams_by_id.get(prj.get("owning_team_id"))
        own_dept = self.repo.departments_by_id.get(prj.get("owning_department_id"))
        mgr = self.repo.employees_by_id.get(prj.get("project_manager_id")) if prj.get("project_manager_id") else None
        lead = self.repo.employees_by_id.get(prj.get("project_lead_id")) if prj.get("project_lead_id") else None

        members = [self.repo.employees_by_id[m] for m in prj.get("member_ids", []) if m in self.repo.employees_by_id]
        tickets = [t for t in self.repo.tickets if t.get("project_id") == project_id]
        open_tickets = [t for t in tickets if t.get("status") in ["Open", "In Progress"]]

        return {
            "status": "success",
            "result_type": "profile",
            "entity_type": "project",
            "entity_id": project_id,
            "data": {
                "project_id": project_id,
                "name": prj["name"],
                "aliases": prj.get("aliases", []),
                "description": prj.get("description"),
                "status": prj.get("status"),
                "project_type": prj.get("project_type"),
                "owning_team": own_team["name"] if own_team else prj.get("owning_team_id"),
                "owning_team_id": prj.get("owning_team_id"),
                "owning_department": own_dept["name"] if own_dept else prj.get("owning_department_id"),
                "owning_department_id": prj.get("owning_department_id"),
                "contributing_department_ids": prj.get("contributing_department_ids", []),
                "project_manager": mgr.get("identity", {}).get("full_name") if mgr else None,
                "project_manager_id": prj.get("project_manager_id"),
                "project_lead": lead.get("identity", {}).get("full_name") if lead else None,
                "project_lead_id": prj.get("project_lead_id"),
                "member_count": len(members),
                "members": [
                    {"employee_id": m["employee_id"], "name": m.get("identity", {}).get("full_name")}
                    for m in members
                ],
                "technologies": prj.get("technologies", []),
                "total_tickets_count": len(tickets),
                "open_tickets_count": len(open_tickets),
            },
            "context_updates": {
                "selected_project_id": project_id,
                "selected_team_id": prj.get("owning_team_id"),
                "selected_department_id": prj.get("owning_department_id"),
            }
        }

    # ---------------------------------------------------------
    # Ticket Queries & Filtering
    # ---------------------------------------------------------
    def get_tickets(
        self,
        assignee_id: Optional[str] = None,
        project_id: Optional[str] = None,
        department_id: Optional[str] = None,
        status_filter: Optional[Union[str, List[str]]] = None,
        priority_filter: Optional[Union[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        tickets = list(self.repo.tickets)

        if assignee_id:
            tickets = [t for t in tickets if t.get("assignee_id") == assignee_id]
        if project_id:
            tickets = [t for t in tickets if t.get("project_id") == project_id]
        if department_id:
            tickets = [t for t in tickets if t.get("department_id") == department_id]

        if status_filter:
            if isinstance(status_filter, str):
                if status_filter == "Open":
                    tickets = [t for t in tickets if t.get("status") in ["Open", "In Progress"]]
                elif status_filter == "Closed":
                    tickets = [t for t in tickets if t.get("status") in ["Closed", "Resolved"]]
                else:
                    tickets = [t for t in tickets if t.get("status") == status_filter]
            elif isinstance(status_filter, list):
                tickets = [t for t in tickets if t.get("status") in status_filter]

        if priority_filter:
            if isinstance(priority_filter, str):
                if priority_filter in ["Critical", "High", "Medium", "Low"]:
                    tickets = [t for t in tickets if t.get("priority") == priority_filter]
                elif priority_filter == "Urgent":
                    tickets = [t for t in tickets if t.get("priority") in ["Critical", "High"]]
            elif isinstance(priority_filter, list):
                tickets = [t for t in tickets if t.get("priority") in priority_filter]

        rows = [
            [
                t["ticket_id"],
                t["title"],
                t.get("status"),
                t.get("priority"),
                t.get("project_id") or "N/A",
                t.get("assignee_id") or "N/A"
            ]
            for t in tickets
        ]

        title = "Tickets"
        if assignee_id:
            emp = self.repo.employees_by_id.get(assignee_id)
            title += f" for {emp.get('identity', {}).get('full_name') if emp else assignee_id}"
        elif project_id:
            prj = self.repo.projects_by_id.get(project_id)
            title += f" for {prj.get('name') if prj else project_id}"
        elif department_id:
            dept = self.repo.departments_by_id.get(department_id)
            title += f" for {dept.get('name') if dept else department_id}"

        return {
            "status": "success",
            "result_type": "table",
            "title": title,
            "count": len(tickets),
            "columns": ["Ticket ID", "Title", "Status", "Priority", "Project", "Assignee"],
            "rows": rows,
            "context_updates": {
                "selected_ticket_id": tickets[0]["ticket_id"] if len(tickets) == 1 else None,
                "visible_ticket_ids": [t["ticket_id"] for t in tickets],
                "last_filters": {
                    "assignee_id": assignee_id,
                    "project_id": project_id,
                    "department_id": department_id,
                    "status_filter": status_filter,
                    "priority_filter": priority_filter,
                }
            }
        }

    # ---------------------------------------------------------
    # Aggregations & Metrics
    # ---------------------------------------------------------
    def get_aggregations(self, metric: str) -> Dict[str, Any]:
        if metric == "department_headcount_max":
            sorted_depts = sorted(self.repo.departments, key=lambda d: len(d.get("member_ids", [])), reverse=True)
            top = sorted_depts[0]
            return {
                "status": "success",
                "result_type": "summary",
                "entity_type": "department",
                "entity_id": top["department_id"],
                "data": {"department_id": top["department_id"], "name": top["name"], "headcount": len(top.get("member_ids", []))},
                "message": f"The department with the most employees is {top['name']} ({top['department_id']}) with {len(top.get('member_ids', []))} employees."
            }

        elif metric == "department_active_projects_max":
            counts = {}
            for p in self.repo.projects:
                if p.get("status") == "Active":
                    did = p.get("owning_department_id")
                    if did:
                        counts[did] = counts.get(did, 0) + 1
            top_did, count = max(counts.items(), key=lambda x: x[1])
            dept = self.repo.departments_by_id[top_did]
            return {
                "status": "success",
                "result_type": "summary",
                "entity_type": "department",
                "entity_id": top_did,
                "data": {"department_id": top_did, "name": dept["name"], "active_projects": count},
                "message": f"The department with the most active projects is {dept['name']} ({top_did}) with {count} active projects."
            }

        elif metric == "department_open_tickets_max":
            counts = {}
            for t in self.repo.tickets:
                if t.get("status") in ["Open", "In Progress"]:
                    did = t.get("department_id")
                    if did:
                        counts[did] = counts.get(did, 0) + 1
            top_did, count = max(counts.items(), key=lambda x: x[1])
            dept = self.repo.departments_by_id[top_did]
            return {
                "status": "success",
                "result_type": "summary",
                "entity_type": "department",
                "entity_id": top_did,
                "data": {"department_id": top_did, "name": dept["name"], "open_tickets": count},
                "message": f"The department with the most open tickets is {dept['name']} ({top_did}) with {count} open or in-progress tickets."
            }

        elif metric == "chart_employees_by_department":
            labels = [d["name"] for d in self.repo.departments]
            values = [len(d.get("member_ids", [])) for d in self.repo.departments]
            return {
                "status": "success",
                "result_type": "chart",
                "chart_type": "bar",
                "title": "Employees by Department",
                "labels": labels,
                "values": values,
            }

        return {"status": "error", "message": f"Unknown aggregation metric: {metric}"}

    # ---------------------------------------------------------
    # Comparison
    # ---------------------------------------------------------
    def compare_entities(self, entity_type: str, id_a: str, id_b: str) -> Dict[str, Any]:
        if entity_type == "department":
            d_a = self.get_department_profile(id_a)
            d_b = self.get_department_profile(id_b)
            return {
                "status": "success",
                "result_type": "comparison",
                "entity_type": "department",
                "entities": [d_a.get("data"), d_b.get("data")],
                "metrics": {
                    d_a.get("data", {}).get("name", id_a): {
                        "headcount": d_a.get("data", {}).get("headcount"),
                        "active_projects": d_a.get("data", {}).get("active_projects_count"),
                        "open_tickets": d_a.get("data", {}).get("open_tickets_count"),
                    },
                    d_b.get("data", {}).get("name", id_b): {
                        "headcount": d_b.get("data", {}).get("headcount"),
                        "active_projects": d_b.get("data", {}).get("active_projects_count"),
                        "open_tickets": d_b.get("data", {}).get("open_tickets_count"),
                    }
                }
            }
        elif entity_type == "project":
            p_a = self.get_project_profile(id_a)
            p_b = self.get_project_profile(id_b)
            return {
                "status": "success",
                "result_type": "comparison",
                "entity_type": "project",
                "entities": [p_a.get("data"), p_b.get("data")],
                "metrics": {
                    p_a.get("data", {}).get("name", id_a): {
                        "member_count": p_a.get("data", {}).get("member_count"),
                        "open_tickets": p_a.get("data", {}).get("open_tickets_count"),
                    },
                    p_b.get("data", {}).get("name", id_b): {
                        "member_count": p_b.get("data", {}).get("member_count"),
                        "open_tickets": p_b.get("data", {}).get("open_tickets_count"),
                    }
                }
            }
        return {"status": "error", "message": f"Unsupported comparison for entity type: {entity_type}"}

    # ---------------------------------------------------------
    # Organizational Tree
    # ---------------------------------------------------------
    def get_reporting_tree(self, root_employee_id: str) -> Dict[str, Any]:
        root = self.repo.employees_by_id.get(root_employee_id)
        if not root:
            return {"status": "not_found", "result_type": "not_found", "entity_type": "employee", "query": root_employee_id}

        def build_node(eid: str) -> Dict[str, Any]:
            emp = self.repo.employees_by_id[eid]
            node = {
                "id": eid,
                "label": emp.get("identity", {}).get("full_name"),
                "designation": emp.get("employment", {}).get("designation"),
                "department": emp.get("employment", {}).get("department"),
                "children": []
            }
            for rep in self.repo.employees_by_manager.get(eid, []):
                node["children"].append(build_node(rep["employee_id"]))
            return node

        tree = build_node(root_employee_id)
        return {
            "status": "success",
            "result_type": "tree",
            "title": f"Reporting Structure under {root.get('identity', {}).get('full_name')}",
            "entity_id": root_employee_id,
            "root": tree,
        }

    # ---------------------------------------------------------
    # Write Request Proposal Builder (No direct mutation!)
    # ---------------------------------------------------------
    def create_write_proposal(self, intent: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Creates a typed action proposal for Person 1's authorization & execution pipeline."""
        return {
            "status": "proposal_created",
            "result_type": "proposal",
            "intent": intent,
            "action_proposal": params,
            "requires_authorization": True,
            "message": f"Typed action proposal created for '{intent}'. Awaiting authorization."
        }


enterprise_engine = EnterpriseQueryEngine()
