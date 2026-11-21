from datetime import date, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from altri_api import errors, rules
from altri_api.calendar import WEEK, last_closed_week_start, local_date
from altri_api.issues import service as issues
from altri_api.models import Issue, Team, Todo, User
from altri_api.schemas import new_id
from altri_api.scorecard.service import tz_of
from altri_api.teams.service import owner_candidates
from altri_api.todos.schemas import CompletionOut, TodoListOut, TodoOut

TODO_DUE_IN = timedelta(days=7)
TodoFilter = Literal["all", "open", "done"]


async def list_todos(
    db: AsyncSession, team: Team, now: datetime, *, status: TodoFilter, meeting_id: str | None
) -> TodoListOut:
    tz = tz_of(team)
    today = local_date(now, tz)
    stmt = select(Todo).where(Todo.team_id == team.id).order_by(Todo.due_date, Todo.created_at, Todo.id)
    if status == "open":
        stmt = stmt.where(Todo.done_at.is_(None))
    elif status == "done":
        stmt = stmt.where(Todo.done_at.is_not(None))
    if meeting_id is not None:
        stmt = stmt.where(Todo.created_in_meeting_id == meeting_id)
    todos = list(await db.scalars(stmt))

    week = last_closed_week_start(now, tz)
    due_that_week = await db.execute(
        select(Todo.due_date, Todo.done_at).where(
            Todo.team_id == team.id, Todo.due_date >= week, Todo.due_date < week + WEEK
        )
    )
    completion = rules.todo_completion([(d, done) for d, done in due_that_week], week, tz)
    return TodoListOut(
        todos=[TodoOut.of(t, overdue=rules.is_overdue(t.due_date, t.done_at, today)) for t in todos],
        last_closed_week=CompletionOut.of(week, completion),
    )


async def get_todo(db: AsyncSession, team_id: str, todo_id: str, *, for_update: bool = False) -> Todo:
    stmt = select(Todo).where(Todo.id == todo_id, Todo.team_id == team_id)
    if for_update:
        stmt = stmt.with_for_update(of=Todo)
    todo = await db.scalar(stmt, execution_options={"populate_existing": True})
    if todo is None:
        raise errors.not_found("To-Do")
    return todo


def to_out(todo: Todo, team: Team, now: datetime) -> TodoOut:
    return TodoOut.of(todo, overdue=rules.is_overdue(todo.due_date, todo.done_at, local_date(now, tz_of(team))))


async def set_done(db: AsyncSession, team: Team, todo_id: str, *, done: bool, now: datetime) -> Todo:
    todo = await get_todo(db, team.id, todo_id, for_update=True)
    if done and todo.done_at is None:
        todo.done_at = now
    elif not done:
        todo.done_at = None
    await db.flush()
    return todo


async def create_for_issue(
    db: AsyncSession, *, team: Team, issue: Issue, title: str, owner_id: str, now: datetime
) -> Todo:
    """Add a To-Do linked to `issue`, due 7 days from today (company time)."""
    if owner_id not in {u.id for u in await owner_candidates(db, team)}:
        raise errors.unprocessable("owner_id must be one of the team's Admins or Team Members")
    todo = Todo(
        id=new_id("t"),
        team_id=team.id,
        title=title,
        owner_id=owner_id,
        due_date=local_date(now, tz_of(team)) + TODO_DUE_IN,
        created_at=now,
        source_issue_id=issue.id,
        created_in_meeting_id=issues.active_meeting_id(team.id),  # evaluated inside the INSERT
    )
    db.add(todo)
    await db.flush()
    return await get_todo(db, team.id, todo.id)


async def make_issue_from_todo(
    db: AsyncSession, *, team: Team, todo: Todo, user: User, today: date, now: datetime
) -> tuple[Issue, bool]:
    """Bonus: raise an overdue To-Do as an Issue, with the same no-duplicates rule as Scores."""
    source_values = {"source_todo_id": todo.id}
    if not rules.is_overdue(todo.due_date, todo.done_at, today):
        existing = await issues.find_open_issue(db, issues.TODO_SOURCE, source_values)
        if existing is not None:
            return existing, False
        raise errors.conflict("Only an overdue To-Do can be made an Issue")
    return await issues.create_issue_once(
        db,
        source=issues.TODO_SOURCE,
        team_id=team.id,
        title=f"Overdue To-Do: {todo.title}"[:200],
        owner_id=user.id,
        now=now,
        source_values=source_values,
    )
