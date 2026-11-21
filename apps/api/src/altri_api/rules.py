"""Business rules from spec 2.6, as pure functions over plain values.

Nothing here touches the database or the clock: callers pass "now"/"today" in. That keeps every rule
unit-testable at its boundaries and lets the API and the rules report share one implementation.
Ratios are computed with exact integer arithmetic so "round half up" never suffers float error.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo

from altri_api.calendar import WEEK, week_bounds_utc

TODO_COMPLETION_TARGET_PERCENT = 90


class GoalType(StrEnum):
    AT_LEAST = "at_least"
    AT_MOST = "at_most"
    BETWEEN = "between"
    EXACTLY = "exactly"


class ScoreStatus(StrEnum):
    ON_TRACK = "on_track"
    OFF_TRACK = "off_track"
    PENDING = "pending"


class RockStatus(StrEnum):
    ON_TRACK = "on_track"
    OFF_TRACK = "off_track"
    COMPLETE = "complete"


# --- Rounding -------------------------------------------------------------------------------------


def round_half_up(value: Decimal, places: int = 0) -> Decimal:
    """12.5 -> 13, 8.25 -> 8.3 (places=1). Decimal in, Decimal out: no binary float rounding."""
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def percent(numerator: int, denominator: int) -> int:
    """Whole percent of numerator/denominator, rounded half up, exactly."""
    if denominator <= 0:
        raise ValueError("denominator must be positive")
    # round_half_up(100 * n / d) == floor((200 * n + d) / (2 * d)) for non-negative n.
    return (200 * numerator + denominator) // (2 * denominator)


# --- Measurable status ----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Goal:
    type: GoalType
    value: Decimal | None = None
    min: Decimal | None = None
    max: Decimal | None = None

    def is_met_by(self, score: Decimal) -> bool:
        """Boundaries are on track."""
        match self.type:
            case GoalType.AT_LEAST:
                assert self.value is not None
                return score >= self.value
            case GoalType.AT_MOST:
                assert self.value is not None
                return score <= self.value
            case GoalType.EXACTLY:
                assert self.value is not None
                return score == self.value
            case GoalType.BETWEEN:
                assert self.min is not None and self.max is not None
                return self.min <= score <= self.max


def measurable_status(goal: Goal, score: Decimal | None, week: date, current_week: date) -> ScoreStatus:
    """A closed week with no score is off track; the current (or a future) week with no score is pending."""
    if score is None:
        return ScoreStatus.PENDING if week >= current_week else ScoreStatus.OFF_TRACK
    return ScoreStatus.ON_TRACK if goal.is_met_by(score) else ScoreStatus.OFF_TRACK


# --- To-Dos ---------------------------------------------------------------------------------------


def is_overdue(due_date: date, done_at: datetime | None, today: date) -> bool:
    """Not done and due before today (company time). Due today is not overdue."""
    return done_at is None and due_date < today


@dataclass(frozen=True, slots=True)
class Completion:
    due: int
    done: int

    @property
    def rate_percent(self) -> int:
        return percent(self.done, self.due)

    @property
    def meets_target(self) -> bool:
        """Compares the exact ratio with 90%, not the rounded percent."""
        return self.done * 100 >= self.due * TODO_COMPLETION_TARGET_PERCENT

    def as_dict(self) -> dict[str, int | bool]:
        return {
            "due": self.due,
            "done": self.done,
            "rate_percent": self.rate_percent,
            "meets_target": self.meets_target,
        }


def todo_completion(todos: Iterable[tuple[date, datetime | None]], week: date, tz: ZoneInfo) -> Completion | None:
    """To-Dos done by the end of `week` / To-Dos due in `week`. None when nothing is due.

    `todos` are (due_date, done_at) pairs. Done after the due week counts as not done; done early counts.
    """
    _, week_end = week_bounds_utc(week, tz)
    due = done = 0
    for due_date, done_at in todos:
        if week <= due_date < week + WEEK:
            due += 1
            if done_at is not None and done_at < week_end:
                done += 1
    return Completion(due=due, done=done) if due else None


# --- Rocks ----------------------------------------------------------------------------------------


def rock_status(seeded: RockStatus, milestones: Iterable[tuple[date, bool]], today: date) -> RockStatus:
    """`milestones` are (due_date, done) pairs. A Milestone due today is not past due."""
    if seeded is RockStatus.COMPLETE:
        return RockStatus.COMPLETE
    if seeded is RockStatus.OFF_TRACK:
        return RockStatus.OFF_TRACK
    if any(not done and due_date < today for due_date, done in milestones):
        return RockStatus.OFF_TRACK
    return RockStatus.ON_TRACK


def rock_progress(seeded: RockStatus, milestones_done: Iterable[bool]) -> int:
    """Completed / total Milestones as a whole percent. No Milestones: 0%, or 100% once Complete."""
    flags = list(milestones_done)
    if not flags:
        return 100 if seeded is RockStatus.COMPLETE else 0
    return percent(sum(flags), len(flags))


# --- Issues ---------------------------------------------------------------------------------------


def issue_order_key(priority: int | None, created_at: datetime, issue_id: str) -> tuple[bool, int, datetime, str]:
    """Priority 5 first down to 1, no priority last; oldest first within a priority; id breaks exact ties."""
    return (priority is None, -(priority or 0), created_at, issue_id)


# --- Meetings -------------------------------------------------------------------------------------


def meeting_rating(ratings: Iterable[int]) -> Decimal | None:
    """Average of submitted ratings to one decimal, half up. No ratings means no score."""
    values = list(ratings)
    if not values:
        return None
    n, total = len(values), sum(values)
    tenths = (20 * total + n) // (2 * n)  # round_half_up(10 * total / n), exactly
    return Decimal(tenths).scaleb(-1)
