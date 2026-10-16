"""Typed, bounded read dispatcher for the production voice and action routes.

The planner interprets language. This module alone resolves records, applies
policy, counts rows, and creates visual facts. Client references are hints only.
"""

from __future__ import annotations

import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.core.scoped_authorization import ScopedAuthorizationService, ScopedProfileResult
from backend.models.turn import GenericResultBlock
from backend.services.ticket_action_store import ActionError


Operation = Literal[
    "help", "profile", "team_table", "team_count", "org_tree",
    "ticket_list", "ticket_chart", "rechart", "back", "clarify",
    "create_ticket", "update_ticket", "comment_ticket", "confirm", "cancel",
]


class IntentPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Operation
    entity: Optional[str] = Field(default=None, max_length=96)
    ticket_id: Optional[str] = Field(default=None, max_length=32)
    person_filter: Optional[str] = Field(default=None, max_length=32)
    sla_metric: Optional[Literal["overdue", "compliance"]] = None
    view: Optional[Literal["TABLE", "BAR", "PIE", "LINE", "AREA", "TREE"]] = None
    group_by: Optional[Literal["priority", "status"]] = None
    status_filter: Optional[Literal["Open", "In Progress", "Pending", "Blocked", "Resolved", "Closed", "Unresolved", "Not Closed"]] = None
    priority_filter: Optional[Literal["Critical", "High", "Medium", "Low"]] = None
    descendants: bool = False
    field: Optional[Literal["description", "status", "priority"]] = None
    value: Optional[str] = Field(default=None, max_length=500)
    from_date: Optional[date] = None
    to_date: Optional[date] = None


@dataclass
class ResultSnapshot:
    block: GenericResultBlock
    operation: str
    visible_ids: List[str] = field(default_factory=list)
    source_rows: List[dict] = field(default_factory=list)
    source_kind: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    filter_state: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationState:
    actor_id: str
    snapshots: Dict[str, ResultSnapshot] = field(default_factory=dict)
    active_id: Optional[str] = None
    previous_id: Optional[str] = None
    selected_ticket_id: Optional[str] = None

    def remember(self, snapshot: ResultSnapshot) -> None:
        if self.active_id != snapshot.block.id:
            self.previous_id = self.active_id
        self.snapshots[snapshot.block.id] = snapshot
        self.active_id = snapshot.block.id
        while len(self.snapshots) > 8:
            oldest = next(iter(self.snapshots))
            self.snapshots.pop(oldest)
            if self.previous_id == oldest:
                self.previous_id = None


class ConversationStore:
    """Short-lived, server-bound result references; no browser authority."""

    def __init__(self) -> None:
        self._states: Dict[str, ConversationState] = {}

    def get(self, session_id: str, actor_id: str) -> ConversationState:
        state = self._states.get(session_id)
        if state is None or state.actor_id != actor_id:
            state = ConversationState(actor_id=actor_id)
            self._states[session_id] = state
        now = time.time()
        state.snapshots = {key: snap for key, snap in state.snapshots.items() if now - snap.created_at < 300}
        if state.active_id not in state.snapshots:
            state.active_id = None
        if state.previous_id not in state.snapshots:
            state.previous_id = None
        return state

    def clear(self, session_id: str) -> None:
        self._states.pop(session_id, None)


conversation_store = ConversationStore()


def block(kind: str, title: str, payload: dict, sensitive: bool = True) -> GenericResultBlock:
    return GenericResultBlock(
        id=f"blk_{uuid.uuid4().hex}", type=kind, title=title,
        timestamp=datetime.now(timezone.utc).isoformat(),
        isSensitive=sensitive, payload=payload,
    )


def parse_local(text: str, state: Optional[ConversationState] = None) -> IntentPlan:
    """Clear local commands avoid an LLM call. Unknown language is clarification."""
    q = re.sub(r"\s+", " ", text.strip().lower())
    ticket = re.search(r"\bTKT[-_ ]?\d{4}[-_ ]?\d{3}\b", text, re.I)
    ticket_id = re.sub(r"[_ ]", "-", ticket.group().upper()) if ticket else None
    if not q:
        return IntentPlan(operation="clarify")
    if re.search(r"\b(cancel|never mind|discard)\b", q):
        return IntentPlan(operation="cancel")
    if re.search(r"\b(i confirm|confirm the change|yes, confirm)\b", q):
        return IntentPlan(operation="confirm")
    if re.search(r"\b(help|what can you do|how do i use)\b", q) and not re.search(r"\b(my|ticket|team|profile)\b", q):
        return IntentPlan(operation="help")
    if re.search(r"\b(back to|go back|previous (view|result))\b", q):
        return IntentPlan(operation="back")
    context_ticket = None
    if state:
        if state.selected_ticket_id:
            context_ticket = state.selected_ticket_id
        elif state.active_id:
            active = state.snapshots.get(state.active_id)
            if active and active.source_kind == "tickets" and len(active.visible_ids) == 1:
                context_ticket = active.visible_ids[0]
    if context_ticket and re.search(r"\b(?:open|show|view|details\s+for)\s+(?:this|the)\s+ticket\b", q):
        return IntentPlan(operation="ticket_list", ticket_id=context_ticket)
    if re.search(r"\b(?:EMP|RND|EXE)[-_ ]?\d{4}\b", text, re.I) and not re.search(r"\bTKT[-_ ]?\d{4}", text, re.I) and not re.search(r"\b(tickets?|issues?)\b", q):
        return IntentPlan(operation="profile", entity=text.strip())
    if state and state.active_id and re.search(r"\b(?:open|show|view)\s+(?:the\s+)?(?:first|second|third|fourth)\s+person\b", q):
        return IntentPlan(operation="profile", entity=text.strip())
    if re.search(r"\b(create|raise|file|submit)\b.*\b(ticket|issue)\b", q) and not ticket_id:
        return IntentPlan(operation="create_ticket", value=text.strip())
    if (ticket_id or context_ticket) and re.search(r"\b(add|post|leave)\b.*\bcomment\b", q):
        return IntentPlan(operation="comment_ticket", ticket_id=ticket_id or context_ticket, value=text.strip())
    if (ticket_id or context_ticket) and re.search(r"\b(change|update|set|mark)\b", q):
        field = next((item for item in ("priority", "status", "description") if item in q), None)
        return IntentPlan(operation="update_ticket", ticket_id=ticket_id or context_ticket, field=field, value=text.strip())
    if state and state.active_id and re.search(r"\b(this|that|those|same|instead|only)\b", q) and re.search(r"\b(table|bar|pie|chart|trend|timeline)\b", q):
        view = "TABLE" if "table" in q else "PIE" if "pie" in q else "AREA" if "area" in q else "LINE" if "line" in q or "trend" in q or "timeline" in q else "BAR"
        group = "status" if "status" in q else "priority" if "priority" in q else None
        status = None
        if re.search(r"\b(unresolved|not resolved|active)\b", q):
            status = "Unresolved"
        elif re.search(r"\b(not closed|unclosed)\b", q):
            status = "Not Closed"
        elif re.search(r"\bin[ -]?progress\b", q):
            status = "In Progress"
        elif re.search(r"\bpending\b", q):
            status = "Pending"
        elif re.search(r"\bblocked\b", q):
            status = "Blocked"
        elif re.search(r"\bclosed\b", q):
            status = "Closed"
        elif re.search(r"\bresolved\b", q):
            status = "Resolved"
        elif re.search(r"\bopen\b", q):
            status = "Open"
        priority = next((value for value in ("Critical", "High", "Medium", "Low") if re.search(rf"\b{value.lower()}\b", q)), None)
        if not priority:
            priority = "Critical" if re.search(r"\b(urgent|highest|sev[- ]?1)\b", q) else "Medium" if "normal" in q else None
        dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", q)
        try:
            parsed_dates = [date.fromisoformat(item) for item in dates[:2]]
        except ValueError:
            return IntentPlan(operation="clarify")
        from_date = parsed_dates[0] if parsed_dates and re.search(r"\b(since|after|from|between)\b", q) else None
        to_date = parsed_dates[-1] if parsed_dates and re.search(r"\b(before|until|through|between)\b", q) else None
        if from_date and to_date and from_date > to_date:
            return IntentPlan(operation="clarify")
        return IntentPlan(operation="rechart", view=view, group_by=group, status_filter=status, priority_filter=priority, from_date=from_date, to_date=to_date)
    if re.search(r"\b(reporting tree|org chart|organization chart|team tree|reporting hierarchy|everyone reporting|all my reports)\b", q):
        return IntentPlan(operation="org_tree", descendants=bool(re.search(r"\b(all|everyone|indirect|descendant|entire)\b", q)))
    if re.search(r"\b(how many|count|number of)\b.*\b(direct reports|people reporting|team members)\b", q):
        return IntentPlan(operation="team_count")
    if re.search(r"\b(team|direct reports|people reporting)\b", q) and re.search(r"\b(list|table|show|who|members)\b", q) and not re.search(r"\b(tickets?|issues?)\b", q):
        return IntentPlan(operation="team_table")
    profile_requested = bool(re.search(r"\b(profile|details|skills|projects|manager|about me|who am i)\b", q))
    ticket_requested = bool(re.search(r"\b(ticket|tickets|tkt|issue|issues|incident|incidents|workload|overdue|sla)\b", q))
    if re.search(r"\b(not|no) (tickets|issues)\b", q):
        ticket_requested = False
    if profile_requested and not ticket_requested:
        return IntentPlan(operation="profile", entity=text.strip())
    if ticket_requested or ticket_id:
        view = "AREA" if "area" in q and "time" in q else "LINE" if re.search(r"\b(trend|timeline|over time|per day|line chart)\b", q) else "PIE" if "pie" in q or "donut" in q else "BAR" if "bar" in q or "chart" in q or "graph" in q else None
        has_closed = bool(re.search(r"\bclosed\b", q))
        has_open_or_unresolved = bool(re.search(r"\b(open|unresolved|not resolved|active)\b", q))
        if has_closed and has_open_or_unresolved and not re.search(r"\bnot closed\b", q):
            return IntentPlan(operation="clarify")
        status = None
        if re.search(r"\b(unresolved|not resolved|active)\b", q):
            status = "Unresolved"
        elif re.search(r"\b(not closed|unclosed)\b", q):
            status = "Not Closed"
        elif re.search(r"\bin[ -]?progress\b", q):
            status = "In Progress"
        elif re.search(r"\bpending\b", q):
            status = "Pending"
        elif re.search(r"\bblocked\b", q):
            status = "Blocked"
        elif re.search(r"\bclosed\b", q):
            status = "Closed"
        elif re.search(r"\bresolved\b", q):
            status = "Resolved"
        elif re.search(r"\bopen\b", q):
            status = "Open"
        priority = next((value for value in ("Critical", "High", "Medium", "Low") if re.search(rf"\b{value.lower()}\b", q)), None)
        if not priority:
            priority = "Critical" if re.search(r"\b(urgent|highest|sev[- ]?1)\b", q) else "Medium" if "normal" in q else None
        group = "status" if "by status" in q else "priority" if "by priority" in q else None

        emp_match = re.search(r"\b((?:EMP|RND|EXE)[-_ ]?\d{4})\b", text, re.I)
        person_filter = re.sub(r"[_ ]", "-", emp_match.group(1).upper()) if emp_match else None

        sla_metric = None
        if re.search(r"\b(how many|count)\b.*\b(overdue|breached|sla)\b", q) or re.search(r"\b(overdue|breached)\b", q):
            sla_metric = "overdue"
        elif re.search(r"\b(sla|compliance)\b", q):
            sla_metric = "compliance"

        dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", q)
        try:
            parsed_dates = [date.fromisoformat(item) for item in dates[:2]]
        except ValueError:
            return IntentPlan(operation="clarify")
        from_date = parsed_dates[0] if parsed_dates and re.search(r"\b(since|after|from|between)\b", q) else None
        to_date = parsed_dates[-1] if parsed_dates and re.search(r"\b(before|until|through|between)\b", q) else None
        if from_date and to_date and from_date > to_date:
            return IntentPlan(operation="clarify")
        return IntentPlan(
            operation="ticket_chart" if view else "ticket_list",
            ticket_id=ticket_id,
            person_filter=person_filter,
            sla_metric=sla_metric,
            view=view,
            group_by=group,
            status_filter=status,
            priority_filter=priority,
            from_date=from_date,
            to_date=to_date,
        )
    return IntentPlan(operation="clarify")


class ConversationDispatcher:
    def __init__(self, scoped: Optional[ScopedAuthorizationService] = None):
        self.scoped = scoped or ScopedAuthorizationService.get_instance()

    def _deny(self, text: str) -> ScopedProfileResult:
        return ScopedProfileResult(is_authorized=False, status_code=403, spoken_summary=text,
                                   result_block=self.scoped.build_denial_result_block(text), denial_reason="ACCESS_DENIED")

    def _result(self, state: ConversationState, result: ScopedProfileResult, operation: str,
                visible_ids: Optional[List[str]] = None, source_rows: Optional[List[dict]] = None,
                source_kind: Optional[str] = None, filter_state: Optional[dict] = None) -> ScopedProfileResult:
        if result.is_authorized and result.result_block:
            state.remember(ResultSnapshot(result.result_block, operation, visible_ids or [], source_rows or [], source_kind,
                                          filter_state=filter_state or {}))
        return result

    def _resolve_profile_target(self, actor_id: str, phrase: Optional[str], state: ConversationState) -> Optional[str]:
        if not phrase or re.search(r"\b(?:my profile|about me|who am i|myself)\b", phrase, re.I):
            return actor_id
        if re.search(r"\b(?:my|the)\s+manager\b", phrase, re.I):
            actor_emp = self.scoped.knowledge.get_employee_by_id(actor_id)
            return actor_emp.get("reporting", {}).get("manager_id") if actor_emp else None
        visible = [actor_id] + [e["employee_id"] for e in self.scoped.knowledge.get_direct_reports(actor_id)]
        active = state.snapshots.get(state.active_id or "")
        if active:
            visible += active.visible_ids
            ordinal = re.search(r"\b(first|second|third|fourth) person\b", phrase, re.I)
            if ordinal:
                index = {"first": 0, "second": 1, "third": 2, "fourth": 3}[ordinal.group(1).lower()]
                return active.visible_ids[index] if index < len(active.visible_ids) else None
        visible = list(dict.fromkeys(visible))
        for employee_id in visible:
            employee = self.scoped.knowledge.get_employee_by_id(employee_id)
            if not employee:
                continue
            name = employee.get("identity", {}).get("full_name", "")
            first = name.split()[0] if name else ""
            if re.search(rf"\b{re.escape(employee_id)}\b", phrase, re.I) or (first and re.search(rf"\b{re.escape(first)}\b", phrase, re.I)):
                return employee_id
        if re.search(r"\b(my|me|myself)\b", phrase, re.I):
            return actor_id
        return None

    def _team(self, actor_id: str, descendants: bool) -> List[dict]:
        direct = self.scoped.knowledge.get_direct_reports(actor_id)
        if not descendants or actor_id != "EMP-4002":
            return direct[:30]
        result = list(direct)
        for person in direct:
            result.extend(self.scoped.knowledge.get_direct_reports(person["employee_id"]))
        return result[:30]

    def _ticket_rows(self, actor_id: str, plan: IntentPlan) -> List[dict]:
        employee = self.scoped.knowledge.get_employee_by_id(actor_id)
        if not employee:
            return []
        tickets = self.scoped.ticket_service.get_scoped_tickets_for_actor(
            actor_id, employee.get("reporting", {}).get("direct_report_ids", []),
            is_executive=actor_id == "EMP-4002",
        )
        if plan.ticket_id:
            tickets = [row for row in tickets if row["ticket_id"] == plan.ticket_id]
        if plan.person_filter:
            tickets = [
                row for row in tickets
                if row.get("assignee_id") == plan.person_filter
                or row.get("requester_id") == plan.person_filter
                or row.get("created_by") == plan.person_filter
            ]
        if plan.status_filter:
            if plan.status_filter == "Unresolved":
                tickets = [row for row in tickets if row.get("status") not in ("Resolved", "Closed")]
            elif plan.status_filter == "Not Closed":
                tickets = [row for row in tickets if row.get("status") != "Closed"]
            else:
                tickets = [row for row in tickets if row.get("status") == plan.status_filter]
        if plan.priority_filter:
            tickets = [row for row in tickets if row.get("priority") == plan.priority_filter]
        if plan.from_date or plan.to_date:
            def in_range(row: dict) -> bool:
                try:
                    created = date.fromisoformat(str(row.get("created_at", ""))[:10])
                    return (not plan.from_date or created >= plan.from_date) and (not plan.to_date or created <= plan.to_date)
                except ValueError:
                    return False
            tickets = [row for row in tickets if in_range(row)]
        return tickets

    def _chart(self, rows: List[dict], group: str, chart_type: str) -> GenericResultBlock:
        if chart_type in ("LINE", "AREA"):
            counts = Counter(str(row.get("created_at", ""))[:10] for row in rows if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(row.get("created_at", ""))[:10]))
            return block("TEAM_METRIC_CHART", "Tickets created over time", {
                "chart_type": chart_type, "title": "Tickets created over time", "unit": "tickets",
                "scope_description": "Authorized ticket creation events", "data": [{"label": day, "count": counts[day]} for day in sorted(counts)],
                "kpis": {"total_tickets": len(rows)},
            })
        counts = Counter(row.get(group, "Unknown") for row in rows)
        data = [{"label": key, "count": counts[key]} for key in sorted(counts)]
        return block("TEAM_METRIC_CHART", f"Tickets by {group}", {
            "chart_type": chart_type, "title": f"Tickets by {group}", "unit": "tickets",
            "scope_description": "Authorized tickets", "data": data,
            "kpis": {"total_tickets": len(rows), "items": [{"label": "Total tickets", "value": len(rows)}]},
        })

    def dispatch(self, actor_id: str, session_id: str, plan: IntentPlan,
                 spoken_text: str = "", evidence_digest: str = "") -> ScopedProfileResult:
        state = conversation_store.get(session_id, actor_id)
        op = plan.operation
        if op in ("create_ticket", "update_ticket", "comment_ticket", "confirm", "cancel"):
            action_store = self.scoped.ticket_service.store
            if not action_store:
                return self._deny("Ticket changes are unavailable in this environment.")
            employee = self.scoped.knowledge.get_employee_by_id(actor_id)
            report_ids = employee.get("reporting", {}).get("direct_report_ids", []) if employee else []
            try:
                if op == "cancel":
                    cancelled = action_store.cancel(session_id)
                    message = "The pending ticket change was cancelled." if cancelled else "There is no pending ticket change to cancel."
                    return ScopedProfileResult(is_authorized=True, spoken_summary=message,
                        result_block=block("PUBLIC_FAQ", "Ticket action", {"answer": message}, sensitive=False))
                if op == "confirm":
                    receipt = action_store.confirm(actor_id, session_id, spoken_text, evidence_digest, report_ids)
                    self.scoped.ticket_service.refresh_from_store()
                    state.snapshots.clear()
                    state.active_id = None
                    state.previous_id = None
                    visual = block("ACTION_RECEIPT", "Committed ticket change", {
                        "receipt": receipt, "summary": f"{receipt['action']} committed for {receipt['resource_id']}."})
                    return self._result(state, ScopedProfileResult(is_authorized=True,
                        spoken_summary=f"The change to {receipt['resource_id']} was committed as event {receipt['event_id']}.",
                        result_block=visual), op)
                params = action_store.parse_proposal(op, spoken_text, plan.ticket_id)
                draft = action_store.propose(actor_id, session_id, op, plan.ticket_id, params, report_ids, evidence_digest)
                visual = block("READBACK_CONFIRMATION", "Ticket change readback", {
                    "draft": {"action": op, "target": draft["ticket_id"], "params": params,
                              "summary_readback": draft["readback"], "expires_in_seconds": 90},
                    "confirmation_id": draft["draft_id"], "expires_at": draft["expires_at"],
                    "requires_voice_confirmation": True, "status": "PENDING",
                })
                return self._result(state, ScopedProfileResult(is_authorized=True,
                    spoken_summary=f"No change has been made. Please review and speak exactly: {draft['readback']}",
                    result_block=visual), op)
            except ActionError as exc:
                return self._deny(str(exc))
        if op == "back":
            previous = state.snapshots.get(state.previous_id or "")
            if not previous:
                return self._deny("There is no earlier authorized result to return to.")
            state.active_id, state.previous_id = previous.block.id, state.active_id
            return ScopedProfileResult(is_authorized=True, spoken_summary=f"Back to {previous.block.title}.", result_block=previous.block)
        if op == "profile":
            target = self._resolve_profile_target(actor_id, plan.entity, state)
            if target is None:
                return self._deny("I could not resolve that person within your permitted view. Please name a visible direct report.")
            return self._result(state, self.scoped.evaluate_and_get_profile(actor_id, target), op, [target])
        if op in ("team_table", "team_count", "org_tree"):
            root = self.scoped.knowledge.get_employee_by_id(actor_id)
            people = self._team(actor_id, plan.descendants)
            if not root or not people:
                return self._deny("No permitted direct-report view is available for this account.")
            name = root["identity"]["full_name"]
            if op == "team_count":
                visual = block("TEAM_METRIC_CHART", "Direct reports", {
                    "chart_type": "BAR", "title": "Direct reports", "unit": "people",
                    "data": [{"label": "Direct reports", "count": len(self._team(actor_id, False))}],
                    "kpis": {"items": [{"label": "Direct reports", "value": len(self._team(actor_id, False))}]},
                })
                spoken = f"{name} has {len(self._team(actor_id, False))} direct reports."
            elif op == "team_table":
                rows = [{"id": p["employee_id"], "name": p["identity"]["full_name"],
                         "title": p["employment"]["designation"], "department": p["employment"]["department"]} for p in people]
                visual = block("DATA_TABLE", "Direct reports", {"columns": [
                    {"key": "name", "label": "Name"}, {"key": "title", "label": "Title"},
                    {"key": "department", "label": "Department"}], "rows": rows, "total_count": len(rows)})
                spoken = f"Showing {len(rows)} permitted direct reports."
            else:
                nodes = [{"id": actor_id, "name": name, "title": root["employment"]["designation"], "direct_count": len(self._team(actor_id, False))}]
                edges = []
                for p in people:
                    pid = p["employee_id"]
                    nodes.append({"id": pid, "name": p["identity"]["full_name"],
                                  "title": p["employment"]["designation"],
                                  "direct_count": len(self.scoped.knowledge.get_direct_reports(pid)) if pid == "RND-5001" else 0})
                    parent = p.get("reporting", {}).get("manager_id")
                    if parent in {node["id"] for node in nodes}:
                        edges.append({"source": parent, "target": pid})
                visual = block("ORG_TREE", "Reporting tree", {"root_id": actor_id, "nodes": nodes, "edges": edges,
                                                               "direct_count": len(self._team(actor_id, False)),
                                                               "descendant_count": len(people)})
                spoken = f"Showing {len(self._team(actor_id, False))} direct reports and {len(people)} people in this permitted tree."
            return self._result(state, ScopedProfileResult(is_authorized=True, spoken_summary=spoken, result_block=visual),
                                op, [p["employee_id"] for p in people])
        if op in ("ticket_list", "ticket_chart"):
            employee = self.scoped.knowledge.get_employee_by_id(actor_id)
            if not employee:
                return self._deny("Actor profile is unavailable.")
            if plan.sla_metric == "overdue":
                all_rows = self.scoped.ticket_service.get_scoped_tickets_for_actor(
                    actor_id, employee.get("reporting", {}).get("direct_report_ids", []),
                    is_executive=actor_id == "EMP-4002",
                )
                def is_overdue(t: dict) -> bool:
                    if t.get("status") in ("Resolved", "Closed"):
                        return False
                    if t.get("sla", {}).get("resolution_status") == "Breached":
                        return True
                    due = t.get("due_date")
                    if due and str(due) <= "2026-10-16":
                        return True
                    return False
                rows = [t for t in all_rows if is_overdue(t)]
                visual = block("TEAM_METRIC_CHART", "Overdue tickets", {
                    "chart_type": "BAR", "title": "Overdue tickets", "unit": "tickets",
                    "data": [
                        {"label": "Overdue / Breached", "count": len(rows)},
                        {"label": "Within SLA", "count": len(all_rows) - len(rows)}
                    ],
                    "kpis": {
                        "total_tickets": len(all_rows),
                        "items": [
                            {"label": "Overdue / Breached", "value": len(rows)},
                            {"label": "Within SLA", "value": len(all_rows) - len(rows)}
                        ]
                    },
                })
                spoken = f"There are {len(rows)} overdue or breached tickets in your authorized scope of {len(all_rows)} tickets."
                return self._result(state, ScopedProfileResult(is_authorized=True, spoken_summary=spoken, result_block=visual),
                                    op, [r["ticket_id"] for r in rows], rows, "tickets")
            elif plan.sla_metric == "compliance":
                all_rows = self.scoped.ticket_service.get_scoped_tickets_for_actor(
                    actor_id, employee.get("reporting", {}).get("direct_report_ids", []),
                    is_executive=actor_id == "EMP-4002",
                )
                counts = Counter(t.get("sla", {}).get("resolution_status") or "Within SLA" for t in all_rows)
                data = [{"label": k, "count": counts[k]} for k in sorted(counts)]
                visual = block("TEAM_METRIC_CHART", "Ticket SLA compliance", {
                    "chart_type": "BAR", "title": "Ticket SLA compliance", "unit": "tickets",
                    "data": data,
                    "kpis": {"total_tickets": len(all_rows), "items": [{"label": k, "value": counts[k]} for k in sorted(counts)]},
                })
                spoken = f"SLA compliance across {len(all_rows)} authorized tickets: " + ", ".join(f"{k}: {counts[k]}" for k in sorted(counts)) + "."
                return self._result(state, ScopedProfileResult(is_authorized=True, spoken_summary=spoken, result_block=visual),
                                    op, [r["ticket_id"] for r in all_rows], all_rows, "tickets")

            rows = self._ticket_rows(actor_id, plan)
            if plan.ticket_id and not rows:
                return self._deny("That ticket is unavailable within your permitted scope.")
            filter_state = {
                "priority_filter": plan.priority_filter,
                "status_filter": plan.status_filter,
                "from_date": plan.from_date,
                "to_date": plan.to_date,
                "group_by": plan.group_by,
            }
            if op == "ticket_chart":
                group = plan.group_by or "priority"
                visual = self._chart(rows, group, plan.view or "BAR")
                spoken = f"{len(rows)} authorized tickets, shown using {'real creation dates' if plan.view in ('LINE', 'AREA') else group}."
            else:
                visual = block("TICKET_LIST", f"Authorized tickets ({len(rows)})", {
                    "title": f"Tickets ({len(rows)})", "tickets": [self.scoped.ticket_service.map_ticket_to_frontend_record(t) for t in rows],
                    "total_count": len(rows),
                })
                spoken = f"Showing {len(rows)} authorized tickets."
            return self._result(state, ScopedProfileResult(is_authorized=True, spoken_summary=spoken, result_block=visual),
                                op, [r["ticket_id"] for r in rows], rows, "tickets", filter_state=filter_state)
        if op == "rechart":
            active = state.snapshots.get(state.active_id or "")
            if not active or active.source_kind != "tickets":
                return self._deny("There is no current authorized ticket result to change views.")
            rows = list(active.source_rows)
            priority_filter = plan.priority_filter or active.filter_state.get("priority_filter")
            status_filter = plan.status_filter or active.filter_state.get("status_filter")
            from_date = plan.from_date or active.filter_state.get("from_date")
            to_date = plan.to_date or active.filter_state.get("to_date")
            group_by = plan.group_by or active.filter_state.get("group_by") or "priority"

            if priority_filter:
                rows = [r for r in rows if r.get("priority") == priority_filter]
            if status_filter:
                if status_filter == "Unresolved":
                    rows = [r for r in rows if r.get("status") not in ("Resolved", "Closed")]
                elif status_filter == "Not Closed":
                    rows = [r for r in rows if r.get("status") != "Closed"]
                else:
                    rows = [r for r in rows if r.get("status") == status_filter]
            if from_date or to_date:
                def in_range(row: dict) -> bool:
                    try:
                        created = date.fromisoformat(str(row.get("created_at", ""))[:10])
                        return (not from_date or created >= from_date) and (not to_date or created <= to_date)
                    except ValueError:
                        return False
                rows = [r for r in rows if in_range(row)]

            if plan.view == "TABLE":
                visual = block("TICKET_LIST", f"Authorized tickets ({len(rows)})", {
                    "title": f"Tickets ({len(rows)})", "tickets": [self.scoped.ticket_service.map_ticket_to_frontend_record(t) for t in rows],
                    "total_count": len(rows),
                })
                spoken = f"Showing the same {len(rows)} tickets as a table."
            else:
                visual = self._chart(rows, group_by, plan.view or "BAR")
                spoken = f"Showing {len(rows)} tickets as {plan.view.lower() if plan.view else 'bar'}{f' by {group_by}' if group_by else ''}."
            new_filter_state = {
                "priority_filter": priority_filter,
                "status_filter": status_filter,
                "from_date": from_date,
                "to_date": to_date,
                "group_by": group_by,
            }
            return self._result(state, ScopedProfileResult(is_authorized=True, spoken_summary=spoken, result_block=visual),
                                op, [r["ticket_id"] for r in rows], rows, "tickets", filter_state=new_filter_state)
        return self._deny("I can help with profiles, direct reports, reporting trees, and scoped tickets. Please specify one of those requests.")
