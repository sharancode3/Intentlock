"""
IntentLock — Scoped Authorization Service
Authoritative policy enforcement boundary that evaluates actor scope and projects
canonical employee records into strictly sanitized, authorized result payloads.

Enforces:
1. Self-Scope: An authenticated actor can view their own profile with secrets scrubbed.
2. Manager-Scope: A manager can only view records of employees who directly report to them.
3. Strict Denial: Unauthorized targets return explicit denials without disclosing private data.
4. Payload Projection: Formats data strictly matching frontend GenericResultBlock contracts.
"""

import time
import logging
from typing import Optional, Dict, Any, List, Tuple
from pydantic import BaseModel

from backend.services.employee_knowledge_service import EmployeeKnowledgeService
from backend.services.ticket_knowledge_service import TicketKnowledgeService
from backend.models.turn import GenericResultBlock

logger = logging.getLogger("intentlock.scoped_authorization")


class ScopedProfileResult(BaseModel):
    is_authorized: bool
    status_code: int = 200
    spoken_summary: str
    result_block: Optional[GenericResultBlock] = None
    denial_reason: Optional[str] = None


class ScopedAuthorizationService:
    _instance: Optional["ScopedAuthorizationService"] = None

    def __init__(
        self,
        knowledge_service: Optional[EmployeeKnowledgeService] = None,
        ticket_service: Optional[TicketKnowledgeService] = None,
    ):
        self.knowledge = knowledge_service or EmployeeKnowledgeService.get_instance()
        self.ticket_service = ticket_service or TicketKnowledgeService.get_instance()

    @classmethod
    def get_instance(cls) -> "ScopedAuthorizationService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _sanitize_self_profile(self, emp: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize an employee record for self-viewing.
        Removes internal security_scope, raw permissions, salary, and system flags.
        """
        projects_obj = emp.get("projects", {})
        current_projects = projects_obj.get("current", []) if isinstance(projects_obj, dict) else []
        project_names = [
            p.get("name") for p in current_projects if isinstance(p, dict) and p.get("name")
        ]

        skills_obj = emp.get("skills", {})
        primary_skills = (
            skills_obj.get("technical", [])
            or skills_obj.get("primary", [])
            if isinstance(skills_obj, dict)
            else []
        )

        reporting = emp.get("reporting", {})

        return {
            "id": emp["employee_id"],
            "name": emp.get("identity", {}).get("full_name", ""),
            "role": emp.get("employment", {}).get("designation", "Employee"),
            "department": emp.get("employment", {}).get("department", "General"),
            "team": emp.get("employment", {}).get("sub_department") or emp.get("employment", {}).get("department"),
            "email": emp.get("identity", {}).get("work_email", ""),
            "active_projects": project_names,
            "status": emp.get("employment", {}).get("status", "Active"),
            "office_location": emp.get("employment", {}).get("location", "Bengaluru"),
            "manager_name": reporting.get("manager_name"),
            "skills": primary_skills[:5],
        }

    def _sanitize_direct_report_profile(self, emp: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize an employee record for viewing by their direct manager."""
        profile = self._sanitize_self_profile(emp)
        skills_obj = emp.get("skills", {})
        if isinstance(skills_obj, dict):
            profile["skills"] = skills_obj.get("technical", []) or skills_obj.get("primary", [])
            profile["secondary_skills"] = skills_obj.get("management", []) or skills_obj.get("secondary", [])
            profile["tools"] = skills_obj.get("tools", [])
        return profile

    def build_profile_result_block(self, sanitized_employee: Dict[str, Any]) -> GenericResultBlock:
        return GenericResultBlock(
            id=f"blk_profile_{sanitized_employee['id']}_{int(time.time())}",
            type="EMPLOYEE_PROFILE",
            title=f"Employee Profile: {sanitized_employee['name']} ({sanitized_employee['id']})",
            timestamp=time.strftime("%I:%M %p", time.localtime()),
            isSensitive=True,
            payload={"employee": sanitized_employee},
        )

    def build_denial_result_block(self, reason: str, target_id: Optional[str] = None) -> GenericResultBlock:
        return GenericResultBlock(
            id=f"blk_denial_{int(time.time())}",
            type="DENIAL_BANNER",
            title="Access Restricted: Policy Authorization Boundary",
            timestamp=time.strftime("%I:%M %p", time.localtime()),
            isSensitive=False,
            payload={
                "message": reason,
                "reason": reason,
                "target_requested": target_id or "Restricted Resource",
                "policy": "Requires verified identity with self-viewing scope or direct reporting manager authorization.",
            },
        )

    def evaluate_and_get_profile(
        self,
        actor_id: str,
        target_id: Optional[str] = None,
    ) -> ScopedProfileResult:
        """
        Authoritative evaluation of profile read scope.

        Rules:
        1. target_id is None or equals actor_id -> Self-viewing permitted.
        2. target_id != actor_id:
           - Check if target exists.
           - Check if target's reporting_manager_id == actor_id -> Manager viewing permitted.
           - Otherwise -> Denied.
        """
        effective_target = target_id.strip() if target_id else actor_id.strip()

        # 1. Self Scope
        if effective_target.lower() == actor_id.strip().lower():
            emp = self.knowledge.get_employee_by_id(actor_id)
            if not emp:
                return ScopedProfileResult(
                    is_authorized=False,
                    status_code=404,
                    spoken_summary="Employee record not found in system directory.",
                    denial_reason="RECORD_NOT_FOUND",
                )
            sanitized = self._sanitize_self_profile(emp)
            result_block = self.build_profile_result_block(sanitized)
            spoken = (
                f"Identity verified as {sanitized['name']}, {sanitized['role']} in {sanitized['department']}. "
                f"Displaying your authorized employee profile."
            )
            return ScopedProfileResult(
                is_authorized=True,
                status_code=200,
                spoken_summary=spoken,
                result_block=result_block,
            )

        # 2. Manager Scope (Viewing direct report)
        target_emp = self.knowledge.get_employee_by_id(effective_target)
        if not target_emp:
            return ScopedProfileResult(
                is_authorized=False,
                status_code=404,
                spoken_summary="The requested employee record could not be found.",
                result_block=self.build_denial_result_block("Record not found in directory", effective_target),
                denial_reason="RECORD_NOT_FOUND",
            )

        reporting_mgr = (
            target_emp.get("reporting", {}).get("manager_id")
            or target_emp.get("employment", {}).get("reporting_manager_id", "")
        )
        if reporting_mgr and reporting_mgr.strip().lower() == actor_id.strip().lower():
            sanitized = self._sanitize_direct_report_profile(target_emp)
            result_block = self.build_profile_result_block(sanitized)
            spoken = (
                f"Authorized manager view: displaying direct report profile for {sanitized['name']} ({sanitized['id']})."
            )
            return ScopedProfileResult(
                is_authorized=True,
                status_code=200,
                spoken_summary=spoken,
                result_block=result_block,
            )

        # 3. Unauthorized Colleague Access -> Explicit Denial
        denial_reason = "UNAUTHORIZED_TARGET: You are not authorized to view this colleague's private personnel record."
        spoken = "Access denied. Company policy restricts private employee records to self-access or direct reporting managers."
        result_block = self.build_denial_result_block(denial_reason, effective_target)
        return ScopedProfileResult(
            is_authorized=False,
            status_code=403,
            spoken_summary=spoken,
            result_block=result_block,
            denial_reason=denial_reason,
        )

    def get_team_summary(self, actor_id: str) -> Dict[str, Any]:
        """
        Retrieve direct report summaries for an authenticated manager or executive.
        Returns empty list if the actor has no direct reports.
        """
        emp = self.knowledge.get_employee_by_id(actor_id)
        if not emp:
            return {"team_count": 0, "direct_reports": []}

        rep_ids = emp.get("reporting", {}).get("direct_report_ids", [])
        reports = []
        for r_id in rep_ids:
            r_emp = self.knowledge.get_employee_by_id(r_id)
            if r_emp:
                reports.append(self._sanitize_direct_report_profile(r_emp))

        return {
            "team_count": len(reports),
            "direct_reports": reports,
        }

    def evaluate_and_get_tickets(
        self,
        actor_id: str,
        query: Optional[str] = None,
    ) -> ScopedProfileResult:
        """
        Authoritative evaluation of ticket read scope.
        Returns a ScopedProfileResult containing GenericResultBlock of type TICKET_LIST.
        """
        actor_emp = self.knowledge.get_employee_by_id(actor_id)
        if not actor_emp:
            return ScopedProfileResult(
                is_authorized=False,
                status_code=404,
                spoken_summary="Employee record not found in system directory.",
                denial_reason="RECORD_NOT_FOUND",
            )

        rep_ids = actor_emp.get("reporting", {}).get("direct_report_ids", [])
        is_exec = bool(actor_emp.get("executive_authority"))

        scoped_tickets = self.ticket_service.get_scoped_tickets_for_actor(
            actor_id=actor_id,
            direct_report_ids=rep_ids,
            is_executive=is_exec,
        )

        # Check for specific ticket inquiry
        if query:
            import re
            m = re.search(r"\b(TKT[-_]?\d{4}[-_]?\d{3}|TKT[-_]?\d{4})\b", query, re.IGNORECASE)
            if m:
                raw_tid = m.group(1).upper().replace("_", "-")
                found = self.ticket_service.get_ticket_by_id(raw_tid)
                if not found:
                    spoken = f"Ticket {raw_tid} was not found in the system directory."
                    return ScopedProfileResult(
                        is_authorized=True,
                        status_code=200,
                        spoken_summary=spoken,
                        result_block=GenericResultBlock(
                            id=f"blk_ticket_empty_{int(time.time())}",
                            type="TICKET_LIST",
                            title=f"Ticket Not Found: {raw_tid}",
                            timestamp=time.strftime("%I:%M %p", time.localtime()),
                            isSensitive=True,
                            payload={"title": f"Ticket {raw_tid} (Not Found)", "tickets": [], "total_count": 0},
                        ),
                    )
                # Check if authorized to view this ticket
                is_authorized_for_ticket = any(t["ticket_id"] == raw_tid for t in scoped_tickets)
                if not is_authorized_for_ticket:
                    denial_reason = f"UNAUTHORIZED_TICKET: You are not authorized to view ticket {raw_tid}."
                    spoken = f"Access denied. Ticket {raw_tid} is restricted and outside your authorized role scope."
                    return ScopedProfileResult(
                        is_authorized=False,
                        status_code=403,
                        spoken_summary=spoken,
                        result_block=self.build_denial_result_block(denial_reason, raw_tid),
                        denial_reason=denial_reason,
                    )
                filtered_tickets = [found]
            else:
                filtered_tickets = self.ticket_service.filter_tickets_for_query(scoped_tickets, query)
        else:
            filtered_tickets = scoped_tickets

        frontend_records = [
            self.ticket_service.map_ticket_to_frontend_record(t)
            for t in filtered_tickets
        ]

        if not frontend_records:
            spoken = f"You have no tickets matching that criteria."
        elif len(frontend_records) == 1:
            t = frontend_records[0]
            spoken = f"Showing ticket {t['ticket_id']}: {t['title']} ({t['priority']} priority, {t['status']})."
        else:
            count = len(frontend_records)
            spoken = f"Displaying {count} authorized tickets matching your request."

        result_block = GenericResultBlock(
            id=f"blk_tickets_{actor_id}_{int(time.time())}",
            type="TICKET_LIST",
            title=f"Authorized Tickets ({len(frontend_records)})",
            timestamp=time.strftime("%I:%M %p", time.localtime()),
            isSensitive=True,
            payload={
                "title": f"Tickets ({len(frontend_records)})",
                "tickets": frontend_records,
                "total_count": len(frontend_records),
            },
        )

        return ScopedProfileResult(
            is_authorized=True,
            status_code=200,
            spoken_summary=spoken,
            result_block=result_block,
        )

    def build_authorized_context_for_llm(
        self,
        actor_id: str,
        query: Optional[str] = None,
        target_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Builds a strictly authorized context dictionary for LLM answering.
        Only data the authenticated actor is authorized to see is included.
        Pre-LLM filtering prevents leaking private data or unauthorized employee records.
        """
        import re

        actor_emp = self.knowledge.get_employee_by_id(actor_id)
        if not actor_emp:
            return {"error": "Actor record not found in system."}

        sanitized_actor = self._sanitize_self_profile(actor_emp)
        context: Dict[str, Any] = {
            "authenticated_actor": sanitized_actor,
        }

        # Check for direct reports (e.g. for EMP-2001 or EMP-4002)
        rep_ids = actor_emp.get("reporting", {}).get("direct_report_ids", [])
        if rep_ids:
            team_summary = self.get_team_summary(actor_id)
            context["authorized_team_members"] = team_summary["direct_reports"]
            context["team_size"] = team_summary["team_count"]

        # Check for executive technology scope (e.g. for EMP-4002)
        exec_auth = actor_emp.get("executive_authority")
        if exec_auth:
            context["executive_scope"] = {
                "technology_authority": exec_auth.get("technology_authority"),
                "board_relationship": exec_auth.get("board_relationship"),
                "assigned_initiatives": sanitized_actor.get("active_projects", []),
            }

        # Check if query requests another employee or if target_id was specified
        effective_target = target_id.strip().upper() if target_id else None
        if not effective_target and query:
            m = re.search(r"\b(EMP[-_]?\d{4}|RND[-_]?\d{4}|EXE[-_]?\d{4})\b", query, re.IGNORECASE)
            if m:
                raw_m = m.group(1).upper().replace("_", "-")
                if raw_m != actor_id:
                    effective_target = raw_m

        if effective_target and effective_target != actor_id:
            # Evaluate scope for the requested target
            eval_res = self.evaluate_and_get_profile(actor_id=actor_id, target_id=effective_target)
            if eval_res.is_authorized and eval_res.result_block:
                context["requested_target_profile"] = eval_res.result_block.payload.get("employee")
            else:
                context["access_denial"] = {
                    "target_requested": effective_target,
                    "status": "DENIED",
                    "reason": "You are not authorized to view this colleague's private personnel record.",
                }

        # Scoped ticket retrieval and pre-LLM filtering
        scoped_tickets = self.ticket_service.get_scoped_tickets_for_actor(
            actor_id=actor_id,
            direct_report_ids=rep_ids,
            is_executive=bool(exec_auth),
        )

        # Check for specific ticket inquiry (e.g. TKT-2026-001 or TKT-9999)
        if query:
            m_tkt = re.search(r"\b(TKT[-_]?\d{4}[-_]?\d{3}|TKT[-_]?\d{4})\b", query, re.IGNORECASE)
            if m_tkt:
                raw_tid = m_tkt.group(1).upper().replace("_", "-")
                found_tkt = self.ticket_service.get_ticket_by_id(raw_tid)
                if not found_tkt:
                    context["ticket_query_result"] = {
                        "ticket_id": raw_tid,
                        "exists": False,
                        "status": "NOT_FOUND",
                        "message": f"Ticket {raw_tid} does not exist in the system directory.",
                    }
                else:
                    is_auth = any(t["ticket_id"] == raw_tid for t in scoped_tickets)
                    if is_auth:
                        context["inspected_ticket"] = found_tkt
                    else:
                        context["ticket_query_result"] = {
                            "ticket_id": raw_tid,
                            "exists": True,
                            "status": "ACCESS_DENIED",
                            "message": f"User {actor_id} is not authorized to access ticket {raw_tid}.",
                        }

        # Filter tickets relevant to query or supply small authorized subset
        if query:
            matching_tickets = self.ticket_service.filter_tickets_for_query(scoped_tickets, query)
        else:
            matching_tickets = scoped_tickets

        # Clean, bounded subset for LLM context (up to 8 tickets)
        context["authorized_tickets"] = [
            {
                "ticket_id": t["ticket_id"],
                "title": t["title"],
                "description": t["description"],
                "status": t["status"],
                "priority": t["priority"],
                "severity": t["severity"],
                "project": t["project"],
                "category": t["category"],
                "assignee_id": t.get("assignee_id"),
                "requester_id": t.get("requester_id"),
                "created_by": t.get("created_by"),
                "due_date": t.get("due_date"),
                "sla": t.get("sla"),
                "escalation": t.get("escalation"),
                "approval": t.get("approval"),
                "comments": t.get("comments", [])[-3:],
                "activity_history": t.get("activity_history", [])[-4:],
                "resolution": t.get("resolution") if t.get("status") in ("Resolved", "Closed") else None,
            }
            for t in matching_tickets[:8]
        ]
        context["ticket_summary"] = {
            "total_authorized_tickets": len(scoped_tickets),
            "matching_tickets_count": len(matching_tickets),
            "open_tickets_count": sum(1 for t in scoped_tickets if t.get("status") in ("Open", "In Progress", "Pending", "Blocked")),
            "resolved_tickets_count": sum(1 for t in scoped_tickets if t.get("status") in ("Resolved", "Closed")),
            "at_risk_sla_count": sum(1 for t in scoped_tickets if t.get("sla", {}).get("resolution_status") == "At Risk"),
            "critical_tickets_count": sum(1 for t in scoped_tickets if t.get("priority") == "Critical"),
        }

        return context

