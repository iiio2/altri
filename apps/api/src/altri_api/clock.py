"""Single source of "now". Everything time-dependent goes through here."""

from datetime import UTC, datetime

from altri_api.config import get_settings


def now() -> datetime:
    """Current instant in UTC, taken from APP_NOW (never the system clock)."""
    return get_settings().app_now.astimezone(UTC)
