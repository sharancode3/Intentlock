"""
tests/test_answer_adapter_truthfulness.py
Tests for Person 2 Stage 9: Truthful narration, grounding verification, and model budget boundaries.
"""

import pytest
import logging
from unittest.mock import AsyncMock, MagicMock, patch
import openai

from backend.adapters.openai_answer_adapter import OpenAIAnswerAdapter
from backend.services.conversation_dispatch import PlannerContext


@pytest.fixture
def unconfigured_adapter():
    return OpenAIAnswerAdapter(client=None, api_key="")


@pytest.fixture
def mock_openai_client():
    client = MagicMock()
    client.responses = MagicMock()
    client.responses.create = AsyncMock()
    client.responses.parse = AsyncMock()
    return client


@pytest.fixture
def configured_adapter(mock_openai_client):
    return OpenAIAnswerAdapter(client=mock_openai_client, api_key="sk-test-key-stage9", model="gpt-4o-mini")


@pytest.mark.asyncio
async def test_unconfigured_adapter_fails_closed(unconfigured_adapter):
    """When API key is unset, adapter reports unavailable and returns empty string, not mock answers."""
    assert unconfigured_adapter.is_configured() is False
    res = await unconfigured_adapter.generate_answer(
        question="Show my team tickets",
        authorized_context={"actor": "EMP-1001"},
        correlation_id="turn-test-1",
    )
    assert res.is_available is False
    assert "unconfigured" in res.answer_text.lower()
    assert res.grounded is False
    assert "OPENAI_API_KEY is not set" in res.error_message


@pytest.mark.asyncio
async def test_empty_model_output_marks_unavailable_no_fabrication(configured_adapter, mock_openai_client):
    """Empty or blank model output must return is_available=False and never fabricate record access."""
    mock_resp = MagicMock()
    mock_resp.output_text = "   \n  "
    mock_openai_client.responses.create.return_value = mock_resp

    res = await configured_adapter.generate_answer(
        question="What is my project assignment?",
        authorized_context={"employee": {"id": "EMP-1001", "name": "Aarav"}},
        correlation_id="turn-test-empty",
    )

    assert res.is_available is False
    assert res.answer_text == ""
    assert res.grounded is False
    assert res.error_message == "EMPTY_OUTPUT"


@pytest.mark.asyncio
async def test_refusal_model_output_fails_grounding(configured_adapter, mock_openai_client):
    """Model refusal phrases are rejected by verify_grounding and marked unavailable."""
    refusal_texts = [
        "I cannot assist with that request.",
        "I am unable to help with employee data.",
        "I am sorry, but I cannot fulfill this request.",
    ]
    for ref_text in refusal_texts:
        mock_resp = MagicMock()
        mock_resp.output_text = ref_text
        mock_openai_client.responses.create.return_value = mock_resp

        res = await configured_adapter.generate_answer(
            question="Show executive compensation",
            authorized_context={"actor": "EMP-1001"},
            correlation_id="turn-test-refusal",
        )

        assert res.is_available is False
        assert res.grounded is False
        assert res.answer_text == ""
        assert "UNGROUNDED" in res.error_message


@pytest.mark.asyncio
async def test_metric_contradiction_fails_grounding(configured_adapter, mock_openai_client):
    """Narration claiming a count contradictory to authorized payload is rejected."""
    # Context has total_count = 3
    context = {
        "actor": "EMP-2001",
        "payload": {
            "total_count": 3,
            "tickets": [{"id": "TKT-2026-001"}, {"id": "TKT-2026-002"}, {"id": "TKT-2026-003"}],
        }
    }

    # Model hallucinates 15 tickets
    mock_resp = MagicMock()
    mock_resp.output_text = "You currently have 15 authorized tickets assigned to your team."
    mock_openai_client.responses.create.return_value = mock_resp

    res = await configured_adapter.generate_answer(
        question="How many tickets does my team have?",
        authorized_context=context,
        correlation_id="turn-test-metric-mismatch",
    )

    assert res.is_available is False
    assert res.grounded is False
    assert "Total count mismatch" in res.error_message


@pytest.mark.asyncio
async def test_grounded_truthful_narration_succeeds(configured_adapter, mock_openai_client):
    """Grounded narration agreeing with authorized context succeeds with telemetry."""
    context = {
        "actor": "EMP-2001",
        "payload": {
            "total_count": 3,
            "tickets": [{"id": "TKT-2026-001"}, {"id": "TKT-2026-002"}, {"id": "TKT-2026-003"}],
        }
    }

    mock_resp = MagicMock()
    mock_resp.output_text = "You have 3 authorized tickets assigned to your team, with two in progress."
    mock_resp.usage = MagicMock(total_tokens=42)
    mock_openai_client.responses.create.return_value = mock_resp

    res = await configured_adapter.generate_answer(
        question="How many tickets does my team have?",
        authorized_context=context,
        correlation_id="turn-test-success",
    )

    assert res.is_available is True
    assert res.grounded is True
    assert res.answer_text == "You have 3 authorized tickets assigned to your team, with two in progress."
    assert res.error_message is None
    assert res.latency_ms is not None


@pytest.mark.asyncio
async def test_rate_limit_error_handled_gracefully(configured_adapter, mock_openai_client):
    """RateLimitError is caught cleanly, returns unavailable, and does not leak unhandled exceptions."""
    mock_openai_client.responses.create.side_effect = openai.RateLimitError(
        message="Rate limit reached", response=MagicMock(status_code=429), body={}
    )

    res = await configured_adapter.generate_answer(
        question="Show my tickets",
        authorized_context={"actor": "EMP-1001"},
        correlation_id="turn-test-ratelimit",
    )

    assert res.is_available is False
    assert res.grounded is False
    assert res.error_message == "RATE_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_timeout_error_handled_gracefully(configured_adapter, mock_openai_client):
    """Timeout error is caught cleanly and returns TIMEOUT."""
    mock_openai_client.responses.create.side_effect = openai.APITimeoutError(request=MagicMock())

    res = await configured_adapter.generate_answer(
        question="Show my tickets",
        authorized_context={"actor": "EMP-1001"},
        correlation_id="turn-test-timeout",
    )

    assert res.is_available is False
    assert res.grounded is False
    assert res.error_message == "TIMEOUT"


@pytest.mark.asyncio
async def test_privacy_in_exception_logging(configured_adapter, mock_openai_client, caplog):
    """Exception logs must sanitize sensitive prompt data and only log error type and correlation ID."""
    mock_openai_client.responses.create.side_effect = RuntimeError("Internal connection failure")

    with caplog.at_level(logging.ERROR, logger="intentlock.openai_adapter"):
        res = await configured_adapter.generate_answer(
            question="What is the secret salary of EMP-9999?",
            authorized_context={"sensitive_token": "super_secret_jwt_value"},
            correlation_id="turn-priv-check",
        )

    assert res.is_available is False
    assert res.error_message == "OPENAI_ERROR: RuntimeError"

    # Verify log output does NOT contain the question or sensitive context
    log_text = caplog.text
    assert "secret salary" not in log_text
    assert "super_secret_jwt_value" not in log_text
    assert "turn-priv-check" in log_text


@pytest.mark.asyncio
async def test_plan_request_strips_sensitive_filter_keys(configured_adapter, mock_openai_client):
    """plan_request strips sensitive tokens and non-allowlisted filter keys from prompt hints."""
    mock_resp = MagicMock()
    mock_resp.output_parsed = None
    mock_openai_client.responses.parse.return_value = mock_resp

    ctx = PlannerContext(
        has_active_result=True,
        source_kind="tickets",
        active_filters={
            "priority": "Critical",
            "session_token": "secret_session_jwt_12345",
            "custom_injection": "DROP TABLE tickets",
        }
    )

    await configured_adapter.plan_request("filter by Critical", context=ctx)

    assert mock_openai_client.responses.parse.called
    call_args = mock_openai_client.responses.parse.call_args
    input_str = call_args.kwargs.get("input", "")

    # Allowed key present
    assert "priority=Critical" in input_str
    # Disallowed keys stripped
    assert "secret_session_jwt_12345" not in input_str
    assert "custom_injection" not in input_str
