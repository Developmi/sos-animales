"""Configuration via pydantic-settings from environment variables.

Exposed settings:
- DATABASE_URL (str): async PostgreSQL connection URL
- SECRET_KEY (str): internal signing key
- PLAUSIBLE_DOMAIN / PLAUSIBLE_URL (str | None): privacy-friendly analytics opt-in
- COMMUNITY_VOTE_THRESHOLD (int): minimum consensus votes for community state overrides
- VALKEY_URL (str): connection URL for Valkey (Redis-compatible) cache
- SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD / FROM_EMAIL: transactional email dispatch for PINs
- R2_ENDPOINT / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_BUCKET_NAME / R2_PUBLIC_URL: Cloudflare R2 photos
"""

from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    COMMUNITY_VOTE_THRESHOLD: int
    VALKEY_URL: str

    # Plausible Analytics (optional - loaded only with explicit user consent)
    PLAUSIBLE_DOMAIN: str | None = None
    PLAUSIBLE_URL: str | None = None

    # SMTP configuration for transactional emails
    SMTP_HOST: str
    SMTP_PORT: int
    SMTP_USER: str
    SMTP_PASSWORD: str
    FROM_EMAIL: str

    # Cloudflare R2 object storage (optional - falls back to placeholder when empty)
    R2_ENDPOINT: str | None = None
    R2_ACCESS_KEY_ID: str | None = None
    R2_SECRET_ACCESS_KEY: str | None = None
    R2_BUCKET_NAME: str | None = None
    R2_PUBLIC_URL: str | None = None

    # Admin authentication
    ADMIN_PASSWORD_HASH: str
    JWT_SECRET: str
    JWT_EXPIRE_MINUTES: int = 480

    # SQLAlchemy echo mode (True logs all queries)
    DATABASE_ECHO: bool = False

    # Freshness policy (days)
    FRESHNESS_DAYS: int = 5
    FRESHNESS_HIDE_DAYS: int = 15

    @field_validator("ADMIN_PASSWORD_HASH", mode="before")
    @classmethod
    def normalize_admin_password_hash(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip().strip("'\"")
            if v.startswith("2b$") or v.startswith("2a$") or v.startswith("2y$"):
                v = "$" + v
        return v

    @field_validator("FRESHNESS_HIDE_DAYS")
    @classmethod
    def validate_hide_days_greater_than_freshness(
        cls, v: int, info: ValidationInfo
    ) -> int:
        if v <= info.data.get("FRESHNESS_DAYS", 5):
            raise ValueError("FRESHNESS_HIDE_DAYS must be greater than FRESHNESS_DAYS")
        return v

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()  # type: ignore
