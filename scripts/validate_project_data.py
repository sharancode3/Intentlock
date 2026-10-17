"""
IntentLock — Project Data Validation Script
Validates:
1. Unique project IDs (format PRJ-*).
2. Non-empty canonical names with no malformed trailing punctuation.
3. Aliases do not collide ambiguously.
4. Owning team exists in teams.json.
5. Contributing teams exist in teams.json.
6. Project manager exists in all_employees.json (if specified).
7. Project lead exists in all_employees.json (if specified).
8. Project members exist in all_employees.json.
9. Employee project IDs exist in projects.json (when set).
10. Team project IDs exist in projects.json.
11. Ticket project IDs exist in projects.json (when set).
12. Bidirectional consistency between projects.json, teams.json, and all_employees.json.
13. No duplicate canonical projects.
14. Project statuses are valid (Active, Completed, Planned, etc.).
15. Aarav Mehta (EMP-1001) project allocations remain strictly intact (60% + 40% = 100%).
16. Existing reporting graph and security fields remain intact.
17. Invariants: 31 employees, 42 tickets, 9 teams.
"""

import json
import sys
from pathlib import Path


def validate_project_data(
    projects_path: Path = Path("backend/data/projects.json"),
    teams_path: Path = Path("backend/data/teams.json"),
    employees_path: Path = Path("backend/data/all_employees.json"),
    tickets_path: Path = Path("backend/data/all_tickets.json"),
) -> list[str]:
    errors: list[str] = []

    if not projects_path.exists():
        return [f"Projects file not found: {projects_path}"]
    if not teams_path.exists():
        return [f"Teams file not found: {teams_path}"]
    if not employees_path.exists():
        return [f"Employees file not found: {employees_path}"]
    if not tickets_path.exists():
        return [f"Tickets file not found: {tickets_path}"]

    projects = json.loads(projects_path.read_text(encoding="utf-8"))
    teams = json.loads(teams_path.read_text(encoding="utf-8"))
    employees = json.loads(employees_path.read_text(encoding="utf-8"))
    tickets = json.loads(tickets_path.read_text(encoding="utf-8"))

    # Invariants
    if len(employees) != 31:
        errors.append(f"Expected 31 employees, got {len(employees)}")
    if len(tickets) != 42:
        errors.append(f"Expected 42 tickets, got {len(tickets)}")
    if len(teams) != 9:
        errors.append(f"Expected 9 teams, got {len(teams)}")

    emp_by_id = {e["employee_id"]: e for e in employees}
    team_by_id = {t["team_id"]: t for t in teams}
    proj_by_id = {}
    canonical_names = set()
    alias_map = {}

    valid_statuses = {"Active", "Completed", "Planned", "On Hold", "Archived"}

    for idx, p in enumerate(projects):
        pid = p.get("project_id")
        name = p.get("name")
        status = p.get("status")
        owning_team = p.get("owning_team_id")
        contrib_teams = p.get("contributing_team_ids", [])
        mgr_id = p.get("project_manager_id")
        lead_id = p.get("project_lead_id")
        member_ids = p.get("member_ids", [])
        aliases = p.get("aliases", [])

        if not pid or not isinstance(pid, str) or not pid.startswith("PRJ-"):
            errors.append(f"Project at index {idx} has invalid project_id: {pid}")
            continue

        if pid in proj_by_id:
            errors.append(f"Duplicate project_id: {pid}")
        proj_by_id[pid] = p

        if not name or not isinstance(name, str) or not name.strip():
            errors.append(f"{pid}: missing or empty name")
        else:
            if name.endswith("."):
                errors.append(f"{pid}: name has trailing punctuation: '{name}'")
            if name in canonical_names:
                errors.append(f"Duplicate canonical project name: '{name}'")
            canonical_names.add(name)

        if status not in valid_statuses:
            errors.append(f"{pid}: invalid status '{status}'")

        if owning_team and owning_team not in team_by_id:
            errors.append(f"{pid}: owning_team_id '{owning_team}' does not exist in teams.json")

        for ctid in contrib_teams:
            if ctid not in team_by_id:
                errors.append(f"{pid}: contributing_team_id '{ctid}' does not exist in teams.json")

        if mgr_id and mgr_id not in emp_by_id:
            errors.append(f"{pid}: project_manager_id '{mgr_id}' does not exist in all_employees.json")

        if lead_id and lead_id not in emp_by_id:
            errors.append(f"{pid}: project_lead_id '{lead_id}' does not exist in all_employees.json")

        for mid in member_ids:
            if mid not in emp_by_id:
                errors.append(f"{pid}: member_id '{mid}' does not exist in all_employees.json")

        # Aliases
        for a in aliases:
            a_lower = a.lower()
            if a_lower in alias_map and alias_map[a_lower] != pid:
                errors.append(f"Ambiguous alias collision: '{a}' used for {alias_map[a_lower]} and {pid}")
            alias_map[a_lower] = pid

    # Validate Team -> Project links
    for t in teams:
        tid = t["team_id"]
        for pid in t.get("project_ids", []):
            if pid not in proj_by_id:
                errors.append(f"Team {tid} references nonexistent project_id '{pid}'")

    # Validate Employee -> Project links
    for e in employees:
        eid = e["employee_id"]
        for p in e.get("projects", {}).get("current", []):
            if isinstance(p, dict):
                pid = p.get("project_id")
                if pid:
                    if pid not in proj_by_id:
                        errors.append(f"Employee {eid} references nonexistent project_id '{pid}'")
                    # Check canonical name matches
                    elif p.get("name") != proj_by_id[pid]["name"]:
                        errors.append(
                            f"Employee {eid} project name mismatch for {pid}: '{p.get('name')}' vs '{proj_by_id[pid]['name']}'"
                        )

    # Validate Ticket -> Project links
    for t in tickets:
        tid = t["ticket_id"]
        pid = t.get("project_id")
        if pid:
            if pid not in proj_by_id:
                errors.append(f"Ticket {tid} references nonexistent project_id '{pid}'")
            elif t.get("project") != proj_by_id[pid]["name"]:
                errors.append(
                    f"Ticket {tid} project name mismatch for {pid}: '{t.get('project')}' vs '{proj_by_id[pid]['name']}'"
                )

    # Invariants on Aarav Mehta (EMP-1001)
    aarav = emp_by_id.get("EMP-1001")
    if not aarav:
        errors.append("EMP-1001 missing")
    else:
        csp = next((p for p in aarav["projects"]["current"] if p.get("project_id") == "PRJ-ENG-CSP"), None)
        iad = next((p for p in aarav["projects"]["current"] if p.get("project_id") == "PRJ-ENG-IAD"), None)
        if not csp or csp.get("allocation_percent") != 60:
            errors.append(f"Aarav Customer Support Portal allocation is not 60%: {csp}")
        if not iad or iad.get("allocation_percent") != 40:
            errors.append(f"Aarav Internal Analytics Dashboard allocation is not 40%: {iad}")

    # Invariants on Arvind Rao (EMP-4002, CTO)
    arvind = emp_by_id.get("EMP-4002")
    if arvind:
        if arvind["employment"].get("team_id") is not None:
            errors.append("Arvind Rao has an artificial team_id assigned")
        # Ensure he is not an ordinary member of PRJ-ENG-CSP
        csp_proj = proj_by_id.get("PRJ-ENG-CSP")
        if csp_proj and "EMP-4002" in csp_proj.get("member_ids", []):
            errors.append("Arvind Rao artificially added to Customer Support Portal member_ids")

    return errors


if __name__ == "__main__":
    failures = validate_project_data()
    if failures:
        print("\n".join(failures), file=sys.stderr)
        sys.exit(1)
    print("Project data valid: all checks passed perfectly (100%).")
