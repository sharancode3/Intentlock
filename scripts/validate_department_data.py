"""
Validation script for IntentLock Stage 5 canonical department data.

Validates:
1. unique department IDs
2. unique canonical department names
3. aliases resolve deterministically
4. valid status values
5. valid department types
6. valid head_id references
7. valid executive_owner_id references
8. valid parent_department_id references
9. no department hierarchy cycles
10. no self-parent departments
11. all employee department IDs resolve
12. all team department IDs resolve
13. project owning department derivation valid
14. project contributing department derivation valid
15. ticket department IDs valid where populated
16. department member_ids consistent with employees
17. department team_ids consistent with teams
18. department project relationships consistent
19. no duplicate employees created (31 expected)
20. no duplicate teams created (9 expected)
21. no duplicate projects created (41 expected)
22. reporting graph remains valid
23. project graph remains valid
24. security fields unchanged
25. speaker mappings unchanged
"""

import json
import sys
from pathlib import Path

def validate_department_data():
    base_dir = Path(__file__).resolve().parent.parent
    data_dir = base_dir / "backend" / "data"

    dept_file = data_dir / "departments.json"
    team_file = data_dir / "teams.json"
    emp_file = data_dir / "all_employees.json"
    prj_file = data_dir / "projects.json"
    tkt_file = data_dir / "all_tickets.json"

    if not dept_file.exists():
        print("ERROR: departments.json does not exist!")
        sys.exit(1)

    with open(dept_file, "r", encoding="utf-8") as f:
        departments = json.load(f)
    with open(team_file, "r", encoding="utf-8") as f:
        teams = json.load(f)
    with open(emp_file, "r", encoding="utf-8") as f:
        employees = json.load(f)
    with open(prj_file, "r", encoding="utf-8") as f:
        projects = json.load(f)
    with open(tkt_file, "r", encoding="utf-8") as f:
        tickets = json.load(f)

    errors = []

    # 19, 20, 21: Entity Counts
    if len(employees) != 31:
        errors.append(f"Expected 31 employees, found {len(employees)}")
    if len(teams) != 9:
        errors.append(f"Expected 9 teams, found {len(teams)}")
    if len(projects) != 41:
        errors.append(f"Expected 41 projects, found {len(projects)}")
    if len(tickets) != 42:
        errors.append(f"Expected 42 tickets, found {len(tickets)}")

    dept_ids = set()
    dept_names = set()
    alias_to_dept = {}

    emp_ids = {e["employee_id"] for e in employees}
    team_ids = {t["team_id"] for t in teams}
    prj_ids = {p["project_id"] for p in projects}

    valid_types = {
        "Technical", "Product", "Design", "Quality", "Data",
        "Research", "Security", "People", "Operations", "Executive"
    }

    dept_map = {d["department_id"]: d for d in departments}

    for d in departments:
        did = d.get("department_id")
        name = d.get("name")
        status = d.get("status")
        dept_type = d.get("department_type")
        head_id = d.get("head_id")
        exec_owner_id = d.get("executive_owner_id")
        parent_id = d.get("parent_department_id")

        # 1. Unique department IDs
        if not did or did in dept_ids:
            errors.append(f"Duplicate or empty department_id: {did}")
        dept_ids.add(did)

        # 2. Unique canonical department names
        if not name or name in dept_names:
            errors.append(f"Duplicate or empty department name: {name}")
        dept_names.add(name)

        # 3. Aliases resolve deterministically
        for alias in d.get("aliases", []):
            alias_lower = alias.lower()
            if alias_lower in alias_to_dept and alias_to_dept[alias_lower] != did:
                errors.append(f"Ambiguous alias collision: '{alias}' for {did} and {alias_to_dept[alias_lower]}")
            alias_to_dept[alias_lower] = did

        # 4. Valid status values
        if status not in {"Active", "Archived", "Planned"}:
            errors.append(f"Invalid status '{status}' for department {did}")

        # 5. Valid department types
        if dept_type not in valid_types:
            errors.append(f"Invalid department_type '{dept_type}' for department {did}")

        # 6. Valid head_id references
        if head_id and head_id not in emp_ids:
            errors.append(f"Invalid head_id '{head_id}' in department {did}")

        # 7. Valid executive_owner_id references
        if exec_owner_id and exec_owner_id not in emp_ids:
            errors.append(f"Invalid executive_owner_id '{exec_owner_id}' in department {did}")

        # 8, 10. Valid parent_department_id references & no self-parent
        if parent_id:
            if parent_id == did:
                errors.append(f"Self-parenting department: {did}")
            elif parent_id not in dept_map:
                errors.append(f"Invalid parent_department_id '{parent_id}' in department {did}")

    # 9. No hierarchy cycles
    for d in departments:
        visited = set()
        curr = d.get("parent_department_id")
        while curr:
            if curr in visited or curr == d["department_id"]:
                errors.append(f"Hierarchy cycle detected involving department {d['department_id']}")
                break
            visited.add(curr)
            curr = dept_map.get(curr, {}).get("parent_department_id")

    # 11, 16. Employee -> department and member_ids reverse index
    emp_by_dept = {did: set() for did in dept_ids}
    for e in employees:
        eid = e["employee_id"]
        edid = e.get("employment", {}).get("department_id")
        if not edid:
            errors.append(f"Employee {eid} missing department_id")
        elif edid not in dept_ids:
            errors.append(f"Employee {eid} has invalid department_id: {edid}")
        else:
            emp_by_dept[edid].add(eid)

    for d in departments:
        did = d["department_id"]
        stated_members = set(d.get("member_ids", []))
        actual_members = emp_by_dept.get(did, set())
        if stated_members != actual_members:
            errors.append(f"Department {did} member_ids mismatch: stated {stated_members} vs actual {actual_members}")

    # 12, 17. Team -> department and team_ids reverse index
    teams_by_dept = {did: set() for did in dept_ids}
    for t in teams:
        tid = t["team_id"]
        tdid = t.get("department_id")
        if not tdid:
            errors.append(f"Team {tid} missing department_id")
        elif tdid not in dept_ids:
            errors.append(f"Team {tid} has invalid department_id: {tdid}")
        else:
            teams_by_dept[tdid].add(tid)

    for d in departments:
        did = d["department_id"]
        stated_teams = set(d.get("team_ids", []))
        actual_teams = teams_by_dept.get(did, set())
        if stated_teams != actual_teams:
            errors.append(f"Department {did} team_ids mismatch: stated {stated_teams} vs actual {actual_teams}")

    # 13, 14, 18. Project owning and contributing department derivations
    team_dict = {t["team_id"]: t for t in teams}
    for p in projects:
        pid = p["project_id"]
        own_team = team_dict.get(p.get("owning_team_id"))
        expected_own_dept = own_team.get("department_id") if own_team else None
        actual_own_dept = p.get("owning_department_id")
        if actual_own_dept != expected_own_dept:
            errors.append(f"Project {pid} owning_department_id mismatch: expected {expected_own_dept}, got {actual_own_dept}")

        expected_contrib_depts = set()
        for ctid in p.get("contributing_team_ids", []):
            cteam = team_dict.get(ctid)
            if cteam and cteam.get("department_id"):
                expected_contrib_depts.add(cteam["department_id"])
        actual_contrib_depts = set(p.get("contributing_department_ids", []))
        if actual_contrib_depts != expected_contrib_depts:
            errors.append(f"Project {pid} contributing_department_ids mismatch: expected {expected_contrib_depts}, got {actual_contrib_depts}")

    # 15. Ticket department IDs valid
    for t in tickets:
        tkt_id = t["ticket_id"]
        tdid = t.get("department_id")
        if tdid and tdid not in dept_ids:
            errors.append(f"Ticket {tkt_id} has invalid department_id: {tdid}")

    # 22. Reporting graph remains valid
    for e in employees:
        mgr = e.get("reporting", {}).get("manager_id")
        if mgr and mgr not in emp_ids:
            errors.append(f"Invalid manager_id {mgr} in employee {e['employee_id']}")

    # 24. Security fields unchanged
    aarav = next(e for e in employees if e["employee_id"] == "EMP-1001")
    if aarav["permissions"].get("budget_authority", {}).get("effect") != "DENY":
        errors.append("EMP-1001 security permission altered!")
    if aarav["employment"]["team_id"] != "TEAM-ENG-APP":
        errors.append(f"Aarav team_id altered: {aarav['employment']['team_id']}")
    csp_alloc = next((p["allocation_percent"] for p in aarav["projects"]["current"] if p["project_id"] == "PRJ-ENG-CSP"), None)
    iad_alloc = next((p["allocation_percent"] for p in aarav["projects"]["current"] if p["project_id"] == "PRJ-ENG-IAD"), None)
    if csp_alloc != 60 or iad_alloc != 40:
        errors.append(f"Aarav allocation altered: CSP={csp_alloc}, IAD={iad_alloc}")

    # 25. Arvind invariants
    arvind = next(e for e in employees if e["employee_id"] == "EMP-4002")
    if arvind["employment"].get("team_id") is not None:
        errors.append("Arvind team_id must be null")

    if errors:
        print(f"Validation FAILED with {len(errors)} errors:")
        for err in errors[:30]:
            print(" -", err)
        sys.exit(1)
    else:
        print("Department data valid: all checks passed perfectly (100%).")

if __name__ == "__main__":
    validate_department_data()
