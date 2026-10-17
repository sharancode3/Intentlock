"""
IntentLock — Deterministic Entity Resolver
Resolves entity mentions to canonical IDs across:
EMPLOYEE, TEAM, DEPARTMENT, PROJECT, TICKET.

Resolution Priority:
1. Exact canonical ID
2. Exact normalized name
3. Exact known alias
4. Unique safe partial match
5. Ambiguous candidates -> clarification
6. No match -> not found
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Tuple

from backend.services.enterprise_data import EnterpriseDataRepository, normalize_text

EntityType = Literal["employee", "team", "department", "project", "ticket"]


@dataclass
class ResolutionResult:
    status: Literal["resolved", "clarification_required", "not_found"]
    entity_type: Optional[EntityType] = None
    entity_id: Optional[str] = None
    canonical_name: Optional[str] = None
    record: Optional[Dict[str, Any]] = None
    query: Optional[str] = None
    candidates: Optional[List[Dict[str, Any]]] = None
    message: Optional[str] = None


class EntityResolver:
    def __init__(self, repo: Optional[EnterpriseDataRepository] = None):
        self.repo = repo or EnterpriseDataRepository.get_instance()

    def resolve_ticket(self, query: str) -> ResolutionResult:
        raw = query.strip()
        ticket_match = re.search(r"\bTKT[-_ ]?\d{4}[-_ ]?\d{3}\b", raw, re.I)
        if ticket_match:
            tkt_id = re.sub(r"[_ ]", "-", ticket_match.group().upper())
            tkt = self.repo.tickets_by_id.get(tkt_id)
            if tkt:
                return ResolutionResult(
                    status="resolved",
                    entity_type="ticket",
                    entity_id=tkt_id,
                    canonical_name=tkt.get("title"),
                    record=tkt,
                    query=query,
                )
            return ResolutionResult(status="not_found", entity_type="ticket", query=tkt_id)

        # Title match
        norm = normalize_text(raw)
        matched = [t for t in self.repo.tickets if normalize_text(t.get("title")) == norm]
        if len(matched) == 1:
            t = matched[0]
            return ResolutionResult(
                status="resolved",
                entity_type="ticket",
                entity_id=t["ticket_id"],
                canonical_name=t.get("title"),
                record=t,
                query=query,
            )
        return ResolutionResult(status="not_found", entity_type="ticket", query=query)

    def resolve_department(self, query: str) -> ResolutionResult:
        norm = normalize_text(query)
        # 1. Exact ID
        upper = query.strip().upper().replace(" ", "-")
        if upper in self.repo.departments_by_id:
            dept = self.repo.departments_by_id[upper]
            return ResolutionResult(
                status="resolved",
                entity_type="department",
                entity_id=upper,
                canonical_name=dept["name"],
                record=dept,
                query=query,
            )

        # 2. Exact name
        if norm in self.repo.departments_by_name:
            dept = self.repo.departments_by_name[norm]
            return ResolutionResult(
                status="resolved",
                entity_type="department",
                entity_id=dept["department_id"],
                canonical_name=dept["name"],
                record=dept,
                query=query,
            )

        # 3. Known alias
        if norm in self.repo.department_aliases:
            did = self.repo.department_aliases[norm]
            dept = self.repo.departments_by_id[did]
            return ResolutionResult(
                status="resolved",
                entity_type="department",
                entity_id=did,
                canonical_name=dept["name"],
                record=dept,
                query=query,
            )

        # 4. Safe substring/word match across departments
        matches = []
        for did, dept in self.repo.departments_by_id.items():
            dept_norm = normalize_text(dept["name"])
            if dept_norm in norm or norm in dept_norm or any(re.search(rf"\b{re.escape(a.lower())}\b", norm) for a in dept.get("aliases", [])):
                matches.append(dept)

        matches = list({m["department_id"]: m for m in matches}.values())
        if len(matches) == 1:
            d = matches[0]
            return ResolutionResult(
                status="resolved",
                entity_type="department",
                entity_id=d["department_id"],
                canonical_name=d["name"],
                record=d,
                query=query,
            )
        elif len(matches) > 1:
            return ResolutionResult(
                status="clarification_required",
                entity_type="department",
                query=query,
                candidates=[{"department_id": m["department_id"], "name": m["name"]} for m in matches],
                message=f"Multiple departments match '{query}'.",
            )

        return ResolutionResult(status="not_found", entity_type="department", query=query)

    def resolve_team(self, query: str) -> ResolutionResult:
        upper = query.strip().upper().replace(" ", "-")
        # 1. Exact ID
        if upper in self.repo.teams_by_id:
            team = self.repo.teams_by_id[upper]
            return ResolutionResult(
                status="resolved",
                entity_type="team",
                entity_id=upper,
                canonical_name=team["name"],
                record=team,
                query=query,
            )

        norm = normalize_text(query)
        # 2. Exact name
        if norm in self.repo.teams_by_name:
            team = self.repo.teams_by_name[norm]
            return ResolutionResult(
                status="resolved",
                entity_type="team",
                entity_id=team["team_id"],
                canonical_name=team["name"],
                record=team,
                query=query,
            )

        # 3. Safe partial/word match
        matches = []
        for tid, team in self.repo.teams_by_id.items():
            team_norm = normalize_text(team["name"])
            if team_norm in norm or norm in team_norm or all(word in norm for word in team_norm.split() if len(word) > 3):
                matches.append(team)

        if len(matches) == 1:
            t = matches[0]
            return ResolutionResult(
                status="resolved",
                entity_type="team",
                entity_id=t["team_id"],
                canonical_name=t["name"],
                record=t,
                query=query,
            )
        elif len(matches) > 1:
            return ResolutionResult(
                status="clarification_required",
                entity_type="team",
                query=query,
                candidates=[{"team_id": m["team_id"], "name": m["name"]} for m in matches],
                message=f"Multiple teams match '{query}'.",
            )

        return ResolutionResult(status="not_found", entity_type="team", query=query)

    def resolve_project(self, query: str) -> ResolutionResult:
        upper = query.strip().upper().replace(" ", "-")
        # 1. Exact ID
        if upper in self.repo.projects_by_id:
            prj = self.repo.projects_by_id[upper]
            return ResolutionResult(
                status="resolved",
                entity_type="project",
                entity_id=upper,
                canonical_name=prj["name"],
                record=prj,
                query=query,
            )

        norm = normalize_text(query)
        # 2. Exact name
        if norm in self.repo.projects_by_name:
            prj = self.repo.projects_by_name[norm]
            return ResolutionResult(
                status="resolved",
                entity_type="project",
                entity_id=prj["project_id"],
                canonical_name=prj["name"],
                record=prj,
                query=query,
            )

        # 3. Known alias
        if norm in self.repo.projects_by_alias:
            prj = self.repo.projects_by_alias[norm]
            return ResolutionResult(
                status="resolved",
                entity_type="project",
                entity_id=prj["project_id"],
                canonical_name=prj["name"],
                record=prj,
                query=query,
            )

        # 4. Safe partial match & phrase match in sentence
        matches = []
        for pid, prj in self.repo.projects_by_id.items():
            prj_norm = normalize_text(prj["name"])
            if prj_norm in norm or norm in prj_norm:
                matches.append(prj)
            else:
                for a in prj.get("aliases", []):
                    a_norm = normalize_text(a)
                    if a_norm in norm or norm in a_norm:
                        matches.append(prj)
                        break

        matches = list({m["project_id"]: m for m in matches}.values())
        if len(matches) == 1:
            p = matches[0]
            return ResolutionResult(
                status="resolved",
                entity_type="project",
                entity_id=p["project_id"],
                canonical_name=p["name"],
                record=p,
                query=query,
            )
        elif len(matches) > 1:
            return ResolutionResult(
                status="clarification_required",
                entity_type="project",
                query=query,
                candidates=[{"project_id": m["project_id"], "name": m["name"]} for m in matches],
                message=f"Multiple projects match '{query}'.",
            )

        return ResolutionResult(status="not_found", entity_type="project", query=query)

    def resolve_employee(self, query: str) -> ResolutionResult:
        raw = query.strip()
        # 1. Exact ID
        id_match = re.search(r"\b((?:EMP|RND|EXE)[-_ ]?\d{4})\b", raw, re.I)
        if id_match:
            eid = re.sub(r"[_ ]", "-", id_match.group(1).upper())
            emp = self.repo.employees_by_id.get(eid)
            if emp:
                return ResolutionResult(
                    status="resolved",
                    entity_type="employee",
                    entity_id=eid,
                    canonical_name=emp.get("identity", {}).get("full_name"),
                    record=emp,
                    query=query,
                )
            return ResolutionResult(status="not_found", entity_type="employee", query=eid)

        norm = normalize_text(raw)
        # 2. Exact full name
        if norm in self.repo.employees_by_name:
            emp = self.repo.employees_by_name[norm]
            return ResolutionResult(
                status="resolved",
                entity_type="employee",
                entity_id=emp["employee_id"],
                canonical_name=emp.get("identity", {}).get("full_name"),
                record=emp,
                query=query,
            )

        # 3. Direct normalized match
        cands = self.repo.employees_by_normalized_name.get(norm, [])
        unique_cands = list({c["employee_id"]: c for c in cands}.values())

        # 4. If query is a sentence, search for employee mentions in the sentence
        if not unique_cands:
            # Check full names first
            for full_n, emp in self.repo.employees_by_name.items():
                if re.search(rf"\b{re.escape(full_n)}\b", norm):
                    return ResolutionResult(
                        status="resolved",
                        entity_type="employee",
                        entity_id=emp["employee_id"],
                        canonical_name=emp.get("identity", {}).get("full_name"),
                        record=emp,
                        query=query,
                    )
            # Check individual tokens / preferred names
            found_by_token = []
            for token in re.findall(r"[a-zA-Z]{3,}", norm):
                if token in ["show", "profile", "manager", "team", "department", "project", "tickets", "ticket", "what", "who", "which", "does", "know", "work"]:
                    continue
                if token in self.repo.employees_by_normalized_name:
                    found_by_token.extend(self.repo.employees_by_normalized_name[token])
            unique_cands = list({c["employee_id"]: c for c in found_by_token}.values())

        if len(unique_cands) == 1:
            e = unique_cands[0]
            return ResolutionResult(
                status="resolved",
                entity_type="employee",
                entity_id=e["employee_id"],
                canonical_name=e.get("identity", {}).get("full_name"),
                record=e,
                query=query,
            )
        elif len(unique_cands) > 1:
            return ResolutionResult(
                status="clarification_required",
                entity_type="employee",
                query=query,
                candidates=[
                    {
                        "employee_id": c["employee_id"],
                        "name": c.get("identity", {}).get("full_name"),
                        "designation": c.get("employment", {}).get("designation"),
                        "department": c.get("employment", {}).get("department"),
                    }
                    for c in unique_cands
                ],
                message=f"Multiple employees match '{query}'. Which one do you mean?",
            )

        return ResolutionResult(status="not_found", entity_type="employee", query=query)

    def resolve_any(self, query: str) -> ResolutionResult:
        """Resolve across employee, project, team, department, and ticket deterministically."""
        # Check ticket ID pattern
        if re.search(r"\bTKT[-_ ]?\d{4}", query, re.I):
            return self.resolve_ticket(query)

        # Check employee ID pattern
        if re.search(r"\b(?:EMP|RND|EXE)[-_ ]?\d{4}\b", query, re.I):
            return self.resolve_employee(query)

        # Try exact employee
        res = self.resolve_employee(query)
        if res.status != "not_found":
            return res

        # Try exact department
        res = self.resolve_department(query)
        if res.status != "not_found":
            return res

        # Try exact team
        res = self.resolve_team(query)
        if res.status != "not_found":
            return res

        # Try exact project
        res = self.resolve_project(query)
        if res.status != "not_found":
            return res

        return ResolutionResult(status="not_found", query=query)


entity_resolver = EntityResolver()
