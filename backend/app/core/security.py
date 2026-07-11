"""JWT + password hashing utilities + symmetric encryption helpers."""
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings

settings = get_settings()

# Hard-coded algorithm whitelist. Do NOT read from settings to avoid
# alg=none / algorithm-confusion attacks (CVE-2022-29217 class).
_ALLOWED_JWT_ALGS = {"HS256", "RS256"}
assert settings.jwt_algorithm in _ALLOWED_JWT_ALGS

# bcrypt 72-byte limit; truncate to be safe.
_BCRYPT_MAX = 72


def _bcrypt_safe(password: str) -> bytes:
    b = password.encode("utf-8")
    if len(b) > _BCRYPT_MAX:
        b = b[:_BCRYPT_MAX]
    return b


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_bcrypt_safe(password), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    # bcrypt.InvalidHashError or value errors propagate so callers can
    # distinguish malformed-hash from wrong-password (avoid account enumeration).
    try:
        return bcrypt.checkpw(_bcrypt_safe(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # Re-raise as ValueError so callers can catch it (not swallow to False).
        raise ValueError("malformed password hash")


# ---- API key hashing (separate cost from passwords) ----

def _api_key_safe(key: str) -> bytes:
    """API keys are URL-safe base64; no truncation concerns (always < 72 bytes)."""
    return key.encode("utf-8")


def hash_api_key(api_key: str) -> str:
    # rounds=10 keeps per-request verify latency < 5 ms while still being
    # slow enough to discourage brute-force on a stolen DB dump.
    return bcrypt.hashpw(_api_key_safe(api_key), bcrypt.gensalt(rounds=10)).decode("utf-8")


def verify_api_key(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_api_key_safe(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(payload: dict[str, Any], expires_minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.jwt_expire_minutes
    )
    to_encode = {**payload, "exp": expire}
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        return None


# ---- Symmetric encryption (Fernet) for SMTP password at-rest ----

def _fernet() -> Fernet:
    key = settings.fernet_key
    # Accept either raw 32-byte urlsafe-b64 or hex.
    try:
        return Fernet(key.encode("utf-8"))
    except Exception:
        # Derive from raw string.
        derived = base64.urlsafe_b64encode(hashlib.sha256(key.encode("utf-8")).digest())
        return Fernet(derived)


def encrypt_str(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_str(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


# ---- Family setup tokens (per-family device-join secret) ----

def mint_setup_token() -> tuple[str, str]:
    """Return (plaintext_token, hash_to_store). Plaintext is shown once."""
    import secrets
    plain = f"FAM-{secrets.token_urlsafe(8)}.{secrets.token_urlsafe(32)}"
    h = hash_password(plain)
    return plain, h


async def verify_setup_token(db: AsyncSession, token: str):
    """Resolve a setup token to a Family, or None if invalid."""
    # The Family.id is no longer embedded in the token to avoid ID-only
    # enumeration; we look up by matching the hash on every family with
    # a non-null setup_token_hash. For ≤hundreds of families this is fine.
    from sqlalchemy import select
    from app.models.family import Family
    r = await db.execute(select(Family).where(Family.setup_token_hash.is_not(None)))
    for fam in r.scalars():
        try:
            if verify_password(token, fam.setup_token_hash):
                return fam
        except Exception:
            continue
    return None