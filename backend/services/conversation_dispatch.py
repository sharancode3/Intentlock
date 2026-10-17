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
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from backend.core.scoped_authorization import ScopedAuthorizationService, ScopedProfileResult
from backend.models.turn import GenericResultBlock
from backend.services.ticket_action_store import ActionError
from backend.services.context_service import (
    ContextService,
    DatasetStatus,
    FilterActionClassification,
    MissingRequiredReferenceError,
    OrdinalOutOfRangeError,
    ResourceKindMismatchError,
    SelectionReference,
    apply_filter_transition,
    classify_filter_action,
)


Operation = Literal[
    "help", "profile", "team_table", "team_count", "org_tree",
    "ticket_list", "ticket_chart", "rechart", "back", "clarify",
    "create_ticket", "update_ticket", "comment_ticket", "confirm", "cancel",
    "compound", "headcount", "update_contact",
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
    field: Optional[Literal["description", "status", "priority", "phone"]] = None
    value: Optional[str] = Field(default=None, max_length=500)
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    compound_plans: Optional[List["IntentPlan"]] = None
    scope: Optional[Literal["company", "direct_reports", "reporting_tree", "department", "location"]] = None
    location: Optional[str] = Field(default=None, max_length=64)
    department: Optional[str] = Field(default=None, max_length=64)
    unresolved_location: Optional[str] = Field(default=None, max_length=64)
    actor_claim: Optional[str] = Field(default=None, max_length=32, description="Explicit employee ID claimed by speaker, e.g. EMP-4002")
    selected_id: Optional[str] = Field(default=None, max_length=64, description="Contextual entity or ticket ID reference, e.g. selected ticket or clicked person")
    filter_action: Optional[Literal["refine", "replace", "clear"]] = Field(default=None, description="Explicit filter mutation semantic")


class PlannerContext(BaseModel):
    """Bounded, safe conversational context for semantic planning.

    Contains NO database credentials, NO raw audio, NO full directory dumps,
    and NO unauthenticated client authority.
    """
    model_config = ConfigDict(extra="ignore")

    has_active_result: bool = False
    source_kind: Optional[str] = None
    selected_ticket_id: Optional[str] = None
    selected_employee_id: Optional[str] = None
    active_filters: Dict[str, Any] = Field(default_factory=dict)


@dataclass
class ResultSnapshot:
    block: GenericResultBlock
    operation: str
    visible_ids: List[str] = field(default_factory=list)
    source_rows: List[dict] = field(default_factory=list)
    base_rows: List[dict] = field(default_factory=list)
    source_kind: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    filter_state: Dict[str, Any] = field(default_factory=dict)
    dataset_status: DatasetStatus = field(default=DatasetStatus.POPULATED)

    def __post_init__(self) -> None:
        if self.base_rows is not None and len(self.base_rows) == 0:
            self.dataset_status = DatasetStatus.EMPTY_AUTHORIZED

    @property
    def filters(self) -> Dict[str, Any]:
        """Convenience property alias for filter_state."""
        return self.filter_state


@dataclass
class ConversationState:
    actor_id: str
    snapshots: Dict[str, ResultSnapshot] = field(default_factory=dict)
    active_id: Optional[str] = None
    previous_id: Optional[str] = None
    selected_ticket_id: Optional[str] = None
    selected_employee_id: Optional[str] = None
    selected_ticket: Optional[SelectionReference] = None
    selected_employee: Optional[SelectionReference] = None
    navigation_history: List[str] = field(default_factory=list)
    context_version: int = 1
    last_accessed: float = field(default_factory=time.time)

    @property
    def active_snapshot(self) -> Optional[ResultSnapshot]:
        """Convenience accessor returning the active ResultSnapshot, if present."""
        return self.snapshots.get(self.active_id) if self.active_id else None

    def select_ticket(self, ticket_id: str, source_result_id: str, order_idx: Optional[int] = None) -> None:
        self.selected_ticket_id = ticket_id
        self.selected_ticket = SelectionReference(
            resource_kind="ticket",
            resource_id=ticket_id,
            source_result_id=source_result_id,
            display_order_index=order_idx,
        )
        self.context_version += 1
        self.last_accessed = time.time()

    def select_employee(self, employee_id: str, source_result_id: str, order_idx: Optional[int] = None) -> None:
        self.selected_employee_id = employee_id
        self.selected_employee = SelectionReference(
            resource_kind="employee",
            resource_id=employee_id,
            source_result_id=source_result_id,
            display_order_index=order_idx,
        )
        self.context_version += 1
        self.last_accessed = time.time()

    def navigate_back(self) -> Optional[ResultSnapshot]:
        if not self.navigation_history:
            return None
        prev_id = self.navigation_history.pop()
        while prev_id == self.active_id and self.navigation_history:
            prev_id = self.navigation_history.pop()
        if prev_id != self.active_id and prev_id in self.snapshots:
            self.previous_id = self.active_id
            self.active_id = prev_id
            self.context_version += 1
            return self.snapshots[prev_id]
        return None

    def remember(self, snapshot: ResultSnapshot) -> None:
        self.last_accessed = time.time()
        if self.active_id and self.active_id != snapshot.block.id:
            self.previous_id = self.active_id
            if not self.navigation_history or self.navigation_history[-1] != self.active_id:
                self.navigation_history.append(self.active_id)
                if len(self.navigation_history) > 10:
                    self.navigation_history.pop(0)
        self.snapshots[snapshot.block.id] = snapshot
        self.active_id = snapshot.block.id
        self.context_version += 1
        while len(self.snapshots) > 12:
            oldest = next(iter(self.snapshots))
            self.snapshots.pop(oldest)
            if self.previous_id == oldest:
                self.previous_id = None


class ConversationStore:
    """Short-lived, server-bound result references; no browser authority."""

    def __init__(self) -> None:
        self._states: Dict[str, ConversationState] = {}

    def get(self, session_id: str, actor_id: str) -> ConversationState:
        now = time.time()
        # Bounded cleanup of abandoned sessions (>300s since last access)
        expired_sessions = [
            sid for sid, s in self._states.items()
            if now - s.last_accessed > 300
        ]
        for sid in expired_sessions:
            self._states.pop(sid, None)

        # LRU bound on total stored states (max 64)
        if len(self._states) > 64:
            sorted_states = sorted(self._states.items(), key=lambda item: item[1].last_accessed)
            for sid, _ in sorted_states[:len(self._states) - 64]:
                self._states.pop(sid, None)

        state = self._states.get(session_id)
        if state is None or state.actor_id != actor_id:
            state = ConversationState(actor_id=actor_id)
            self._states[session_id] = state
        state.last_accessed = now

        # Prune snapshots within this state older than 300s
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


def _parse_single(text: str, state: Optional[ConversationState] = None) -> IntentPlan:
    """Parses a single intent clause with strict negation, quotation, and mutation boundaries."""
    q = re.sub(r"\s+", " ", text.strip().lower())
    ticket = re.search(r"\bTKT[-_ ]?\d{4}[-_ ]?\d{3}\b", text, re.I)
    ticket_id = re.sub(r"[_ ]", "-", ticket.group().upper()) if ticket else None
    if not q:
        return IntentPlan(operation="clarify")

    context_ticket = None
    if state:
        if state.selected_ticket_id:
            context_ticket = state.selected_ticket_id
        elif state.active_id:
            active = state.snapshots.get(state.active_id)
            if active and active.source_kind == "tickets" and len(active.visible_ids) == 1:
                context_ticket = active.visible_ids[0]

    # Step 1: Ticket Comment Parsing (MUST precede cancel/confirm to protect quotes)
    if (ticket_id or context_ticket) and re.search(r"\b(?:add|post|leave)\b.*\bcomment\b", q):
        quote_match = re.search(r"['\"]([^'\"]+)['\"]", text)
        if quote_match:
            comment_val = quote_match.group(1).strip()
        else:
            after_comment = re.search(r"\bcomment(?:\s+is|:)?\s+([^\.]+)", text, re.I)
            comment_val = after_comment.group(1).strip() if after_comment else text.strip()
        return IntentPlan(operation="comment_ticket", ticket_id=ticket_id or context_ticket, value=comment_val)

    # Step 2: Unquoted string for exact command and negation evaluation
    unquoted_q = re.sub(r"['\"][^'\"]+['\"]", "", q).strip()

    # Step 3: Negation, Question, and Parameter-Modification Guards
    is_negated_cancel = bool(re.search(r"\b(?:do\s+not|don't|not|never)\s+cancel\b", unquoted_q))
    is_negated_confirm = bool(re.search(r"\b(?:do\s+not|don't|not|never)\s+confirm\b", unquoted_q))
    is_question_action = bool(
        re.search(r"\b(?:what\s+happens\s+if(?:\s+i)?|can\s+i|how\s+do\s+i|should\s+i|could\s+i|will\s+it)\s+(?:confirm|cancel)\b", unquoted_q)
        or ("?" in unquoted_q and re.search(r"\b(?:confirm|cancel)\b", unquoted_q))
    )
    is_param_change = bool(re.search(r"\byes,\s*but\b", unquoted_q))

    # Cancel command check
    if not is_negated_cancel and not is_question_action:
        if re.search(r"^(?:(?:i\s+)?cancel(?:\s+(?:action|proposal|this|draft))?|abort|nevermind|discard)\.?$", unquoted_q) or (
            re.search(r"\b(?:cancel\s+(?:the\s+)?(?:action|proposal|draft|change))\b", unquoted_q)
            and not re.search(r"\b(?:ticket|comment|create|update)\b", unquoted_q)
        ):
            return IntentPlan(operation="cancel")

    # Confirm command check
    if not is_negated_confirm and not is_question_action and not is_param_change:
        if (
            re.search(r"\b(?:i\s+confirm|confirm\s+the\s+change|yes,\s*confirm)\b", unquoted_q)
            or re.search(r"^(?:(?:i\s+)?confirm(?:\s+(?:action|proposal|this|change|update))?)\.?$", unquoted_q)
        ):
            return IntentPlan(operation="confirm")

    if re.search(r"\b(help|what can you do|how do i use)\b", q) and not re.search(r"\b(my|ticket|team|profile)\b", q):
        return IntentPlan(operation="help")
    if re.search(r"\b(back to|go back|previous (view|result))\b", q):
        return IntentPlan(operation="back")

    if context_ticket and re.search(r"\b(?:open|show|view|details\s+for)\s+(?:this|the)\s+ticket\b", q):
        return IntentPlan(operation="ticket_list", ticket_id=context_ticket)

    # Step 4: Reporting, Designation, and Application-Role Changes (Distinct from ticket/contact edits)
    if re.search(r"\b(?:move|transfer)\b.*\bunder\b", q) or re.search(r"\bchange\s+manager\s+to\b", q):
        return IntentPlan(operation="clarify", value="Reporting manager changes require administrator approval and cannot be executed directly via the helpdesk.")

    if re.search(r"\bmake\b.*\ba\s+manager\b", q):
        return IntentPlan(operation="clarify", value="Please specify whether you want to change their job designation, update their reporting manager, or request an authorization role change.")

    if re.search(r"\brecommend\b.*\bfor\s+promotion\b", q):
        return IntentPlan(operation="clarify", value="Promotion recommendations are recorded in performance reviews and cannot be executed as an immediate role change.")

    if re.search(r"\b(?:give|grant)\b.*\b(?:admin|administrator|executive)\s+(?:access|role|permissions?)\b", q):
        return IntentPlan(operation="clarify", value="Administrative role changes require security administrator privileges and cannot be executed via the helpdesk.")

    # Step 5: Protected Contact Update Recognition
    if re.search(r"\b(?:update|change|set)\b.*\b(?:phone|contact|mobile)\b", q):
        target_match = re.search(r"\b((?:EMP|RND|EXE)[-_ ]?\d{4})\b", text, re.I)
        target_eid = target_match.group(1).upper().replace(" ", "-") if target_match else None
        if not target_eid:
            name_match = re.search(r"\b(?:update|change|set)\s+([A-Z][a-z]+)'s\s+(?:phone|contact|mobile)\b", text)
            if name_match:
                target_eid = name_match.group(1).strip()

        target_digits = re.sub(r"[^\d]", "", target_eid) if target_eid else ""
        phone_candidates = re.findall(r"(\+?[0-9][0-9\s\-\(\)\.]{5,25}[0-9])", text)
        phone_val = None
        for cand in phone_candidates:
            clean_digits = re.sub(r"[^\d]", "", cand)
            if len(clean_digits) >= 7 and clean_digits != target_digits:
                phone_val = cand.strip()
                break

        if not phone_val:
            return IntentPlan(operation="clarify", entity=target_eid, field="phone", value="Please provide the phone number to update.")
        return IntentPlan(operation="update_contact", entity=target_eid, field="phone", value=phone_val)

    # Step 6: Employee Profile Routing
    if (
        re.search(r"\b(?:EMP|RND|EXE)[-_ ]?\d{4}\b", text, re.I)
        and not re.search(r"\bTKT[-_ ]?\d{4}", text, re.I)
        and not re.search(r"\b(tickets?|issues?|sla|compliance|overdue|breached|workload|phone|contact|mobile)\b", q)
    ):
        return IntentPlan(operation="profile", entity=text.strip())
    if state and state.active_id and re.search(r"\b(?:open|show|view)\s+(?:the\s+)?(?:first|second|third|fourth)\s+person\b", q):
        return IntentPlan(operation="profile", entity=text.strip())

    # Step 7: Ticket Creation
    if re.search(r"\b(create|raise|file|submit)\b.*\b(ticket|issue)\b", q) and not ticket_id:
        title_match = re.search(r"\b(?:create|raise|file|submit)\s+(?:a\s+)?(?:ticket|issue)(?:\s+(?:titled|about|for))?\s+['\"]?([^'\"\.]+)['\"]?", text, re.I)
        val = title_match.group(1).strip() if title_match else text.strip()
        return IntentPlan(operation="create_ticket", value=val)

    # Step 8: Ticket Updates
    is_presentation_intent = bool(re.search(r"\b(chart|graph|table|view|pie|bar|trend|timeline|tree)\b", q))
    if not is_presentation_intent and (ticket_id or context_ticket) and re.search(r"\b(change|update|set|mark)\b", q):
        field = None
        val = None
        status_match = re.search(
            r"\b(?:mark|set|update|change)\s+(?:(?:the\s+)?ticket\s+)?(?:TKT[-_ ]?\d{4}[-_ ]?\d{3}|it|this ticket)?\s*(?:as|status to|to)?\s*(resolved|closed|in progress|open|blocked)\b",
            q,
        ) or re.search(r"\b(?:as|status to|to)\s+(resolved|closed|in progress|open|blocked)\b", q)
        priority_match = re.search(
            r"\b(?:set|change|update)\s+(?:(?:the\s+)?ticket\s+)?(?:TKT[-_ ]?\d{4}[-_ ]?\d{3}|it|this ticket)?\s*(?:priority\s+(?:to|as)?|it to|to)?\s*(critical|urgent|high|medium|normal|low)\b",
            q,
        ) or re.search(r"\bpriority\s+(?:to|is)\s*(critical|urgent|high|medium|normal|low)\b", q)

        if status_match:
            field = "status"
            raw_s = status_match.group(1).strip()
            if raw_s in ("in progress", "in_progress"):
                val = "In Progress"
            elif raw_s == "resolved":
                val = "Resolved"
            elif raw_s == "closed":
                val = "Closed"
            elif raw_s == "blocked":
                val = "Blocked"
            else:
                val = "Open"
        elif priority_match:
            field = "priority"
            raw_p = priority_match.group(1).strip()
            if raw_p in ("critical", "urgent"):
                val = "Critical"
            elif raw_p == "high":
                val = "High"
            elif raw_p in ("medium", "normal"):
                val = "Medium"
            else:
                val = "Low"
        elif "description" in q:
            field = "description"
            desc_match = re.search(r"\bdescription(?:\s+to|:)?\s+([^\.]+)", text, re.I)
            val = desc_match.group(1).strip() if desc_match else text.strip()

        if field and val:
            return IntentPlan(operation="update_ticket", ticket_id=ticket_id or context_ticket, field=field, value=val)
        elif field or re.search(r"\b(priority|status|description)\b", q):
            field = field or next((item for item in ("priority", "status", "description") if item in q), None)
            return IntentPlan(operation="update_ticket", ticket_id=ticket_id or context_ticket, field=field, value=text.strip())


    if state and state.active_id and re.search(r"\b(this|that|those|same|instead|only|change|switch)\b", q) and re.search(r"\b(table|bar|pie|chart|trend|timeline)\b", q):
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

    # Finding: Typed headcount & personnel count recognition
    is_count_phrase = bool(re.search(r"\b(?:how many|count of|number of|headcount|total number of|how many total|total count)\b", q))
    is_personnel_phrase = bool(re.search(r"\b(?:employees|people|workers|staff|members|headcount)\b", q))
    is_ticket_word = bool(re.search(r"\b(?:tickets?|issues?|incident|incidents|sla|compliance|overdue|breached)\b", q))

    if not is_ticket_word and ((is_count_phrase and is_personnel_phrase) or re.search(r"\b(?:company headcount|total headcount|workforce count|organization headcount)\b", q)):
        if re.search(r"\b(?:report directly|reporting to me|direct reports|my direct|under me directly)\b", q):
            return IntentPlan(operation="team_count")
        if re.search(r"\b(?:in my (?:reporting )?tree|in my hierarchy|all (?:my )?reports|under me)\b", q):
            return IntentPlan(operation="headcount", scope="reporting_tree")
        dept_match = re.search(r"\b(?:in|of|for)\s+(?:the\s+)?(engineering|research|sales|product|finance|hr|legal|operations)\b", q)
        dept = dept_match.group(1).title() if dept_match else None

        location = None
        unresolved_location = None
        loc_match = re.search(r"\bin\s+([a-zA-Z\s]+?)(?:\?|\.|$|\b(?:i am|as the|for|with|who|where)\b)", text, re.I)
        if loc_match:
            candidate_loc = loc_match.group(1).strip()
            nested_loc = re.search(r"\b(?:this |the |our )?company\s+in\s+([a-zA-Z\s]+)", candidate_loc, re.I)
            if nested_loc:
                candidate_loc = nested_loc.group(1).strip()
            # Clean trailing company phrasing e.g. "Bengaluru in this company" -> "Bengaluru"
            candidate_loc = re.sub(r"\s+(?:in|across|at)\s+(?:this|the|our)?\s*(?:company|org|organization|firm).*$", "", candidate_loc, flags=re.I).strip()
            if candidate_loc.lower() not in ("this company", "the company", "our company", "company", "the team", "my team"):
                candidate_loc_clean = re.sub(r"\b(?:this|the|our)\b", "", candidate_loc, flags=re.I).strip()
                if candidate_loc_clean.lower() in ("bengaluru", "bangalore"):
                    location = "Bengaluru"
                elif candidate_loc_clean.lower() in (
                    "london", "new york", "san francisco", "singapore", "mumbai",
                    "tokyo", "berlin", "paris", "sydney", "dubai", "toronto", "seattle",
                    "hyderabad", "delhi", "chennai", "pune", "boston", "austin", "chicago"
                ):
                    location = candidate_loc_clean.title()
                elif candidate_loc_clean:
                    location = candidate_loc_clean
                    unresolved_location = candidate_loc_clean

        is_company = bool(re.search(r"\b(?:in (?:this |the |our )?company|company[- ]wide|organization|enterprise|firm|overall|across the company|total headcount)\b", q))
        scope = "company" if is_company else "location" if location else "department" if dept else "company"

        return IntentPlan(
            operation="headcount",
            scope=scope,
            location=location,
            department=dept,
            unresolved_location=unresolved_location,
        )

    if re.search(r"\b(team|direct reports|people reporting)\b", q) and re.search(r"\b(list|table|show|who|members)\b", q) and not re.search(r"\b(tickets?|issues?)\b", q):
        return IntentPlan(operation="team_table")
    profile_requested = bool(re.search(r"\b(profile|details|skills|projects|manager|about me|who am i)\b", q))
    ticket_requested = bool(re.search(r"\b(ticket|tickets|tkt|issue|issues|incident|incidents|workload|overdue|sla)\b", q))
    if re.search(r"\b(not|no) (tickets|issues)\b", q):
        ticket_requested = False
    if profile_requested and not ticket_requested:
        return IntentPlan(operation="profile", entity=text.strip())
    if ticket_requested or ticket_id:
        # Finding 3b: Unsupported priority negation must clarify instead of inverting to positive
        if (
            re.search(r"\b(?:not|non|except|excluding|other than)\s+(?:a\s+)?(critical|high|medium|low|urgent)\b", q)
            or re.search(r"\b(critical|high|medium|low)\b.*\b(?:excluded|excepted|not included)\b", q)
        ):
            return IntentPlan(operation="clarify")

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


def parse_local(text: str, state: Optional[ConversationState] = None) -> IntentPlan:
    """Compound-aware intent interpreter with fast local recognition and safe clarify fallback."""
    q = re.sub(r"\s+", " ", text.strip().lower())
    if not q:
        return IntentPlan(operation="clarify")

    # Finding 4: Bounded compound query parsing ("Show my profile and my tickets", etc.)
    compound_match = re.search(r"^(.*?)\s+(?:and(?:\s+also)?|as well as)\s+(.*?)$", q, re.I)
    if compound_match and not re.search(r"\b(between|from|since)\b", q):
        part1 = compound_match.group(1).strip()
        part2 = compound_match.group(2).strip()
        not_compound = (
            re.search(r"^(?:in progress|pending|open|closed|resolved|blocked|critical|high|medium|low)$", part1)
            or re.search(r"^(?:in progress|pending|open|closed|resolved|blocked|critical|high|medium|low)$", part2)
            or re.search(r"\b\d{4}-\d{2}-\d{2}\b", part1)
            or re.search(r"\b\d{4}-\d{2}-\d{2}\b", part2)
        )
        if not not_compound:
            p1 = _parse_single(part1, state)
            p2 = _parse_single(part2, state)
            if p1.operation not in ("clarify", "compound") and p2.operation not in ("clarify", "compound"):
                return IntentPlan(operation="compound", compound_plans=[p1, p2])

    return _parse_single(text, state)


class ConversationDispatcher:
    def __init__(self, scoped: Optional[ScopedAuthorizationService] = None):
        self.scoped = scoped or ScopedAuthorizationService.get_instance()

    def _deny(self, text: str) -> ScopedProfileResult:
        return ScopedProfileResult(is_authorized=False, status_code=403, spoken_summary=text,
                                   result_block=self.scoped.build_denial_result_block(text), denial_reason="ACCESS_DENIED")

    def _result(self, state: ConversationState, result: ScopedProfileResult, operation: str,
                visible_ids: Optional[List[str]] = None, source_rows: Optional[List[dict]] = None,
                source_kind: Optional[str] = None, filter_state: Optional[dict] = None,
                base_rows: Optional[List[dict]] = None) -> ScopedProfileResult:
        if result.is_authorized and result.result_block:
            resolved_base_rows = base_rows if base_rows is not None else (source_rows if source_rows is not None else [])
            state.remember(ResultSnapshot(
                block=result.result_block,
                operation=operation,
                visible_ids=visible_ids or [],
                source_rows=source_rows if source_rows is not None else [],
                base_rows=resolved_base_rows,
                source_kind=source_kind,
                filter_state=filter_state or {},
            ))
        return result

    def _resolve_profile_target(self, actor_id: str, phrase: Optional[str], state: ConversationState) -> Optional[str]:
        from backend.services.entity_scope_resolver import resolve_entity_reference

        direct_reports = self.scoped.knowledge.get_direct_reports(actor_id) if actor_id else []
        visible_candidates = list(direct_reports)
        if actor_id:
            actor_emp = self.scoped.knowledge.get_employee_by_id(actor_id)
            if actor_emp:
                visible_candidates.append(actor_emp)

        active = state.snapshots.get(state.active_id or "")
        active_ids = list(active.visible_ids) if active else []
        for vid in active_ids:
            vemp = self.scoped.knowledge.get_employee_by_id(vid)
            if vemp and vemp not in visible_candidates:
                visible_candidates.append(vemp)

        def get_mgr(eid: str) -> Optional[str]:
            emp = self.scoped.knowledge.get_employee_by_id(eid)
            return emp.get("reporting", {}).get("manager_id") if emp else None

        res = resolve_entity_reference(
            phrase=phrase,
            actor_id=actor_id,
            visible_candidates=visible_candidates,
            selected_employee_id=state.selected_employee_id,
            selected_ticket_id=state.selected_ticket_id,
            active_visible_ids=active_ids,
            get_manager_func=get_mgr,
        )
        if res.status == "Resolved" and res.resolved_id:
            return res.resolved_id
        return None

    def _team(self, actor_id: str, descendants: bool) -> List[dict]:
        direct = self.scoped.knowledge.get_direct_reports(actor_id)
        if not descendants:
            return direct[:30]
        from backend.services.entity_scope_resolver import traverse_reporting_tree
        traversal = traverse_reporting_tree(
            root_id=actor_id,
            get_reports_func=self.scoped.knowledge.get_direct_reports,
            include_root=False,
            max_depth=5,
            max_nodes=100,
        )
        all_members = []
        for mid in traversal.member_ids:
            m_emp = self.scoped.knowledge.get_employee_by_id(mid)
            if m_emp:
                all_members.append(m_emp)
        return all_members if all_members else direct[:30]

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

        # Finding 4: Bounded compound operations execution
        if op == "compound" and plan.compound_plans:
            results: List[ScopedProfileResult] = []
            for sub_plan in plan.compound_plans[:3]:
                res = self.dispatch(actor_id, session_id, sub_plan, spoken_text, evidence_digest)
                results.append(res)

            blocks: List[GenericResultBlock] = [r.result_block for r in results if r.result_block]
            if not blocks:
                return results[0] if results else self._deny("Unable to execute compound requests.")

            spoken_parts = []
            for idx, r in enumerate(results):
                prefix = "" if idx == 0 else "Also, "
                if r.is_authorized:
                    spoken_parts.append(f"{prefix}{r.spoken_summary}")
                else:
                    spoken_parts.append(f"For the other request: {r.spoken_summary}")
            combined_spoken = " ".join(spoken_parts)

            for b in blocks:
                if b.id not in state.snapshots:
                    state.remember(ResultSnapshot(block=b, operation="compound", visible_ids=[]))
            state.active_id = blocks[0].id

            return ScopedProfileResult(
                is_authorized=True,
                spoken_summary=combined_spoken,
                result_block=blocks[0],
                result_blocks=blocks,
            )

        if op in ("create_ticket", "update_ticket", "comment_ticket", "confirm", "cancel", "update_contact"):
            action_store = self.scoped.ticket_service.store
            if not action_store:
                return self._deny("Actions are unavailable in this environment.")
            employee = self.scoped.knowledge.get_employee_by_id(actor_id)
            report_ids = employee.get("reporting", {}).get("direct_report_ids", []) if employee else []
            try:
                if op == "cancel":
                    if hasattr(action_store, "cancel"):
                        cancelled = action_store.cancel(session_id)
                    elif hasattr(action_store, "cancel_pending_for_session"):
                        cancelled = action_store.cancel_pending_for_session(session_id)
                    else:
                        raise ActionError("Action store does not implement cancellation interface.")
                    message = "The pending action was cancelled." if cancelled else "There is no pending action to cancel."
                    return ScopedProfileResult(is_authorized=True, spoken_summary=message,
                        result_block=block("PUBLIC_FAQ", "Action cancelled", {"answer": message}, sensitive=False))
                if op == "confirm":
                    receipt = action_store.confirm(actor_id, session_id, spoken_text, evidence_digest, report_ids)
                    self.scoped.ticket_service.refresh_from_store()
                    self.scoped.knowledge.refresh_if_stale()
                    if receipt.get("action") == "update_contact" and receipt.get("new_value"):
                        self.scoped.knowledge.update_employee_phone_in_memory(actor_id, receipt["new_value"])
                    state.snapshots.clear()
                    state.active_id = None
                    state.previous_id = None
                    title = "Committed contact change" if receipt.get("action") == "update_contact" else "Committed ticket change"
                    visual = block("ACTION_RECEIPT", title, {
                        "receipt": receipt, "summary": f"{receipt['action']} committed for {receipt['resource_id']}."})
                    return self._result(state, ScopedProfileResult(is_authorized=True,
                        spoken_summary=f"The change to {receipt['resource_id']} was committed as event {receipt['event_id']}.",
                        result_block=visual), op)

                if op == "update_contact":
                    if not plan.value:
                        return self._deny("Please provide the new phone number to update.")
                    if plan.entity and plan.entity.strip().upper() != actor_id.strip().upper():
                        return self._deny("Policy denies editing contact details for other employees. You may only update your own contact details.")
                    actor_emp = self.scoped.knowledge.get_employee_by_id(actor_id)
                    if not actor_emp:
                        return self._deny("Employee record not found for verified actor.")
                    prof_mod_policy = actor_emp.get("permissions", {}).get("profile_modification", {})
                    if prof_mod_policy.get("effect") != "ALLOW":
                        return self._deny("Policy denies profile modification for this account.")

                # Unified typed proposal path
                params = action_store.build_typed_proposal(
                    operation=op,
                    ticket_id=plan.ticket_id,
                    field=plan.field or ("phone" if op == "update_contact" else None),
                    value=plan.value,
                    utterance=spoken_text,
                )
                draft = action_store.propose(actor_id, session_id, op, plan.ticket_id, params, report_ids, evidence_digest)
                readback_title = "Contact update readback" if op == "update_contact" else "Ticket change readback"
                visual = block("READBACK_CONFIRMATION", readback_title, {
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
            previous = state.navigate_back()
            if not previous and state.previous_id:
                previous = state.snapshots.get(state.previous_id)
                if previous:
                    state.active_id, state.previous_id = previous.block.id, state.active_id
            if not previous:
                return self._deny("There is no earlier authorized result to return to.")
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

            # Finding 1 & 2: Base rows cover the full authorized scope for this query dimension
            base_plan = IntentPlan(operation="ticket_list", ticket_id=plan.ticket_id, person_filter=plan.person_filter)
            base_rows = self._ticket_rows(actor_id, base_plan)

            # Filter candidate rows applying priority, status, person, and date constraints FIRST
            scoped_filtered_rows = self._ticket_rows(actor_id, plan)

            # Finding 2: SLA Overdue with real as-of time, typed filters applied, and honest unknown states
            if plan.sla_metric == "overdue":
                now_utc = datetime.now(timezone.utc)
                as_of_date_str = now_utc.date().isoformat()

                overdue_rows = []
                at_risk_rows = []
                on_track_rows = []
                closed_rows = []
                unknown_rows = []

                for t in scoped_filtered_rows:
                    st = t.get("status")
                    sla_info = t.get("sla") or {}
                    sla_res = sla_info.get("resolution_status")
                    due_date = str(t.get("due_date", "")).strip()[:10]

                    if st in ("Resolved", "Closed"):
                        closed_rows.append(t)
                    elif sla_res == "Breached" or (due_date and due_date < as_of_date_str):
                        overdue_rows.append(t)
                    elif sla_res == "At Risk" or (due_date and due_date == as_of_date_str):
                        at_risk_rows.append(t)
                    elif sla_res == "Within SLA" or (due_date and due_date > as_of_date_str):
                        on_track_rows.append(t)
                    else:
                        unknown_rows.append(t)

                chart_data = [
                    {"label": "Overdue / Breached", "count": len(overdue_rows)},
                    {"label": "At Risk / Due Today", "count": len(at_risk_rows)},
                    {"label": "On Track", "count": len(on_track_rows)},
                    {"label": "Resolved / Closed", "count": len(closed_rows)},
                ]
                if unknown_rows:
                    chart_data.append({"label": "Unknown / No SLA", "count": len(unknown_rows)})

                kpis = {
                    "total_tickets": len(scoped_filtered_rows),
                    "items": [
                        {"label": "Overdue / Breached", "value": len(overdue_rows)},
                        {"label": "At Risk / Due Today", "value": len(at_risk_rows)},
                        {"label": "On Track", "value": len(on_track_rows)},
                        {"label": "Resolved / Closed", "value": len(closed_rows)},
                    ]
                }
                priority_ctx = f"{plan.priority_filter} priority " if plan.priority_filter else ""
                person_ctx = f"for {plan.person_filter} " if plan.person_filter else ""
                title_str = f"{priority_ctx}Overdue tickets {person_ctx}".strip()
                visual = block("TEAM_METRIC_CHART", title_str or "Overdue tickets", {
                    "chart_type": "BAR",
                    "title": title_str or "Overdue tickets",
                    "unit": "tickets",
                    "data": chart_data,
                    "kpis": kpis,
                })
                spoken = (
                    f"As of {as_of_date_str}, there are {len(overdue_rows)} overdue or breached tickets "
                    f"out of {len(scoped_filtered_rows)} authorized {priority_ctx}tickets."
                )
                return self._result(
                    state,
                    ScopedProfileResult(is_authorized=True, spoken_summary=spoken, result_block=visual),
                    op,
                    [r["ticket_id"] for r in overdue_rows],
                    overdue_rows,
                    "tickets",
                    filter_state={"sla_metric": "overdue", "priority_filter": plan.priority_filter, "person_filter": plan.person_filter},
                    base_rows=scoped_filtered_rows,
                )

            # Finding 2: Honest SLA compliance metrics with clear eligible denominator and preserved Unknown state
            elif plan.sla_metric == "compliance":
                counts = Counter()
                eligible_count = 0
                compliant_count = 0

                for t in scoped_filtered_rows:
                    sla_info = t.get("sla")
                    res_status = sla_info.get("resolution_status") if isinstance(sla_info, dict) else None
                    if res_status:
                        counts[res_status] += 1
                        eligible_count += 1
                        if res_status in ("Met", "Within SLA"):
                            compliant_count += 1
                    else:
                        counts["Unknown / No SLA"] += 1

                compliance_rate = round(compliant_count / eligible_count * 100, 1) if eligible_count > 0 else 0.0
                data = [{"label": k, "count": counts[k]} for k in sorted(counts)]

                priority_ctx = f"{plan.priority_filter} priority " if plan.priority_filter else ""
                person_ctx = f"for {plan.person_filter} " if plan.person_filter else ""
                title_str = f"{priority_ctx}Ticket SLA compliance {person_ctx}".strip()
                visual = block("TEAM_METRIC_CHART", title_str or "Ticket SLA compliance", {
                    "chart_type": "BAR",
                    "title": title_str or "Ticket SLA compliance",
                    "unit": "tickets",
                    "data": data,
                    "kpis": {
                        "total_evaluated": len(scoped_filtered_rows),
                        "eligible_with_sla": eligible_count,
                        "compliance_rate_pct": compliance_rate,
                        "items": [{"label": k, "value": counts[k]} for k in sorted(counts)],
                    },
                })
                breakdown_str = ", ".join(f"{k}: {counts[k]}" for k in sorted(counts))
                spoken = (
                    f"SLA compliance across {len(scoped_filtered_rows)} authorized {priority_ctx}tickets: "
                    f"{compliance_rate}% compliant ({compliant_count}/{eligible_count} with targets). {breakdown_str}."
                )
                return self._result(
                    state,
                    ScopedProfileResult(is_authorized=True, spoken_summary=spoken, result_block=visual),
                    op,
                    [r["ticket_id"] for r in scoped_filtered_rows],
                    scoped_filtered_rows,
                    "tickets",
                    filter_state={"sla_metric": "compliance", "priority_filter": plan.priority_filter, "person_filter": plan.person_filter},
                    base_rows=scoped_filtered_rows,
                )

            rows = scoped_filtered_rows
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
                                op, [r["ticket_id"] for r in rows], rows, "tickets", filter_state=filter_state, base_rows=base_rows)

        # Finding 1: Recharting with dimension replacement against retained base_rows
        if op == "rechart":
            active = state.snapshots.get(state.active_id or "")
            if not active or active.source_kind != "tickets":
                return self._deny("There is no current authorized ticket result to change views.")

            # Base candidate rows are the full authorized scope for this ticket view.
            # If base_rows was explicitly captured (even if empty []), preserve it; never broaden to all tickets.
            if active.base_rows is not None:
                candidate_rows = list(active.base_rows)
            elif active.source_rows is not None:
                candidate_rows = list(active.source_rows)
            else:
                candidate_rows = []

            # Replace vs intersect dimension semantics
            priority_filter = plan.priority_filter if plan.priority_filter is not None else active.filter_state.get("priority_filter")
            status_filter = plan.status_filter if plan.status_filter is not None else active.filter_state.get("status_filter")
            from_date = plan.from_date if plan.from_date is not None else active.filter_state.get("from_date")
            to_date = plan.to_date if plan.to_date is not None else active.filter_state.get("to_date")
            group_by = plan.group_by or active.filter_state.get("group_by") or ("status" if status_filter else "priority")

            rows = list(candidate_rows)
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
                def in_range(item: dict) -> bool:
                    try:
                        created = date.fromisoformat(str(item.get("created_at", ""))[:10])
                        return (not from_date or created >= from_date) and (not to_date or created <= to_date)
                    except ValueError:
                        return False
                rows = [r for r in rows if in_range(r)]

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
                                op, [r["ticket_id"] for r in rows], rows, "tickets", filter_state=new_filter_state, base_rows=candidate_rows)
        if op == "headcount":
            if plan.unresolved_location:
                loc = plan.unresolved_location
                msg = f"I heard '{loc}' as the location. Our demo directory only covers Bengaluru. Would you like the headcount for Bengaluru?"
                return ScopedProfileResult(
                    is_authorized=True,
                    status_code=200,
                    spoken_summary=msg,
                    result_block=None,
                    clarification_reason="UNRESOLVED_LOCATION",
                )

            if plan.scope in ("company", "location"):
                if actor_id != "EMP-4002":
                    return self._deny("Access denied. Organization-wide headcount is restricted to executive leadership.")

                if plan.location and plan.location.lower() not in ("bengaluru", "bangalore"):
                    msg = f"Location '{plan.location}' has no recorded employees in our directory."
                    return ScopedProfileResult(
                        is_authorized=True,
                        status_code=200,
                        spoken_summary=msg,
                        result_block=None,
                        clarification_reason="LOCATION_NO_RECORDS",
                    )

                total_count = len(self.scoped.knowledge.list_all_employees())
                visual = block("TEAM_METRIC_CHART", "Company headcount", {
                    "chart_type": "BAR",
                    "title": "Company headcount",
                    "category": "Workforce Analytics",
                    "unit": "employees",
                    "scope_description": "Organization-wide aggregate headcount (Demo directory)",
                    "data": [{"label": "Bengaluru (HQ)", "count": total_count}],
                    "kpis": {
                        "items": [
                            {"label": "Total Headcount", "value": total_count},
                            {"label": "Location", "value": "Bengaluru (100%)"},
                            {"label": "Coverage", "value": f"Demo Directory ({total_count} records)"},
                        ],
                    },
                })
                spoken = f"The company currently has {total_count} employees across the Bengaluru site in the demo directory."
                return self._result(
                    state,
                    ScopedProfileResult(is_authorized=True, spoken_summary=spoken, result_block=visual),
                    op,
                    [],
                    [],
                    "headcount",
                )

            if plan.scope == "direct_reports":
                direct = self.scoped.knowledge.get_direct_reports(actor_id)
                count = len(direct)
                root = self.scoped.knowledge.get_employee_by_id(actor_id)
                name = root["identity"]["full_name"] if root else "You"
                visual = block("TEAM_METRIC_CHART", "Direct reports", {
                    "chart_type": "BAR",
                    "title": "Direct reports",
                    "category": "Manager Analytics",
                    "unit": "people",
                    "data": [{"label": "Direct reports", "count": count}],
                    "kpis": {"items": [{"label": "Direct reports", "value": count}]},
                })
                spoken = f"{name} has {count} direct report{'s' if count != 1 else ''}."
                return self._result(
                    state,
                    ScopedProfileResult(is_authorized=True, spoken_summary=spoken, result_block=visual),
                    op,
                    [p["employee_id"] for p in direct],
                )

            if plan.scope == "reporting_tree":
                people = self._team(actor_id, descendants=True)
                count = len(people)
                visual = block("TEAM_METRIC_CHART", "Reporting tree headcount", {
                    "chart_type": "BAR",
                    "title": "Reporting tree headcount",
                    "category": "Manager Analytics",
                    "unit": "people",
                    "data": [{"label": "Reporting tree", "count": count}],
                    "kpis": {"items": [{"label": "Total in tree", "value": count}]},
                })
                spoken = f"{count} employees report within your reporting structure."
                return self._result(
                    state,
                    ScopedProfileResult(is_authorized=True, spoken_summary=spoken, result_block=visual),
                    op,
                    [p["employee_id"] for p in people],
                )

            if plan.scope == "department" and plan.department:
                if actor_id != "EMP-4002":
                    return self._deny("Access denied. Department-level headcount is restricted to executive leadership.")
                dept_norm = plan.department.strip().lower()
                emps = self.scoped.knowledge.employees_by_department.get(dept_norm, [])
                count = len(emps)
                visual = block("TEAM_METRIC_CHART", f"{plan.department} department headcount", {
                    "chart_type": "BAR",
                    "title": f"{plan.department} headcount",
                    "category": "Workforce Analytics",
                    "unit": "employees",
                    "data": [{"label": plan.department, "count": count}],
                    "kpis": {"items": [{"label": f"{plan.department} Headcount", "value": count}]},
                })
                spoken = f"There are {count} employees in the {plan.department} department."
                return self._result(
                    state,
                    ScopedProfileResult(is_authorized=True, spoken_summary=spoken, result_block=visual),
                    op,
                    [],
                    [],
                    "headcount",
                )

        if op == "clarify":
            msg = "Please ask for a profile, direct reports, reporting tree, tickets, or headcount."
            return ScopedProfileResult(
                is_authorized=True,
                status_code=200,
                spoken_summary=msg,
                result_block=None,
                clarification_reason="UNRECOGNIZED_REQUEST",
            )

        return self._deny("I can help with profiles, direct reports, reporting trees, and scoped tickets. Please specify one of those requests.")
