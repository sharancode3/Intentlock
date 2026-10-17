"""
IntentLock — Enterprise Data Repository
Centralized, read-only service responsible for loading canonical organizational data:
all_employees.json, all_tickets.json, teams.json, projects.json, departments.json.

Loads data ONCE into memory at startup and builds fast normalized lookup indexes.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("enterprise_data_repository")


def normalize_text(val: Optional[str]) -> str:
    """Strip whitespace, collapse repeated spaces, and lowercase."""
    if not val:
        return ""
    cleaned = re.sub(r"\s+", " ", val.strip().lower())
    # strip trailing punctuation safely
    cleaned = re.sub(r"[\.\,\;\:\!\?]+$", "", cleaned).strip()
    return cleaned


class EnterpriseDataRepository:
    _instance: Optional["EnterpriseDataRepository"] = None

    def __init__(self, data_dir: Optional[str] = None):
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            base_dir = Path(__file__).resolve().parent.parent
            self.data_dir = base_dir / "data"

        self.is_loaded: bool = False
        self._cached_directory_revision: Optional[int] = None
        self._cached_ticket_revision: Optional[int] = None

        # Raw containers
        self.employees: List[Dict[str, Any]] = []
        self.tickets: List[Dict[str, Any]] = []
        self.teams: List[Dict[str, Any]] = []
        self.projects: List[Dict[str, Any]] = []
        self.departments: List[Dict[str, Any]] = []

        # Employee Indexes
        self.employees_by_id: Dict[str, Dict[str, Any]] = {}
        self.employees_by_name: Dict[str, Dict[str, Any]] = {}
        self.employees_by_normalized_name: Dict[str, List[Dict[str, Any]]] = {}
        self.employees_by_department: Dict[str, List[Dict[str, Any]]] = {}
        self.employees_by_team: Dict[str, List[Dict[str, Any]]] = {}
        self.employees_by_manager: Dict[str, List[Dict[str, Any]]] = {}

        # Team Indexes
        self.teams_by_id: Dict[str, Dict[str, Any]] = {}
        self.teams_by_name: Dict[str, Dict[str, Any]] = {}
        self.teams_by_department: Dict[str, List[Dict[str, Any]]] = {}

        # Project Indexes
        self.projects_by_id: Dict[str, Dict[str, Any]] = {}
        self.projects_by_name: Dict[str, Dict[str, Any]] = {}
        self.projects_by_alias: Dict[str, Dict[str, Any]] = {}
        self.projects_by_team: Dict[str, List[Dict[str, Any]]] = {}
        self.projects_by_department: Dict[str, List[Dict[str, Any]]] = {}

        # Ticket Indexes
        self.tickets_by_id: Dict[str, Dict[str, Any]] = {}
        self.tickets_by_project: Dict[str, List[Dict[str, Any]]] = {}
        self.tickets_by_department: Dict[str, List[Dict[str, Any]]] = {}
        self.tickets_by_assignee: Dict[str, List[Dict[str, Any]]] = {}

        # Department Indexes
        self.departments_by_id: Dict[str, Dict[str, Any]] = {}
        self.departments_by_name: Dict[str, Dict[str, Any]] = {}
        self.department_aliases: Dict[str, str] = {}

        self.load_data()

    @classmethod
    def get_instance(cls, data_dir: Optional[str] = None) -> "EnterpriseDataRepository":
        if cls._instance is None:
            cls._instance = cls(data_dir=data_dir)
        return cls._instance

    def load_data(self) -> None:
        if self.is_loaded:
            return

        emp_path = self.data_dir / "all_employees.json"
        tkt_path = self.data_dir / "all_tickets.json"
        team_path = self.data_dir / "teams.json"
        prj_path = self.data_dir / "projects.json"
        dept_path = self.data_dir / "departments.json"

        with open(emp_path, "r", encoding="utf-8") as f:
            self.employees = json.load(f)
        with open(tkt_path, "r", encoding="utf-8") as f:
            self.tickets = json.load(f)
        with open(team_path, "r", encoding="utf-8") as f:
            self.teams = json.load(f)
        with open(prj_path, "r", encoding="utf-8") as f:
            self.projects = json.load(f)
        with open(dept_path, "r", encoding="utf-8") as f:
            self.departments = json.load(f)

        self._build_indexes()
        self.is_loaded = True
        logger.info(
            "EnterpriseDataRepository loaded: %d employees, %d tickets, %d teams, %d projects, %d departments.",
            len(self.employees), len(self.tickets), len(self.teams), len(self.projects), len(self.departments)
        )

    def _build_indexes(self) -> None:
        # Clear existing
        self.employees_by_id.clear()
        self.employees_by_name.clear()
        self.employees_by_normalized_name.clear()
        self.employees_by_department.clear()
        self.employees_by_team.clear()
        self.employees_by_manager.clear()

        self.teams_by_id.clear()
        self.teams_by_name.clear()
        self.teams_by_department.clear()

        self.projects_by_id.clear()
        self.projects_by_name.clear()
        self.projects_by_alias.clear()
        self.projects_by_team.clear()
        self.projects_by_department.clear()

        self.tickets_by_id.clear()
        self.tickets_by_project.clear()
        self.tickets_by_department.clear()
        self.tickets_by_assignee.clear()

        self.departments_by_id.clear()
        self.departments_by_name.clear()
        self.department_aliases.clear()

        # 1. Departments
        for d in self.departments:
            did = d["department_id"]
            self.departments_by_id[did] = d
            self.departments_by_name[normalize_text(d["name"])] = d
            self.department_aliases[normalize_text(d["name"])] = did
            for alias in d.get("aliases", []):
                self.department_aliases[normalize_text(alias)] = did

        # 2. Teams
        for t in self.teams:
            tid = t["team_id"]
            self.teams_by_id[tid] = t
            self.teams_by_name[normalize_text(t["name"])] = t
            did = t.get("department_id")
            if did:
                self.teams_by_department.setdefault(did, []).append(t)

        # 3. Projects
        for p in self.projects:
            pid = p["project_id"]
            self.projects_by_id[pid] = p
            self.projects_by_name[normalize_text(p["name"])] = p
            for alias in p.get("aliases", []):
                self.projects_by_alias[normalize_text(alias)] = p
            tid = p.get("owning_team_id")
            if tid:
                self.projects_by_team.setdefault(tid, []).append(p)
            did = p.get("owning_department_id")
            if did:
                self.projects_by_department.setdefault(did, []).append(p)

        # 4. Employees
        for e in self.employees:
            eid = e["employee_id"]
            self.employees_by_id[eid] = e
            full_name = e.get("identity", {}).get("full_name", "")
            pref_name = e.get("identity", {}).get("preferred_name", "")

            norm_full = normalize_text(full_name)
            self.employees_by_name[norm_full] = e
            self.employees_by_normalized_name.setdefault(norm_full, []).append(e)

            if pref_name:
                norm_pref = normalize_text(pref_name)
                self.employees_by_normalized_name.setdefault(norm_pref, []).append(e)

            # index first and last names for partial search
            parts = norm_full.split()
            if len(parts) > 1:
                first, last = parts[0], parts[-1]
                self.employees_by_normalized_name.setdefault(first, []).append(e)
                self.employees_by_normalized_name.setdefault(last, []).append(e)

            did = e.get("employment", {}).get("department_id")
            if did:
                self.employees_by_department.setdefault(did, []).append(e)
            tid = e.get("employment", {}).get("team_id")
            if tid:
                self.employees_by_team.setdefault(tid, []).append(e)
            mid = e.get("reporting", {}).get("manager_id")
            if mid:
                self.employees_by_manager.setdefault(mid, []).append(e)

        # 5. Tickets
        for t in self.tickets:
            tkt_id = t["ticket_id"]
            self.tickets_by_id[tkt_id] = t
            pid = t.get("project_id")
            if pid:
                self.tickets_by_project.setdefault(pid, []).append(t)
            did = t.get("department_id")
            if did:
                self.tickets_by_department.setdefault(did, []).append(t)
            aid = t.get("assignee_id")
            if aid:
                self.tickets_by_assignee.setdefault(aid, []).append(t)

    def is_postgres_active(self) -> bool:
        if os.getenv("INTENTLOCK_OFFLINE_TESTS") == "1":
            return False
        try:
            from backend.core.config import settings
            from backend.adapters.postgres_client import PostgresClient
            return bool(settings.STORAGE_BACKEND == "postgres" or PostgresClient.get_instance().is_configured)
        except Exception:
            return False

    def sync_from_postgres(self) -> bool:
        """
        Synchronize enterprise data from authoritative PostgreSQL tables if configured.
        Loads employees, tickets, departments, teams, and projects from the database.
        """
        if not self.is_postgres_active():
            return False
        try:
            from backend.adapters.postgres_employee_repository import PostgresEmployeeRepository
            from backend.adapters.postgres_ticket_action_store import PostgresTicketActionStore

            emp_repo = PostgresEmployeeRepository.get_instance()
            tkt_store = PostgresTicketActionStore.get_instance()

            db_employees = emp_repo.list_all_employees()
            db_tickets = tkt_store.list_tickets()
            db_depts = emp_repo.list_departments()
            db_teams = emp_repo.list_teams()
            db_projects = emp_repo.list_projects()

            if db_employees:
                self.employees = db_employees
            if db_tickets:
                self.tickets = db_tickets
            if db_depts:
                self.departments = db_depts
            if db_teams:
                self.teams = db_teams
            if db_projects:
                self.projects = db_projects

            self._cached_directory_revision = emp_repo.get_directory_revision()
            self._cached_ticket_revision = emp_repo.get_ticket_revision()

            self._build_indexes()
            logger.info(
                "EnterpriseDataRepository synced from Postgres: %d employees, %d tickets, %d teams, %d projects, %d departments (dir_rev=%s, tkt_rev=%s).",
                len(self.employees), len(self.tickets), len(self.teams), len(self.projects), len(self.departments),
                self._cached_directory_revision, self._cached_ticket_revision
            )
            return True
        except Exception as exc:
            logger.warning("Failed to sync EnterpriseDataRepository from Postgres: %s", exc)
            return False

    def refresh_if_stale(self) -> bool:
        """Checks directory and ticket revisions in DB. If changed, refreshes cache."""
        if not self.is_postgres_active():
            return False
        try:
            from backend.adapters.postgres_employee_repository import PostgresEmployeeRepository
            emp_repo = PostgresEmployeeRepository.get_instance()
            dir_rev = emp_repo.get_directory_revision()
            tkt_rev = emp_repo.get_ticket_revision()

            if (self._cached_directory_revision is None or dir_rev != self._cached_directory_revision or
                self._cached_ticket_revision is None or tkt_rev != self._cached_ticket_revision):
                logger.info("EnterpriseDataRepository detected stale revisions (dir: %s -> %s, tkt: %s -> %s). Refreshing...",
                            self._cached_directory_revision, dir_rev, self._cached_ticket_revision, tkt_rev)
                return self.sync_from_postgres()
            return False
        except Exception as exc:
            logger.warning("Failed checking revision staleness: %s", exc)
            return False

    def update_employee_field(self, employee_id: str, field: str, new_value: Any, version: Optional[int] = None) -> None:
        """Update an employee field in-memory so enterprise query indexes reflect committed actions."""
        emp = self.employees_by_id.get(employee_id)
        if emp:
            if field in ("work_phone", "phone"):
                emp.setdefault("identity", {})["work_phone"] = new_value
                emp["identity"].setdefault("contact", {})["phone"] = new_value
            elif field in emp.get("identity", {}):
                emp["identity"][field] = new_value
            elif field in emp.get("employment", {}):
                emp["employment"][field] = new_value
            if version is not None:
                emp["version"] = version
            # Also update raw list item
            for idx, e in enumerate(self.employees):
                if e.get("employee_id") == employee_id:
                    self.employees[idx] = emp
                    break

    def update_ticket_field(self, ticket_id: str, field: str, new_value: Any, version: Optional[int] = None) -> None:
        """Update a ticket field in-memory so enterprise query indexes reflect committed actions."""
        tkt = self.tickets_by_id.get(ticket_id)
        if tkt:
            tkt[field] = new_value
            if version is not None:
                tkt["version"] = version
            for idx, t in enumerate(self.tickets):
                if t.get("ticket_id") == ticket_id:
                    self.tickets[idx] = t
                    break

    def reload(self) -> None:
        """Force re-reading of canonical datasets and rebuilding indexes."""
        self.is_loaded = False
        self.load_data()
        if self.is_postgres_active():
            self.sync_from_postgres()


enterprise_repo = EnterpriseDataRepository.get_instance()
