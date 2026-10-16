"""Check employee IDs and reporting edges in the compact demo fixture."""

import json
from pathlib import Path


def validate(path: Path = Path("backend/data/all_employees.json")) -> list[str]:
    employees = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    by_id = {row["employee_id"]: row for row in employees}
    if len(by_id) != len(employees):
        errors.append("Duplicate employee IDs")
    for employee_id, row in by_id.items():
        reporting = row.get("reporting", {})
        manager = reporting.get("manager_id")
        if manager:
            if manager not in by_id:
                errors.append(f"{employee_id}: missing manager {manager}")
            elif employee_id not in by_id[manager].get("reporting", {}).get("direct_report_ids", []):
                errors.append(f"{employee_id}: missing reverse report edge on {manager}")
        children = reporting.get("direct_report_ids", [])
        if len(children) != len(set(children)):
            errors.append(f"{employee_id}: duplicate direct-report edge")
        for child in children:
            if child not in by_id:
                errors.append(f"{employee_id}: missing report {child}")
            elif by_id[child].get("reporting", {}).get("manager_id") != employee_id:
                errors.append(f"{employee_id}: inconsistent report edge to {child}")
        seen = {employee_id}
        cursor = manager
        while cursor and cursor in by_id:
            if cursor in seen:
                errors.append(f"{employee_id}: reporting cycle")
                break
            seen.add(cursor)
            cursor = by_id[cursor].get("reporting", {}).get("manager_id")
    return errors


if __name__ == "__main__":
    failures = validate()
    if failures:
        raise SystemExit("\n".join(failures))
    print("Employee graph valid")
