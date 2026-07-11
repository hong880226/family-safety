"""Unit tests for security primitives."""
import base64

import pytest

from app.core.security import (
    create_access_token,
    decrypt_str,
    decode_access_token,
    encrypt_str,
    hash_password,
    mint_setup_token,
    verify_password,
)


def test_hash_and_verify_roundtrip():
    h = hash_password("hunter2hunter2")
    assert h != "hunter2hunter2"
    assert verify_password("hunter2hunter2", h)
    assert not verify_password("wrong-password", h)


def test_verify_password_propagates_malformed_hash():
    """A malformed hash must raise — never silently return False.

    Otherwise callers cannot distinguish "wrong password" from "no hash set",
    enabling account enumeration via timing or response shape.
    """
    with pytest.raises(ValueError):
        verify_password("anything", "not-a-valid-bcrypt-hash")


def test_bcrypt_72_byte_truncation_safe():
    """bcrypt truncates at 72 bytes; both halves of a 80-char password
    must match because we truncate the same way on hash and verify."""
    pw = "a" * 80
    h = hash_password(pw)
    assert verify_password("a" * 72, h)
    assert not verify_password("a" * 71, h)


def test_encrypt_decrypt_roundtrip():
    plain = "smtp-password-with-unicode-密钥"
    token = encrypt_str(plain)
    assert token != plain
    assert decrypt_str(token) == plain


def test_decrypt_garbage_returns_none():
    assert decrypt_str("not-a-fernet-token") is None


def test_jwt_roundtrip():
    tok = create_access_token({"sub": "42", "family_id": 7, "role": "parent"})
    payload = decode_access_token(tok)
    assert payload is not None
    assert payload["sub"] == "42"
    assert payload["family_id"] == 7


def test_jwt_tampered_returns_none():
    tok = create_access_token({"sub": "42"})
    tampered = tok[:-2] + ("A" if tok[-2] != "A" else "B") + tok[-1]
    assert decode_access_token(tampered) is None


def test_setup_token_format():
    plain, h = mint_setup_token()
    assert plain.startswith("FAM-")
    assert "." in plain  # new format separates family part from secret
    assert h != plain
    # Verify with the correct token succeeds.
    assert verify_password(plain, h)
    # Wrong token fails.
    assert not verify_password("FAM-anything", h)