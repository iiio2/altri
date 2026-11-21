"""Company-time calendar: weeks (Monday-Sunday), quarters and "today".

All timestamps are stored in UTC. Weeks, due dates and quarters are calendar concepts in the company's
time zone, so every conversion between the two goes through this module. Pure functions only.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

WEEK = timedelta(days=7)


def local_date(instant: datetime, tz: ZoneInfo) -> date:
    """Calendar date of a UTC instant in company time."""
    return instant.astimezone(tz).date()


def week_start(day: date) -> date:
    """The Monday of the week containing `day`. Weeks are named by their Monday."""
    return day - timedelta(days=day.weekday())


def is_week_start(day: date) -> bool:
    return day.weekday() == 0


def current_week_start(now: datetime, tz: ZoneInfo) -> date:
    return week_start(local_date(now, tz))


def last_closed_week_start(now: datetime, tz: ZoneInfo) -> date:
    """The full week before the current one."""
    return current_week_start(now, tz) - WEEK


def week_starts_ending_at(last: date, count: int) -> list[date]:
    """`count` consecutive week starts, oldest first, ending with `last`."""
    return [last - WEEK * i for i in reversed(range(count))]


def local_midnight_utc(day: date, tz: ZoneInfo) -> datetime:
    """The UTC instant at which `day` begins in company time (DST-aware)."""
    return datetime.combine(day, time.min, tzinfo=tz).astimezone(UTC)


def week_bounds_utc(start: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """[Monday 00:00, next Monday 00:00) in company time, as UTC instants.

    The half-open end is Sunday 23:59:59.999... A DST change makes the week 167 or 169 hours long.
    """
    return local_midnight_utc(start, tz), local_midnight_utc(start + WEEK, tz)


def quarter_label(day: date) -> str:
    """Calendar quarter, e.g. `2026-Q4`."""
    return f"{day.year}-Q{(day.month - 1) // 3 + 1}"


def format_week(start: date) -> str:
    """Human week label used in generated Issue titles, e.g. `Nov 2` (matches the seed)."""
    return f"{start:%b} {start.day}"
