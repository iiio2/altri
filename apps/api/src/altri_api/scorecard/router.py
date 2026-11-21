from datetime import date
from typing import Annotated

from fastapi import APIRouter, Path, Query, Response, status

from altri_api import clock, rules
from altri_api.auth.deps import Db, ReadableTeam, WritableTeam
from altri_api.errors import COMMON_ERRORS
from altri_api.issues.schemas import IssueOut
from altri_api.issues.service import SCORE_SOURCE, find_open_issue
from altri_api.live.hub import Resource, notify_changed
from altri_api.schemas import as_number, id_path
from altri_api.scorecard import service
from altri_api.scorecard.schemas import CellOut, ScorecardOut, ScoreIn

router = APIRouter(prefix="/teams/{team_id}", tags=["scorecard"])

MeasurableId = Annotated[str, id_path("Measurable id, e.g. `m1`")]
WeekStart = Annotated[date, Path(description="Week start: the Monday (company time), e.g. `2026-11-02`")]
ERRORS = {**COMMON_ERRORS, 404: {"description": "No such Measurable in this team"}}


@router.get("/scorecard", response_model=ScorecardOut, summary="Measurables by week with statuses", responses=ERRORS)
async def get_scorecard(
    team: ReadableTeam,
    db: Db,
    weeks: Annotated[int, Query(ge=1, le=52, description="How many weeks, ending with the current one")] = 13,
) -> ScorecardOut:
    return await service.build_scorecard(db, team, clock.now(), weeks)


@router.put(
    "/measurables/{measurable_id}/scores/{week_start}",
    response_model=CellOut,
    summary="Enter, change or clear a score",
    responses={
        **ERRORS,
        409: {"description": "`expected_version` given and the score changed since (body has `current_version`)"},
        422: {"description": "Not a Monday, a future week, or an invalid value"},
    },
)
async def put_score(
    ctx: WritableTeam, db: Db, measurable_id: MeasurableId, week_start: WeekStart, body: ScoreIn
) -> CellOut:
    """Last save wins by default. Pass `expected_version` to get a 409 instead of overwriting a newer value."""
    now = clock.now()
    current = service.check_week(week_start, ctx.team, now)
    measurable = await service.get_measurable(db, ctx.team.id, measurable_id)
    score = await service.set_score(
        db,
        measurable=measurable,
        week=week_start,
        value=body.value,
        expected_version=body.expected_version,
        user=ctx.user,
        now=now,
    )
    await db.commit()
    notify_changed(ctx.team.id, Resource.SCORECARD)

    value = score.value if score else None
    open_issue = await find_open_issue(
        db, SCORE_SOURCE, {"source_measurable_id": measurable.id, "source_week_start": week_start}
    )
    return CellOut(
        measurable_id=measurable.id,
        week_start=week_start,
        value=as_number(value),
        status=rules.measurable_status(service.goal_of(measurable), value, week_start, current),
        version=score.version if score else 0,
        open_issue_id=open_issue.id if open_issue else None,
    )


@router.post(
    "/measurables/{measurable_id}/scores/{week_start}/issue",
    response_model=IssueOut,
    status_code=status.HTTP_201_CREATED,
    summary="Make it an Issue (idempotent)",
    responses={
        **ERRORS,
        200: {"model": IssueOut, "description": "An unsolved Issue already existed for this cell; it is returned"},
        409: {"description": "The cell is not off track"},
    },
)
async def make_it_an_issue(
    ctx: WritableTeam, db: Db, measurable_id: MeasurableId, week_start: WeekStart, response: Response
) -> IssueOut:
    """Creates an Issue titled with the Measurable and week, owned by the caller. If an unsolved Issue already
    exists for this Measurable and week, returns it with 200 instead. Safe under concurrent clicks."""
    measurable = await service.get_measurable(db, ctx.team.id, measurable_id)
    issue, created = await service.make_issue_from_score(
        db, team=ctx.team, measurable=measurable, week=week_start, user=ctx.user, now=clock.now()
    )
    await db.commit()
    if created:
        notify_changed(ctx.team.id, Resource.ISSUES, Resource.SCORECARD)
    else:
        response.status_code = status.HTTP_200_OK
    return IssueOut.of(issue)
