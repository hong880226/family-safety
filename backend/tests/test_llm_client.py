"""Unit tests for the LLM client circuit breaker + retry behaviour.

We don't hit a real LLM; we mock httpx.AsyncClient.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.llm import client as llm_client_mod
from app.llm.client import LLMClient, LLMError, reset_breaker_for_tests


def _make_http_error(status_code: int) -> httpx.HTTPStatusError:
    """Build a synthetic HTTPStatusError."""
    req = httpx.Request("POST", "https://example.com/v1/chat/completions")
    resp = httpx.Response(status_code, request=req)
    return httpx.HTTPStatusError("transient", request=req, response=resp)


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_repeated_failures():
    reset_breaker_for_tests()

    fake_response = MagicMock()
    fake_response.status_code = 503
    fake_response.raise_for_status.side_effect = _make_http_error(503)

    with patch.object(httpx, "AsyncClient") as mock_async:
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=cm)
        cm.__aexit__ = AsyncMock(return_value=None)
        cm.post = AsyncMock(return_value=fake_response)
        mock_async.return_value = cm

        client = LLMClient(api_key="x", base_url="https://example.com/v1",
                           timeout=1)
        # Drive 5 calls in a row, all failing.
        for _ in range(5):
            with pytest.raises(LLMError):
                await client.chat(
                    [{"role": "user", "content": "hi"}],
                    max_retries=1,
                )
        # 6th call should fail-fast because the breaker is OPEN.
        with pytest.raises(LLMError) as exc_info:
            await client.chat(
                [{"role": "user", "content": "hi"}],
                max_retries=1,
            )
        assert "circuit breaker" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_breaker_resets_on_success():
    reset_breaker_for_tests()

    # First call: 500
    fail_resp = MagicMock()
    fail_resp.status_code = 503
    fail_resp.raise_for_status.side_effect = _make_http_error(503)
    # Second call: 200 OK
    ok_resp = MagicMock()
    ok_resp.status_code = 200
    ok_resp.raise_for_status = MagicMock()
    ok_resp.json.return_value = {
        "choices": [{"message": {"content": "hi"}}]
    }

    with patch.object(httpx, "AsyncClient") as mock_async:
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=cm)
        cm.__aexit__ = AsyncMock(return_value=None)
        cm.post = AsyncMock(side_effect=[fail_resp, ok_resp])
        mock_async.return_value = cm

        client = LLMClient(api_key="x", base_url="https://example.com/v1",
                           timeout=1)
        with pytest.raises(LLMError):
            await client.chat([{"role": "user", "content": "hi"}],
                              max_retries=1)
        # Now succeed
        result = await client.chat([{"role": "user", "content": "hi"}],
                                   max_retries=1)
        assert result == "hi"


def test_parse_json_response_handles_markdown_fence():
    text = "Sure, here is the JSON:\n```json\n{\"a\": 1}\n```"
    parsed = LLMClient.parse_json_response(text)
    assert parsed == {"a": 1}


def test_parse_json_response_handles_bare_object():
    text = "Result: {\"score\": 5, \"items\": [1,2,3]}"
    parsed = LLMClient.parse_json_response(text)
    assert parsed["score"] == 5
    assert parsed["items"] == [1, 2, 3]


def test_parse_json_response_raises_on_garbage():
    with pytest.raises(LLMError):
        LLMClient.parse_json_response("not json at all")