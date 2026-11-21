"""Spec 2.6 business rules, each with its boundary cases. Pure functions: no database, no clock."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from altri_api import calendar
from altri_api.rules import (
    Goal,
    GoalType,
    RockStatus,
    ScoreStatus,
    is_overdue,
    issue_order_key,
    measurable_status,
    meeting_rating,
    percent,
    rock_progress,
    rock_status,
    round_half_up,
    todo_completion,
)

CHI = ZoneInfo("America/Chicago")
D = Decimal


def utc(s: str) -> datetime:
    return datetime.fromisoformat(s).astimezone(UTC)


# --- Time -----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("instant", "week"),
    [
        ("2026-11-11T15:00:00Z", date(2026, 11, 9)),  # the seed's now: Wednesday
        ("2026-11-16T05:59:59Z", date(2026, 11, 9)),  # Sunday 23:59:59 Chicago (CST, UTC-6)
        ("2026-11-16T06:00:00Z", date(2026, 11, 16)),  # Monday 00:00:00 Chicago
        ("2026-11-02T05:59:59Z", date(2026, 10, 26)),  # last second of the week DST ended in
        ("2026-10-26T04:59:59Z", date(2026, 10, 19)),  # Sunday 23:59:59 CDT (UTC-5)
        ("2026-10-26T05:00:00Z", date(2026, 10, 26)),  # Monday 00:00 CDT
    ],
)
def test_week_boundaries_are_in_company_time(instant: str, week: date) -> None:
    assert calendar.current_week_start(utc(instant), CHI) == week


def test_last_closed_week_is_the_full_week_before_the_current_one() -> None:
    assert calendar.last_closed_week_start(utc("2026-11-11T15:00:00Z"), CHI) == date(2026, 11, 2)


def test_week_bounds_follow_dst() -> None:
    start, end = calendar.week_bounds_utc(date(2026, 10, 26), CHI)  # DST ends Sunday Nov 1
    assert (start, end) == (utc("2026-10-26T05:00:00Z"), utc("2026-11-02T06:00:00Z"))
    assert end - start == timedelta(hours=169)


def test_thirteen_weeks_end_with_the_current_one() -> None:
    weeks = calendar.week_starts_ending_at(date(2026, 11, 9), 13)
    assert (weeks[0], weeks[-1], len(weeks)) == (date(2026, 8, 17), date(2026, 11, 9), 13)


@pytest.mark.parametrize(
    ("day", "label"),
    [(date(2026, 9, 30), "2026-Q3"), (date(2026, 10, 1), "2026-Q4"), (date(2026, 12, 31), "2026-Q4")],
)
def test_calendar_quarters(day: date, label: str) -> None:
    assert calendar.quarter_label(day) == label


# --- Rounding -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "places", "expected"),
    [(D("12.5"), 0, D("13")), (D("8.25"), 1, D("8.3")), (D("8.24"), 1, D("8.2")), (D("0.5"), 0, D("1"))],
)
def test_round_half_up(value: Decimal, places: int, expected: Decimal) -> None:
    assert round_half_up(value, places) == expected


@pytest.mark.parametrize(
    ("n", "d", "expected"), [(1, 8, 13), (1, 3, 33), (2, 3, 67), (9, 10, 90), (0, 3, 0), (3, 3, 100), (1, 200, 1)]
)
def test_percent_rounds_half_up_exactly(n: int, d: int, expected: int) -> None:
    assert percent(n, d) == expected


# --- Measurable status ----------------------------------------------------------------------------

CURRENT = date(2026, 11, 9)
CLOSED = date(2026, 11, 2)


@pytest.mark.parametrize(
    ("goal", "score", "expected"),
    [
        (Goal(GoalType.AT_LEAST, value=D(10)), D(10), ScoreStatus.ON_TRACK),  # boundary
        (Goal(GoalType.AT_LEAST, value=D(10)), D("9.9999"), ScoreStatus.OFF_TRACK),
        (Goal(GoalType.AT_MOST, value=D("3.0")), D("3.0"), ScoreStatus.ON_TRACK),  # boundary
        (Goal(GoalType.AT_MOST, value=D("3.0")), D("3.1"), ScoreStatus.OFF_TRACK),
        (Goal(GoalType.BETWEEN, min=D(2), max=D(4)), D(2), ScoreStatus.ON_TRACK),  # lower boundary
        (Goal(GoalType.BETWEEN, min=D(2), max=D(4)), D(4), ScoreStatus.ON_TRACK),  # upper boundary
        (Goal(GoalType.BETWEEN, min=D(2), max=D(4)), D("4.5"), ScoreStatus.OFF_TRACK),
        (Goal(GoalType.BETWEEN, min=D(2), max=D(4)), D("1.8"), ScoreStatus.OFF_TRACK),
        (Goal(GoalType.EXACTLY, value=D(1)), D("1.0000"), ScoreStatus.ON_TRACK),
        (Goal(GoalType.EXACTLY, value=D(1)), D(2), ScoreStatus.OFF_TRACK),
    ],
)
def test_measurable_status_compares_with_goal(goal: Goal, score: Decimal, expected: ScoreStatus) -> None:
    assert measurable_status(goal, score, CLOSED, CURRENT) is expected
    assert measurable_status(goal, score, CURRENT, CURRENT) is expected  # a current-week score is judged too


def test_missing_score_is_off_track_when_closed_and_pending_when_current() -> None:
    goal = Goal(GoalType.AT_LEAST, value=D(10))
    assert measurable_status(goal, None, CLOSED, CURRENT) is ScoreStatus.OFF_TRACK
    assert measurable_status(goal, None, CURRENT, CURRENT) is ScoreStatus.PENDING


# --- To-Dos ---------------------------------------------------------------------------------------

TODAY = date(2026, 11, 11)


def test_overdue_boundaries() -> None:
    assert is_overdue(date(2026, 11, 10), None, TODAY)  # due yesterday, not done
    assert not is_overdue(TODAY, None, TODAY)  # due today is not overdue
    assert not is_overdue(date(2026, 11, 10), utc("2026-11-12T00:00:00Z"), TODAY)  # done (even late)


WEEK = date(2026, 11, 2)
WEEK_END = utc("2026-11-09T06:00:00Z")  # Monday 00:00 Chicago


def test_completion_counts_done_by_the_end_of_the_due_week() -> None:
    todos = [
        (date(2026, 11, 6), WEEK_END - timedelta(seconds=1)),  # Sunday 23:59:59: done
        (date(2026, 11, 8), WEEK_END),  # Monday 00:00:00: done after its week, counts as not done
        (date(2026, 11, 3), utc("2026-10-20T12:00:00Z")),  # done early: done
        (date(2026, 11, 4), None),  # not done
        (date(2026, 11, 9), None),  # due next week: not counted
        (date(2026, 11, 1), None),  # due last week: not counted
    ]
    c = todo_completion(todos, WEEK, CHI)
    assert c is not None
    assert (c.due, c.done, c.rate_percent, c.meets_target) == (4, 2, 50, False)


def test_completion_target_is_met_at_exactly_90_percent() -> None:
    done = [(date(2026, 11, 3), WEEK_END - timedelta(days=1))]
    c = todo_completion(done * 9 + [(date(2026, 11, 3), None)], WEEK, CHI)
    assert c is not None and (c.rate_percent, c.meets_target) == (90, True)


def test_completion_target_compares_the_exact_ratio_not_the_rounded_percent() -> None:
    done = [(date(2026, 11, 3), WEEK_END - timedelta(days=1))]
    # 179/199 = 89.95% rounds to 90% but is below target.
    c = todo_completion(done * 179 + [(date(2026, 11, 3), None)] * 20, WEEK, CHI)
    assert c is not None and (c.rate_percent, c.meets_target) == (90, False)


def test_completion_with_nothing_due_has_no_rate() -> None:
    assert todo_completion([(date(2026, 11, 20), None)], WEEK, CHI) is None


# --- Rocks ----------------------------------------------------------------------------------------


def test_rock_status_rules() -> None:
    past_due = [(date(2026, 11, 10), False)]
    assert rock_status(RockStatus.ON_TRACK, past_due, TODAY) is RockStatus.OFF_TRACK
    assert rock_status(RockStatus.ON_TRACK, [(TODAY, False)], TODAY) is RockStatus.ON_TRACK  # due today: not past due
    assert rock_status(RockStatus.ON_TRACK, [(date(2026, 11, 10), True)], TODAY) is RockStatus.ON_TRACK  # done
    assert rock_status(RockStatus.OFF_TRACK, [], TODAY) is RockStatus.OFF_TRACK  # no Milestones: seeded status
    assert rock_status(RockStatus.ON_TRACK, [], TODAY) is RockStatus.ON_TRACK
    assert rock_status(RockStatus.COMPLETE, past_due, TODAY) is RockStatus.COMPLETE  # Complete wins


def test_rock_progress_rules() -> None:
    assert rock_progress(RockStatus.ON_TRACK, [True] + [False] * 7) == 13  # 12.5% rounds half up
    assert rock_progress(RockStatus.ON_TRACK, [True, False, False]) == 33
    assert rock_progress(RockStatus.ON_TRACK, []) == 0
    assert rock_progress(RockStatus.COMPLETE, []) == 100
    assert rock_progress(RockStatus.COMPLETE, [True, False]) == 50  # Milestones decide when there are some


# --- Issues ---------------------------------------------------------------------------------------


def test_issue_order() -> None:
    t = utc("2026-10-01T00:00:00Z")
    issues = [
        ("none_old", None, t),
        ("p3", 3, t),
        ("p5_new", 5, t + timedelta(days=2)),
        ("p5_old", 5, t + timedelta(days=1)),
        ("p1", 1, t),
        ("none_new", None, t + timedelta(days=5)),
    ]
    ordered = sorted(issues, key=lambda i: issue_order_key(i[1], i[2], i[0]))
    assert [i[0] for i in ordered] == ["p5_old", "p5_new", "p3", "p1", "none_old", "none_new"]


# --- Meetings -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ratings", "expected"),
    [([8, 9, 7], D("8.0")), ([8, 9, 8, 8], D("8.3")), ([7, 8], D("7.5")), ([1, 1, 2], D("1.3")), ([10], D("10.0"))],
)
def test_meeting_rating_is_the_average_to_one_decimal_half_up(ratings: list[int], expected: Decimal) -> None:
    assert meeting_rating(ratings) == expected


def test_meeting_without_ratings_has_no_score() -> None:
    assert meeting_rating([]) is None
