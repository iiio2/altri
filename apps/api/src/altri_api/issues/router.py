from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from altri_api import clock, errors
from altri_api.auth.deps import Db, ReadableTeam, WritableTeam
from altri_api.errors import COMMON_ERRORS
from altri_api.issues import service
from altri_api.issues.schemas import IssueCreateIn, IssueOut, IssueSolveIn, IssueTodoIn, IssueUpdateIn
from altri_api.live.hub import Resource, notify_changed
from altri_api.models import Issue
from altri_api.schemas import id_path, new_id
from altri_api.todos import service as todos
from altri_api.todos.schemas import TodoOut

router = APIRouter(prefix="/teams/{team_id}/issues", tags=["issues"])

IssueId = Annotated[str, id_path("Issue id, e.g. `i1`")]
ERRORS = {**COMMON_ERRORS, 404: {"description": "No such Issue in this team"}}


@router.get("", response_model=list[IssueOut], summary="List Issues", responses=ERRORS)
async def list_issues(
    team: ReadableTeam,
    db: Db,
    status: Annotated[
        Literal["open", "solved"],
        Query(description="`open`: unsolved, in Issue order (priority 5→1, none last; oldest first). "
              "`solved`: most recently solved first"),
    ] = "open",
) -> list[IssueOut]:  # fmt: skip
    return [IssueOut.of(i) for i in await service.list_issues(db, team.id, solved=status == "solved")]


@router.post(
    "", response_model=IssueOut, status_code=status.HTTP_201_CREATED, summary="Create an Issue", responses=ERRORS
)
async def create_issue(ctx: WritableTeam, db: Db, body: IssueCreateIn) -> IssueOut:
    """The caller becomes the owner."""
    issue = Issue(
        id=new_id("i"),
        team_id=ctx.team.id,
        title=body.title,
        priority=body.priority,
        owner_id=ctx.user.id,
        created_at=clock.now(),
    )
    db.add(issue)
    await db.flush()
    issue = await service.get_issue(db, ctx.team.id, issue.id)
    await db.commit()
    notify_changed(ctx.team.id, Resource.ISSUES)
    return IssueOut.of(issue)


@router.get("/{issue_id}", response_model=IssueOut, summary="One Issue", responses=ERRORS)
async def get_issue(team: ReadableTeam, db: Db, issue_id: IssueId) -> IssueOut:
    return IssueOut.of(await service.get_issue(db, team.id, issue_id))


@router.patch(
    "/{issue_id}",
    response_model=IssueOut,
    summary="Set priority",
    responses={**ERRORS, 409: {"description": "Already solved, or `expected_version` is stale"}},
)
async def update_issue(ctx: WritableTeam, db: Db, issue_id: IssueId, body: IssueUpdateIn) -> IssueOut:
    issue = await service.get_issue(db, ctx.team.id, issue_id, for_update=True)
    if issue.solved_at is not None:
        raise errors.conflict("A solved Issue can't be changed")
    if body.expected_version is not None and body.expected_version != issue.version:
        raise errors.version_conflict(issue.version)
    if issue.priority != body.priority:
        issue.priority = body.priority
        issue.version += 1
    await db.commit()
    notify_changed(ctx.team.id, Resource.ISSUES)
    return IssueOut.of(issue)


@router.post(
    "/{issue_id}/solve",
    response_model=IssueOut,
    summary="Solve with a note",
    responses={**ERRORS, 409: {"description": "Already solved"}},
)
async def solve_issue(ctx: WritableTeam, db: Db, issue_id: IssueId, body: IssueSolveIn) -> IssueOut:
    """Records the solve time and note. Solving while the team's meeting runs links the Issue to that meeting
    (it then appears in the meeting summary)."""
    issue = await service.get_issue(db, ctx.team.id, issue_id, for_update=True)
    if issue.solved_at is not None:
        raise errors.conflict("Issue is already solved")
    issue.solved_at = clock.now()
    issue.resolution_note = body.resolution_note
    issue.solved_in_meeting_id = service.active_meeting_id(ctx.team.id)  # evaluated inside the UPDATE
    issue.version += 1
    await db.flush()
    await db.refresh(issue)
    await db.commit()
    notify_changed(ctx.team.id, Resource.ISSUES, Resource.SCORECARD, Resource.MEETING)
    return IssueOut.of(issue)


@router.post(
    "/{issue_id}/todos",
    response_model=TodoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a follow-up To-Do",
    responses={**ERRORS, 422: {"description": "Invalid title, or the owner isn't one of the team's owners"}},
)
async def add_todo(ctx: WritableTeam, db: Db, issue_id: IssueId, body: IssueTodoIn) -> TodoOut:
    """Creates a To-Do linked to the Issue, due 7 days from today (company time). The owner must be one of
    the team's Admins or Team Members (see `owner_candidates` on GET /teams/{team_id})."""
    now = clock.now()
    issue = await service.get_issue(db, ctx.team.id, issue_id)
    todo = await todos.create_for_issue(
        db, team=ctx.team, issue=issue, title=body.title, owner_id=body.owner_id, now=now
    )
    await db.commit()
    notify_changed(ctx.team.id, Resource.TODOS, Resource.MEETING)
    return todos.to_out(todo, ctx.team, now)
