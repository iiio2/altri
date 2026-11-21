from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from altri_api.models import Role, Team, TeamMembership, User


async def owner_candidates(db: AsyncSession, team: Team) -> list[User]:
    """Users who may own To-Dos and Issues in `team`: its Team Members, plus Admins (who act in every team).

    The same rule is enforced in the database by the `altri_check_owner` trigger.
    """
    is_member = exists().where(TeamMembership.team_id == team.id, TeamMembership.user_id == User.id)
    stmt = (
        select(User)
        .where(User.company_id == team.company_id, User.role != Role.OBSERVER)
        .where(or_(User.role == Role.ADMIN, is_member))
        .order_by(User.name, User.id)
    )
    return list(await db.scalars(stmt))


async def members(db: AsyncSession, team: Team) -> list[User]:
    stmt = (
        select(User)
        .join(TeamMembership, TeamMembership.user_id == User.id)
        .where(TeamMembership.team_id == team.id)
        .order_by(User.name, User.id)
    )
    return list(await db.scalars(stmt))
