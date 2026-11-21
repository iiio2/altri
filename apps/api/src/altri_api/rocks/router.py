from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from altri_api import clock, errors, rules
from altri_api.auth.deps import Db, ReadableTeam, WritableTeam
from altri_api.calendar import local_date, quarter_label
from altri_api.errors import COMMON_ERRORS
from altri_api.issues import service as issues
from altri_api.issues.schemas import IssueOut
from altri_api.live.hub import Resource, notify_changed
from altri_api.models import Issue, Rock
from altri_api.schemas import UserRef, id_path
from altri_api.scorecard.service import tz_of

router = APIRouter(prefix="/teams/{team_id}/rocks", tags=["rocks"])

RockId = Annotated[str, id_path("Rock id, e.g. `r1`")]


class MilestoneOut(BaseModel):
    id: str
    title: str
    due_date: date
    done: bool
    past_due: bool = Field(description="Not done and due before today. Due today is not past due")


class RockOut(BaseModel):
    id: str
    title: str
    owner: UserRef
    quarter: str
    status: rules.RockStatus = Field(description="Computed: seeded status, or off_track if a Milestone is past due")
    seeded_status: rules.RockStatus
    progress_percent: int
    milestones: list[MilestoneOut]
    open_issue_id: str | None = Field(description="Unsolved Issue raised from this Rock, if any")


class RocksOut(BaseModel):
    quarter: str
    rocks: list[RockOut]


def rock_out(rock: Rock, today: date, open_issue_id: str | None) -> RockOut:
    return RockOut(
        id=rock.id,
        title=rock.title,
        owner=UserRef.model_validate(rock.owner),
        quarter=rock.quarter,
        status=rules.rock_status(rock.status, [(m.due_date, m.done) for m in rock.milestones], today),
        seeded_status=rock.status,
        progress_percent=rules.rock_progress(rock.status, [m.done for m in rock.milestones]),
        milestones=[
            MilestoneOut(
                id=m.id, title=m.title, due_date=m.due_date, done=m.done, past_due=not m.done and m.due_date < today
            )
            for m in rock.milestones
        ],
        open_issue_id=open_issue_id,
    )


@router.get("", response_model=RocksOut, summary="Rocks for a quarter (read-only)", responses=COMMON_ERRORS)
async def list_rocks(
    team: ReadableTeam,
    db: Db,
    quarter: Annotated[
        str | None, Query(pattern=r"^\d{4}-Q[1-4]$", description="e.g. `2026-Q4`; defaults to the current quarter")
    ] = None,
) -> RocksOut:
    today = local_date(clock.now(), tz_of(team))
    quarter = quarter or quarter_label(today)
    rocks = await db.scalars(select(Rock).where(Rock.team_id == team.id, Rock.quarter == quarter).order_by(Rock.id))
    open_issues = await _open_issues_by_rock(db, team.id)
    return RocksOut(quarter=quarter, rocks=[rock_out(r, today, open_issues.get(r.id)) for r in rocks])


async def _open_issues_by_rock(db: Db, team_id: str) -> dict[str, str]:
    rows = await db.execute(
        select(Issue.source_rock_id, Issue.id).where(
            Issue.team_id == team_id, Issue.solved_at.is_(None), Issue.source_rock_id.is_not(None)
        )
    )
    return {rock_id: issue_id for rock_id, issue_id in rows if rock_id is not None}


@router.post(
    "/{rock_id}/issue",
    response_model=IssueOut,
    status_code=status.HTTP_201_CREATED,
    summary="Make an off-track Rock an Issue (idempotent)",
    responses={
        **COMMON_ERRORS,
        200: {"model": IssueOut, "description": "An unsolved Issue already existed for this Rock"},
        404: {"description": "No such Rock in this team"},
        409: {"description": "The Rock is not off track"},
    },
)
async def make_it_an_issue(ctx: WritableTeam, db: Db, rock_id: RockId, response: Response) -> IssueOut:
    now = clock.now()
    rock = await db.scalar(select(Rock).where(Rock.id == rock_id, Rock.team_id == ctx.team.id))
    if rock is None:
        raise errors.not_found("Rock")
    source_values = {"source_rock_id": rock.id}
    today = local_date(now, tz_of(ctx.team))
    computed = rules.rock_status(rock.status, [(m.due_date, m.done) for m in rock.milestones], today)
    if computed is not rules.RockStatus.OFF_TRACK:
        existing = await issues.find_open_issue(db, issues.ROCK_SOURCE, source_values)
        if existing is None:
            raise errors.conflict(f"Only an off-track Rock can be made an Issue (this one is {computed.value})")
        issue, created = existing, False
    else:
        issue, created = await issues.create_issue_once(
            db,
            source=issues.ROCK_SOURCE,
            team_id=ctx.team.id,
            title=f"Off-track Rock: {rock.title}"[:200],
            owner_id=ctx.user.id,
            now=now,
            source_values=source_values,
        )
    await db.commit()
    if created:
        notify_changed(ctx.team.id, Resource.ISSUES, Resource.ROCKS)
    else:
        response.status_code = status.HTTP_200_OK
    return IssueOut.of(issue)
