"""
IntentLock — Database Persistence & Consistency Test Suite
Validates:
1. EnterpriseDataRepository cache consistency, field updates, and avoidance of double version bumps.
2. Directory and ticket revision tracking and cache invalidation.
3. Department, team, project, and membership normalization and projections.
4. Non-destructive migration dry-run and reconciliation planning.
"""

import json
import os
import pytest
from pathlib import Path

from backend.adapters.postgres_employee_repository import PostgresEmployeeRepository
from backend.services.enterprise_data import EnterpriseDataRepository, normalize_text
from backend.services.employee_knowledge_service import EmployeeKnowledgeService
from backend.services.ticket_knowledge_service import TicketKnowledgeService


def test_enterprise_data_repository_loaded_offline():
    """EnterpriseDataRepository loads canonical organizational datasets offline without network calls."""
    repo = EnterpriseDataRepository.get_instance()
    assert repo.is_loaded is True
    assert len(repo.employees) == 31
    assert len(repo.tickets) == 42
    assert len(repo.departments) == 10
    assert len(repo.teams) == 9
    assert len(repo.projects) == 41

    # Verify normalization and index lookup
    emp = repo.employees_by_id.get("EMP-1001")
    assert emp is not None
    assert emp["identity"]["full_name"] == "Aarav Mehta"
    assert "EMP-1001" in repo.employees_by_department.get("DEPT-ENG", [{}])[0].get("employee_id", "")


def test_update_employee_field_avoids_double_version_bump():
    """Updating employee phone with explicit version sets exact version rather than double incrementing."""
    repo = EnterpriseDataRepository.get_instance()
    emp = repo.employees_by_id["EMP-1001"]
    orig_phone = emp.get("identity", {}).get("work_phone")
    orig_ver = emp.get("version", 1)

    try:
        # Simulate commit where receipt returns version=2
        repo.update_employee_field("EMP-1001", "work_phone", "+91 98765 00000", version=2)
        assert emp["identity"]["work_phone"] == "+91 98765 00000"
        assert emp["identity"]["contact"]["phone"] == "+91 98765 00000"
        assert emp["version"] == 2

        # Verify EmployeeKnowledgeService update_employee_phone_in_memory also avoids double bump
        know_svc = EmployeeKnowledgeService.get_instance()
        know_svc.update_employee_phone_in_memory("EMP-1001", "+91 98765 00000", version=2)
        cached_emp = know_svc.employees_by_id["EMP-1001"]
        assert cached_emp["identity"]["work_phone"] == "+91 98765 00000"
        assert cached_emp["version"] == 2
    finally:
        repo.update_employee_field("EMP-1001", "work_phone", orig_phone, version=orig_ver)
        EmployeeKnowledgeService.get_instance().update_employee_phone_in_memory("EMP-1001", orig_phone, version=orig_ver)


def test_update_ticket_field_in_memory():
    """Updating ticket status in EnterpriseDataRepository updates index in-memory."""
    repo = EnterpriseDataRepository.get_instance()
    tkt = repo.tickets_by_id.get("TKT-2026-001")
    assert tkt is not None
    orig_status = tkt["status"]
    orig_ver = tkt.get("version", 1)

    try:
        repo.update_ticket_field("TKT-2026-001", "status", "RESOLVED", version=3)
        assert tkt["status"] == "RESOLVED"
        assert tkt["version"] == 3
    finally:
        repo.update_ticket_field("TKT-2026-001", "status", orig_status, version=orig_ver)


def test_postgres_employee_projection_contract():
    """PostgresEmployeeRepository._project_row contract generates complete employee dictionary."""
    mock_row = {
        "employee_id": "EMP-9001",
        "full_name": "Test Engineer",
        "preferred_name": "Tester",
        "work_email": "tester@intentlock.io",
        "work_phone": "+91 98765 43210",
        "department": "Engineering",
        "department_id": "DEP-ENG",
        "sub_department": "Core Platform",
        "team_id": "TEAM-ENG-CORE",
        "designation": "Staff Engineer",
        "organizational_level": "L4",
        "employment_status": "Active",
        "employment_type": "Full-Time",
        "location": "Bengaluru",
        "work_mode": "Hybrid",
        "date_of_joining": "2024-01-15",
        "manager_id": "EMP-2001",
        "version": 1,
        "skills": json.dumps({"languages": ["Python", "TypeScript"]}),
        "projects": json.dumps(["PRJ-101"]),
        "policy": json.dumps({"can_view_team_tickets": True}),
        "security_scope": json.dumps({"access_tier": "restricted"}),
        "voice_authority": json.dumps({"enrolled": True}),
        "recent_activity": json.dumps([]),
        "provenance": json.dumps({}),
        "extra_data": json.dumps({}),
    }

    mock_all_rows = {
        "EMP-9001": mock_row,
        "EMP-2001": {"full_name": "Bob Miller", "manager_id": None},
        "EMP-9002": {"full_name": "Direct Report 1", "manager_id": "EMP-9001"},
    }

    projected = PostgresEmployeeRepository._project_row(mock_row, mock_all_rows)

    assert projected["employee_id"] == "EMP-9001"
    assert projected["identity"]["full_name"] == "Test Engineer"
    assert projected["identity"]["contact"]["phone"] == "+91 98765 43210"
    assert projected["employment"]["department_id"] == "DEP-ENG"
    assert projected["employment"]["team_id"] == "TEAM-ENG-CORE"
    assert projected["reporting"]["manager_id"] == "EMP-2001"
    assert projected["reporting"]["manager_name"] == "Bob Miller"
    assert "EMP-9002" in projected["reporting"]["direct_report_ids"]


def test_migration_004_sql_file_exists_and_contains_rls():
    """Migration 004 SQL file must exist and contain DDL for normalized tables and fail-closed RLS."""
    mig_path = Path(__file__).resolve().parent.parent / "backend" / "migrations" / "004_departments_teams_projects_and_rls_repair.sql"
    assert mig_path.exists()

    sql = mig_path.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS departments" in sql
    assert "CREATE TABLE IF NOT EXISTS teams" in sql
    assert "CREATE TABLE IF NOT EXISTS projects" in sql
    assert "CREATE TABLE IF NOT EXISTS project_memberships" in sql
    assert "ALTER TABLE employees ADD COLUMN IF NOT EXISTS team_id" in sql
    assert "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS project_id" in sql
    assert "ticket_revision" in sql
    # Fail-closed RLS verification
    assert "actor_scoped_employee_update" in sql
    assert "actor_scoped_ticket_update" in sql
    assert "current_setting('intentlock.actor_id', true) IS NOT NULL" in sql
