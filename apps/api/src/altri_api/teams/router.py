from fastapi import APIRouter
from sqlalchemy import select

from altri_api.auth import service
from altri_api.auth.deps import CurrentUser, Db, ReadableTeam
from altri_api.auth.schemas import TeamOut, UserOut
from altri_api.models import Team, TeamMembership, User

router = APIRouter(prefix="/teams", tags=["teams"])

ERRORS = {
    401: {"description": "Missing, invalid or expired session"},
    403: {"description": "The team does not exist or the user cannot access it"},
}


class TeamDetailOut(TeamOut):
    members: list[UserOut]


@router.get("", response_model=list[TeamOut], summary="Teams the current user can open", responses=ERRORS)
async def list_teams(user: CurrentUser, db: Db) -> list[Team]:
    return await service.teams_for_user(db, user)


@router.get("/{team_id}", response_model=TeamDetailOut, summary="One team with its members", responses=ERRORS)
async def get_team(team: ReadableTeam, db: Db) -> TeamDetailOut:
    members = await db.scalars(
        select(User)
        .join(TeamMembership, TeamMembership.user_id == User.id)
        .where(TeamMembership.team_id == team.id)
        .order_by(User.name)
    )
    return TeamDetailOut(id=team.id, name=team.name, members=[UserOut.model_validate(m) for m in members])
