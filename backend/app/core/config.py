"""Application settings loaded from environment variables."""
import secrets
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "FamilySafety Backend"
    app_version: str = "0.1.0"
    # Defaults to prod to fail safely: dev must explicitly opt in.
    environment: Literal["dev", "test", "prod"] = "prod"
    debug: bool = False

    api_v1_prefix: str = "/api/v1"

    database_url: str = Field(
        default="sqlite+aiosqlite:///./familysafety.db",
        description="Database connection URL (async)",
    )
    redis_url: str = Field(default="redis://localhost:6379/0")

    # JWT — secrets.token_urlsafe(32) returns 43-char URL-safe string.
    jwt_secret: str = Field(default="")
    jwt_algorithm: Literal["HS256", "RS256"] = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24h (was 7d; refresh-token work tracked separately)

    # SMTP password at-rest encryption (Fernet). If unset, fall back to deriving
    # from jwt_secret (less ideal but works for dev).
    fernet_key: str = Field(default="")

    llm_base_url: str = Field(default="https://api.deepseek.com/v1")
    llm_api_key: str = Field(default="")
    llm_model: str = Field(default="deepseek-chat")
    llm_timeout_seconds: int = 30

    # Where uploaded screenshot bytes are persisted. Relative paths in the
    # DB are joined onto this root. Default targets the conventional Linux
    # deployment location; tests override via monkeypatch to a tmp dir.
    screenshots_dir: str = Field(default="/var/lib/familysafety/screenshots")

    # CORS — defaults to empty; environment must opt in.
    # Annotated[..., NoDecode] tells pydantic-settings to skip JSON parsing
    # for this list field so our field_validator below can handle CSV/empty/"*".
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    cors_allow_credentials: bool = True

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, v):
        # Accept JSON list, CSV, or "*" from env.
        if v is None or v == "":
            return []
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v == "*":
                return ["*"]
            if v.startswith("["):
                import json
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

    @model_validator(mode="after")
    def _validate_production_safety(self):
        # In prod, refuse to start with insecure defaults.
        if self.environment == "prod":
            if self.debug:
                raise ValueError("debug=True is not allowed when environment='prod'")
            if not self.jwt_secret or len(self.jwt_secret) < 32:
                raise ValueError(
                    "JWT_SECRET must be set to a random string >=32 chars in prod"
                )
            if "*" in self.cors_origins and self.cors_allow_credentials:
                # Spec forbids credentialed cross-origin with "*"; refuse loud.
                raise ValueError(
                    "cors_origins=['*'] with credentials is forbidden in prod"
                )
        else:
            # dev/test: mint ephemeral secret if missing so we don't bake a value in source.
            if not self.jwt_secret:
                self.jwt_secret = secrets.token_urlsafe(32)
        if not self.fernet_key:
            # Derive from jwt_secret (32 bytes) so dev works without explicit config.
            # In prod, prefer explicit fernet_key.
            import base64
            import hashlib
            self.fernet_key = base64.urlsafe_b64encode(
                hashlib.sha256(self.jwt_secret.encode("utf-8")).digest()
            ).decode("utf-8")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()