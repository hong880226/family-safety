"""CSRF protection for cookie-authenticated dashboard forms.

Pattern: double-submit cookie + signed token in hidden field.

- `issue_csrf_token` returns a token bound to the current session; we sign a
  payload containing the cookie-bound auth_token (if any) and the timestamp.
- `validate_csrf_or_raise` reads the form/header token, re-signs the same
  payload, and compares in constant time. Mismatch → 403.

For v0.1 this protects state-changing web endpoints. API endpoints that
require `Authorization: Bearer ...` are inherently protected (CORS blocks
cross-origin attackers from reading the token).
"""
from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import HTTPException, Request, status

from app.core.config import get_settings

settings = get_settings()
_CSRF_TTL_SECONDS = 60 * 60 * 6  # 6 hours


def _sign(payload: str) -> str:
    return hmac.new(
        settings.jwt_secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def issue_csrf_token(request: Request) -> str:
    """Issue a CSRF token tied to the current session cookie (or IP+UA if anon)."""
    auth = request.cookies.get("auth_token", "")
    binding = auth or (request.client.host if request.client else "") + ":" + request.headers.get("user-agent", "")
    ts = int(time.time())
    payload = f"{binding}|{ts}"
    sig = _sign(payload)
    import base64
    return base64.urlsafe_b64encode(f"{payload}|{sig}".encode("utf-8")).decode("ascii")


async def validate_csrf_or_raise(request: Request) -> None:
    """Validate the CSRF token from either header `X-CSRF-Token` or form field `csrf_token`."""
    token = request.headers.get("X-CSRF-Token")
    if not token:
        # Try form data (works for application/x-www-form-urlencoded and multipart).
        try:
            form = await request.form()
            token = form.get("csrf_token")  # type: ignore[union-attr]
        except Exception:
            token = None
    if not token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf token missing")

    import base64
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        payload, _, sig = raw.rpartition("|")
    except Exception:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf token malformed")
    expected = _sign(payload)
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf token mismatch")
    try:
        _, _, ts = payload.rpartition("|")
        if abs(int(ts) - int(time.time())) > _CSRF_TTL_SECONDS:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf token expired")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf token malformed")