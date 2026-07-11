"""Unified LLM client supporting any OpenAI-compatible endpoint.

Includes:
- Exponential backoff with jitter
- Per-process circuit breaker: skip LLM entirely for a cool-down window
  after repeated failures, protecting the request thread from cascading
  latency when the upstream is down.
"""
from __future__ import annotations

import asyncio
import json
import random
import re
import threading
import time
from typing import Any

import httpx
from loguru import logger

from app.core.config import get_settings

settings = get_settings()


class LLMError(Exception):
    pass


# ---- Circuit breaker (process-wide) ----

class _CircuitBreaker:
    """Simple in-memory breaker.

    Three states:
      - CLOSED: requests flow through.
      - OPEN: requests fail-fast with LLMError for `cooldown_s` seconds.
      - HALF_OPEN: one probe request allowed; on success → CLOSED, on fail → OPEN.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, failure_threshold: int = 5, cooldown_s: float = 30.0):
        self.failure_threshold = failure_threshold
        self.cooldown_s = cooldown_s
        self._state = self.CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._lock = threading.Lock()

    def allow(self) -> tuple[bool, str]:
        with self._lock:
            if self._state == self.CLOSED:
                return True, self.CLOSED
            if self._state == self.OPEN:
                if time.monotonic() - self._opened_at >= self.cooldown_s:
                    self._state = self.HALF_OPEN
                    return True, self.HALF_OPEN
                return False, self.OPEN
            # HALF_OPEN: allow the single probe through
            return True, self.HALF_OPEN

    def record_success(self) -> None:
        with self._lock:
            self._state = self.CLOSED
            self._failures = 0

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._state == self.HALF_OPEN:
                self._state = self.OPEN
                self._opened_at = time.monotonic()
            elif self._failures >= self.failure_threshold:
                self._state = self.OPEN
                self._opened_at = time.monotonic()
                logger.warning(
                    "LLM circuit breaker OPEN after {} consecutive failures; "
                    "skipping calls for {}s",
                    self._failures, self.cooldown_s,
                )


_breaker = _CircuitBreaker(failure_threshold=5, cooldown_s=30.0)


def reset_breaker_for_tests() -> None:
    """Test helper."""
    global _breaker
    _breaker = _CircuitBreaker()


class LLMClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model
        self.timeout = timeout or settings.llm_timeout_seconds

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        response_format_json: bool = False,
        max_retries: int = 3,
    ) -> str:
        """Send chat completion request. Returns raw text content.

        Retries with exponential backoff + jitter. Respects the circuit
        breaker: if the breaker is OPEN, fails fast with LLMError.
        """
        if not self.api_key:
            raise LLMError("LLM_API_KEY is not configured")

        allowed, state = _breaker.allow()
        if not allowed:
            raise LLMError(
                f"LLM circuit breaker is OPEN; skipping call (cooldown {_breaker.cooldown_s}s)"
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format_json:
            payload["response_format"] = {"type": "json_object"}

        url = f"{self.base_url}/chat/completions"
        last_exc: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    if resp.status_code in (429, 500, 502, 503, 504):
                        # Transient — retry with backoff.
                        raise httpx.HTTPStatusError(
                            f"transient {resp.status_code}",
                            request=resp.request,
                            response=resp,
                        )
                    resp.raise_for_status()
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    _breaker.record_success()
                    return content.strip() if content else ""
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
                last_exc = e
                logger.warning(
                    "LLM call attempt {}/{} failed: {}",
                    attempt, max_retries, e,
                )
                if attempt < max_retries:
                    # Exponential backoff with full jitter.
                    delay = min(8.0, 2 ** (attempt - 1)) + random.random()
                    await asyncio.sleep(delay)

        _breaker.record_failure()
        raise LLMError(f"LLM call failed after {max_retries} retries: {last_exc}")

    @staticmethod
    def parse_json_response(text: str) -> Any:
        """Robustly extract JSON from an LLM response."""
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        m = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        raise LLMError(f"Could not parse JSON from LLM response: {text[:200]}")