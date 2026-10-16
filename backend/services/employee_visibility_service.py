"""
IntentLock — Employee Visibility Service
Enforces deterministic access and visibility filtering on employee records
before data is exposed to LLM context builders or client APIs.
Prevents credential exposure and enforces organizational privacy boundaries.
"""

from typing import Dict, Any, List, Optional, Set
import copy

class EmployeeVisibilityService:
    # Explicitly forbidden secrets that are NEVER exposed under any circumstances
    PROHIBITED_SECRET_KEYS: Set[str] = {
        "password",
        "api_key",
        "private_key",
        "secret",
        "token",
        "credential",
        "signing_key",
        "access_token",
    }

    @classmethod
    def filter_employee(
        cls,
        target: Dict[str, Any],
        actor_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        is_authenticated: bool = False,
        requested_fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Filter a canonical employee dictionary to only the fields visible
        to the specified actor.
        """
        if not target:
            return {}

        clean_target = copy.deepcopy(target)

        # Baseline: Strip any accidentally present credential or raw secret
        cls._strip_prohibited_secrets(clean_target)

        # Self-access: if actor is the employee themselves and authenticated
        is_self = is_authenticated and bool(actor_id and actor_id.upper() == target["employee_id"].upper())
        if is_self:
            return cls._filter_for_self(clean_target, requested_fields)

        # Manager-access: if actor is the target's manager
        is_manager = is_authenticated and bool(actor_id and target.get("reporting", {}).get("manager_id") == actor_id.upper())
        if is_manager:
            return cls._filter_for_manager(clean_target, requested_fields)

        # Executive-access: if actor has executive role
        is_exec = is_authenticated and (actor_role in ["executive", "L5", "L6"] or (actor_id and actor_id.startswith("EXE-")))
        if is_exec:
            return cls._filter_for_executive(clean_target, requested_fields)

        # Default / Anonymous / Colleague Directory View
        return cls._filter_for_directory(clean_target, requested_fields)

    @classmethod
    def _strip_prohibited_secrets(cls, data: Any) -> None:
        """Recursively scrub any sensitive credential keys."""
        if isinstance(data, dict):
            for k in list(data.keys()):
                if any(sec in k.lower() for sec in cls.PROHIBITED_SECRET_KEYS):
                    del data[k]
                else:
                    cls._strip_prohibited_secrets(data[k])
        elif isinstance(data, list):
            for item in data:
                cls._strip_prohibited_secrets(item)

    @classmethod
    def _filter_for_directory(
        cls,
        emp: Dict[str, Any],
        requested_fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Standard public / anonymous directory visibility."""
        record: Dict[str, Any] = {
            "employee_id": emp["employee_id"],
            "identity": {
                "full_name": emp["identity"]["full_name"],
                "preferred_name": emp["identity"]["preferred_name"],
                "work_email": emp["identity"]["work_email"],
            },
            "employment": {
                "designation": emp["employment"]["designation"],
                "department": emp["employment"]["department"],
                "sub_department": emp["employment"]["sub_department"],
                "organizational_level": emp["employment"]["organizational_level"],
                "location": emp["employment"]["location"],
                "work_mode": emp["employment"]["work_mode"],
                "status": emp["employment"]["status"],
            },
            "reporting": {
                "manager_name": emp["reporting"]["manager_name"],
                "manager_id": emp["reporting"]["manager_id"],
                "direct_report_ids": emp["reporting"].get("direct_report_ids", []),
            },
            "skills": emp.get("skills", {}),
            "projects": {
                "current": [
                    {
                        "name": p["name"],
                        "role": p["role"],
                        "status": p.get("status", "Active"),
                    }
                    for p in emp.get("projects", {}).get("current", [])
                ],
                "previous": [
                    {
                        "name": p["name"],
                        "role": p["role"],
                        "status": p.get("status", "Completed"),
                    }
                    for p in emp.get("projects", {}).get("previous", [])
                ],
            },
            "education": emp.get("education", []),
            "experience": {
                "total_years": emp.get("experience", {}).get("total_years", 0),
                "professional_summary": emp.get("experience", {}).get("professional_summary", ""),
                "career_history": emp.get("experience", {}).get("career_history", []),
            },
            "achievements": emp.get("achievements", []),
        }

        # Include sanitized public research overview if applicable
        if emp.get("research"):
            r = emp["research"]
            record["research"] = {
                "specialization": r.get("specialization"),
                "secondary_areas": r.get("secondary_areas", []),
                "publications": r.get("publications", []),
                "patents": r.get("patents", []),
                "prototypes": r.get("prototypes", []),
            }

        # Include high-level executive remit if applicable (without financial secrets)
        if emp.get("executive_authority"):
            ea = emp["executive_authority"]
            record["executive_authority"] = {
                "board_relationship": ea.get("board_relationship"),
                "technology_authority": ea.get("technology_authority"),
            }

        return record

    @classmethod
    def _filter_for_self(
        cls,
        emp: Dict[str, Any],
        requested_fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Authenticated employee viewing their own authoritative record."""
        # Own employee can see all of their profile fields, permissions, and voice rules
        return emp

    @classmethod
    def _filter_for_manager(
        cls,
        emp: Dict[str, Any],
        requested_fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Manager viewing an authorized direct report."""
        record = cls._filter_for_directory(emp, requested_fields)
        # Managers can see full allocation percentages, responsibilities, and permissions
        record["projects"] = emp.get("projects", {})
        record["responsibilities"] = emp.get("responsibilities", [])
        record["permissions"] = emp.get("permissions", {})
        record["recent_activity"] = emp.get("recent_activity", [])
        return record

    @classmethod
    def _filter_for_executive(
        cls,
        emp: Dict[str, Any],
        requested_fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Executive viewing organizational records."""
        record = cls._filter_for_directory(emp, requested_fields)
        record["responsibilities"] = emp.get("responsibilities", [])
        record["permissions"] = emp.get("permissions", {})
        if emp.get("executive_authority"):
            record["executive_authority"] = emp["executive_authority"]
        if emp.get("research"):
            record["research"] = emp["research"]
        return record
