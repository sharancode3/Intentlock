"""
IntentLock — Postgres Employee Repository
Authoritative PostgreSQL repository for canonical employee records, reporting structure,
directory revision tracking, and protected contact updates in Supabase.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from backend.adapters.postgres_client import PostgresClient, sanitize_db_error

logger = logging.getLogger("intentlock.postgres_employee_repo")


class PostgresEmployeeRepository:
    _instance: Optional["PostgresEmployeeRepository"] = None

    def __init__(self, client: Optional[PostgresClient] = None):
        self.client = client or PostgresClient.get_instance()

    @classmethod
    def get_instance(cls, client: Optional[PostgresClient] = None) -> "PostgresEmployeeRepository":
        if cls._instance is None:
            cls._instance = cls(client=client)
        return cls._instance

    @staticmethod
    def _project_row(row: dict, all_rows_map: Optional[Dict[str, dict]] = None) -> Dict[str, Any]:
        """
        Projects a PostgreSQL employee row into the canonical JSON dictionary contract
        used throughout IntentLock's authorization, knowledge, and presentation layers.
        Derives manager_name and direct_report_ids from authoritative manager_id FKs.
        Preserves 100% of canonical fields including employment status, date of joining,
        security scope, voice authority, and recent activity.
        """
        eid = row["employee_id"]
        mgr_id = row.get("manager_id")
        mgr_name = None

        if mgr_id and all_rows_map and mgr_id in all_rows_map:
            mgr_name = all_rows_map[mgr_id].get("full_name")

        direct_report_ids = []
        if all_rows_map:
            for other_id, other_row in all_rows_map.items():
                if other_row.get("manager_id") == eid:
                    direct_report_ids.append(other_id)

        # Parse JSONB fields safely if returned as strings
        def _ensure_json(val, default):
            if val is None:
                return default
            if isinstance(val, (dict, list)):
                return val
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except Exception:
                    return default
            return default

        skills = _ensure_json(row.get("skills"), {})
        projects = _ensure_json(row.get("projects"), {})
        experience = _ensure_json(row.get("experience"), {})
        education = _ensure_json(row.get("education"), [])
        responsibilities = _ensure_json(row.get("responsibilities"), [])
        achievements = _ensure_json(row.get("achievements"), [])
        research = _ensure_json(row.get("research"), None)
        executive_auth = _ensure_json(row.get("executive_authority"), None)
        policy = _ensure_json(row.get("policy"), {})
        provenance = _ensure_json(row.get("provenance"), {})
        extra = _ensure_json(row.get("extra_data"), {})

        work_phone = row.get("work_phone")
        work_email = row.get("work_email") or extra.get("identity", {}).get("work_email", "")

        # Extract employment fields with fallbacks to extra_data
        status = (
            row.get("employment_status")
            or extra.get("employment", {}).get("status")
            or "Active"
        )
        sub_dept = (
            row.get("sub_department")
            or extra.get("employment", {}).get("sub_department")
        )
        research_lvl = (
            row.get("research_level")
            or extra.get("employment", {}).get("research_level")
        )
        emp_type = (
            row.get("employment_type")
            or extra.get("employment", {}).get("employment_type")
            or "Full-Time"
        )
        doj = (
            row.get("date_of_joining")
            or extra.get("employment", {}).get("date_of_joining")
        )

        security_scope = _ensure_json(
            row.get("security_scope"), extra.get("security_scope", {})
        )
        voice_authority = _ensure_json(
            row.get("voice_authority"), extra.get("voice_authority", {})
        )
        recent_activity = _ensure_json(
            row.get("recent_activity"), extra.get("recent_activity", [])
        )

        res: Dict[str, Any] = {
            "employee_id": eid,
            "version": row.get("version", 1),
            "identity": {
                "full_name": row.get("full_name", ""),
                "preferred_name": row.get("preferred_name"),
                "work_email": work_email,
                "work_phone": work_phone,
                "contact": {
                    "email": work_email,
                    "phone": work_phone,
                },
            },
            "employment": {
                "department": row.get("department", ""),
                "sub_department": sub_dept,
                "designation": row.get("designation", ""),
                "organizational_level": row.get("organizational_level", "L1"),
                "research_level": research_lvl,
                "employment_type": emp_type,
                "location": row.get("location", "Bengaluru"),
                "work_mode": row.get("work_mode", "Hybrid"),
                "status": status,
                "date_of_joining": doj,
            },
            "reporting": {
                "manager_id": mgr_id,
                "manager_name": mgr_name,
                "direct_report_ids": direct_report_ids,
            },
            "skills": skills,
            "projects": projects,
            "experience": experience,
            "education": education,
            "responsibilities": responsibilities,
            "achievements": achievements,
            "permissions": policy,
            "security_scope": security_scope,
            "voice_authority": voice_authority,
            "recent_activity": recent_activity,
            "provenance": provenance,
        }

        if research:
            res["research"] = research
        if executive_auth:
            res["executive_authority"] = executive_auth

        return res

    async def get_directory_revision_async(self) -> int:
        """Fetch current directory invalidation revision."""
        async with self.client.acquire() as conn:
            rev = await conn.fetchval(
                "SELECT revision FROM directory_metadata WHERE key = 'directory_revision'"
            )
            return int(rev or 1)

    def get_directory_revision(self) -> int:
        return self.client.run(self.get_directory_revision_async())

    async def list_all_employees_async(self) -> List[Dict[str, Any]]:
        """Fetch all canonical employee records from Supabase Postgres with derived reporting edges."""
        try:
            async with self.client.acquire() as conn:
                rows = await conn.fetch("SELECT * FROM employees ORDER BY employee_id ASC")
                raw_dict_map = {r["employee_id"]: dict(r) for r in rows}
                return [self._project_row(r, raw_dict_map) for r in raw_dict_map.values()]
        except Exception as exc:
            logger.error("Failed to fetch employees from Postgres: %s", sanitize_db_error(str(exc)))
            raise RuntimeError(f"Postgres directory read failed: {sanitize_db_error(str(exc))}") from None

    def list_all_employees(self) -> List[Dict[str, Any]]:
        return self.client.run(self.list_all_employees_async())

    async def get_employee_by_id_async(self, employee_id: str) -> Optional[Dict[str, Any]]:
        """Fetch single employee with complete derived reporting graph."""
        if not employee_id:
            return None
        all_emps = await self.list_all_employees_async()
        target_norm = employee_id.strip().upper()
        for emp in all_emps:
            if emp["employee_id"] == target_norm:
                return emp
        return None

    def get_employee_by_id(self, employee_id: str) -> Optional[Dict[str, Any]]:
        return self.client.run(self.get_employee_by_id_async(employee_id))

    async def update_contact_phone_async(
        self,
        actor_id: str,
        target_id: str,
        new_phone: str,
        expected_version: int,
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Atomically update an employee's contact phone number with version checking and
        directory revision invalidation in a single transaction.
        """
        async with self.client.transaction(actor_id=actor_id) as conn:
            row = await conn.fetchrow(
                "SELECT version, work_phone FROM employees WHERE employee_id = $1 FOR UPDATE",
                target_id,
            )
            if not row:
                raise ValueError(f"Employee {target_id} not found.")

            current_ver = row["version"]
            if current_ver != expected_version:
                raise ValueError(
                    f"Version conflict: expected version {expected_version}, but current version is {current_ver}."
                )

            new_ver = current_ver + 1
            await conn.execute(
                """
                UPDATE employees
                SET work_phone = $1, version = $2, updated_at = NOW()
                WHERE employee_id = $3 AND version = $4
                """,
                new_phone,
                new_ver,
                target_id,
                current_ver,
            )

            # Bump directory metadata revision for cross-process and local invalidation
            await conn.execute(
                """
                INSERT INTO directory_metadata (key, revision, updated_at)
                VALUES ('directory_revision', 2, NOW())
                ON CONFLICT (key) DO UPDATE
                SET revision = directory_metadata.revision + 1, updated_at = NOW()
                """
            )

            # Re-read updated row
            all_emps = await self.list_all_employees_async()
            updated_emp = next((e for e in all_emps if e["employee_id"] == target_id), None)
            if not updated_emp:
                raise RuntimeError("Failed to reload updated employee record.")

            return new_ver, updated_emp

    def update_contact_phone(
        self,
        actor_id: str,
        target_id: str,
        new_phone: str,
        expected_version: int,
    ) -> Tuple[int, Dict[str, Any]]:
        return self.client.run(self.update_contact_phone_async(actor_id, target_id, new_phone, expected_version))
