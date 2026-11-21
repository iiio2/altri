"""Load seed.json into the database. Safe to rerun: rows are keyed by their seed ids.

Usage: uv run python -m altri_api.seed [path/to/seed.json] [--reset]
"""

import argparse
import asyncio
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from altri_api.calendar import last_closed_week_start
from altri_api.config import get_settings
from altri_api.db import get_engine, get_sessionmaker
from altri_api.models import (
    Company,
    Issue,
    Measurable,
    Meeting,
    MeetingAttendee,
    MeetingRating,
    MeetingSection,
    Milestone,
    Rock,
    Role,
    Score,
    Team,
    TeamMembership,
    Todo,
    User,
)
from altri_api.rules import GoalType, RockStatus


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _SeedCompany(_Strict):
    id: str
    name: str
    timezone: str


class _SeedTeam(_Strict):
    id: str
    name: str


class _SeedUser(_Strict):
    id: str
    name: str
    email: str
    role: Role


class _SeedMembership(_Strict):
    user_id: str
    team_id: str


class _SeedGoal(_Strict):
    type: GoalType
    value: Decimal | None = None
    min: Decimal | None = None
    max: Decimal | None = None


class _SeedMeasurable(_Strict):
    id: str
    team_id: str
    name: str
    owner_id: str
    unit: str
    goal: _SeedGoal


class _SeedScore(_Strict):
    measurable_id: str
    week_start: date
    value: Decimal


class _SeedRock(_Strict):
    id: str
    team_id: str
    title: str
    owner_id: str
    quarter: str
    status: RockStatus


class _SeedMilestone(_Strict):
    id: str
    rock_id: str
    title: str
    due_date: date
    done: bool


class _SeedSource(_Strict):
    measurable_id: str
    week_start: date


class _SeedIssue(_Strict):
    id: str
    team_id: str
    title: str
    owner_id: str
    priority: int | None
    created_at: AwareDatetime
    solved_at: AwareDatetime | None
    resolution_note: str | None
    source: _SeedSource | None


class _SeedTodo(_Strict):
    id: str
    team_id: str
    title: str
    owner_id: str
    due_date: date
    done_at: AwareDatetime | None
    source_issue_id: str | None
    created_at: AwareDatetime


class _SeedRating(_Strict):
    user_id: str
    rating: int


class _SeedMeeting(_Strict):
    id: str
    team_id: str
    facilitator_id: str
    started_at: AwareDatetime
    ended_at: AwareDatetime
    attendee_ids: list[str]
    ratings: list[_SeedRating]


class SeedFile(BaseModel):
    model_config = ConfigDict(extra="ignore")  # `meta` is informational

    company: _SeedCompany
    teams: list[_SeedTeam]
    users: list[_SeedUser]
    memberships: list[_SeedMembership]
    measurables: list[_SeedMeasurable] = []
    scores: list[_SeedScore] = []
    rocks: list[_SeedRock] = []
    milestones: list[_SeedMilestone] = []
    issues: list[_SeedIssue] = []
    todos: list[_SeedTodo] = []
    meetings: list[_SeedMeeting] = []

    @model_validator(mode="after")
    def _meetings_have_ended(self) -> SeedFile:
        if any(m.ended_at < m.started_at for m in self.meetings):
            raise ValueError("seeded meetings must end after they start")
        return self


def load_seed_file(path: Path) -> SeedFile:
    return SeedFile.model_validate(json.loads(path.read_text()))


OnConflict = Literal["update", "ignore"]


async def _upsert(
    session: AsyncSession, model: type, rows: list[dict[str, Any]], key: list[str], on_conflict: OnConflict = "update"
) -> None:
    if not rows:
        return
    stmt = pg_insert(model).values(rows)
    update_cols = {c: stmt.excluded[c] for c in rows[0] if c not in key}
    if on_conflict == "update" and update_cols:
        stmt = stmt.on_conflict_do_update(index_elements=key, set_=update_cols)
    else:
        stmt = stmt.on_conflict_do_nothing(index_elements=key)
    await session.execute(stmt)


def _meeting_at(meetings: list[_SeedMeeting], team_id: str, instant: datetime | None) -> str | None:
    """The seeded meeting of `team_id` that was running at `instant`, if any."""
    if instant is None:
        return None
    return next((m.id for m in meetings if m.team_id == team_id and m.started_at <= instant <= m.ended_at), None)


# Tables people change through the app. A rerun inserts missing seed rows but never overwrites their edits.
MUTABLE_TABLES = ["meeting_ratings", "meeting_attendees", "todos", "issues", "meetings", "scores"]


async def reset_mutable_data(session: AsyncSession) -> None:
    """Back to a freshly seeded state: drop everything the app writes (run apply_seed afterwards)."""
    await session.execute(text(f"TRUNCATE {', '.join(MUTABLE_TABLES)}, auth_sessions"))


async def apply_seed(session: AsyncSession, seed: SeedFile) -> None:
    """Idempotent. Reference data (company, teams, users, Measurables, Rocks) is upserted from the file;
    app-editable data (Scores, Issues, To-Dos, meetings) is only inserted when its seed id is missing."""
    company_id = seed.company.id
    tz = ZoneInfo(seed.company.timezone)

    await _upsert(session, Company, [seed.company.model_dump()], ["id"])
    await _upsert(session, Team, [{**t.model_dump(), "company_id": company_id} for t in seed.teams], ["id"])
    await _upsert(
        session,
        User,
        [{**u.model_dump(), "email": u.email.strip().lower(), "company_id": company_id} for u in seed.users],
        ["id"],
    )
    await _upsert(session, TeamMembership, [m.model_dump() for m in seed.memberships], ["user_id", "team_id"])

    measurables = [
        {
            **m.model_dump(exclude={"goal"}),
            "goal_type": m.goal.type,
            "goal_value": m.goal.value,
            "goal_min": m.goal.min,
            "goal_max": m.goal.max,
            "position": i,
        }
        for i, m in enumerate(seed.measurables)
    ]
    await _upsert(session, Measurable, measurables, ["id"])
    await _upsert(session, Rock, [r.model_dump() for r in seed.rocks], ["id"])
    await _upsert(session, Milestone, [m.model_dump() for m in seed.milestones], ["id"])

    await _upsert(session, Score, [s.model_dump() for s in seed.scores], ["measurable_id", "week_start"], "ignore")

    meetings = [
        {
            **m.model_dump(exclude={"attendee_ids", "ratings"}),
            # Seeded meetings ended in Conclude; when that section began isn't recorded, so use the start.
            "section": MeetingSection.CONCLUDE,
            "section_started_at": m.started_at,
            "scorecard_week": last_closed_week_start(m.started_at, tz),
        }
        for m in seed.meetings
    ]
    await _upsert(session, Meeting, meetings, ["id"], "ignore")
    attendees = [
        {"meeting_id": m.id, "user_id": uid, "joined_at": m.started_at} for m in seed.meetings for uid in m.attendee_ids
    ]
    await _upsert(session, MeetingAttendee, attendees, ["meeting_id", "user_id"], "ignore")
    ratings = [
        {"meeting_id": m.id, "user_id": r.user_id, "rating": r.rating, "rated_at": m.ended_at}
        for m in seed.meetings
        for r in m.ratings
    ]
    await _upsert(session, MeetingRating, ratings, ["meeting_id", "user_id"], "ignore")

    # Seeded Issues and To-Dos don't say which meeting they belong to; derive it from the meeting windows.
    issues = [
        {
            **i.model_dump(exclude={"source"}),
            "source_measurable_id": i.source.measurable_id if i.source else None,
            "source_week_start": i.source.week_start if i.source else None,
            "solved_in_meeting_id": _meeting_at(seed.meetings, i.team_id, i.solved_at),
        }
        for i in seed.issues
    ]
    await _upsert(session, Issue, issues, ["id"], "ignore")
    todos = [
        {**t.model_dump(), "created_in_meeting_id": _meeting_at(seed.meetings, t.team_id, t.created_at)}
        for t in seed.todos
    ]
    await _upsert(session, Todo, todos, ["id"], "ignore")


async def main(path: Path, *, reset: bool) -> None:
    seed = load_seed_file(path)
    async with get_sessionmaker()() as session, session.begin():
        if reset:
            await reset_mutable_data(session)
        await apply_seed(session, seed)
    await get_engine().dispose()
    counts = ", ".join(
        f"{len(getattr(seed, k))} {k}"
        for k in ("teams", "users", "measurables", "scores", "issues", "todos", "meetings")
    )
    print(f"{'Reset and seeded' if reset else 'Seeded'} {counts} from {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load seed.json (idempotent).")
    parser.add_argument("path", nargs="?", type=Path, default=None, help="defaults to SEED_PATH (docs/seed.json)")
    parser.add_argument(
        "--reset", action="store_true", help="first delete Scores, Issues, To-Dos, meetings and sessions"
    )
    args = parser.parse_args()
    asyncio.run(main(args.path or get_settings().seed_path, reset=args.reset))
