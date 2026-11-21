"""Rules report: every computed value from spec 2.6, as JSON, for APP_NOW.

Usage: uv run python -m altri_api.report [--out rules_report.json]

Reads the configured database (run it on a freshly seeded one: `pnpm db:seed -- --reset`). Always evaluates at
exactly APP_NOW, whatever APP_CLOCK says. Uses the same rule functions and summary builder as the API.
"""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from altri_api import rules
from altri_api.calendar import current_week_start, local_date, week_starts_ending_at
from altri_api.config import get_settings
from altri_api.db import get_engine, get_sessionmaker
from altri_api.meetings.service import build_summary
from altri_api.models import Issue, Meeting, Rock, Team, Todo
from altri_api.scorecard.service import SCORECARD_WEEKS, goal_of, scores_for, team_measurables, tz_of


def _iso_utc(instant: datetime) -> str:
    return instant.astimezone(UTC).isoformat().replace("+00:00", "Z")


async def team_report(db: AsyncSession, team: Team, now: datetime) -> dict[str, Any]:
    tz = tz_of(team)
    today = local_date(now, tz)
    current = current_week_start(now, tz)
    weeks = week_starts_ending_at(current, SCORECARD_WEEKS)

    measurables = await team_measurables(db, team.id)
    scores = await scores_for(db, [m.id for m in measurables], weeks[0], current)
    measurable_status = {
        m.id: {
            w.isoformat(): rules.measurable_status(
                goal_of(m), getattr(scores.get((m.id, w)), "value", None), w, current
            )
            for w in weeks
        }
        for m in measurables
    }

    todos = list(await db.scalars(select(Todo).where(Todo.team_id == team.id)))
    pairs = [(t.due_date, t.done_at) for t in todos]
    todo_completion = {}
    for w in weeks:
        completion = rules.todo_completion(pairs, w, tz)
        todo_completion[w.isoformat()] = completion.as_dict() if completion else None
    overdue = sorted(t.id for t in todos if rules.is_overdue(t.due_date, t.done_at, today))

    rocks = {
        r.id: {
            "status": rules.rock_status(r.status, [(m.due_date, m.done) for m in r.milestones], today),
            "progress_percent": rules.rock_progress(r.status, [m.done for m in r.milestones]),
        }
        for r in await db.scalars(select(Rock).where(Rock.team_id == team.id).order_by(Rock.id))
    }

    open_issues = await db.scalars(select(Issue).where(Issue.team_id == team.id, Issue.solved_at.is_(None)))
    issue_order = [
        i.id for i in sorted(open_issues, key=lambda i: rules.issue_order_key(i.priority, i.created_at, i.id))
    ]

    meetings = {}
    ended = await db.scalars(
        select(Meeting).where(Meeting.team_id == team.id, Meeting.ended_at.is_not(None)).order_by(Meeting.id)
    )
    for meeting in ended:
        summary = await build_summary(db, meeting)
        meetings[meeting.id] = {
            "scorecard_week": summary.scorecard_week.isoformat(),
            "measurable_status": {m.id: m.status for m in summary.measurables},
            "issues_solved": sorted(i.id for i in summary.issues_solved),
            "todos_created": sorted(t.id for t in summary.todos_created),
            "attendee_ids": sorted(a.id for a in summary.attendees),
            "rating": summary.average_rating,
        }

    return {
        "measurable_status": measurable_status,
        "todo_completion": todo_completion,
        "overdue_todos": overdue,
        "rocks": rocks,
        "issue_order": issue_order,
        "meetings": meetings,
    }


async def build_report(db: AsyncSession, now: datetime) -> dict[str, Any]:
    teams = await db.scalars(select(Team).order_by(Team.id))
    return {"now": _iso_utc(now), "teams": {t.id: await team_report(db, t, now) for t in teams}}


async def generate() -> dict[str, Any]:
    now = get_settings().app_now.astimezone(UTC)  # exactly APP_NOW, never the ticking clock
    async with get_sessionmaker()() as db:
        report = await build_report(db, now)
    await get_engine().dispose()
    return report


def main(out: Path | None) -> None:
    text = json.dumps(asyncio.run(generate()), indent=2) + "\n"
    if out is None:
        sys.stdout.write(text)
    else:
        out.write_text(text)
        print(f"Wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Print every computed rule value (spec 2.6) as JSON.")
    parser.add_argument("--out", type=Path, default=None, help="write to this file instead of stdout")
    main(parser.parse_args().out)
