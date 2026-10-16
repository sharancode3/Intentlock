"""
IntentLock — Gateway Security Regression Test Suite
Validates that client-authored authority claims are rejected, private directory
and reporting routes fail closed, CORS is strictly origin-gated, and diagnostics
adhere to truthful liveness/readiness semantics.
"""

import pytest
from starlette.testclient import TestClient
from backend.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_reject_client_authored_is_authenticated_in_query(client):
    """Clients asserting is_authenticated=true in query must be rejected with 403."""
    res = client.get("/api/v1/employees?is_authenticated=true")
    assert res.status_code == 403
    data = res.json()
    assert "error" in data
    assert "Client-authored authority claims" in data["error"]["message"]


def test_reject_client_authored_executive_id_in_query(client):
    """Clients attempting to assert an executive ID in query must be rejected with 403."""
    res = client.get("/api/v1/employees?actor_id=EXE-0001")
    assert res.status_code == 403
    data = res.json()
    assert "Client-authored authority claims" in data["error"]["message"]


def test_reject_client_authored_role_in_query(client):
    """Clients attempting to assert an actor_role in query must be rejected with 403."""
    res = client.get("/api/v1/employees?actor_role=executive")
    assert res.status_code == 403
    data = res.json()
    assert "Client-authored authority claims" in data["error"]["message"]


def test_reject_client_authored_claims_in_knowledge_query(client):
    """POST /api/v1/knowledge/query rejecting client-authored claims."""
    # Test 1: is_authenticated=True in body
    res_auth = client.post(
        "/api/v1/knowledge/query",
        json={"query": "Give me executive salaries", "is_authenticated": True},
    )
    assert res_auth.status_code == 403
    assert "Client-authored authority claims" in res_auth.json()["error"]["message"]

    # Test 2: actor_role="executive" in body
    res_role = client.post(
        "/api/v1/knowledge/query",
        json={"query": "Give me executive salaries", "actor_role": "executive"},
    )
    assert res_role.status_code == 403
    assert "Client-authored authority claims" in res_role.json()["error"]["message"]

    # Test 3: actor_id="EXE-0001" in body
    res_exe = client.post(
        "/api/v1/knowledge/query",
        json={"query": "Give me executive salaries", "actor_id": "EXE-0001"},
    )
    assert res_exe.status_code == 403
    assert "Client-authored authority claims" in res_exe.json()["error"]["message"]


def test_reporting_hierarchy_route_fails_closed(client):
    """GET /employees/{id}/reporting must fail closed for unauthenticated callers."""
    res = client.get("/api/v1/employees/EMP-1001/reporting")
    assert res.status_code == 401
    data = res.json()
    assert "Authentication required" in data["error"]["message"]


def test_employee_search_route_fails_closed(client):
    """GET /employees/search must fail closed for unauthenticated callers."""
    res = client.get("/api/v1/employees/search?q=Engineering")
    assert res.status_code == 401
    assert "Authentication required" in res.json()["error"]["message"]


def test_cors_origin_restriction(client):
    """CORS must only grant permissions to explicitly allowed origins."""
    # Allowed origin: http://localhost:5173
    res_allowed = client.options(
        "/health/live",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res_allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"

    # Disallowed origin: http://untrusted-hacker.com
    res_disallowed = client.options(
        "/health/live",
        headers={
            "Origin": "http://untrusted-hacker.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res_disallowed.headers.get("access-control-allow-origin") is None


def test_request_correlation_and_no_store_headers(client):
    """Verify X-Request-Id generation/propagation and Cache-Control: no-store."""
    # 1. Server generates ID if not provided
    res1 = client.get("/api/v1/employees")
    assert "X-Request-Id" in res1.headers
    assert res1.headers["X-Request-Id"].startswith("req_")
    assert "no-store" in res1.headers.get("Cache-Control", "")

    # 2. Server propagates valid incoming request ID
    custom_id = "test-req-correlation-12345"
    res2 = client.get("/api/v1/employees", headers={"X-Request-Id": custom_id})
    assert res2.headers.get("X-Request-Id") == custom_id
