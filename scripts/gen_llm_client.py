"""P2: LLM client only (prompts and fallback will be separate small scripts)."""
from pathlib import Path

BACKEND = Path("E:/codeRepo/familysafety/backend")


def write(rel: str, content: str) -> None:
    target = BACKEND / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"  wrote {rel} ({len(content)} bytes)")


# ============ LLM client ============
write("app/llm/__init__.py", '"""LLM integration layer."""\n')

write("app/llm/client.py", '''"""Unified LLM client supporting any OpenAI-compatible endpoint."""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx
from loguru import logger

from app.core.config import get_settings

settings = get_settings()


class LLMError(Exception):
    pass


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
        max_retries: int = 2,
    ) -> str:
        """Send chat completion request. Returns raw text content."""
        if not self.api_key:
            raise LLMError("LLM_API_KEY is not configured")

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
                    resp.raise_for_status()
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    return content.strip() if content else ""
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
                last_exc = e
                logger.warning(f"LLM call attempt {attempt} failed: {e}")
                await asyncio.sleep(2 ** (attempt - 1))

        raise LLMError(f"LLM call failed after {max_retries} retries: {last_exc}")

    @staticmethod
    def parse_json_response(text: str) -> Any:
        """Robustly extract JSON from an LLM response."""
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        m = re.search(r"```(?:json)?\\s*(\\{.*?\\}|\\[.*?\\])\\s*```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        m = re.search(r"\\{.*\\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        raise LLMError(f"Could not parse JSON from LLM response: {text[:200]}")
''')
