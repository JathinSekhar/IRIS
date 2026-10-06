from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IRIS_", env_file=BACKEND_DIR / ".env", extra="ignore")

    # Database. Supabase Postgres in real use; SQLite is only a zero-setup fallback for quick local runs.
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'iris.db').as_posix()}"

    # Supabase Auth. The anon (publishable) key is public by design; never put the service_role key here.
    supabase_url: str = ""
    supabase_anon_key: str = ""

    # Where the web app is served. Used for the redirect links in confirmation and reset emails.
    site_url: str = "http://localhost:5173"

    access_cookie: str = "iris_session"
    refresh_cookie: str = "iris_refresh"
    cookie_secure: bool = False
    refresh_cookie_days: int = 7
    cors_origins: list[str] = ["http://localhost:5173"]

    consent_version: str = "2026-10"
    checkin_valid_days: int = 14
    checkin_skip_snooze_hours: int = 24


settings = Settings()
