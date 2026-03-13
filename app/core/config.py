"""
app/core/config.py
===================
Pydantic-settings configuration.

Changes vs previous version:
  - Added FORCE_HTTPS: bool (default False)
    When True, ForceHttpsMiddleware rewrites all request schemes to https.
    Set FORCE_HTTPS=true in .env if your reverse proxy does NOT forward
    X-Forwarded-Proto headers to the container.
    See middleware.py for full explanation.
"""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Application ───────────────────────────────────────────
    APP_NAME: str = "MAKTech Financial Flow"
    APP_ENV: str = "development"

    # ── Database ──────────────────────────────────────────────
    DATABASE_URL: str

    # ── JWT ───────────────────────────────────────────────────
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Fernet (card data encryption at rest) ─────────────────
    FERNET_KEY: str

    # ── SMTP ──────────────────────────────────────────────────
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_TLS: bool = True

    EMAILS_FROM_EMAIL: str = ""
    EMAILS_FROM_NAME: str = "MAKTech FinFlow"

    # ── CORS ──────────────────────────────────────────────────
    ALLOWED_ORIGINS: str = "https://fin-flow.maktechlaravel.cloud,http://localhost:3000,http://localhost:5173"

    # ── HTTPS enforcement ─────────────────────────────────────
    # Set FORCE_HTTPS=true in .env if your reverse proxy does NOT forward
    # X-Forwarded-Proto: https to the container.
    # Coolify + Traefik forward it automatically — leave False by default.
    FORCE_HTTPS: bool = False

    # ── Finance ───────────────────────────────────────────────
    BDT_DEFAULT_RATE: float = 110.0

    # ── Cloudinary ────────────────────────────────────────────
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    # ── Computed properties ───────────────────────────────────

    @property
    def smtp_from_header(self) -> str:
        """RFC 5322 From header: 'Name <email>' or just 'email'."""
        if self.EMAILS_FROM_NAME and self.EMAILS_FROM_EMAIL:
            return f"{self.EMAILS_FROM_NAME} <{self.EMAILS_FROM_EMAIL}>"
        return self.EMAILS_FROM_EMAIL or self.SMTP_USER

    @property
    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    @property
    def smtp_configured(self) -> bool:
        return bool(self.SMTP_USER and self.SMTP_PASSWORD)


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()