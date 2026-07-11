"""Unit tests for the CSRF service."""
import time

import pytest
from fastapi import HTTPException, Request

from app.services.csrf import issue_csrf_token, validate_csrf_or_raise


def _make_request(cookies: dict[str, str] | None = None, headers: dict[str, str] | None = None):
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/web/settings",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "cookies": cookies or {},
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_issue_returns_non_empty_string():
    req = _make_request()
    tok = issue_csrf_token(req)
    assert isinstance(tok, str)
    assert len(tok) > 20


@pytest.mark.asyncio
async def test_valid_header_token_passes():
    """Round-trip via X-CSRF-Token header."""
    from starlette.requests import Request as SRequest

    scope = {"type": "http", "method": "POST", "headers": [], "cookies": {}}
    req = SRequest(scope)
    tok = issue_csrf_token(req)
    req_with_token = SRequest({**scope, "headers": [(b"x-csrf-token", tok.encode())]})
    # Should not raise.
    await validate_csrf_or_raise(req_with_token)


@pytest.mark.asyncio
async def test_missing_token_raises():
    req = _make_request()
    with pytest.raises(HTTPException) as exc_info:
        await validate_csrf_or_raise(req)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_malformed_token_raises():
    req = _make_request(headers={"X-CSRF-Token": "not-base64"})
    with pytest.raises(HTTPException) as exc_info:
        await validate_csrf_or_raise(req)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_tampered_signature_raises():
    """Alter the last byte of a real token; signature must not match."""
    from starlette.requests import Request as SRequest
    from starlette.datastructures import FormData

    # Build a fake multipart-like body so request.form() can run.
    # Simpler: just call the lower-level decode path directly via issue.
    scope = {"type": "http", "method": "POST", "headers": [], "cookies": {}}
    req = SRequest(scope)
    tok = issue_csrf_token(req)
    # Flip one char.
    bad = tok[:-1] + ("A" if tok[-1] != "A" else "B")
    req2 = SRequest({**scope, "headers": [(b"x-csrf-token", bad.encode())]})
    with pytest.raises(HTTPException) as exc_info:
        await validate_csrf_or_raise(req2)
    assert exc_info.value.status_code == 403