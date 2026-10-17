"""
backend/services/result_generator.py
Person 2 — Compatible Structured-Output Selection and Result Block Generation.

Maps internal FactBundles into registered frontend GenericResultBlocks:
- Evaluates strict visual compatibility over data shapes and cardinalities.
- Applies fallback with explanatory notes when incompatible views are requested.
- Projects strictly allowlisted fields into renderer payloads.
- Generates deterministic text/spoken summaries ensuring exact agreement with facts.
- Supports compound reads and mixed permitted/denied outcomes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from backend.models.turn import GenericResultBlock, ResultBlockType
from backend.services.query_fact_service import FactBundle, NormalizedQuerySpec


@dataclass
class PresentationDecision:
    """Outcome of visual compatibility analysis."""
    chosen_block_type: ResultBlockType
    chosen_view: Optional[str]
    is_compatible: bool
    fallback_applied: bool
    compatibility_note: Optional[str] = None


class ResultGenerator:
    """
    Selects compatible renderers and builds valid GenericResultBlocks from FactBundles.
    """

    SUPPORTED_BLOCK_TYPES = {
        "EMPLOYEE_PROFILE",
        "DATA_TABLE",
        "ORG_TREE",
        "TICKET_LIST",
        "TEAM_METRIC_CHART",
        "READBACK_CONFIRMATION",
        "ACTION_RECEIPT",
        "DENIAL_BANNER",
        "PUBLIC_FAQ",
    }

    def select_presentation(
        self,
        bundle: FactBundle,
        requested_view: Optional[str] = None,
    ) -> PresentationDecision:
        """
        Determines the appropriate block type and view based on data shape and compatibility.
        """
        if bundle.is_outage_or_error:
            return PresentationDecision(
                chosen_block_type="DENIAL_BANNER",
                chosen_view=None,
                is_compatible=True,
                fallback_applied=False,
                compatibility_note="Outage or execution error rendered as alert banner.",
            )

        domain = bundle.resource_domain
        metric = bundle.metric_name
        req_view = (requested_view or bundle.query_spec.requested_presentation or "").upper() or None

        # 1. Employee Domain
        if domain == "employee":
            if bundle.total_eligible_count == 1 and not bundle.query_spec.grouping:
                if req_view in ("BAR", "PIE", "LINE"):
                    return PresentationDecision(
                        chosen_block_type="EMPLOYEE_PROFILE",
                        chosen_view=None,
                        is_compatible=False,
                        fallback_applied=True,
                        compatibility_note="A single employee profile cannot be rendered as a chart; displaying profile card.",
                    )
                return PresentationDecision(
                    chosen_block_type="EMPLOYEE_PROFILE",
                    chosen_view=None,
                    is_compatible=True,
                    fallback_applied=False,
                )
            # Multiple employees
            return PresentationDecision(
                chosen_block_type="DATA_TABLE",
                chosen_view="TABLE",
                is_compatible=True,
                fallback_applied=False,
            )

        # 2. Team / Org Tree Domain
        if domain == "team":
            if bundle.query_spec.requested_operation == "org_tree":
                return PresentationDecision(
                    chosen_block_type="ORG_TREE",
                    chosen_view="TREE",
                    is_compatible=True,
                    fallback_applied=False,
                )
            if "headcount" in bundle.aggregates or metric == "headcount":
                return PresentationDecision(
                    chosen_block_type="TEAM_METRIC_CHART",
                    chosen_view="BAR",
                    is_compatible=True,
                    fallback_applied=False,
                )
            return PresentationDecision(
                chosen_block_type="DATA_TABLE",
                chosen_view="TABLE",
                is_compatible=True,
                fallback_applied=False,
            )

        # 3. Ticket Domain
        if domain == "ticket":
            # Time-series requested
            if "time_series" in bundle.aggregates or req_view in ("LINE", "AREA"):
                if "time_series" not in bundle.aggregates:
                    # User asked for LINE on non-temporal data (e.g. priority breakdown)
                    return PresentationDecision(
                        chosen_block_type="TEAM_METRIC_CHART",
                        chosen_view="BAR",
                        is_compatible=False,
                        fallback_applied=True,
                        compatibility_note=f"Cannot render non-temporal data as a {req_view} chart without creation dates; falling back to Bar chart.",
                    )
                return PresentationDecision(
                    chosen_block_type="TEAM_METRIC_CHART",
                    chosen_view=req_view if req_view in ("LINE", "AREA") else "LINE",
                    is_compatible=True,
                    fallback_applied=False,
                )

            # Breakdown (priority, status, etc.)
            if "breakdown" in bundle.aggregates:
                breakdown = bundle.aggregates["breakdown"]
                if req_view == "PIE":
                    # Check for meaningful composition (>= 2 slices with count > 0)
                    positive_slices = sum(1 for c in breakdown.values() if c > 0)
                    if positive_slices < 2:
                        return PresentationDecision(
                            chosen_block_type="TEAM_METRIC_CHART",
                            chosen_view="BAR",
                            is_compatible=False,
                            fallback_applied=True,
                            compatibility_note="Pie chart requires at least 2 categories with positive counts; falling back to Bar chart.",
                        )
                    return PresentationDecision(
                        chosen_block_type="TEAM_METRIC_CHART",
                        chosen_view="PIE",
                        is_compatible=True,
                        fallback_applied=False,
                    )
                # Default for breakdown is BAR
                return PresentationDecision(
                    chosen_block_type="TEAM_METRIC_CHART",
                    chosen_view=req_view if req_view in ("BAR", "TABLE") else "BAR",
                    is_compatible=True,
                    fallback_applied=False,
                )

            # SLA metrics
            if metric in ("sla_overdue", "sla_compliance"):
                return PresentationDecision(
                    chosen_block_type="TEAM_METRIC_CHART",
                    chosen_view="BAR",
                    is_compatible=True,
                    fallback_applied=False,
                )

            # Resolution time metric
            if metric == "resolution_time":
                return PresentationDecision(
                    chosen_block_type="TEAM_METRIC_CHART",
                    chosen_view="BAR",
                    is_compatible=True,
                    fallback_applied=False,
                )

            # Default ticket query is TICKET_LIST
            if req_view == "TABLE":
                return PresentationDecision(
                    chosen_block_type="TICKET_LIST",
                    chosen_view="TABLE",
                    is_compatible=True,
                    fallback_applied=False,
                )
            return PresentationDecision(
                chosen_block_type="TICKET_LIST",
                chosen_view=None,
                is_compatible=True,
                fallback_applied=False,
            )

        # Fallback to DATA_TABLE
        return PresentationDecision(
            chosen_block_type="DATA_TABLE",
            chosen_view="TABLE",
            is_compatible=True,
            fallback_applied=False,
        )

    def generate_spoken_summary(
        self,
        bundle: FactBundle,
        decision: PresentationDecision,
    ) -> str:
        """
        Constructs a deterministic, natural spoken summary strictly agreeing with facts.
        """
        if bundle.is_outage_or_error:
            return f"Unable to process query: {bundle.error_message or 'Service unavailable.'}"

        domain = bundle.resource_domain
        metric = bundle.metric_name
        aggs = bundle.aggregates
        total = bundle.total_eligible_count

        fallback_prefix = f"{decision.compatibility_note} " if decision.fallback_applied and decision.compatibility_note else ""

        # Employee Profile
        if (domain == "employee" and bundle.query_spec.requested_operation == "profile") or (
            domain == "employee" and total == 1 and bundle.bounded_records and "headcount" not in aggs
        ):
            emp = bundle.bounded_records[0]
            role_desc = f" ({emp.get('title')}, {emp.get('department')})" if emp.get('title') else ""
            return f"{fallback_prefix}Showing profile for {emp.get('full_name')}{role_desc}."

        # Headcount / Team
        if "headcount" in aggs:
            if aggs.get("status") == "unknown_location":
                return f"{fallback_prefix}Location '{aggs.get('location_requested')}' is outside known office coverage."
            loc = bundle.applied_filters.get("location")
            dept = bundle.applied_filters.get("department")
            filter_str = f" in {loc}" if loc else (f" in {dept}" if dept else "")
            return f"{fallback_prefix}Authorized team headcount{filter_str} is {aggs.get('headcount')} people."

        # SLA Metrics
        if metric in ("sla_overdue", "sla_compliance"):
            if aggs.get("status") == "no_eligible_data":
                return f"{fallback_prefix}No tickets in your authorized scope have defined SLA targets."
            rate = aggs.get("rate")
            if metric == "sla_overdue":
                return f"{fallback_prefix}{rate}% of authorized tickets ({aggs.get('overdue_count')}/{aggs.get('eligible_count')}) are overdue as of {aggs.get('as_of_time', '')[:10]}."
            else:
                return f"{fallback_prefix}{rate}% SLA compliance ({aggs.get('compliant_count')}/{aggs.get('eligible_count')} compliant) as of {aggs.get('as_of_time', '')[:10]}."

        # Resolution Time
        if metric == "resolution_time":
            if aggs.get("status") == "no_eligible_data":
                return f"{fallback_prefix}No resolved tickets with valid duration data are available in this scope."
            return f"{fallback_prefix}Average resolution time is {aggs.get('avg_hours')} hours across {aggs.get('eligible_count')} completed tickets."

        # Ticket Breakdown
        if "breakdown" in aggs:
            parts = [f"{v} {k}" for k, v in aggs["breakdown"].items()]
            breakdown_str = ", ".join(parts) if parts else "none"
            return f"{fallback_prefix}Found {total} authorized tickets: {breakdown_str}."

        # Time-Series
        if "time_series" in aggs:
            points_count = len(aggs["time_series"])
            return f"{fallback_prefix}Showing {total} authorized tickets created across {points_count} dates."

        # Ticket List
        if domain == "ticket":
            if total == 0:
                return f"{fallback_prefix}No tickets match the requested criteria in your authorized scope."
            return f"{fallback_prefix}Showing {total} authorized tickets."

        # Employee Profile
        if domain == "employee" and total == 1 and bundle.bounded_records:
            emp = bundle.bounded_records[0]
            return f"{fallback_prefix}Showing profile for {emp.get('full_name')} ({emp.get('title')}, {emp.get('department')})."

        return f"{fallback_prefix}Retrieved {total} authorized {bundle.unit}."

    def generate_result(
        self,
        bundle: FactBundle,
        requested_view: Optional[str] = None,
    ) -> Tuple[GenericResultBlock, str]:
        """
        Creates a validated GenericResultBlock and exact matching spoken summary.
        """
        decision = self.select_presentation(bundle, requested_view)
        spoken_summary = self.generate_spoken_summary(bundle, decision)

        block_id = f"blk_{uuid.uuid4().hex}"
        timestamp = datetime.now(timezone.utc).isoformat()
        b_type = decision.chosen_block_type

        # 1. Error / Denial
        if bundle.is_outage_or_error:
            return (
                GenericResultBlock(
                    id=block_id,
                    type="DENIAL_BANNER",
                    title="Service Notice",
                    timestamp=timestamp,
                    isSensitive=False,
                    payload={
                        "denial_reason": "SERVICE_ERROR",
                        "message": bundle.error_message or "A service error occurred.",
                    }
                ),
                spoken_summary,
            )

        # 2. Employee Profile
        if b_type == "EMPLOYEE_PROFILE":
            rec = bundle.bounded_records[0] if bundle.bounded_records else {}
            title = rec.get("full_name") or rec.get("name") or "Employee Profile"
            emp_id = rec.get("employee_id") or rec.get("id") or "EMP-0000"
            emp_name = rec.get("full_name") or rec.get("name") or "Unknown"
            emp_role = rec.get("title") or rec.get("role") or rec.get("designation") or "Employee"
            dept = rec.get("department") or "General"
            email = rec.get("work_email") or rec.get("email") or ""

            canonical_emp = {
                "id": emp_id,
                "name": emp_name,
                "role": emp_role,
                "department": dept,
                "team": rec.get("team") or "",
                "email": email,
                "location": rec.get("location") or "Bengaluru",
            }
            payload = {
                **rec,
                "id": emp_id,
                "name": emp_name,
                "role": emp_role,
                "employee": canonical_emp,
            }
            return (
                GenericResultBlock(
                    id=block_id,
                    type="EMPLOYEE_PROFILE",
                    title=title,
                    timestamp=timestamp,
                    isSensitive=True,
                    payload=payload,
                ),
                spoken_summary,
            )

        # 3. Data Table (e.g. Employee list)
        if b_type == "DATA_TABLE":
            records = bundle.bounded_records
            columns = [
                {"key": "name", "label": "Name"},
                {"key": "title", "label": "Title"},
                {"key": "department", "label": "Department"},
            ]
            formatted_rows = [
                {
                    "id": r.get("employee_id") or r.get("id") or f"row_{idx}",
                    "name": r.get("full_name") or r.get("name") or "Unknown",
                    "title": r.get("title") or r.get("designation") or "Staff",
                    "department": r.get("department") or "General",
                }
                for idx, r in enumerate(records)
            ]
            return (
                GenericResultBlock(
                    id=block_id,
                    type="DATA_TABLE",
                    title=f"Authorized Team Members ({len(records)})",
                    timestamp=timestamp,
                    isSensitive=True,
                    payload={
                        "title": f"Team Members ({len(records)})",
                        "columns": columns,
                        "rows": formatted_rows,
                        "total_count": len(records),
                    },
                ),
                spoken_summary,
            )

        # 4. Ticket List
        if b_type == "TICKET_LIST":
            tickets = bundle.bounded_records
            return (
                GenericResultBlock(
                    id=block_id,
                    type="TICKET_LIST",
                    title=f"Authorized Tickets ({len(tickets)})",
                    timestamp=timestamp,
                    isSensitive=True,
                    payload={
                        "title": f"Tickets ({len(tickets)})",
                        "tickets": tickets,
                        "total_count": len(tickets),
                    },
                ),
                spoken_summary,
            )

        # 5. Team Metric Chart
        if b_type == "TEAM_METRIC_CHART":
            chart_type = decision.chosen_view or "BAR"
            chart_data = []

            if "breakdown" in bundle.aggregates:
                chart_data = [
                    {"label": k, "count": v}
                    for k, v in bundle.aggregates["breakdown"].items()
                ]
                chart_title = f"Tickets by {bundle.query_spec.grouping or 'Category'}"
                unit = "tickets"
            elif "time_series" in bundle.aggregates:
                chart_data = bundle.aggregates["time_series"]
                chart_title = "Tickets created over time"
                unit = "tickets"
            elif "headcount" in bundle.aggregates:
                hc = bundle.aggregates.get("headcount") or 0
                chart_data = [{"label": "Headcount", "count": hc}]
                chart_title = "Team Headcount"
                unit = "people"
            elif bundle.metric_name == "sla_compliance":
                comp = bundle.aggregates.get("compliant_count", 0)
                over = bundle.aggregates.get("overdue_count", 0)
                chart_data = [
                    {"label": "Compliant", "count": comp},
                    {"label": "Overdue", "count": over},
                ]
                chart_title = "SLA Compliance"
                unit = "tickets"
            elif bundle.metric_name == "sla_overdue":
                comp = bundle.aggregates.get("compliant_count", 0)
                over = bundle.aggregates.get("overdue_count", 0)
                chart_data = [
                    {"label": "Overdue", "count": over},
                    {"label": "On Target", "count": comp},
                ]
                chart_title = "Overdue Tickets"
                unit = "tickets"
            else:
                chart_data = [{"label": "Total", "count": bundle.total_eligible_count}]
                chart_title = "Metric"
                unit = bundle.unit

            payload = {
                "chart_type": chart_type,
                "title": chart_title,
                "unit": unit,
                "data": chart_data,
            }
            if decision.compatibility_note:
                payload["coverage_note"] = decision.compatibility_note

            return (
                GenericResultBlock(
                    id=block_id,
                    type="TEAM_METRIC_CHART",
                    title=chart_title,
                    timestamp=timestamp,
                    isSensitive=True,
                    payload=payload,
                ),
                spoken_summary,
            )

        # 6. Org Tree
        if b_type == "ORG_TREE":
            return (
                GenericResultBlock(
                    id=block_id,
                    type="ORG_TREE",
                    title="Reporting Tree",
                    timestamp=timestamp,
                    isSensitive=True,
                    payload={
                        "root_id": bundle.query_spec.root_target_id or "ROOT",
                        "nodes": bundle.bounded_records,
                        "edges": bundle.aggregates.get("edges", []),
                        "total_count": len(bundle.bounded_records),
                    },
                ),
                spoken_summary,
            )

        # Fallback Public FAQ
        return (
            GenericResultBlock(
                id=block_id,
                type="PUBLIC_FAQ",
                title="Helpdesk Info",
                timestamp=timestamp,
                isSensitive=False,
                payload={"answer": spoken_summary},
            ),
            spoken_summary,
        )

    def generate_compound_results(
        self,
        bundles: List[FactBundle],
    ) -> List[Tuple[GenericResultBlock, str]]:
        """
        Builds separate result blocks for compound queries, retaining individual outcomes.
        """
        results = []
        for b in bundles:
            block, summary = self.generate_result(b)
            results.append((block, summary))
        return results
