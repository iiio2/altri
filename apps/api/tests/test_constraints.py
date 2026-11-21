"""The database itself rejects invalid data, independent of the API layer."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from altri_api import config
from altri_api.models import TeamMembership, User
from altri_api.seed import apply_seed, load_seed_file
from tests.conftest import SEED_NOW

USER_INSERT = "INSERT INTO users (id, company_id, name, email, role) VALUES (:id, 'co_1', :name, :email, :role)"


@pytest.mark.parametrize(
    "row",
    [
        {"id": "x1", "name": "X", "email": "x1@acme.test", "role": "superuser"},  # unknown role
        {"id": "x2", "name": "X", "email": "X2@Acme.test", "role": "observer"},  # not normalized
        {"id": "x3", "name": "X", "email": "no-at-sign", "role": "observer"},
        {"id": "x4", "name": "X", "email": "blake@acme.test", "role": "observer"},  # duplicate email
        {"id": "x5", "name": "  ", "email": "x5@acme.test", "role": "observer"},  # blank name
    ],
)
async def test_invalid_users_are_rejected(session: AsyncSession, row: dict[str, str]) -> None:
    with pytest.raises(IntegrityError):
        await session.execute(text(USER_INSERT), row)
    await session.rollback()


async def test_membership_requires_existing_team(session: AsyncSession) -> None:
    session.add(TeamMembership(user_id="u2", team_id="team_missing"))
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_session_cannot_expire_before_it_starts(session: AsyncSession) -> None:
    stmt = text("INSERT INTO auth_sessions (token_hash, user_id, created_at, expires_at) VALUES (:h, 'u1', :c, :e)")
    with pytest.raises(IntegrityError):
        await session.execute(stmt, {"h": "a" * 64, "c": SEED_NOW, "e": SEED_NOW - timedelta(seconds=1)})
    await session.rollback()


async def test_seed_is_safe_to_rerun(session: AsyncSession) -> None:
    async def counts() -> tuple[int, int]:
        users = await session.scalar(select(func.count()).select_from(User))
        members = await session.scalar(select(func.count()).select_from(TeamMembership))
        return users, members

    before = await counts()
    await apply_seed(session, load_seed_file(config.get_settings().seed_path))
    await session.commit()

    assert await counts() == before == (9, 11)


async def test_seed_rerun_keeps_app_changes(session: AsyncSession, fresh_data: None) -> None:
    await session.execute(text("UPDATE todos SET done_at = now() WHERE id = 't12'"))
    await session.commit()

    await apply_seed(session, load_seed_file(config.get_settings().seed_path))
    await session.commit()

    assert await session.scalar(text("SELECT done_at IS NOT NULL FROM todos WHERE id = 't12'"))
    await session.rollback()


# --- Domain constraints ---------------------------------------------------------------------------


async def _rejects(session: AsyncSession, sql: str, params: dict | None = None) -> str:
    with pytest.raises(IntegrityError) as exc:
        await session.execute(text(sql), params or {})
    await session.rollback()
    return str(exc.value.orig)


ISSUE = (
    "INSERT INTO issues (id, team_id, title, owner_id, created_at{cols}) "
    "VALUES ('ix', :team, :title, :owner, now(){vals})"
)


def issue_sql(cols: str = "", vals: str = "") -> str:
    return ISSUE.format(cols=cols, vals=vals)


@pytest.mark.parametrize(
    ("owner", "team", "reason"),
    [
        ("u5", "team_lead", "observer"),  # Observers own nothing
        ("u8", "team_lead", "not a member"),  # Team Member of another team
    ],
)
async def test_owner_must_be_allowed_to_own(session: AsyncSession, owner: str, team: str, reason: str) -> None:
    message = await _rejects(session, issue_sql(), {"team": team, "title": "x", "owner": owner})
    assert reason in message


async def test_admin_may_own_outside_their_teams(session: AsyncSession) -> None:
    await session.execute(text(issue_sql()), {"team": "team_ops", "title": "x", "owner": "u1"})
    await session.rollback()


@pytest.mark.parametrize(
    ("cols", "vals"),
    [
        (", priority", ", 6"),
        (", priority", ", 0"),
        (", solved_at", ", now()"),  # solved without a note
        (", resolution_note", ", 'note'"),  # note without being solved
        (", source_measurable_id", ", 'm1'"),  # Measurable without a week
        (", source_measurable_id, source_week_start", ", 'm1', '2026-11-03'"),  # week not a Monday
        (", source_measurable_id, source_week_start", ", 'm6', '2026-11-02'"),  # Measurable of another team
        (", source_measurable_id, source_week_start, source_rock_id", ", 'm1', '2026-11-02', 'r1'"),  # two sources
        (", source_rock_id", ", 'r6'"),  # Rock of another team
    ],
)
async def test_invalid_issues_are_rejected(session: AsyncSession, cols: str, vals: str) -> None:
    await _rejects(session, issue_sql(cols, vals), {"team": "team_lead", "title": "x", "owner": "u2"})


async def test_blank_titles_are_rejected(session: AsyncSession) -> None:
    await _rejects(session, issue_sql(), {"team": "team_lead", "title": "   ", "owner": "u2"})


async def test_one_unsolved_issue_per_score(session: AsyncSession) -> None:
    # i5 is the unsolved Issue for m1 / Nov 2.
    message = await _rejects(
        session,
        issue_sql(", source_measurable_id, source_week_start", ", 'm1', '2026-11-02'"),
        {"team": "team_lead", "title": "dup", "owner": "u2"},
    )
    assert "uq_issues_open_per_score" in message


async def test_todo_cannot_link_an_issue_of_another_team(session: AsyncSession) -> None:
    await _rejects(
        session,
        "INSERT INTO todos (id, team_id, title, owner_id, due_date, created_at, source_issue_id) "
        "VALUES ('tx', 'team_lead', 'x', 'u2', '2026-11-18', now(), 'i8')",
    )


async def test_one_active_meeting_per_team(session: AsyncSession) -> None:
    insert = (
        "INSERT INTO meetings (id, team_id, facilitator_id, started_at, section, section_started_at, scorecard_week) "
        "VALUES (:id, 'team_lead', 'u2', now(), 'scorecard', now(), '2026-11-02')"
    )
    await session.execute(text(insert), {"id": "mx1"})
    message = await _rejects(session, insert, {"id": "mx2"})
    assert "uq_meetings_active_per_team" in message


async def test_observer_cannot_facilitate(session: AsyncSession) -> None:
    await _rejects(
        session,
        "INSERT INTO meetings (id, team_id, facilitator_id, started_at, section, section_started_at, scorecard_week) "
        "VALUES ('mx', 'team_lead', 'u5', now(), 'scorecard', now(), '2026-11-02')",
    )


@pytest.mark.parametrize(
    ("user", "rating"),
    [("u2", 11), ("u2", 0), ("u5", 7), ("u6", 7)],  # out of range, observer, not an attendee
)
async def test_invalid_ratings_are_rejected(session: AsyncSession, user: str, rating: int) -> None:
    await _rejects(
        session,
        "INSERT INTO meeting_ratings (meeting_id, user_id, rating, rated_at) VALUES ('mt1', :u, :r, now())",
        {"u": user, "r": rating},
    )


@pytest.mark.parametrize(
    ("week", "value"),
    [("2026-11-03", "1"), ("2026-11-02", "'NaN'")],
)
async def test_invalid_scores_are_rejected(session: AsyncSession, week: str, value: str) -> None:
    # m5 has no score for Nov 2, so only the CHECK constraints can refuse these.
    sql = f"INSERT INTO scores (measurable_id, week_start, value) VALUES ('m5', '{week}', {value})"  # noqa: S608
    await _rejects(session, sql)


async def test_goal_shape_is_enforced(session: AsyncSession) -> None:
    await _rejects(session, "UPDATE measurables SET goal_value = NULL WHERE id = 'm1'")
    await _rejects(session, "UPDATE measurables SET goal_min = 5, goal_max = 1 WHERE id = 'm3'")
