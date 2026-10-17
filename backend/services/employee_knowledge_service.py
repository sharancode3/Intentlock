"""
IntentLock — Employee Knowledge Service
Fast, in-memory, completely local employee/company retrieval service.
Loads the canonical dataset ONCE at startup and maintains normalized indexes.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional, Set

from backend.core.config import settings

logger = logging.getLogger("employee_knowledge_service")

class EmployeeKnowledgeService:
    _instance: Optional["EmployeeKnowledgeService"] = None

    def __init__(self, data_path: Optional[str] = None):
        self.data_path = data_path or settings.DATA_PATH
        self.is_loaded: bool = False
        self._raw_employees: List[Dict[str, Any]] = []
        self._cached_revision: int = 1

        # In-memory indexes
        self.employees_by_id: Dict[str, Dict[str, Any]] = {}
        self.employees_by_name: Dict[str, Dict[str, Any]] = {}
        self.employees_by_department: Dict[str, List[Dict[str, Any]]] = {}
        self.employees_by_role: Dict[str, List[Dict[str, Any]]] = {}
        self.employees_by_manager_id: Dict[str, List[Dict[str, Any]]] = {}
        self.employees_by_skill: Dict[str, List[Dict[str, Any]]] = {}
        self.employees_by_project: Dict[str, List[Dict[str, Any]]] = {}
        self.employees_by_level: Dict[str, List[Dict[str, Any]]] = {}
        self.direct_reports_by_id: Dict[str, List[Dict[str, Any]]] = {}

        self.load_data()

    @classmethod
    def get_instance(cls, data_path: Optional[str] = None) -> "EmployeeKnowledgeService":
        if cls._instance is None:
            cls._instance = cls(data_path=data_path)
        return cls._instance

    @staticmethod
    def _normalize(val: Optional[str]) -> str:
        """Helper to trim and lowercase a string for case-insensitive lookup."""
        return val.strip().lower() if val else ""

    def load_data(self) -> None:
        """Load canonical employee dataset from Postgres or local JSON and build indexes."""
        if self.is_loaded:
            logger.info("EmployeeKnowledgeService is already loaded into memory.")
            return

        if settings.STORAGE_BACKEND == "postgres":
            from backend.adapters.postgres_employee_repository import PostgresEmployeeRepository
            repo = PostgresEmployeeRepository.get_instance()
            logger.info("Loading canonical employee dataset from Supabase Postgres...")
            self._raw_employees = repo.list_all_employees()
            self._cached_revision = repo.get_directory_revision()
        else:
            if not os.path.exists(self.data_path):
                raise FileNotFoundError(
                    f"Canonical dataset not found at {self.data_path}. "
                    "Please run scripts/build_employee_knowledge_base.py first."
                )

            logger.info(f"Loading canonical employee dataset from {self.data_path}...")
            with open(self.data_path, "r", encoding="utf-8") as f:
                self._raw_employees = json.load(f)

        self._build_indexes()
        self.is_loaded = True
        logger.info(
            f"Successfully loaded and indexed {len(self._raw_employees)} employees."
        )

    def refresh_if_stale(self) -> None:
        """Checks directory revision and reloads indexes if another process or transaction mutated records."""
        if settings.STORAGE_BACKEND == "postgres":
            from backend.adapters.postgres_employee_repository import PostgresEmployeeRepository
            repo = PostgresEmployeeRepository.get_instance()
            try:
                rev = repo.get_directory_revision()
                if rev != self._cached_revision:
                    self._raw_employees = repo.list_all_employees()
                    self._build_indexes()
                    self._cached_revision = rev
                    logger.info("Employee directory cache invalidated and reloaded to revision %s.", rev)
            except Exception as exc:
                logger.warning("Directory revision check failed: %s", exc)

    def reload(self) -> None:
        """Forces immediate rebuild of employee indexes."""
        self.is_loaded = False
        self.load_data()

    def update_employee_phone_in_memory(self, employee_id: str, new_phone: str) -> None:
        """Update an employee's phone number in the in-memory cache (for testing or local cache sync)."""
        emp = self.employees_by_id.get(employee_id)
        if emp:
            emp.setdefault("identity", {})["work_phone"] = new_phone
            emp["identity"].setdefault("contact", {})["phone"] = new_phone
            emp["version"] = emp.get("version", 1) + 1

    def _build_indexes(self) -> None:
        """Build normalized indexes over the raw in-memory employee records."""
        self.employees_by_id.clear()
        self.employees_by_name.clear()
        self.employees_by_department.clear()
        self.employees_by_role.clear()
        self.employees_by_manager_id.clear()
        self.employees_by_skill.clear()
        self.employees_by_project.clear()
        self.employees_by_level.clear()
        self.direct_reports_by_id.clear()

        for emp in self._raw_employees:
            eid = emp["employee_id"]
            self.employees_by_id[eid] = emp

            # Index by name (full and preferred)
            full_name_norm = self._normalize(emp["identity"]["full_name"])
            self.employees_by_name[full_name_norm] = emp
            pref_name_norm = self._normalize(emp["identity"].get("preferred_name"))
            if pref_name_norm and pref_name_norm not in self.employees_by_name:
                self.employees_by_name[pref_name_norm] = emp

            # Index by department
            dept_norm = self._normalize(emp["employment"]["department"])
            self.employees_by_department.setdefault(dept_norm, []).append(emp)

            # Index by role / designation
            role_norm = self._normalize(emp["employment"]["designation"])
            self.employees_by_role.setdefault(role_norm, []).append(emp)

            # Index by level
            lvl_norm = self._normalize(emp["employment"]["organizational_level"])
            self.employees_by_level.setdefault(lvl_norm, []).append(emp)

            # Index by manager ID
            mgr_id = emp["reporting"].get("manager_id")
            if mgr_id:
                self.employees_by_manager_id.setdefault(mgr_id, []).append(emp)

            # Index by skills (technical, management, research, tools)
            skills_dict = emp.get("skills", {})
            for skill_type, skill_list in skills_dict.items():
                for s in skill_list:
                    s_norm = self._normalize(s)
                    self.employees_by_skill.setdefault(s_norm, []).append(emp)

            # Index by projects (current and previous)
            projects_dict = emp.get("projects", {})
            all_projs = projects_dict.get("current", []) + projects_dict.get("previous", [])
            for p in all_projs:
                p_norm = self._normalize(p["name"])
                self.employees_by_project.setdefault(p_norm, []).append(emp)

        # Build direct reports index
        for eid, emp in self.employees_by_id.items():
            report_ids = emp["reporting"].get("direct_report_ids", [])
            reports = [self.employees_by_id[rid] for rid in report_ids if rid in self.employees_by_id]
            self.direct_reports_by_id[eid] = reports

    # =========================================================================
    # Required Retrieval Methods
    # =========================================================================

    def list_all_employees(self) -> List[Dict[str, Any]]:
        """Return all canonical employee records."""
        self.refresh_if_stale()
        return list(self._raw_employees)

    def get_employee_by_id(self, employee_id: str) -> Optional[Dict[str, Any]]:
        """Exact lookup by employee ID (case-insensitive e.g. emp-1001 or EMP-1001)."""
        if not employee_id:
            return None
        self.refresh_if_stale()
        return self.employees_by_id.get(employee_id.strip().upper())

    def find_employee_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Lookup by full name, preferred name, or substring match."""
        if not name:
            return None
        self.refresh_if_stale()
        norm_name = self._normalize(name)
        if norm_name in self.employees_by_name:
            return self.employees_by_name[norm_name]

        # Partial matching
        for k, emp in self.employees_by_name.items():
            if norm_name in k or k in norm_name:
                return emp
        return None

    def search_employees(self, query: str) -> List[Dict[str, Any]]:
        """Free-text multi-field search across identity, designation, department, skills, and projects."""
        if not query:
            return []
        self.refresh_if_stale()
        q_norm = self._normalize(query)
        results: Dict[str, Dict[str, Any]] = {}

        # Check exact or partial name
        for k, emp in self.employees_by_name.items():
            if q_norm in k or k in q_norm:
                results[emp["employee_id"]] = emp

        # Check department
        for d, emps in self.employees_by_department.items():
            if q_norm in d:
                for emp in emps:
                    results[emp["employee_id"]] = emp

        # Check role / designation
        for r, emps in self.employees_by_role.items():
            if q_norm in r:
                for emp in emps:
                    results[emp["employee_id"]] = emp

        # Check skills
        for s, emps in self.employees_by_skill.items():
            if q_norm in s:
                for emp in emps:
                    results[emp["employee_id"]] = emp

        # Check projects
        for p, emps in self.employees_by_project.items():
            if q_norm in p:
                for emp in emps:
                    results[emp["employee_id"]] = emp

        return list(results.values())

    def get_employee_projects(self, employee_id: str) -> Dict[str, Any]:
        """Retrieve current and past projects for an employee."""
        emp = self.get_employee_by_id(employee_id)
        if not emp:
            return {"current": [], "previous": []}
        return emp.get("projects", {"current": [], "previous": []})

    def get_employee_skills(self, employee_id: str) -> Dict[str, List[str]]:
        """Retrieve structured skills for an employee."""
        emp = self.get_employee_by_id(employee_id)
        if not emp:
            return {"technical": [], "management": [], "research": [], "tools": []}
        return emp.get("skills", {"technical": [], "management": [], "research": [], "tools": []})

    def get_employee_career_history(self, employee_id: str) -> List[Dict[str, Any]]:
        """Retrieve career and previous work history for an employee."""
        emp = self.get_employee_by_id(employee_id)
        if not emp:
            return []
        return emp.get("experience", {}).get("career_history", [])

    def get_employee_education(self, employee_id: str) -> List[Dict[str, Any]]:
        """Retrieve education records for an employee."""
        emp = self.get_employee_by_id(employee_id)
        if not emp:
            return []
        return emp.get("education", [])

    def get_manager(self, employee_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve the direct manager record for an employee."""
        emp = self.get_employee_by_id(employee_id)
        if not emp:
            return None
        mgr_id = emp["reporting"].get("manager_id")
        if not mgr_id:
            return None
        return self.get_employee_by_id(mgr_id)

    def get_direct_reports(self, employee_id: str) -> List[Dict[str, Any]]:
        """Retrieve all employees who report directly to this employee."""
        eid = employee_id.strip().upper()
        return self.direct_reports_by_id.get(eid, [])

    def get_reporting_chain(self, employee_id: str) -> List[Dict[str, Any]]:
        """Retrieve full hierarchical reporting chain from employee up to CEO."""
        chain = []
        curr = self.get_employee_by_id(employee_id)
        visited = set()

        while curr and curr["employee_id"] not in visited:
            chain.append(curr)
            visited.add(curr["employee_id"])
            mgr_id = curr["reporting"].get("manager_id")
            if not mgr_id:
                break
            curr = self.get_employee_by_id(mgr_id)
        return chain

    def get_department_members(self, department: str) -> List[Dict[str, Any]]:
        """Retrieve all employees belonging to a department."""
        dept_norm = self._normalize(department)
        for d, emps in self.employees_by_department.items():
            if dept_norm in d or d in dept_norm:
                return emps
        return []

    def get_employees_by_role(self, role: str) -> List[Dict[str, Any]]:
        """Retrieve employees with a specific designation or keyword."""
        role_norm = self._normalize(role)
        results = []
        for r, emps in self.employees_by_role.items():
            if role_norm in r or r in role_norm:
                for e in emps:
                    if e not in results:
                        results.append(e)
        return results

    def get_employees_by_skill(self, skill: str) -> List[Dict[str, Any]]:
        """Retrieve employees who possess a given skill or tool."""
        s_norm = self._normalize(skill)
        results = []
        for s, emps in self.employees_by_skill.items():
            if s_norm in s or s in s_norm:
                for e in emps:
                    if e not in results:
                        results.append(e)
        return results

    def get_employees_by_project(self, project_name: str) -> List[Dict[str, Any]]:
        """Retrieve employees participating in a specified project."""
        p_norm = self._normalize(project_name)
        results = []
        for p, emps in self.employees_by_project.items():
            if p_norm in p or p in p_norm:
                for e in emps:
                    if e not in results:
                        results.append(e)
        return results

    def get_employee_permissions(self, employee_id: str) -> Dict[str, Any]:
        """Retrieve descriptive permission rules for an employee."""
        emp = self.get_employee_by_id(employee_id)
        if not emp:
            return {}
        return emp.get("permissions", {})

    def get_employee_research_profile(self, employee_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve R&D profile for research team members."""
        emp = self.get_employee_by_id(employee_id)
        if not emp:
            return None
        return emp.get("research")

    def get_employee_executive_authority(self, employee_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve executive authority profile for directors / executives."""
        emp = self.get_employee_by_id(employee_id)
        if not emp:
            return None
        return emp.get("executive_authority")
