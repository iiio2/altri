from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from altri_api import clock
from altri_api.auth.deps import Db, ReadableTeam, WritableTeam
from altri_api.calendar import local_date
from altri_api.errors import COMMON_ERRORS
from altri_api.issues.schemas import IssueOut
from altri_api.live.hub import Resource, notify_changed
from altri_api.schemas import ID_PATTERN, id_path
from altri_api.scorecard.service import tz_of
from altri_api.todos import service
from altri_api.todos.schemas import TodoListOut, TodoOut, TodoUpdateIn

router = APIRouter(prefix="/teams/{team_id}/todos", tags=["todos"])

TodoId = Annotated[str, id_path("To-Do id, e.g. `t12`")]
ERRORS = {**COMMON_ERRORS, 404: {"description": "No such To-Do in this team"}}


@router.get("", response_model=TodoListOut, summary="To-Dos and last closed week's completion", responses=ERRORS)
async def list_todos(
    team: ReadableTeam,
    db: Db,
    status: Annotated[service.TodoFilter, Query(description="Filter by done state")] = "all",
    meeting_id: Annotated[
        str | None, Query(pattern=ID_PATTERN, description="Only To-Dos created during this meeting")
    ] = None,
) -> TodoListOut:
    """Ordered by due date. Each To-Do carries an `overdue` flag computed for today in company time."""
    return await service.list_todos(db, team, clock.now(), status=status, meeting_id=meeting_id)


@router.patch("/{todo_id}", response_model=TodoOut, summary="Mark done, or undo", responses=ERRORS)
async def update_todo(ctx: WritableTeam, db: Db, todo_id: TodoId, body: TodoUpdateIn) -> TodoOut:
    now = clock.now()
    todo = await service.set_done(db, ctx.team, todo_id, done=body.done, now=now)
    await db.commit()
    notify_changed(ctx.team.id, Resource.TODOS)
    return service.to_out(todo, ctx.team, now)


@router.post(
    "/{todo_id}/issue",
    response_model=IssueOut,
    status_code=status.HTTP_201_CREATED,
    summary="Make an overdue To-Do an Issue (idempotent)",
    responses={
        **ERRORS,
        200: {"model": IssueOut, "description": "An unsolved Issue already existed for this To-Do"},
        409: {"description": "The To-Do is not overdue"},
    },
)
async def make_it_an_issue(ctx: WritableTeam, db: Db, todo_id: TodoId, response: Response) -> IssueOut:
    now = clock.now()
    todo = await service.get_todo(db, ctx.team.id, todo_id)
    issue, created = await service.make_issue_from_todo(
        db, team=ctx.team, todo=todo, user=ctx.user, today=local_date(now, tz_of(ctx.team)), now=now
    )
    await db.commit()
    if created:
        notify_changed(ctx.team.id, Resource.ISSUES)
    else:
        response.status_code = status.HTTP_200_OK
    return IssueOut.of(issue)
