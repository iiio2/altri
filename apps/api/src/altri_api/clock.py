"""Single source of "now". Everything time-dependent goes through here.

The app's "now" is anchored at APP_NOW, never the system's wall clock:
  * APP_CLOCK=ticking (default): APP_NOW plus the time elapsed since this process started, measured with a
    monotonic timer. The meeting timer needs time to pass, yet the business date stays where the seed expects.
  * APP_CLOCK=frozen: exactly APP_NOW. Used by tests and the rules report so results are reproducible.
"""

import time
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from altri_api.calendar import local_date
from altri_api.config import get_settings

_STARTED_MONOTONIC = time.monotonic()


def now() -> datetime:
    """Current instant in UTC."""
    settings = get_settings()
    anchor = settings.app_now.astimezone(UTC)
    if settings.app_clock == "frozen":
        return anchor
    return anchor + timedelta(seconds=time.monotonic() - _STARTED_MONOTONIC)


def today(tz: ZoneInfo) -> date:
    """Today's date in company time."""
    return local_date(now(), tz)
