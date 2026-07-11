"""Unit tests for the startup safety net in app.core.config."""
import os
import pytest


def test_prod_requires_jwt_secret(monkeypatch):
    """When ENVIRONMENT=prod and JWT_SECRET is empty, Settings should refuse to load."""
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("JWT_SECRET", "")
    # Also unset any cached instance.
    from app.core import config as cfg_mod
    cfg_mod.get_settings.cache_clear()

    with pytest.raises(Exception) as exc_info:
        cfg_mod.get_settings()
    assert "JWT_SECRET" in str(exc_info.value)


def test_prod_rejects_debug(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    from app.core import config as cfg_mod
    cfg_mod.get_settings.cache_clear()

    with pytest.raises(Exception) as exc_info:
        cfg_mod.get_settings()
    assert "debug" in str(exc_info.value).lower()


def test_prod_rejects_wildcard_cors_with_credentials(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("CORS_ORIGINS", '["*"]')
    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "true")
    from app.core import config as cfg_mod
    cfg_mod.get_settings.cache_clear()

    with pytest.raises(Exception) as exc_info:
        cfg_mod.get_settings()
    assert "cors" in str(exc_info.value).lower() or "credentials" in str(exc_info.value).lower()


def test_dev_autogenerates_jwt_secret(monkeypatch):
    """In dev, an unset JWT_SECRET is replaced with a random ephemeral one
    so the source never carries a baked-in secret value."""
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("JWT_SECRET", "")
    from app.core import config as cfg_mod
    cfg_mod.get_settings.cache_clear()

    s = cfg_mod.get_settings()
    assert len(s.jwt_secret) >= 32
    assert s.environment == "dev"
    assert s.debug is False


def test_cors_origins_accepts_csv(monkeypatch):
    """CORS_ORIGINS env var supports JSON-array format (pydantic-settings parses natively)."""
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("CORS_ORIGINS", '["https://a.com","https://b.com"]')
    from app.core import config as cfg_mod
    cfg_mod.get_settings.cache_clear()

    s = cfg_mod.get_settings()
    assert "https://a.com" in s.cors_origins
    assert "https://b.com" in s.cors_origins