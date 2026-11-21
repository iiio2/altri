from fastapi import APIRouter
from pydantic import Field

from altri_api import clock
from altri_api.auth import service as auth_service
from altri_api.auth.deps import CurrentUser, Db, ReadableTeam
from altri_api.auth.schemas import TeamOut, UserOut
from altri_api.calendar import current_week_start, last_closed_week_start, local_date, quarter_label
from altri_api.errors import COMMON_ERRORS
from altri_api.models import Team
from altri_api.scorecard.service import tz_of
from altri_api.teams import service

router = APIRouter(prefix="/teams", tags=["teams"])


class TeamDetailOut(TeamOut):
    timezone: str = Field(description="Company time zone; weeks run Monday-Sunday in it")
    today: str = Field(description="Today's date in company time (from APP_NOW)")
    current_week: str
    last_closed_week: str
    current_quarter: str
    members: list[UserOut]
    owner_candidates: list[UserOut] = Field(
        description="Who can own To-Dos here: the team's Team Members plus Admins. Observers never own anything"
    )


@router.get("", response_model=list[TeamOut], summary="Teams the current user can open", responses=COMMON_ERRORS)
async def list_teams(user: CurrentUser, db: Db) -> list[Team]:
    return await auth_service.teams_for_user(db, user)


@router.get("/{team_id}", response_model=TeamDetailOut, summary="One team with its members", responses=COMMON_ERRORS)
async def get_team(team: ReadableTeam, db: Db) -> TeamDetailOut:
    tz = tz_of(team)
    now = clock.now()
    today = local_date(now, tz)
    return TeamDetailOut(
        id=team.id,
        name=team.name,
        timezone=team.company.timezone,
        today=today.isoformat(),
        current_week=current_week_start(now, tz).isoformat(),
        last_closed_week=last_closed_week_start(now, tz).isoformat(),
        current_quarter=quarter_label(today),
        members=[UserOut.model_validate(m) for m in await service.members(db, team)],
        owner_candidates=[UserOut.model_validate(u) for u in await service.owner_candidates(db, team)],
    )
