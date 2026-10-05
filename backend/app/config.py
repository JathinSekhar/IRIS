from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IRIS_", env_file=BACKEND_DIR / ".env", extra="ignore")

    secret_key: str = "dev-only-insecure-secret-change-me"
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'iris.db').as_posix()}"
    access_token_minutes: int = 60 * 8
    cookie_name: str = "iris_session"
    cookie_secure: bool = False
    cors_origins: list[str] = ["http://localhost:5173"]

    consent_version: str = "2026-10"
    checkin_valid_days: int = 14
    checkin_skip_snooze_hours: int = 24


settings = Settings()
