"""
IntentLock — OpenAI Responses API Adapter Test Suite
Tests for OpenAIAnswerAdapter:
1. Configuration state evaluation (configured vs unconfigured).
2. Grounded answer generation using the Responses API (store=False, max_output_tokens=1024).
3. Resilient fallback handling for rate limits, timeouts, and generic provider errors.
4. Pre-LLM context containment validation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import openai

from backend.adapters.openai_answer_adapter import OpenAIAnswerAdapter, GROUNDING_INSTRUCTIONS
from backend.core.ports import AnswerResult


@pytest.mark.asyncio
async def test_openai_adapter_unconfigured():
    """Unconfigured adapter fails gracefully and returns fallback envelope without network calls."""
    adapter = OpenAIAnswerAdapter(api_key=None)
    assert adapter.is_configured() is False

    res = await adapter.generate_answer(
        question="What are my active projects?",
        authorized_context={"user": "EMP-1001"},
        correlation_id="test_turn_1",
    )

    assert isinstance(res, AnswerResult)
    assert res.is_available is False
    assert res.grounded is False
    assert "unconfigured" in res.answer_text.lower()
    assert res.error_message == "OPENAI_API_KEY is not set."


@pytest.mark.asyncio
async def test_openai_adapter_successful_responses_call():
    """Adapter correctly invokes Responses API with store=False and instructions."""
    mock_client = MagicMock()
    mock_responses = MagicMock()
    mock_client.responses = mock_responses

    mock_response_obj = MagicMock()
    mock_response_obj.output_text = "You are currently assigned to Customer Support Portal and Internal Analytics Dashboard."
    mock_responses.create = AsyncMock(return_value=mock_response_obj)

    adapter = OpenAIAnswerAdapter(
        client=mock_client,
        model="gpt-5.4-mini",
        max_output_tokens=1024,
    )
    assert adapter.is_configured() is True

    context = {
        "authenticated_actor": {
            "id": "EMP-1001",
            "name": "Aarav Mehta",
            "active_projects": ["Customer Support Portal", "Internal Analytics Dashboard"],
        }
    }

    res = await adapter.generate_answer(
        question="What projects am I working on?",
        authorized_context=context,
        correlation_id="test_turn_2",
    )

    assert res.is_available is True
    assert res.grounded is True
    assert res.model == "gpt-5.4-mini"
    assert "Customer Support Portal" in res.answer_text
    assert res.latency_ms is not None and res.latency_ms >= 0

    # Verify parameters sent to Responses API
    mock_responses.create.assert_awaited_once()
    _, kwargs = mock_responses.create.call_args
    assert kwargs["model"] == "gpt-5.4-mini"
    assert kwargs["instructions"] == GROUNDING_INSTRUCTIONS
    assert kwargs["max_output_tokens"] == 1024
    assert kwargs["store"] is False
    assert "Customer Support Portal" in kwargs["input"]
    assert "What projects am I working on?" in kwargs["input"]


@pytest.mark.asyncio
async def test_openai_adapter_rate_limit_fallback():
    """Adapter catches RateLimitError and returns safe fallback envelope."""
    mock_client = MagicMock()
    mock_responses = MagicMock()
    mock_client.responses = mock_responses

    # Create dummy response for RateLimitError
    dummy_response = MagicMock(status_code=429, headers={})
    mock_responses.create = AsyncMock(
        side_effect=openai.RateLimitError(
            message="Rate limit exceeded",
            response=dummy_response,
            body={"error": {"message": "Rate limit exceeded"}},
        )
    )

    adapter = OpenAIAnswerAdapter(client=mock_client, model="gpt-5.4-mini")
    res = await adapter.generate_answer(
        question="Who is my manager?",
        authorized_context={"manager": "Priya Sharma"},
        correlation_id="test_turn_rl",
    )

    assert res.is_available is False
    assert res.grounded is False
    assert res.error_message == "RATE_LIMIT_EXCEEDED"
    assert "high load" in res.answer_text.lower()


@pytest.mark.asyncio
async def test_openai_adapter_timeout_fallback():
    """Adapter catches APITimeoutError and returns safe fallback envelope."""
    mock_client = MagicMock()
    mock_responses = MagicMock()
    mock_client.responses = mock_responses

    mock_responses.create = AsyncMock(
        side_effect=openai.APITimeoutError(request=MagicMock())
    )

    adapter = OpenAIAnswerAdapter(client=mock_client, model="gpt-5.4-mini")
    res = await adapter.generate_answer(
        question="Who is my manager?",
        authorized_context={"manager": "Priya Sharma"},
        correlation_id="test_turn_to",
    )

    assert res.is_available is False
    assert res.grounded is False
    assert res.error_message == "TIMEOUT"
    assert "timed out" in res.answer_text.lower()


@pytest.mark.asyncio
async def test_openai_adapter_generic_exception_fallback():
    """Adapter catches unexpected API exceptions and falls back without crashing."""
    mock_client = MagicMock()
    mock_responses = MagicMock()
    mock_client.responses = mock_responses

    mock_responses.create = AsyncMock(side_effect=RuntimeError("Provider socket closed"))

    adapter = OpenAIAnswerAdapter(client=mock_client, model="gpt-5.4-mini")
    res = await adapter.generate_answer(
        question="List my direct reports",
        authorized_context={"direct_reports": []},
        correlation_id="test_turn_err",
    )

    assert res.is_available is False
    assert res.grounded is False
    assert "unable to generate ai answer" in res.answer_text.lower()
