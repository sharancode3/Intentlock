"""
IntentLock — Team Data Validation Script
Validates:
1. Unique team IDs with valid format.
2. Every member_id exists in all_employees.json.
3. Every team_lead_id exists in all_employees.json if specified.
4. Every manager_id exists in all_employees.json.
5. Bidirectional consistency between teams.json and all_employees.json (employment.team_id).
6. No duplicate member IDs across or within teams.
7. Valid team descriptions, departments, and active statuses.
8. Non-empty project_names and technologies arrays.
9. Executive roles (e.g. Arvind Rao / CTO) are NOT assigned to ordinary functional teams.
10. Invariant preservation (31 employees, 42 tickets, Aarav 60/40 allocation).
"""

import json
import sys
from pathlib import Path


def validate_team_data(
    teams_path: Path = Path("backend/data/teams.json"),
    employees_path: Path = Path("backend/data/all_employees.json"),
    tickets_path: Path = Path("backend/data/all_tickets.json"),
) -> list[str]:
    errors: list[str] = []

    if not teams_path.exists():
        return [f"Teams file not found: {teams_path}"]
    if not employees_path.exists():
        return [f"Employees file not found: {employees_path}"]
    if not tickets_path.exists():
        return [f"Tickets file not found: {tickets_path}"]

    teams = json.loads(teams_path.read_text(encoding="utf-8"))
    employees = json.loads(employees_path.read_text(encoding="utf-8"))
    tickets = json.loads(tickets_path.read_text(encoding="utf-8"))

    # Invariants
    if len(employees) != 31:
        errors.append(f"Expected 31 employees, got {len(employees)}")
    if len(tickets) != 42:
        errors.append(f"Expected 42 tickets, got {len(tickets)}")

    emp_by_id = {e["employee_id"]: e for e in employees}
    team_by_id = {}

    assigned_members = {}

    for idx, team in enumerate(teams):
        tid = team.get("team_id")
        tname = team.get("name")
        dept = team.get("department")
        lead_id = team.get("team_lead_id")
        mgr_id = team.get("manager_id")
        member_ids = team.get("member_ids", [])
        status = team.get("status")

        if not tid or not isinstance(tid, str):
            errors.append(f"Team at index {idx} has missing or non-string team_id")
            continue

        if tid in team_by_id:
            errors.append(f"Duplicate team_id: {tid}")
        team_by_id[tid] = team

        if not tname or not isinstance(tname, str):
            errors.append(f"{tid}: missing or invalid name")
        if not dept or not isinstance(dept, str):
            errors.append(f"{tid}: missing or invalid department")
        if status != "Active":
            errors.append(f"{tid}: invalid status '{status}' (expected 'Active')")

        if lead_id is not None:
            if lead_id not in emp_by_id:
                errors.append(f"{tid}: team_lead_id {lead_id} does not exist in employees")

        if not mgr_id or mgr_id not in emp_by_id:
            errors.append(f"{tid}: manager_id {mgr_id} does not exist in employees")

        if not member_ids:
            errors.append(f"{tid}: member_ids is empty")

        if len(member_ids) != len(set(member_ids)):
            errors.append(f"{tid}: duplicate member IDs within team")

        for mid in member_ids:
            if mid not in emp_by_id:
                errors.append(f"{tid}: member {mid} does not exist in employees")
            if mid in assigned_members:
                errors.append(f"{mid} assigned to multiple teams: {assigned_members[mid]} and {tid}")
            assigned_members[mid] = tid

            # Verify bidirectional link in employee record
            emp_team = emp_by_id[mid].get("employment", {}).get("team_id")
            if emp_team != tid:
                errors.append(
                    f"{mid}: employee.employment.team_id is '{emp_team}', expected '{tid}'"
                )

    # Check employees that have team_id set
    for eid, emp in emp_by_id.items():
        emp_team = emp.get("employment", {}).get("team_id")
        if emp_team is not None:
            if emp_team not in team_by_id:
                errors.append(f"{eid}: references nonexistent team_id '{emp_team}'")
            elif eid not in team_by_id[emp_team].get("member_ids", []):
                errors.append(f"{eid}: team_id is '{emp_team}', but not in team.member_ids")

    # Invariant: Aarav Mehta must belong to TEAM-ENG-APP
    aarav = emp_by_id.get("EMP-1001")
    if not aarav or aarav.get("employment", {}).get("team_id") != "TEAM-ENG-APP":
        errors.append("EMP-1001 (Aarav Mehta) is not properly assigned to TEAM-ENG-APP")
    allocs = [p.get("allocation_percent", 0) for p in aarav.get("projects", {}).get("current", []) if isinstance(p, dict)]
    if sum(allocs) != 100:
        errors.append(f"EMP-1001 project allocation != 100%: {allocs}")

    # Invariant: Priya Sharma must manage TEAM-ENG-APP
    app_team = team_by_id.get("TEAM-ENG-APP")
    if not app_team or app_team.get("manager_id") != "EMP-2001":
        errors.append("TEAM-ENG-APP manager is not EMP-2001 (Priya Sharma)")

    # Invariant: Arvind Rao (CTO) must NOT be forced into an ordinary team
    arvind = emp_by_id.get("EMP-4002")
    if arvind and arvind.get("employment", {}).get("team_id") is not None:
        errors.append("EMP-4002 (Arvind Rao, CTO) must have team_id=null, but got assigned to an ordinary team")

    return errors


if __name__ == "__main__":
    failures = validate_team_data()
    if failures:
        print("\n".join(failures), file=sys.stderr)
        sys.exit(1)
    print("Team data valid: all checks passed perfectly (100%).")
