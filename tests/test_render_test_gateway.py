"""
IntentLock — Test Suite for Local Voice & Render Testing Gateway
Validates:
1. Health and pre-warmed speech engine readiness.
2. Fixture resolution (employee_self, manager_team, executive_all, anonymous_visitor).
3. Own-scope query resolution (Aarav Mehta).
4. Deliberate cross-scope policy denial.
5. Aggregate headcount / distribution chart construction.
6. Real speech audio decode and transcription roundtrip.
"""

import pytest
from starlette.testclient import TestClient
from backend.test_integration.test_gateway import test_app
from backend.test_integration.test_speech_service import synthesize_speech

@pytest.fixture(scope="module")
def client():
    with TestClient(test_app) as test_client:
        yield test_client

def test_gateway_health(client):
    res = client.get("/api/test/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "HEALTHY"
    assert data["test_mode"] is True
    assert data["whisper_ready"] is True
    assert data["kokoro_ready"] is True
    assert data["indexed_employees"] == 31

def test_available_fixtures(client):
    res = client.get("/api/test/fixtures")
    assert res.status_code == 200
    fixtures = {f["fixture_id"]: f for f in res.json()["fixtures"]}
    assert "employee_self" in fixtures
    assert "manager_team" in fixtures
    assert "executive_all" in fixtures
    assert "anonymous_visitor" in fixtures
    assert fixtures["employee_self"]["employee_id"] == "EMP-1001"
    assert fixtures["manager_team"]["employee_id"] == "EMP-2001"

def test_self_scope_employee_query(client):
    res = client.post("/api/test/turn/text", json={
        "text": "Who is Aarav Mehta?",
        "fixture_id": "employee_self"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["result_block"]["type"] == "EMPLOYEE_PROFILE"
    assert data["result_block"]["payload"]["employee"]["id"] == "EMP-1001"
    assert len(data["tts_audio_base64"]) > 0

def test_cross_scope_denial(client):
    # Anonymous visitor querying private profile
    res = client.post("/api/test/turn/text", json={
        "text": "Show me the employee profile and salary of Aarav Mehta",
        "fixture_id": "anonymous_visitor"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["result_block"]["type"] == "DENIAL_BANNER"
    assert data["result_block"]["payload"]["code"] == "INSUFFICIENT_SCOPE"

def test_manager_headcount_chart(client):
    res = client.post("/api/test/turn/text", json={
        "text": "How many direct reports does Priya Sharma have? Show distribution",
        "fixture_id": "manager_team"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["result_block"]["type"] == "TEAM_METRIC_CHART"
    assert "data" in data["result_block"]["payload"]
    assert len(data["result_block"]["payload"]["data"]) > 0

def test_audio_turn_processing(client):
    # Generate real voice speech
    wav_bytes, _ = synthesize_speech("Who is Priya Sharma?")
    res = client.post(
        "/api/test/turn/audio",
        files={"audio_file": ("query.wav", wav_bytes, "audio/wav")},
        data={"fixture_id": "manager_team"}
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data["user_transcript"]) > 0
    assert "priya" in data["user_transcript"].lower() or "sharma" in data["user_transcript"].lower()
    assert data["result_block"]["type"] in ["EMPLOYEE_PROFILE", "TEAM_METRIC_CHART", "PUBLIC_FAQ"]
    assert len(data["tts_audio_base64"]) > 0
