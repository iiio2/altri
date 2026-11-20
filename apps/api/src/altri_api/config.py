"""Runtime settings, read from the environment and the repo-root `.env`."""

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", REPO_ROOT / "apps/api/.env"),
        extra="ignore",
    )

    database_url: str
    # The app's notion of "now". Never read the system clock for business logic.
    app_now: AwareDatetime = Field(default=datetime.fromisoformat("2026-11-11T15:00:00Z"))
    company_timezone: str = "America/Chicago"

    session_cookie_name: str = "altri_session"
    session_ttl_hours: int = Field(default=24 * 7, gt=0)
    # Set true behind HTTPS. Plain-HTTP local dev needs it false.
    session_cookie_secure: bool = False

    seed_path: Path = REPO_ROOT / "docs/seed.json"

    @field_validator("company_timezone")
    @classmethod
    def _valid_tz(cls, v: str) -> str:
        ZoneInfo(v)  # raises on unknown zone
        return v

    @property
    def sqlalchemy_url(self) -> str:
        """Same URL, pinned to the psycopg 3 driver (it understands libpq params like sslmode)."""
        url = self.database_url
        for prefix in ("postgresql+psycopg://", "postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        raise ValueError("DATABASE_URL must be a postgresql:// URL")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
