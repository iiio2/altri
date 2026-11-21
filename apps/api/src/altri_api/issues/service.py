"""Issue queries and the duplicate-free "create once per source" insert."""

from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, ScalarSelect, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from altri_api import errors, rules
from altri_api.models import Issue, Meeting
from altri_api.schemas import new_id


def active_meeting_id(team_id: str) -> ScalarSelect[str]:
    """Subquery: the team's running meeting, if any. Used to stamp Issues solved / To-Dos created in it."""
    return select(Meeting.id).where(Meeting.team_id == team_id, Meeting.ended_at.is_(None)).scalar_subquery()


async def get_issue(db: AsyncSession, team_id: str, issue_id: str, *, for_update: bool = False) -> Issue:
    stmt = select(Issue).where(Issue.id == issue_id, Issue.team_id == team_id)
    if for_update:
        stmt = stmt.with_for_update(of=Issue)
    issue = await db.scalar(stmt, execution_options={"populate_existing": True})
    if issue is None:
        raise errors.not_found("Issue")
    return issue


async def list_issues(db: AsyncSession, team_id: str, *, solved: bool) -> list[Issue]:
    stmt = select(Issue).where(Issue.team_id == team_id)
    if solved:
        rows = await db.scalars(stmt.where(Issue.solved_at.is_not(None)).order_by(Issue.solved_at.desc(), Issue.id))
        return list(rows)
    rows = await db.scalars(stmt.where(Issue.solved_at.is_(None)))
    return sorted(rows, key=lambda i: rules.issue_order_key(i.priority, i.created_at, i.id))


# Each "source" of an Issue has a partial unique index allowing one unsolved Issue per source. The conflict
# target below must repeat that index's columns and predicate so Postgres can infer it.
SCORE_SOURCE = (["source_measurable_id", "source_week_start"], "solved_at IS NULL AND source_measurable_id IS NOT NULL")
ROCK_SOURCE = (["source_rock_id"], "solved_at IS NULL AND source_rock_id IS NOT NULL")
TODO_SOURCE = (["source_todo_id"], "solved_at IS NULL AND source_todo_id IS NOT NULL")


async def create_issue_once(
    db: AsyncSession,
    *,
    source: tuple[list[str], str],
    team_id: str,
    title: str,
    owner_id: str,
    now: datetime,
    source_values: dict[str, Any],
) -> tuple[Issue, bool]:
    """Insert an Issue for `source_values` unless an unsolved one already exists. Returns (issue, created).

    Concurrency: INSERT ... ON CONFLICT DO NOTHING against the partial unique index. When two requests race,
    the second insert waits on the first's uncommitted index entry, then sees the conflict and inserts nothing;
    its follow-up SELECT (a new READ COMMITTED snapshot) returns the winner's row. No locks held across requests,
    no check-then-insert gap, and the database guarantees a single row even if this code had a bug.
    """
    columns, predicate = source
    values = {"id": new_id("i"), "team_id": team_id, "title": title, "owner_id": owner_id, "created_at": now}
    match: list[ColumnElement[bool]] = [getattr(Issue, c) == source_values[c] for c in columns]
    for _ in range(3):  # retry only if the winner got solved between our INSERT and SELECT
        stmt = (
            pg_insert(Issue)
            .values(**values, **source_values)
            .on_conflict_do_nothing(index_elements=columns, index_where=text(predicate))
            .returning(Issue.id)
        )
        if (inserted_id := await db.scalar(stmt)) is not None:
            return await get_issue(db, team_id, inserted_id), True
        existing = await db.scalar(select(Issue).where(*match, Issue.solved_at.is_(None)))
        if existing is not None:
            return existing, False
    raise errors.conflict("The Issue changed while it was being created; try again")


async def find_open_issue(
    db: AsyncSession, source: tuple[list[str], str], source_values: dict[str, Any]
) -> Issue | None:
    columns, _ = source
    return await db.scalar(
        select(Issue).where(*[getattr(Issue, c) == source_values[c] for c in columns], Issue.solved_at.is_(None))
    )
