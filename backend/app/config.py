from functools import lru_cache
from typing import List, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Application ────────────────────────────────────────────────────────────
    APP_NAME: str = "InfraPulse AI"
    APP_ENV: str = "development"
    APP_DEBUG: bool = False
    APP_VERSION: str = "1.0.0"

    # ── Security ───────────────────────────────────────────────────────────────
    SECRET_KEY: str = "change-me-to-a-very-long-random-secret-key-at-least-64-chars"
    ENCRYPTION_KEY: str = ""  # 32-byte Fernet key (base64 encoded)

    # ── Database ───────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://infrapulse:infrapulse_secret@localhost:5432/infrapulse"
    SYNC_DATABASE_URL: str = "postgresql://infrapulse:infrapulse_secret@localhost:5432/infrapulse"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # ── Redis ──────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://:redis_secret@localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://:redis_secret@localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://:redis_secret@localhost:6379/2"

    # ── JWT ────────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = "change-me-jwt-secret-key-very-long-and-random"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ── Platform Admin ─────────────────────────────────────────────────────────
    PLATFORM_ADMIN_EMAIL: str = "admin@infrapulse.local"
    PLATFORM_ADMIN_PASSWORD: str = "ChangeMe123!"
    PLATFORM_ADMIN_NAME: str = "Platform Administrator"

    # ── CORS ───────────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: str = "http://localhost,http://localhost:80"

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    # ── Rate Limiting ──────────────────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 100
    MAX_LOGIN_ATTEMPTS: int = 5
    ACCOUNT_LOCKOUT_MINUTES: int = 15

    # ── SMTP ───────────────────────────────────────────────────────────────────
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_TLS: bool = True
    SMTP_FROM_ADDRESS: str = "noreply@infrapulse.local"
    SMTP_FROM_NAME: str = "InfraPulse AI"

    # ── AI Providers (platform-level defaults) ─────────────────────────────────
    OPENAI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # ── Agent ──────────────────────────────────────────────────────────────────
    AGENT_REGISTRATION_TOKEN_EXPIRE_HOURS: int = 24
    AGENT_HEARTBEAT_INTERVAL_SECONDS: int = 60
    AGENT_HEARTBEAT_TIMEOUT_SECONDS: int = 300

    # ── Demo / Seed Data ───────────────────────────────────────────────────────
    SEED_DEMO_DATA: bool = True
    DEMO_MODE: bool = True

    # ── Logging ────────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = True

    model_config = {"env_file": ".env", "case_sensitive": True, "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
