from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from altri_api import errors, rules
from altri_api.calendar import (
    current_week_start,
    format_week,
    is_week_start,
    last_closed_week_start,
    week_starts_ending_at,
)
from altri_api.issues import service as issues
from altri_api.models import Issue, Measurable, Score, Team, User
from altri_api.schemas import UserRef, as_number
from altri_api.scorecard.schemas import CellOut, GoalOut, MeasurableRowOut, ScorecardOut

SCORECARD_WEEKS = 13


def goal_of(m: Measurable) -> rules.Goal:
    return rules.Goal(type=m.goal_type, value=m.goal_value, min=m.goal_min, max=m.goal_max)


async def team_measurables(db: AsyncSession, team_id: str) -> list[Measurable]:
    stmt = select(Measurable).where(Measurable.team_id == team_id).order_by(Measurable.position, Measurable.id)
    return list(await db.scalars(stmt))


async def scores_for(
    db: AsyncSession, measurable_ids: list[str], first: date, last: date
) -> dict[tuple[str, date], Score]:
    rows = await db.scalars(
        select(Score).where(Score.measurable_id.in_(measurable_ids), Score.week_start.between(first, last))
    )
    return {(s.measurable_id, s.week_start): s for s in rows}


def tz_of(team: Team) -> ZoneInfo:
    return ZoneInfo(team.company.timezone)


async def build_scorecard(db: AsyncSession, team: Team, now: datetime, weeks: int = SCORECARD_WEEKS) -> ScorecardOut:
    tz = tz_of(team)
    current = current_week_start(now, tz)
    week_list = week_starts_ending_at(current, weeks)
    measurables = await team_measurables(db, team.id)
    scores = await scores_for(db, [m.id for m in measurables], week_list[0], current)
    open_issues = {
        (i.source_measurable_id, i.source_week_start): i.id
        for i in await db.scalars(
            select(Issue).where(
                Issue.team_id == team.id,
                Issue.solved_at.is_(None),
                Issue.source_week_start.between(week_list[0], current),
            )
        )
    }

    rows = []
    for m in measurables:
        goal = goal_of(m)
        cells = []
        for week in week_list:
            score = scores.get((m.id, week))
            value = score.value if score else None
            cells.append(
                CellOut(
                    measurable_id=m.id,
                    week_start=week,
                    value=as_number(value),
                    status=rules.measurable_status(goal, value, week, current),
                    version=score.version if score else 0,
                    open_issue_id=open_issues.get((m.id, week)),
                )
            )
        rows.append(
            MeasurableRowOut(
                id=m.id,
                name=m.name,
                unit=m.unit,
                owner=UserRef.model_validate(m.owner),
                goal=GoalOut(type=m.goal_type, value=as_number(m.goal_value), min=as_number(m.goal_min),
                             max=as_number(m.goal_max)),
                cells=cells,
            )
        )  # fmt: skip
    return ScorecardOut(
        current_week=current, last_closed_week=last_closed_week_start(now, tz), weeks=week_list, measurables=rows
    )


async def get_measurable(db: AsyncSession, team_id: str, measurable_id: str) -> Measurable:
    m = await db.scalar(select(Measurable).where(Measurable.id == measurable_id, Measurable.team_id == team_id))
    if m is None:
        raise errors.not_found("Measurable")
    return m


def check_week(week: date, team: Team, now: datetime) -> date:
    """A score week must be a Monday and not after the current week. Returns the current week start."""
    if not is_week_start(week):
        raise errors.unprocessable("week_start must be a Monday (weeks are named by their Monday)")
    current = current_week_start(now, tz_of(team))
    if week > current:
        raise errors.unprocessable("Scores can't be entered for future weeks")
    return current


async def set_score(
    db: AsyncSession,
    *,
    measurable: Measurable,
    week: date,
    value: Decimal | None,
    expected_version: int | None,
    user: User,
    now: datetime,
) -> Score | None:
    """Write (or clear) one cell. Last save wins unless `expected_version` is given."""
    key = (Score.measurable_id == measurable.id, Score.week_start == week)
    if value is None:
        stmt = delete(Score).where(*key)
        if expected_version is not None:
            stmt = stmt.where(Score.version == expected_version)
        deleted = (await db.execute(stmt.returning(Score.version))).first()
        if expected_version is not None and deleted is None:
            await _check_version(db, measurable.id, week, expected_version)
        return None

    insert = pg_insert(Score).values(
        measurable_id=measurable.id, week_start=week, value=value, version=1, updated_at=now, updated_by_id=user.id
    )
    upsert = insert.on_conflict_do_update(
        index_elements=["measurable_id", "week_start"],
        set_={
            "value": insert.excluded.value,
            "version": Score.version + 1,
            "updated_at": insert.excluded.updated_at,
            "updated_by_id": insert.excluded.updated_by_id,
        },
        # With a guard, an existing row is only overwritten at the expected version (0 means "expected none").
        where=(Score.version == expected_version) if expected_version is not None else None,
    ).returning(Score)
    score = await db.scalar(upsert, execution_options={"populate_existing": True})
    if score is None:  # only possible when the guard refused the overwrite
        await _check_version(db, measurable.id, week, -1)
    return score


async def _check_version(db: AsyncSession, measurable_id: str, week: date, expected: int) -> None:
    """409 unless the cell is at `expected` (0 = no score). Rolls back first so nothing half-done commits."""
    stmt = select(Score.version).where(Score.measurable_id == measurable_id, Score.week_start == week)
    current = await db.scalar(stmt) or 0
    if current != expected:
        await db.rollback()
        raise errors.version_conflict(current)


async def make_issue_from_score(
    db: AsyncSession, *, team: Team, measurable: Measurable, week: date, user: User, now: datetime
) -> tuple[Issue, bool]:
    """Make it an Issue on an off-track cell, or return the existing unsolved Issue for that cell."""
    current = check_week(week, team, now)
    source_values = {"source_measurable_id": measurable.id, "source_week_start": week}
    score = await db.scalar(select(Score.value).where(Score.measurable_id == measurable.id, Score.week_start == week))
    status = rules.measurable_status(goal_of(measurable), score, week, current)
    if status is not rules.ScoreStatus.OFF_TRACK:
        existing = await issues.find_open_issue(db, issues.SCORE_SOURCE, source_values)
        if existing is not None:
            return existing, False
        raise errors.conflict(f"Only an off-track score can be made an Issue (this one is {status.value})")
    return await issues.create_issue_once(
        db,
        source=issues.SCORE_SOURCE,
        team_id=team.id,
        title=f"{measurable.name}, week of {format_week(week)}",
        owner_id=user.id,
        now=now,
        source_values=source_values,
    )
