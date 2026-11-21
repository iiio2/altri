from typing import Annotated

from fastapi import APIRouter, status
from sqlalchemy.ext.asyncio import AsyncSession

from altri_api import clock
from altri_api.auth.deps import CurrentUser, Db, ReadableTeam, WritableTeam
from altri_api.errors import COMMON_ERRORS
from altri_api.live.hub import hub
from altri_api.meetings import service
from altri_api.meetings.schemas import MeetingListItemOut, MeetingStateOut, MeetingSummaryOut, RatingIn, SectionIn
from altri_api.models import Meeting
from altri_api.schemas import id_path

router = APIRouter(prefix="/teams/{team_id}/meetings", tags=["meetings"])

MeetingId = Annotated[str, id_path("Meeting id, e.g. `mt1`")]
ERRORS = {**COMMON_ERRORS, 404: {"description": "No such meeting in this team"}}
STATE_ERRORS = {**ERRORS, 409: {"description": "The meeting has ended, or isn't in the right section"}}


async def publish_state(db: AsyncSession, meeting: Meeting) -> MeetingStateOut:
    """Build the authoritative state from the database and push it to every live client of the team."""
    state = await service.build_state(db, meeting, clock.now())
    hub.publish(meeting.team_id, {"type": "meeting", "meeting": state.model_dump(mode="json")})
    return state


@router.get("", response_model=list[MeetingListItemOut], summary="Meetings, newest first", responses=ERRORS)
async def list_meetings(team: ReadableTeam, db: Db) -> list[MeetingListItemOut]:
    return await service.list_meetings(db, team.id)


@router.post(
    "",
    response_model=MeetingStateOut,
    status_code=status.HTTP_201_CREATED,
    summary="Start the Level 10 Meeting",
    responses={**ERRORS, 409: {"description": "A meeting is already running (body has its `meeting_id`)"}},
)
async def start_meeting(ctx: WritableTeam, db: Db) -> MeetingStateOut:
    """The caller (Admin or Team Member) becomes the facilitator. One active meeting per team."""
    meeting = await service.start(db, team=ctx.team, user=ctx.user, now=clock.now())
    await db.commit()
    return await publish_state(db, meeting)


@router.get(
    "/active",
    response_model=MeetingStateOut | None,
    summary="The running meeting, or null",
    responses=ERRORS,
)
async def get_active_meeting(team: ReadableTeam, db: Db) -> MeetingStateOut | None:
    meeting = await service.active_meeting(db, team.id)
    return await service.build_state(db, meeting, clock.now()) if meeting else None


@router.get("/{meeting_id}", response_model=MeetingStateOut, summary="Meeting state", responses=ERRORS)
async def get_meeting(team: ReadableTeam, db: Db, meeting_id: MeetingId) -> MeetingStateOut:
    """Current section, server-owned timer, attendees and ratings. Same payload as the live `meeting` event."""
    return await service.build_state(db, await service.get_meeting(db, team.id, meeting_id), clock.now())


@router.post("/{meeting_id}/join", response_model=MeetingStateOut, summary="Join", responses=STATE_ERRORS)
async def join_meeting(team: ReadableTeam, user: CurrentUser, db: Db, meeting_id: MeetingId) -> MeetingStateOut:
    """Anyone who can read the team can join, Observers included. Idempotent."""
    meeting = await service.join(db, team=team, meeting_id=meeting_id, user=user, now=clock.now())
    await db.commit()
    return await publish_state(db, meeting)


@router.put(
    "/{meeting_id}/section",
    response_model=MeetingStateOut,
    summary="Move to a section (facilitator)",
    responses=STATE_ERRORS,
)
async def set_section(ctx: WritableTeam, db: Db, meeting_id: MeetingId, body: SectionIn) -> MeetingStateOut:
    """Only the facilitator. Naming the target section (rather than "next") makes retries and double clicks safe."""
    meeting, changed = await service.set_section(
        db, team=ctx.team, meeting_id=meeting_id, user=ctx.user, section=body.section, now=clock.now()
    )
    await db.commit()
    if not changed:
        return await service.build_state(db, meeting, clock.now())
    return await publish_state(db, meeting)


@router.put("/{meeting_id}/rating", response_model=MeetingStateOut, summary="Rate 1-10", responses=STATE_ERRORS)
async def rate_meeting(ctx: WritableTeam, db: Db, meeting_id: MeetingId, body: RatingIn) -> MeetingStateOut:
    """Attending Admins and Team Members, during Conclude. Re-rating replaces the earlier rating."""
    meeting = await service.rate(
        db, team=ctx.team, meeting_id=meeting_id, user=ctx.user, rating=body.rating, now=clock.now()
    )
    await db.commit()
    return await publish_state(db, meeting)


@router.post(
    "/{meeting_id}/end",
    response_model=MeetingSummaryOut,
    summary="End the meeting (facilitator)",
    responses=STATE_ERRORS,
)
async def end_meeting(ctx: WritableTeam, db: Db, meeting_id: MeetingId) -> MeetingSummaryOut:
    """Only the facilitator, at any time. Returns the summary; live clients get the ended state."""
    meeting = await service.end(db, team=ctx.team, meeting_id=meeting_id, user=ctx.user, now=clock.now())
    await db.commit()
    await publish_state(db, meeting)
    return await service.build_summary(db, meeting)


@router.get(
    "/{meeting_id}/summary",
    response_model=MeetingSummaryOut,
    summary="Summary of an ended meeting",
    responses={**ERRORS, 409: {"description": "The meeting is still running"}},
)
async def get_summary(team: ReadableTeam, db: Db, meeting_id: MeetingId) -> MeetingSummaryOut:
    """Scorecard statuses for the reviewed week, Issues solved and To-Dos created during the meeting,
    attendees and the rating. Works for any ended meeting, seeded ones included."""
    return await service.build_summary(db, await service.get_meeting(db, team.id, meeting_id))
