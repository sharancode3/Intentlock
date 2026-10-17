"""
backend/services/query_fact_service.py
Person 2 — Authorized Queries, Deterministic Calculations, and Fact Bundles.

Transforms resolved semantic requests into normalized query specifications,
executes deterministic calculations over authorized records, and builds
immutable, allowlisted FactBundles for visual rendering and truthful narration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple, Union
import statistics

from backend.services.entity_scope_resolver import normalize_location


@dataclass
class NormalizedQuerySpec:
    """
    Normalized, typed specification of an authorized query.
    Never contains arbitrary SQL or model-controlled authorization parameters.
    """
    resource_domain: Literal["employee", "ticket", "team", "organization"]
    requested_operation: str
    root_target_id: Optional[str] = None
    scope: Optional[Literal["self", "direct_reports", "descendants", "department", "company"]] = None
    filters: Dict[str, Any] = field(default_factory=dict)
    dates: Dict[str, Any] = field(default_factory=dict)
    grouping: Optional[Literal["priority", "status", "category", "created_date", "assignee"]] = None
    metric: Optional[Literal["count", "headcount", "sla_overdue", "sla_compliance", "resolution_time"]] = None
    sort_order: Optional[str] = None
    display_limit: Optional[int] = None
    requested_presentation: Optional[str] = None
    coverage_requirements: Dict[str, Any] = field(default_factory=dict)
    source_context_id: Optional[str] = None


@dataclass
class FactBundle:
    """
    Immutable bundle of deterministic facts derived from authorized data.
    Single source of truth reused for visual payload, text, and voice narration.
    """
    query_spec: NormalizedQuerySpec
    resource_domain: str
    metric_name: str
    authorized_scope_description: str
    applied_filters: Dict[str, Any]
    as_of_time: str
    data_revision: Optional[str] = None
    coverage_description: str = "Authorized production snapshot"
    aggregates: Dict[str, Any] = field(default_factory=dict)
    unit: str = "items"
    total_eligible_count: int = 0
    missing_or_unknown_count: int = 0
    bounded_records: List[Dict[str, Any]] = field(default_factory=list)
    truncation_metadata: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    is_outage_or_error: bool = False
    error_message: Optional[str] = None


class QueryFactService:
    """
    Service for calculating deterministic metrics and assembling FactBundles.
    """

    ALLOWED_TICKET_FIELDS = {
        "ticket_id", "title", "description", "priority", "status",
        "category", "assignee_id", "requester_id", "created_at", "updated_at",
        "due_date", "resolved_at", "closed_at", "owner_team", "department"
    }

    ALLOWED_EMPLOYEE_FIELDS = {
        "employee_id", "full_name", "first_name", "last_name", "title",
        "department", "location", "manager_id", "work_email", "reports_count"
    }

    def project_ticket_record(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        """Allowlist-only projection of ticket data for UI/narration layers."""
        res: Dict[str, Any] = {}
        for key in self.ALLOWED_TICKET_FIELDS:
            if key in ticket:
                res[key] = ticket[key]
        return res

    def project_employee_record(self, emp: Dict[str, Any]) -> Dict[str, Any]:
        """Allowlist-only projection of employee data, stripping private metadata."""
        res: Dict[str, Any] = {}
        ident = emp.get("identity", {}) if isinstance(emp.get("identity"), dict) else emp
        org = emp.get("organization", {}) if isinstance(emp.get("organization"), dict) else emp

        res["employee_id"] = ident.get("employee_id") or emp.get("employee_id")
        res["full_name"] = ident.get("full_name") or emp.get("full_name")
        res["title"] = org.get("title") or emp.get("title")
        res["department"] = org.get("department") or emp.get("department")
        res["location"] = org.get("location") or emp.get("location")
        res["manager_id"] = org.get("manager_id") or emp.get("manager_id")
        res["work_email"] = ident.get("work_email") or emp.get("work_email")
        if "reports_count" in emp:
            res["reports_count"] = emp["reports_count"]
        return res

    def calculate_ticket_breakdown(
        self,
        tickets: List[Dict[str, Any]],
        group_by: str,
    ) -> Tuple[Dict[str, int], int]:
        """
        Calculates exact count breakdown by dimension.
        Normalizes aliases and tracks missing/unknown values explicitly.
        """
        counts: Dict[str, int] = {}
        unknown_count = 0

        for t in tickets:
            val = t.get(group_by)
            if not val:
                unknown_count += 1
                counts["Unknown"] = counts.get("Unknown", 0) + 1
                continue

            str_val = str(val).strip()
            # Normalize common casing/synonyms
            if group_by == "priority":
                if str_val.lower() in ("critical", "urgent"):
                    str_val = "Critical"
                elif str_val.lower() in ("high",):
                    str_val = "High"
                elif str_val.lower() in ("medium", "normal"):
                    str_val = "Medium"
                elif str_val.lower() in ("low",):
                    str_val = "Low"
            elif group_by == "status":
                if str_val.lower() in ("in progress", "in_progress"):
                    str_val = "In Progress"
                elif str_val.lower() in ("open",):
                    str_val = "Open"
                elif str_val.lower() in ("resolved",):
                    str_val = "Resolved"
                elif str_val.lower() in ("closed",):
                    str_val = "Closed"
                elif str_val.lower() in ("blocked",):
                    str_val = "Blocked"
                elif str_val.lower() in ("pending",):
                    str_val = "Pending"

            counts[str_val] = counts.get(str_val, 0) + 1

        return counts, unknown_count

    def calculate_created_date_time_series(
        self,
        tickets: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Groups tickets strictly by their creation date.
        Never labels creation counts as backlog or resolution trends.
        """
        buckets: Dict[str, int] = {}
        missing_or_invalid = 0

        for t in tickets:
            raw_dt = t.get("created_at") or t.get("created_date")
            if not raw_dt:
                missing_or_invalid += 1
                continue

            try:
                # Handle ISO timestamps or YYYY-MM-DD
                dt_str = str(raw_dt)[:10]
                # Validate date parsing
                datetime.strptime(dt_str, "%Y-%m-%d")
                buckets[dt_str] = buckets.get(dt_str, 0) + 1
            except (ValueError, TypeError):
                missing_or_invalid += 1

        # Sorted by ascending date
        sorted_series = [
            {"date": d, "count": buckets[d], "label": d}
            for d in sorted(buckets.keys())
        ]
        return sorted_series, missing_or_invalid

    def calculate_resolution_time_metrics(
        self,
        tickets: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Calculates resolution duration metrics for completed tickets only.
        Excludes unresolved tickets and rejects invalid negative intervals.
        """
        durations_hours: List[float] = []
        unresolved_count = 0
        invalid_negative_count = 0

        for t in tickets:
            status = str(t.get("status", "")).lower()
            if status not in ("resolved", "closed"):
                unresolved_count += 1
                continue

            created_str = t.get("created_at")
            resolved_str = t.get("resolved_at") or t.get("closed_at")
            if not created_str or not resolved_str:
                unresolved_count += 1
                continue

            try:
                # Normalize ISO format
                c_dt = datetime.fromisoformat(str(created_str).replace("Z", "+00:00"))
                r_dt = datetime.fromisoformat(str(resolved_str).replace("Z", "+00:00"))
                duration_sec = (r_dt - c_dt).total_seconds()
                if duration_sec < 0:
                    invalid_negative_count += 1
                    continue
                durations_hours.append(round(duration_sec / 3600.0, 2))
            except (ValueError, TypeError):
                invalid_negative_count += 1

        eligible_count = len(durations_hours)
        if eligible_count == 0:
            return {
                "eligible_count": 0,
                "unresolved_count": unresolved_count,
                "invalid_negative_count": invalid_negative_count,
                "avg_hours": None,
                "median_hours": None,
                "status": "no_eligible_data",
                "unit": "hours",
            }

        avg_h = round(sum(durations_hours) / eligible_count, 1)
        med_h = round(statistics.median(durations_hours), 1)

        return {
            "eligible_count": eligible_count,
            "unresolved_count": unresolved_count,
            "invalid_negative_count": invalid_negative_count,
            "avg_hours": avg_h,
            "median_hours": med_h,
            "min_hours": min(durations_hours),
            "max_hours": max(durations_hours),
            "status": "calculated",
            "unit": "hours",
        }

    def calculate_sla_metrics(
        self,
        tickets: List[Dict[str, Any]],
        metric_type: Literal["overdue", "compliance"],
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Deterministic SLA calculation with injectable clock.
        Handles zero-denominator truthfully without reporting 0% for unknown data.
        """
        current_time = now or datetime.now(timezone.utc)
        eligible_tickets = []
        overdue_tickets = []
        compliant_tickets = []
        unknown_target_count = 0

        for t in tickets:
            sla_info = t.get("sla") or {}
            due_date_str = t.get("due_date")
            res_status = sla_info.get("resolution_status")

            has_sla = bool(sla_info or due_date_str)
            if not has_sla:
                unknown_target_count += 1
                continue

            eligible_tickets.append(t)
            status = str(t.get("status", "")).lower()
            is_closed = status in ("resolved", "closed")

            # Check overdue / breach condition
            is_overdue = False
            if res_status == "Breached":
                is_overdue = True
            elif not is_closed and due_date_str:
                try:
                    due_dt = datetime.fromisoformat(str(due_date_str).replace("Z", "+00:00"))
                    if current_time > due_dt:
                        is_overdue = True
                except (ValueError, TypeError):
                    pass

            if is_overdue:
                overdue_tickets.append(t)
            else:
                compliant_tickets.append(t)

        eligible_count = len(eligible_tickets)
        if eligible_count == 0:
            return {
                "eligible_count": 0,
                "overdue_count": 0,
                "compliant_count": 0,
                "rate": None,
                "rate_percent_str": "N/A (No eligible SLA targets)",
                "unknown_target_count": unknown_target_count,
                "status": "no_eligible_data",
                "as_of_time": current_time.isoformat(),
            }

        overdue_count = len(overdue_tickets)
        compliant_count = len(compliant_tickets)

        if metric_type == "overdue":
            rate = round((overdue_count / eligible_count) * 100.0, 1)
            return {
                "metric": "overdue",
                "eligible_count": eligible_count,
                "overdue_count": overdue_count,
                "compliant_count": compliant_count,
                "rate": rate,
                "rate_percent_str": f"{rate}% ({overdue_count}/{eligible_count} overdue)",
                "unknown_target_count": unknown_target_count,
                "status": "calculated",
                "as_of_time": current_time.isoformat(),
            }
        else:
            rate = round((compliant_count / eligible_count) * 100.0, 1)
            return {
                "metric": "compliance",
                "eligible_count": eligible_count,
                "compliant_count": compliant_count,
                "overdue_count": overdue_count,
                "rate": rate,
                "rate_percent_str": f"{rate}% ({compliant_count}/{eligible_count} compliant)",
                "unknown_target_count": unknown_target_count,
                "status": "calculated",
                "as_of_time": current_time.isoformat(),
            }

    def calculate_team_headcount(
        self,
        team_members: List[Dict[str, Any]],
        location_filter: Optional[str] = None,
        department_filter: Optional[str] = None,
        coverage_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Deterministic team headcount calculation with dynamic coverage checking.
        """
        filtered = list(team_members)

        if location_filter:
            norm_loc = normalize_location(location_filter, coverage_metadata=coverage_metadata)
            if not norm_loc.is_covered:
                return {
                    "headcount": None,
                    "status": "unknown_location",
                    "location_requested": location_filter,
                    "available_locations": norm_loc.message,
                    "explanation": f"Location '{location_filter}' is outside known coverage.",
                }
            canonical_loc = norm_loc.canonical_location
            filtered = [
                m for m in filtered
                if (m.get("organization", {}).get("location") or m.get("location")) == canonical_loc
            ]

        if department_filter:
            filtered = [
                m for m in filtered
                if str(m.get("organization", {}).get("department") or m.get("department", "")).lower()
                == department_filter.lower()
            ]

        return {
            "headcount": len(filtered),
            "status": "calculated",
            "total_available_in_scope": len(team_members),
            "filtered_members": filtered,
        }

    def build_fact_bundle(
        self,
        query_spec: NormalizedQuerySpec,
        authorized_records: List[Dict[str, Any]],
        scope_description: str,
        data_revision: Optional[str] = None,
        now: Optional[datetime] = None,
        is_error: bool = False,
        error_message: Optional[str] = None,
    ) -> FactBundle:
        """
        Assembles a complete, immutable FactBundle from authorized records.
        """
        as_of = (now or datetime.now(timezone.utc)).isoformat()

        if is_error:
            return FactBundle(
                query_spec=query_spec,
                resource_domain=query_spec.resource_domain,
                metric_name=query_spec.metric or "error",
                authorized_scope_description=scope_description,
                applied_filters=query_spec.filters,
                as_of_time=as_of,
                data_revision=data_revision,
                coverage_description="Query execution failed",
                aggregates={},
                unit="",
                total_eligible_count=0,
                is_outage_or_error=True,
                error_message=error_message,
                notes=["Backend query or repository encountered an error."],
            )

        domain = query_spec.resource_domain
        metric = query_spec.metric or "count"
        aggregates: Dict[str, Any] = {}
        notes: List[str] = []
        bounded_records: List[Dict[str, Any]] = []
        missing_count = 0
        total_eligible = len(authorized_records)

        if domain == "ticket":
            # Project records through allowlist
            bounded_records = [self.project_ticket_record(t) for t in authorized_records]

            if query_spec.grouping:
                breakdown, unk = self.calculate_ticket_breakdown(authorized_records, query_spec.grouping)
                aggregates["breakdown"] = breakdown
                aggregates["total_count"] = total_eligible
                missing_count = unk
                unit = "tickets"
                if unk > 0:
                    notes.append(f"{unk} tickets have unknown {query_spec.grouping}.")

            elif metric in ("sla_overdue", "sla_compliance"):
                m_type = "overdue" if metric == "sla_overdue" else "compliance"
                sla_res = self.calculate_sla_metrics(authorized_records, m_type, now=now)
                aggregates.update(sla_res)
                unit = "percent" if sla_res.get("rate") is not None else "tickets"
                missing_count = sla_res.get("unknown_target_count", 0)
                if sla_res.get("status") == "no_eligible_data":
                    notes.append("No tickets in scope have defined SLA targets.")

            elif metric == "resolution_time":
                res_time = self.calculate_resolution_time_metrics(authorized_records)
                aggregates.update(res_time)
                unit = "hours"
                missing_count = res_time.get("unresolved_count", 0)
                if res_time.get("status") == "no_eligible_data":
                    notes.append("No resolved or closed tickets with valid duration in scope.")

            elif query_spec.requested_presentation in ("LINE", "AREA"):
                series, miss = self.calculate_created_date_time_series(authorized_records)
                aggregates["time_series"] = series
                aggregates["total_count"] = total_eligible
                missing_count = miss
                unit = "tickets"
                notes.append("Grouped strictly by ticket creation date; not historical backlog.")

            else:
                aggregates["total_count"] = total_eligible
                unit = "tickets"

        elif domain in ("employee", "team"):
            bounded_records = [self.project_employee_record(e) for e in authorized_records]
            if query_spec.requested_operation in ("headcount", "team_count"):
                loc_filter = query_spec.filters.get("location")
                dept_filter = query_spec.filters.get("department")

                hc_res = self.calculate_team_headcount(
                    authorized_records,
                    location_filter=loc_filter,
                    department_filter=dept_filter,
                )
                aggregates.update(hc_res)
                unit = "people"
                if hc_res.get("status") == "unknown_location":
                    notes.append(hc_res.get("explanation", "Unknown location."))
            else:
                aggregates["total_count"] = total_eligible
                unit = "people"

        else:
            aggregates["total_count"] = total_eligible
            unit = "items"

        return FactBundle(
            query_spec=query_spec,
            resource_domain=domain,
            metric_name=metric,
            authorized_scope_description=scope_description,
            applied_filters=query_spec.filters,
            as_of_time=as_of,
            data_revision=data_revision,
            coverage_description="Production authorized dataset",
            aggregates=aggregates,
            unit=unit,
            total_eligible_count=total_eligible,
            missing_or_unknown_count=missing_count,
            bounded_records=bounded_records,
            truncation_metadata={"displayed_count": len(bounded_records), "total_count": total_eligible},
            notes=notes,
        )
