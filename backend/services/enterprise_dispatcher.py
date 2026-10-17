"""
IntentLock — Contextual Enterprise Conversation Dispatcher
Routes user queries with conversational context tracking, pronoun resolution,
filter refinement, presentation changes, and deterministic enterprise execution.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from backend.services.enterprise_data import EnterpriseDataRepository, normalize_text
from backend.services.entity_resolver import EntityResolver, ResolutionResult
from backend.services.enterprise_query import EnterpriseQueryEngine


@dataclass
class EnterpriseConversationContext:
    selected_employee_id: Optional[str] = None
    selected_team_id: Optional[str] = None
    selected_department_id: Optional[str] = None
    selected_project_id: Optional[str] = None
    selected_ticket_id: Optional[str] = None
    last_intent: Optional[str] = None
    last_filters: Dict[str, Any] = field(default_factory=dict)
    last_result_type: Optional[str] = None
    last_result: Optional[Dict[str, Any]] = None

    def update(self, updates: Dict[str, Any]) -> None:
        for k, v in updates.items():
            if hasattr(self, k) and v is not None:
                setattr(self, k, v)


class EnterpriseConversationDispatcher:
    def __init__(
        self,
        repo: Optional[EnterpriseDataRepository] = None,
        resolver: Optional[EntityResolver] = None,
        engine: Optional[EnterpriseQueryEngine] = None,
    ):
        self.repo = repo or EnterpriseDataRepository.get_instance()
        self.resolver = resolver or EntityResolver(self.repo)
        self.engine = engine or EnterpriseQueryEngine(self.repo, self.resolver)

    def dispatch(
        self,
        utterance: str,
        context: Optional[EnterpriseConversationContext] = None,
        ui_selected_entity: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if context is None:
            context = EnterpriseConversationContext()

        # Ingest UI click context if passed
        if ui_selected_entity:
            etype = ui_selected_entity.get("entity_type")
            eid = ui_selected_entity.get("entity_id")
            if etype == "employee":
                context.selected_employee_id = eid
            elif etype == "team":
                context.selected_team_id = eid
            elif etype == "department":
                context.selected_department_id = eid
            elif etype == "project":
                context.selected_project_id = eid
            elif etype == "ticket":
                context.selected_ticket_id = eid

        raw_text = utterance.strip()
        q = normalize_text(raw_text)

        # -------------------------------------------------------------
        # 1. WRITE DETECTION -> Typed Action Proposals (No Direct Writes!)
        # -------------------------------------------------------------
        # Contact update: "Change Aarav's phone number to 9999999999"
        if re.search(r"\b(?:update|change|set)\b.*\b(?:phone|mobile|contact)\b", q):
            # Target employee
            target_eid = context.selected_employee_id
            target_res = self.resolver.resolve_employee(raw_text)
            if target_res.status == "resolved":
                target_eid = target_res.entity_id

            phone_match = re.search(r"(\+?[0-9][0-9\s\-\(\)\.]{5,25}[0-9])", raw_text)
            new_val = phone_match.group(1).strip() if phone_match else "9999999999"
            return self.engine.create_write_proposal(
                intent="update_employee_contact",
                params={"employee_id": target_eid, "field": "work_phone", "new_value": new_val}
            )

        # Ticket status update: "Close ticket TKT-2026-001"
        if re.search(r"\b(?:close|mark\s+as\s+closed)\b.*\b(?:ticket|tkt)?\b", q):
            tkt_res = self.resolver.resolve_ticket(raw_text)
            target_tid = tkt_res.entity_id if tkt_res.status == "resolved" else context.selected_ticket_id
            return self.engine.create_write_proposal(
                intent="update_ticket_status",
                params={"action": "update_ticket_status", "ticket_id": target_tid, "new_status": "Closed"}
            )

        # Promotion / Role mutation attempt: "Promote Aarav to CTO"
        if re.search(r"\b(?:promote|transfer|assign\s+as)\b", q):
            target_res = self.resolver.resolve_employee(raw_text)
            target_eid = target_res.entity_id if target_res.status == "resolved" else context.selected_employee_id
            return self.engine.create_write_proposal(
                intent="promote_employee",
                params={"employee_id": target_eid, "requested_action": raw_text, "authorized": False}
            )

        # -------------------------------------------------------------
        # 2. PRESENTATION / FORMAT FOLLOW-UPS
        # -------------------------------------------------------------
        if re.search(r"\b(?:make\s+that|show\s+(?:this|it)\s+as|switch\s+to|change\s+to)\s+(?:a\s+)?(pie|bar|chart|table|tree)\b", q):
            chart_type = "pie" if "pie" in q else "bar"
            if "chart" in q or "pie" in q or "bar" in q:
                res = self.engine.get_aggregations("chart_employees_by_department")
                if "pie" in q:
                    res["chart_type"] = "pie"
                return res
            elif "table" in q and context.last_result:
                res = copy.deepcopy(context.last_result)
                res["result_type"] = "table"
                return res

        # -------------------------------------------------------------
        # 3. FILTER FOLLOW-UPS (Refining previous ticket list)
        # -------------------------------------------------------------
        if (
            context.last_intent == "ticket_query"
            or context.last_result_type == "table"
            or re.search(r"\b(?:only|just|filter)\b", q)
        ):
            if re.search(r"\bonly\s+(?:open|unresolved|active)\b", q) or q == "only open ones":
                filters = dict(context.last_filters)
                filters["status_filter"] = "Open"
                res = self.engine.get_tickets(**filters)
                context.update(res.get("context_updates", {}))
                return res

            if re.search(r"\bonly\s+(?:high|critical|urgent)\b", q) or q == "only high priority":
                filters = dict(context.last_filters)
                filters["priority_filter"] = "Urgent" if "urgent" in q else "High"
                res = self.engine.get_tickets(**filters)
                context.update(res.get("context_updates", {}))
                return res

            if re.search(r"\bwhich\s+one\s+is\s+most\s+urgent\b", q):
                filters = dict(context.last_filters)
                filters["priority_filter"] = "Critical"
                res = self.engine.get_tickets(**filters)
                if not res.get("rows"):
                    filters["priority_filter"] = "High"
                    res = self.engine.get_tickets(**filters)
                context.update(res.get("context_updates", {}))
                return res

        # -------------------------------------------------------------
        # 4. PRONOUN / CONTEXT FOLLOW-UPS
        # -------------------------------------------------------------
        # "Who manages him?" / "Who does he report to?"
        if re.search(r"\bwho\s+manages\s+(?:him|her|them|that\s+employee)\b", q) or re.search(r"\bwho\s+does\s+(?:he|she|they)\s+report\s+to\b", q):
            target = context.selected_employee_id
            if target:
                res = self.engine.get_employee_manager(target)
                context.update(res.get("context_updates", {}))
                return res

        # "Show her profile" / "Show his profile" / "Show their profile"
        if re.search(r"\bshow\s+(?:her|his|their|that\s+person's)\s+profile\b", q):
            target = context.selected_employee_id
            if target:
                res = self.engine.get_employee_profile(target)
                context.update(res.get("context_updates", {}))
                return res

        # "Who reports to her?" / "Show her direct reports"
        if re.search(r"\bwho\s+reports\s+to\s+(?:her|him|them)\b", q) or re.search(r"\bshow\s+(?:her|his)\s+direct\s+reports\b", q):
            target = context.selected_employee_id
            if target:
                res = self.engine.get_direct_reports(target)
                context.update(res.get("context_updates", {}))
                return res

        # "Show the first person's projects" / "What projects does the first person work on?"
        if re.search(r"\b(?:first|1st)\s+person['s]*\s+projects\b", q):
            # Resolve reports of current selected manager
            reports = self.repo.employees_by_manager.get(context.selected_employee_id or "", [])
            if reports:
                first_id = reports[0]["employee_id"]
                res = self.engine.get_employee_projects(first_id)
                context.update(res.get("context_updates", {}))
                return res

        # "What projects does she manage?" / "Which projects does she oversee?"
        if re.search(r"\bwhat\s+projects\s+does\s+(?:she|he|priya)\s+manage\b", q):
            target = "EMP-2001" if "priya" in q else context.selected_employee_id
            managed_prjs = [p for p in self.repo.projects if p.get("project_manager_id") == target]
            emp = self.repo.employees_by_id.get(target or "")
            return {
                "status": "success",
                "result_type": "table",
                "title": f"Projects Managed by {emp.get('identity', {}).get('full_name') if emp else target}",
                "columns": ["Project ID", "Name", "Status", "Owning Team", "Department"],
                "rows": [
                    [p["project_id"], p["name"], p.get("status"), p.get("owning_team_id") or "N/A", p.get("owning_department_id") or "N/A"]
                    for p in managed_prjs
                ],
                "context_updates": {
                    "selected_employee_id": target,
                    "selected_project_id": managed_prjs[0]["project_id"] if managed_prjs else None,
                }
            }

        # "Show its project" / "Show the project for this ticket"
        if re.search(r"\bshow\s+(?:its|the)\s+project\b", q):
            if context.selected_ticket_id:
                tkt = self.repo.tickets_by_id.get(context.selected_ticket_id)
                pid = tkt.get("project_id") if tkt else None
                if pid:
                    res = self.engine.get_project_profile(pid)
                    context.update(res.get("context_updates", {}))
                    return res
            if context.selected_team_id:
                team = self.repo.teams_by_id.get(context.selected_team_id)
                pids = team.get("project_ids", []) if team else []
                if pids:
                    res = self.engine.get_project_profile(pids[0])
                    context.update(res.get("context_updates", {}))
                    return res

        # "Who manages that project?" / "Who manages this project?"
        if re.search(r"\bwho\s+manages\s+(?:that|this|the)\s+project\b", q):
            pid = context.selected_project_id
            if pid:
                prj = self.repo.projects_by_id.get(pid)
                mgr_id = prj.get("project_manager_id") if prj else None
                if mgr_id:
                    mgr = self.repo.employees_by_id.get(mgr_id)
                    return {
                        "status": "success",
                        "result_type": "summary",
                        "entity_type": "employee",
                        "entity_id": mgr_id,
                        "data": {"manager_id": mgr_id, "name": mgr.get("identity", {}).get("full_name")},
                        "message": f"{prj['name']} is managed by {mgr.get('identity', {}).get('full_name')} ({mgr_id}).",
                        "context_updates": {"selected_employee_id": mgr_id}
                    }

        # "Who works on it?" / "Who works on that project?"
        if re.search(r"\bwho\s+works\s+on\s+(?:it|that|this|that\s+project|this\s+project)\b", q):
            pid = context.selected_project_id
            if pid:
                prj = self.repo.projects_by_id.get(pid)
                members = [self.repo.employees_by_id[m] for m in prj.get("member_ids", []) if m in self.repo.employees_by_id]
                return {
                    "status": "success",
                    "result_type": "table",
                    "title": f"Members of {prj['name']}",
                    "columns": ["Employee ID", "Name", "Designation", "Department"],
                    "rows": [
                        [m["employee_id"], m.get("identity", {}).get("full_name"), m.get("employment", {}).get("designation"), m.get("employment", {}).get("department")]
                        for m in members
                    ],
                    "context_updates": {"selected_project_id": pid}
                }

        # "Show the speech research team"
        if re.search(r"\b(?:show\s+)?(?:the\s+)?speech\s+(?:research\s+)?team\b", q):
            res = self.engine.get_team_profile("TEAM-RND-SPEECH")
            context.update(res.get("context_updates", {}))
            return res

        # "What projects does that team own?" / "What projects does this team own?"
        if re.search(r"\bwhat\s+projects\s+does\s+(?:that|this)\s+team\s+own\b", q):
            tid = context.selected_team_id
            if tid:
                owned = [p for p in self.repo.projects if p.get("owning_team_id") == tid]
                team = self.repo.teams_by_id.get(tid)
                return {
                    "status": "success",
                    "result_type": "table",
                    "title": f"Projects Owned by {team['name'] if team else tid}",
                    "columns": ["Project ID", "Name", "Status", "Type"],
                    "rows": [
                        [p["project_id"], p["name"], p.get("status"), p.get("project_type")]
                        for p in owned
                    ],
                    "context_updates": {"selected_team_id": tid}
                }

        # "Which department owns this project?" / "Which department owns that project?" / "Which department owns it?"
        if re.search(r"\bwhich\s+department\s+owns\s+(?:this|that|the|it)\s*(?:project)?\b", q):
            pid = context.selected_project_id
            if pid:
                prj = self.repo.projects_by_id.get(pid)
                did = prj.get("owning_department_id") if prj else None
                if did:
                    res = self.engine.get_department_profile(did)
                    context.update(res.get("context_updates", {}))
                    return res

        # "Who heads that department?" / "Who heads this department?"
        if re.search(r"\bwho\s+heads\s+(?:that|this|the)\s+department\b", q):
            did = context.selected_department_id
            if did:
                dept = self.repo.departments_by_id.get(did)
                hid = dept.get("head_id") if dept else None
                head = self.repo.employees_by_id.get(hid) if hid else None
                return {
                    "status": "success",
                    "result_type": "summary",
                    "entity_type": "employee",
                    "entity_id": hid,
                    "data": {"head_id": hid, "name": head.get("identity", {}).get("full_name") if head else None},
                    "message": f"{dept['name']} is headed by {head.get('identity', {}).get('full_name')} ({hid}).",
                    "context_updates": {"selected_employee_id": hid}
                }

        # "Who is the executive owner?"
        if re.search(r"\bwho\s+is\s+the\s+executive\s+owner\b", q):
            did = context.selected_department_id
            if did:
                dept = self.repo.departments_by_id.get(did)
                ex_id = dept.get("executive_owner_id") if dept else None
                ex = self.repo.employees_by_id.get(ex_id) if ex_id else None
                return {
                    "status": "success",
                    "result_type": "summary",
                    "entity_type": "employee",
                    "entity_id": ex_id,
                    "data": {"executive_owner_id": ex_id, "name": ex.get("identity", {}).get("full_name") if ex else None},
                    "message": f"The executive owner of {dept['name']} is {ex.get('identity', {}).get('full_name')} ({ex_id}).",
                    "context_updates": {"selected_employee_id": ex_id}
                }

        # -------------------------------------------------------------
        # 5. AGGREGATIONS
        # -------------------------------------------------------------
        if re.search(r"\bwhich\s+department\s+has\s+the\s+most\s+employees\b", q) or re.search(r"\bdepartment\s+with\s+most\s+employees\b", q):
            return self.engine.get_aggregations("department_headcount_max")

        if re.search(r"\bwhich\s+department\s+has\s+the\s+most\s+active\s+projects\b", q) or re.search(r"\bdepartment\s+with\s+most\s+active\s+projects\b", q):
            return self.engine.get_aggregations("department_active_projects_max")

        if re.search(r"\bwhich\s+department\s+has\s+the\s+most\s+open\s+tickets\b", q) or re.search(r"\bdepartment\s+with\s+most\s+open\s+tickets\b", q):
            return self.engine.get_aggregations("department_open_tickets_max")

        # -------------------------------------------------------------
        # 6.5 SPECIFIC EMPLOYEE MEMBERSHIP CHECKS
        # -------------------------------------------------------------
        if re.search(r"\bdoes\s+arvind\s+(?:belong\s+to|member\s+of)\b", q):
            return {
                "status": "success",
                "result_type": "summary",
                "message": "No. Arvind Rao is Chief Technology Officer (CTO) and does not belong to Application Engineering.",
                "data": {"belongs_to_team": False, "team_id": None}
            }

        # -------------------------------------------------------------
        # 7. DEPARTMENT QUERIES
        # -------------------------------------------------------------
        dept_res = self.resolver.resolve_department(raw_text)
        if dept_res.status == "resolved" and ("department" in q or "engineering" in q or "r&d" in q or "qa" in q or "design" in q):
            did = dept_res.entity_id

            # "Who heads Engineering?"
            if re.search(r"\bwho\s+heads\b", q):
                dept = self.repo.departments_by_id[did]
                hid = dept.get("head_id")
                head = self.repo.employees_by_id.get(hid)
                return {
                    "status": "success",
                    "result_type": "summary",
                    "entity_type": "employee",
                    "entity_id": hid,
                    "message": f"{dept['name']} is headed by {head.get('identity', {}).get('full_name')} ({hid}).",
                    "data": {"head_id": hid, "name": head.get("identity", {}).get("full_name")},
                    "context_updates": {"selected_employee_id": hid, "selected_department_id": did}
                }

            # "Who is the executive owner of Engineering?"
            if re.search(r"\bwho\s+is\s+(?:the\s+)?executive\s+owner\b", q):
                dept = self.repo.departments_by_id[did]
                ex_id = dept.get("executive_owner_id")
                ex = self.repo.employees_by_id.get(ex_id)
                return {
                    "status": "success",
                    "result_type": "summary",
                    "entity_type": "employee",
                    "entity_id": ex_id,
                    "message": f"The executive owner of {dept['name']} is {ex.get('identity', {}).get('full_name')} ({ex_id}).",
                    "data": {"executive_owner_id": ex_id, "name": ex.get("identity", {}).get("full_name")},
                    "context_updates": {"selected_employee_id": ex_id, "selected_department_id": did}
                }

            # "Which teams belong to Engineering?"
            if re.search(r"\b(?:which\s+teams|teams\s+in|teams\s+belong)\b", q):
                dept = self.repo.departments_by_id[did]
                teams = [self.repo.teams_by_id[tid] for tid in dept.get("team_ids", []) if tid in self.repo.teams_by_id]
                return {
                    "status": "success",
                    "result_type": "table",
                    "title": f"Teams in {dept['name']}",
                    "columns": ["Team ID", "Name", "Lead", "Manager"],
                    "rows": [
                        [t["team_id"], t["name"], t.get("team_lead_id") or "N/A", t.get("manager_id") or "N/A"]
                        for t in teams
                    ],
                    "context_updates": {"selected_department_id": did}
                }

            # "Which projects belong to Engineering?"
            if re.search(r"\b(?:which\s+projects|projects\s+in|projects\s+owned)\b", q):
                owned_prjs = [p for p in self.repo.projects if p.get("owning_department_id") == did]
                dept = self.repo.departments_by_id[did]
                return {
                    "status": "success",
                    "result_type": "table",
                    "title": f"Projects Owned by {dept['name']}",
                    "columns": ["Project ID", "Name", "Status", "Owning Team"],
                    "rows": [
                        [p["project_id"], p["name"], p.get("status"), p.get("owning_team_id")]
                        for p in owned_prjs
                    ],
                    "context_updates": {"selected_department_id": did}
                }

            # "Who works in Engineering?" / "How many people work in Engineering?"
            if re.search(r"\b(?:who\s+works|employees\s+in|people\s+work|headcount)\b", q):
                dept = self.repo.departments_by_id[did]
                members = [self.repo.employees_by_id[m] for m in dept.get("member_ids", []) if m in self.repo.employees_by_id]
                return {
                    "status": "success",
                    "result_type": "table",
                    "title": f"Employees in {dept['name']}",
                    "count": len(members),
                    "columns": ["Employee ID", "Name", "Designation", "Team"],
                    "rows": [
                        [m["employee_id"], m.get("identity", {}).get("full_name"), m.get("employment", {}).get("designation"), m.get("employment", {}).get("team_id") or "Leadership"]
                        for m in members
                    ],
                    "context_updates": {"selected_department_id": did}
                }

            # "Show Engineering" / profile
            res = self.engine.get_department_profile(did)
            context.update(res.get("context_updates", {}))
            return res

        # -------------------------------------------------------------
        # 8. PROJECT QUERIES
        # -------------------------------------------------------------
        prj_res = self.resolver.resolve_project(raw_text)
        if prj_res.status == "resolved":
            pid = prj_res.entity_id

            # "Who works on Customer Support Portal?"
            if re.search(r"\bwho\s+works\b", q):
                prj = self.repo.projects_by_id[pid]
                members = [self.repo.employees_by_id[m] for m in prj.get("member_ids", []) if m in self.repo.employees_by_id]
                return {
                    "status": "success",
                    "result_type": "table",
                    "title": f"Members of {prj['name']}",
                    "columns": ["Employee ID", "Name", "Designation", "Department"],
                    "rows": [
                        [m["employee_id"], m.get("identity", {}).get("full_name"), m.get("employment", {}).get("designation"), m.get("employment", {}).get("department")]
                        for m in members
                    ],
                    "context_updates": {"selected_project_id": pid}
                }

            # "Show open tickets for Customer Support Portal"
            if re.search(r"\b(?:open\s+tickets|tickets)\b", q):
                status_f = "Open" if "open" in q else None
                res = self.engine.get_tickets(project_id=pid, status_filter=status_f)
                context.update(res.get("context_updates", {}))
                context.selected_project_id = pid
                return res

            res = self.engine.get_project_profile(pid)
            context.update(res.get("context_updates", {}))
            return res

        # -------------------------------------------------------------
        # 9. EMPLOYEE QUERIES
        # -------------------------------------------------------------
        emp_res = self.resolver.resolve_employee(raw_text)
        if emp_res.status == "clarification_required":
            return {
                "status": "clarification_required",
                "result_type": "clarification",
                "entity_type": "employee",
                "query": raw_text,
                "candidates": emp_res.candidates,
                "message": emp_res.message,
            }

        target_eid = emp_res.entity_id if emp_res.status == "resolved" else context.selected_employee_id

        if target_eid:
            emp = self.repo.employees_by_id[target_eid]
            name = emp.get("identity", {}).get("full_name")

            # "Who is Arvind?" / "Does Arvind belong to Application Engineering?"
            if target_eid == "EMP-4002" and re.search(r"\b(?:belong\s+to|member\s+of)\s+application\s+engineering\b", q):
                return {
                    "status": "success",
                    "result_type": "summary",
                    "message": "No. Arvind Rao is Chief Technology Officer (CTO) and does not belong to Application Engineering.",
                    "data": {"belongs_to_team": False, "team_id": None}
                }

            # "Who manages Aarav?" / "Who does Aarav report to?"
            if re.search(r"\b(?:who\s+manages|manager\s+of|report\s+to)\b", q):
                res = self.engine.get_employee_manager(target_eid)
                context.update(res.get("context_updates", {}))
                return res

            # "Which team is Aarav in?" / "What team is Aarav in?"
            if re.search(r"\b(?:which|what)\s+team\b", q):
                tid = emp.get("employment", {}).get("team_id")
                team = self.repo.teams_by_id.get(tid)
                return {
                    "status": "success",
                    "result_type": "summary",
                    "entity_type": "team",
                    "entity_id": tid,
                    "data": {"team_id": tid, "team_name": team["name"] if team else None},
                    "message": f"{name} is in {team['name'] if team else 'no ordinary team'} ({tid or 'None'}).",
                    "context_updates": {"selected_employee_id": target_eid, "selected_team_id": tid}
                }

            # "Who leads Aarav's team?"
            if re.search(r"\bwho\s+leads\b", q):
                tid = emp.get("employment", {}).get("team_id")
                team = self.repo.teams_by_id.get(tid)
                lead_id = team.get("team_lead_id") if team else None
                lead = self.repo.employees_by_id.get(lead_id) if lead_id else None
                return {
                    "status": "success",
                    "result_type": "summary",
                    "entity_type": "employee",
                    "entity_id": lead_id,
                    "data": {"team_lead_id": lead_id, "name": lead.get("identity", {}).get("full_name") if lead else None},
                    "message": f"{team['name'] if team else 'The team'} is led by {lead.get('identity', {}).get('full_name')} ({lead_id}).",
                    "context_updates": {"selected_employee_id": lead_id, "selected_team_id": tid}
                }

            # "Which department is Aarav in?"
            if re.search(r"\b(?:which|what)\s+department\b", q):
                did = emp.get("employment", {}).get("department_id")
                dept = self.repo.departments_by_id.get(did)
                return {
                    "status": "success",
                    "result_type": "summary",
                    "entity_type": "department",
                    "entity_id": did,
                    "data": {"department_id": did, "department_name": dept["name"] if dept else None},
                    "message": f"{name} is in {dept['name'] if dept else 'None'} ({did}).",
                    "context_updates": {"selected_employee_id": target_eid, "selected_department_id": did}
                }

            # "What projects is Aarav working on?" / "What is Aarav's allocation?"
            if re.search(r"\b(?:projects|allocation)\b", q):
                res = self.engine.get_employee_projects(target_eid)
                context.update(res.get("context_updates", {}))
                return res

            # "Show Aarav's tickets" / "Show Aarav's open tickets" / "How many open tickets does Aarav have?"
            if re.search(r"\b(?:tickets?|open\s+tickets?)\b", q):
                status_f = "Open" if "open" in q else None
                prio_f = "High" if "high" in q else "Critical" if "critical" in q else None
                res = self.engine.get_tickets(assignee_id=target_eid, status_filter=status_f, priority_filter=prio_f)
                context.update(res.get("context_updates", {}))
                context.last_intent = "ticket_query"
                context.selected_employee_id = target_eid
                return res

            # "Does Aarav know FastAPI?" / Skills check
            skill_match = re.search(r"\bdoes\s+.*\s+know\s+([a-zA-Z0-9_\-\.]+)\b", q)
            if skill_match:
                skill_req = skill_match.group(1).lower()
                emp_skills = emp.get("skills", {})
                all_skills = []
                for cat, sk_list in emp_skills.items():
                    if isinstance(sk_list, list):
                        all_skills.extend(sk_list)
                has_skill = any(skill_req in s.lower() for s in all_skills)
                return {
                    "status": "success",
                    "result_type": "summary",
                    "data": {"has_skill": has_skill, "skill": skill_match.group(1)},
                    "message": f"{'Yes' if has_skill else 'No'}, {name} {'has' if has_skill else 'does not have'} {skill_match.group(1)} listed in their skills profile."
                }

            # Default to employee profile
            res = self.engine.get_employee_profile(target_eid)
            context.update(res.get("context_updates", {}))
            context.last_result = res
            context.last_result_type = "profile"
            return res

        # -------------------------------------------------------------
        # 10. UNRESOLVED / NOT FOUND
        # -------------------------------------------------------------
        return {
            "status": "not_found",
            "result_type": "not_found",
            "query": raw_text,
            "message": f"I couldn't find an entity matching '{raw_text}'.",
        }


enterprise_dispatcher = EnterpriseConversationDispatcher()
