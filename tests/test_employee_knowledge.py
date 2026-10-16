"""
IntentLock — Employee Knowledge Base & Retrieval Test Suite
Validates schema integrity, in-memory indexing, visibility filtering,
compact context building, and knowledge queries.
"""

import pytest
from starlette.testclient import TestClient

from backend.main import app
from backend.services.employee_knowledge_service import EmployeeKnowledgeService
from backend.services.employee_visibility_service import EmployeeVisibilityService
from backend.services.employee_context_builder import EmployeeContextBuilder
from backend.services.ollama_knowledge_service import OllamaKnowledgeService

@pytest.fixture(scope="module")
def knowledge_service():
    return EmployeeKnowledgeService.get_instance()

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client

def test_knowledge_base_loaded(knowledge_service):
    """Verify all employees are loaded once and indexed."""
    employees = knowledge_service.list_all_employees()
    assert len(employees) == 31, f"Expected 31 employees, got {len(employees)}"
    assert knowledge_service.is_loaded is True

def test_canonical_schema_fields(knowledge_service):
    """Verify all employees conform to the canonical schema without malformed objects."""
    employees = knowledge_service.list_all_employees()
    for emp in employees:
        assert "employee_id" in emp
        assert "identity" in emp
        assert "employment" in emp
        assert "reporting" in emp
        assert "experience" in emp
        assert "skills" in emp
        assert "projects" in emp
        assert "permissions" in emp
        assert "security_scope" in emp
        assert "voice_authority" in emp
        assert "provenance" in emp

        # Verify security scope invariants
        sec = emp["security_scope"]
        assert sec["can_change_own_authority"] is False
        assert sec["can_grant_self_admin"] is False
        assert sec["can_disable_intentlock"] is False
        assert sec["can_delete_audit_history"] is False
        assert sec["can_bypass_speaker_verification"] is False

def test_exact_employee_lookup(knowledge_service):
    """Verify exact lookup by employee ID."""
    aarav = knowledge_service.get_employee_by_id("EMP-1001")
    assert aarav is not None
    assert aarav["identity"]["full_name"] == "Aarav Mehta"
    assert aarav["employment"]["department"] == "Engineering"

    # Case insensitivity
    aarav_lower = knowledge_service.get_employee_by_id("emp-1001")
    assert aarav_lower is not None
    assert aarav_lower["employee_id"] == "EMP-1001"

def test_reporting_hierarchy(knowledge_service):
    """Verify manager IDs and direct reports are accurately mapped."""
    priya = knowledge_service.get_employee_by_id("EMP-2001")
    assert priya is not None
    # Priya manages Aarav (EMP-1001) and Neha Rao (EMP-1501)
    assert "EMP-1001" in priya["reporting"]["direct_report_ids"]
    assert "EMP-1501" in priya["reporting"]["direct_report_ids"]

    # Verify reverse lookup: Aarav's manager is Priya
    mgr = knowledge_service.get_manager("EMP-1001")
    assert mgr is not None
    assert mgr["employee_id"] == "EMP-2001"

    # Verify CEO reports to Board
    ceo = knowledge_service.get_employee_by_id("EXE-0001")
    assert ceo is not None
    assert ceo["reporting"]["manager_id"] is None

def test_cto_merged_profile(knowledge_service):
    """Verify CTO (EMP-4002) is a single unified record with executive and technology authority."""
    cto = knowledge_service.get_employee_by_id("EMP-4002")
    assert cto is not None
    assert cto["identity"]["full_name"] == "Arvind Rao"
    assert "Chief Technology Officer" in cto["employment"]["designation"]
    assert cto["executive_authority"] is not None
    assert "Technology Authority" in cto["executive_authority"] or cto["executive_authority"].get("technology_authority")

def test_visibility_filter_scrubs_secrets(knowledge_service):
    """Verify visibility filter never reveals private secrets or raw credentials."""
    raw_emp = knowledge_service.get_employee_by_id("EMP-1001")
    # Simulate an accidental injection of a sensitive secret
    test_emp = dict(raw_emp)
    test_emp["api_key"] = "SUPER_SECRET_KEY_123"
    test_emp["private_key"] = "PRIVATE_KEY_PEM"

    filtered = EmployeeVisibilityService.filter_employee(test_emp, is_authenticated=False)
    assert "api_key" not in filtered
    assert "private_key" not in filtered

def test_context_builder_compactness(knowledge_service):
    """Verify context builder outputs concise bounded context."""
    aarav = knowledge_service.get_employee_by_id("EMP-1001")
    ctx = EmployeeContextBuilder.build_context([aarav], query="What projects is Aarav working on?")
    assert "EMPLOYEE RECORD" in ctx
    assert "Aarav Mehta" in ctx
    assert "Customer Support Portal" in ctx
    # Should not include unrelated bulk fields
    assert "Executive Authority" not in ctx

def test_fastapi_endpoints(client):
    """Test all REST API routes."""
    # Health check
    res_health = client.get("/api/v1/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "HEALTHY"
    assert res_health.json()["indexed_employees_count"] == 31

    # Employee list
    res_list = client.get("/api/v1/employees")
    assert res_list.status_code == 200
    assert res_list.json()["total"] == 31

    # Employee single
    res_single = client.get("/api/v1/employees/EMP-1001")
    assert res_single.status_code == 200
    assert res_single.json()["identity"]["full_name"] == "Aarav Mehta"

    # Search
    res_search = client.get("/api/v1/employees/search?q=FastAPI")
    assert res_search.status_code == 200
    assert res_search.json()["count"] >= 1

    # Knowledge query
    res_q = client.post("/api/v1/knowledge/query", json={"query": "Who is Aarav Mehta?"})
    assert res_q.status_code == 200
    data = res_q.json()
    assert "Aarav Mehta" in data["answer"]
    assert data["grounded"] is True
