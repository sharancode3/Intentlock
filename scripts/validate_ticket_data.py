"""
IntentLock — Ticket Data Validation Script
Validates all_tickets.json against all_employees.json and ensures:
1. Unique ticket IDs
2. Valid employee references (requester, assignee, creator, approver, escalation, comments, activity)
3. Valid enum fields (status, priority, severity, ticket_type, resolution_status)
4. Chronological date consistency
5. Valid approval flows
6. Valid escalation paths
7. Rich resolution data for resolved/closed tickets
"""

import sys
import os
import json
from datetime import datetime
from typing import Dict, Any, List, Set

VALID_STATUSES = {"Open", "In Progress", "Pending", "Blocked", "Resolved", "Closed"}
VALID_PRIORITIES = {"Low", "Medium", "High", "Critical"}
VALID_SEVERITIES = {"S1", "S2", "S3", "S4"}
VALID_TYPES = {"Bug", "Incident", "Feature", "Access Request", "Maintenance", "Architecture Review", "Security Task"}
VALID_SLA_STATUSES = {"Within SLA", "At Risk", "Breached", "Met"}
VALID_APPROVAL_STATUSES = {"Not Required", "Pending", "Approved", "Rejected"}

def parse_iso(dt_str: str) -> datetime:
    return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))

def validate_ticket_data(
    tickets_path: str = "backend/data/all_tickets.json",
    employees_path: str = "backend/data/all_employees.json",
) -> Dict[str, Any]:
    if not os.path.exists(tickets_path):
        return {"success": False, "error": f"Tickets file not found at {tickets_path}"}
    if not os.path.exists(employees_path):
        return {"success": False, "error": f"Employees file not found at {employees_path}"}

    with open(employees_path, "r", encoding="utf-8") as f:
        employees = json.load(f)
    valid_emp_ids: Set[str] = {e["employee_id"] for e in employees}

    with open(tickets_path, "r", encoding="utf-8") as f:
        tickets = json.load(f)

    report = {
        "total_tickets": len(tickets),
        "unique_ids_pass": True,
        "employee_refs_pass": True,
        "dates_pass": True,
        "approvals_pass": True,
        "escalations_pass": True,
        "resolutions_pass": True,
        "enums_pass": True,
        "errors": []
    }

    seen_ids = set()
    aarav_count = 0
    priya_count = 0
    arvind_count = 0

    for idx, t in enumerate(tickets):
        tid = t.get("ticket_id")
        if not tid:
            report["unique_ids_pass"] = False
            report["errors"].append(f"Ticket #{idx} missing ticket_id")
            continue

        if tid in seen_ids:
            report["unique_ids_pass"] = False
            report["errors"].append(f"Duplicate ticket ID: {tid}")
        seen_ids.add(tid)

        # Count primary personas
        req = t.get("requester_id")
        asn = t.get("assignee_id")
        crb = t.get("created_by")
        app = t.get("approval", {}).get("approver_id")
        esc = t.get("escalation", {}).get("escalated_to")

        if "EMP-1001" in (req, asn, crb):
            aarav_count += 1
        if "EMP-2001" in (req, asn, crb, app, esc):
            priya_count += 1
        if "EMP-4002" in (req, asn, crb, app, esc):
            arvind_count += 1

        # Check Enums
        status = t.get("status")
        priority = t.get("priority")
        severity = t.get("severity")
        ttype = t.get("ticket_type")
        sla_status = t.get("sla", {}).get("resolution_status")

        if status not in VALID_STATUSES:
            report["enums_pass"] = False
            report["errors"].append(f"Ticket {tid} invalid status '{status}'")
        if priority not in VALID_PRIORITIES:
            report["enums_pass"] = False
            report["errors"].append(f"Ticket {tid} invalid priority '{priority}'")
        if severity not in VALID_SEVERITIES:
            report["enums_pass"] = False
            report["errors"].append(f"Ticket {tid} invalid severity '{severity}'")
        if ttype not in VALID_TYPES:
            report["enums_pass"] = False
            report["errors"].append(f"Ticket {tid} invalid ticket_type '{ttype}'")
        if sla_status not in VALID_SLA_STATUSES:
            report["enums_pass"] = False
            report["errors"].append(f"Ticket {tid} invalid sla resolution_status '{sla_status}'")

        # Check Employee References
        for role_field in ["requester_id", "created_by"]:
            val = t.get(role_field)
            if val and val not in valid_emp_ids:
                report["employee_refs_pass"] = False
                report["errors"].append(f"Ticket {tid} references invalid {role_field}: '{val}'")

        if asn and asn not in valid_emp_ids:
            report["employee_refs_pass"] = False
            report["errors"].append(f"Ticket {tid} references invalid assignee_id: '{asn}'")

        # Approver check
        if app and app not in valid_emp_ids:
            report["employee_refs_pass"] = False
            report["errors"].append(f"Ticket {tid} references invalid approver_id: '{app}'")

        # Escalated_to check
        if esc and esc not in valid_emp_ids:
            report["employee_refs_pass"] = False
            report["errors"].append(f"Ticket {tid} references invalid escalated_to: '{esc}'")

        # Dates check
        c_at = t.get("created_at")
        u_at = t.get("updated_at")
        r_at = t.get("resolved_at")
        cl_at = t.get("closed_at")

        if not c_at or not u_at:
            report["dates_pass"] = False
            report["errors"].append(f"Ticket {tid} missing created_at or updated_at")
        else:
            try:
                dt_c = parse_iso(c_at)
                dt_u = parse_iso(u_at)
                if dt_c > dt_u:
                    report["dates_pass"] = False
                    report["errors"].append(f"Ticket {tid} created_at ({c_at}) > updated_at ({u_at})")

                if r_at:
                    dt_r = parse_iso(r_at)
                    if dt_r < dt_c:
                        report["dates_pass"] = False
                        report["errors"].append(f"Ticket {tid} resolved_at ({r_at}) < created_at ({c_at})")
                    if cl_at:
                        dt_cl = parse_iso(cl_at)
                        if dt_cl < dt_r:
                            report["dates_pass"] = False
                            report["errors"].append(f"Ticket {tid} closed_at ({cl_at}) < resolved_at ({r_at})")
            except Exception as e:
                report["dates_pass"] = False
                report["errors"].append(f"Ticket {tid} invalid date format: {e}")

        # Approvals check
        approval = t.get("approval", {})
        app_status = approval.get("status")
        if app_status not in VALID_APPROVAL_STATUSES:
            report["approvals_pass"] = False
            report["errors"].append(f"Ticket {tid} invalid approval status '{app_status}'")
        if approval.get("required") and not approval.get("approver_id"):
            report["approvals_pass"] = False
            report["errors"].append(f"Ticket {tid} approval required but missing approver_id")
        if app_status == "Approved" and not approval.get("approved_at"):
            report["approvals_pass"] = False
            report["errors"].append(f"Ticket {tid} is Approved but missing approved_at")

        # Escalations check
        escalation = t.get("escalation", {})
        if escalation.get("is_escalated") and not escalation.get("escalated_to"):
            report["escalations_pass"] = False
            report["errors"].append(f"Ticket {tid} is_escalated=True but missing escalated_to")

        # Resolutions check
        if status in {"Resolved", "Closed"}:
            res = t.get("resolution", {})
            if not res.get("summary") or not res.get("root_cause") or not res.get("resolved_by"):
                report["resolutions_pass"] = False
                report["errors"].append(f"Ticket {tid} status={status} but missing resolution details")

        # Comments validation
        for c in t.get("comments", []):
            author = c.get("author_id")
            if author and author not in valid_emp_ids:
                report["employee_refs_pass"] = False
                report["errors"].append(f"Ticket {tid} comment references invalid author_id: '{author}'")
            c_time = c.get("created_at")
            if c_time and c_at and parse_iso(c_time) < parse_iso(c_at):
                report["dates_pass"] = False
                report["errors"].append(f"Ticket {tid} comment created before ticket created_at")

        # Activity history validation
        for h in t.get("activity_history", []):
            actor = h.get("actor")
            if actor and actor not in valid_emp_ids:
                report["employee_refs_pass"] = False
                report["errors"].append(f"Ticket {tid} activity references invalid actor: '{actor}'")

    report["persona_counts"] = {
        "Aarav (EMP-1001)": aarav_count,
        "Priya (EMP-2001)": priya_count,
        "Arvind (EMP-4002)": arvind_count
    }

    report["success"] = (
        report["unique_ids_pass"] and
        report["employee_refs_pass"] and
        report["dates_pass"] and
        report["approvals_pass"] and
        report["escalations_pass"] and
        report["resolutions_pass"] and
        report["enums_pass"]
    )
    return report

if __name__ == "__main__":
    rep = validate_ticket_data()
    print("=" * 60)
    print("INTENTLOCK TICKET DATASET VALIDATION REPORT")
    print("=" * 60)
    print(f"Total Tickets: {rep['total_tickets']}")
    print(f"Unique IDs: {'PASS' if rep['unique_ids_pass'] else 'FAIL'}")
    print(f"Employee References: {'PASS' if rep['employee_refs_pass'] else 'FAIL'}")
    print(f"Dates & Chronology: {'PASS' if rep['dates_pass'] else 'FAIL'}")
    print(f"Approvals: {'PASS' if rep['approvals_pass'] else 'FAIL'}")
    print(f"Escalations: {'PASS' if rep['escalations_pass'] else 'FAIL'}")
    print(f"Resolutions: {'PASS' if rep['resolutions_pass'] else 'FAIL'}")
    print(f"Enums & Types: {'PASS' if rep['enums_pass'] else 'FAIL'}")
    print("Persona Involvement:")
    for k, v in rep["persona_counts"].items():
        print(f"  - {k}: {v} tickets")
    if rep["errors"]:
        print("\nERRORS ENCOUNTERED:")
        for err in rep["errors"]:
            print(f"  [!] {err}")
        sys.exit(1)
    else:
        print("\nALL VALIDATION CHECKS PASSED PERFECTLY (100%).")
        sys.exit(0)
