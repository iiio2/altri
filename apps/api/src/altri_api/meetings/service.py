"""Level 10 Meeting lifecycle. The `meetings` row is the single source of truth for live state.

Every transition locks the meeting row (SELECT ... FOR UPDATE), so a rating can't land after the end, and two
facilitator clicks apply in order. One active meeting per team is guaranteed by a partial unique index.
"""

from datetime import datetime

from psycopg import errors as pg_errors
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from altri_api import errors, rules
from altri_api.calendar import current_week_start, last_closed_week_start
from altri_api.meetings.schemas import (
    AGENDA,
    AttendeeOut,
    MeetingListItemOut,
    MeetingStateOut,
    MeetingSummaryOut,
    RatingOut,
    SummaryIssueOut,
    SummaryMeasurableOut,
    SummaryTodoOut,
)
from altri_api.models import (
    Issue,
    Meeting,
    MeetingAttendee,
    MeetingRating,
    MeetingSection,
    Score,
    Team,
    Todo,
    User,
)
from altri_api.schemas import UserRef, UserWithRole, as_number, new_id
from altri_api.scorecard.schemas import GoalOut
from altri_api.scorecard.service import goal_of, team_measurables, tz_of


async def get_meeting(db: AsyncSession, team_id: str, meeting_id: str, *, for_update: bool = False) -> Meeting:
    stmt = select(Meeting).where(Meeting.id == meeting_id, Meeting.team_id == team_id)
    if for_update:
        stmt = stmt.with_for_update(of=Meeting)
    meeting = await db.scalar(stmt, execution_options={"populate_existing": True})
    if meeting is None:
        raise errors.not_found("Meeting")
    return meeting


async def active_meeting(db: AsyncSession, team_id: str) -> Meeting | None:
    return await db.scalar(select(Meeting).where(Meeting.team_id == team_id, Meeting.ended_at.is_(None)))


async def _ratings(db: AsyncSession, meeting_id: str) -> list[MeetingRating]:
    stmt = select(MeetingRating).where(MeetingRating.meeting_id == meeting_id).order_by(MeetingRating.user_id)
    return list(await db.scalars(stmt))


async def _attendees(db: AsyncSession, meeting_id: str) -> list[MeetingAttendee]:
    stmt = (
        select(MeetingAttendee)
        .where(MeetingAttendee.meeting_id == meeting_id)
        .order_by(MeetingAttendee.joined_at, MeetingAttendee.user_id)
    )
    return list(await db.scalars(stmt))


def _average(ratings: list[MeetingRating]) -> float | None:
    avg = rules.meeting_rating(r.rating for r in ratings)
    return None if avg is None else float(avg)


async def build_state(db: AsyncSession, meeting: Meeting, now: datetime) -> MeetingStateOut:
    # A restart can put the app clock (APP_NOW + uptime) behind stored times; never show negative time.
    as_of = meeting.ended_at or now
    elapsed = max(0, int((as_of - meeting.section_started_at).total_seconds()))
    duration = meeting.section.duration_seconds
    ratings = await _ratings(db, meeting.id)
    return MeetingStateOut(
        id=meeting.id,
        team_id=meeting.team_id,
        status="ended" if meeting.ended_at else "active",
        facilitator=UserRef.model_validate(meeting.facilitator),
        started_at=meeting.started_at,
        ended_at=meeting.ended_at,
        scorecard_week=meeting.scorecard_week,
        agenda=AGENDA,
        section=meeting.section,
        section_started_at=meeting.section_started_at,
        section_duration_seconds=duration,
        section_elapsed_seconds=elapsed,
        over_time=elapsed > duration,
        server_now=now,
        attendees=[
            AttendeeOut(id=a.user.id, name=a.user.name, role=a.user.role, joined_at=a.joined_at)
            for a in await _attendees(db, meeting.id)
        ],
        ratings=[RatingOut(user_id=r.user_id, rating=r.rating) for r in ratings],
        average_rating=_average(ratings),
    )


async def list_meetings(db: AsyncSession, team_id: str) -> list[MeetingListItemOut]:
    meetings = await db.scalars(select(Meeting).where(Meeting.team_id == team_id).order_by(Meeting.started_at.desc()))
    return [
        MeetingListItemOut(
            id=m.id,
            status="ended" if m.ended_at else "active",
            facilitator=UserRef.model_validate(m.facilitator),
            started_at=m.started_at,
            ended_at=m.ended_at,
            average_rating=_average(await _ratings(db, m.id)),
        )
        for m in meetings
    ]


async def _add_attendee(db: AsyncSession, meeting: Meeting, user: User, now: datetime) -> None:
    stmt = pg_insert(MeetingAttendee).values(
        meeting_id=meeting.id, user_id=user.id, joined_at=max(now, meeting.started_at)
    )
    await db.execute(stmt.on_conflict_do_nothing(index_elements=["meeting_id", "user_id"]))


async def start(db: AsyncSession, *, team: Team, user: User, now: datetime) -> Meeting:
    """Start a meeting with `user` as facilitator (and first attendee). 409 if one is already running."""
    meeting = Meeting(
        id=new_id("mt"),
        team_id=team.id,
        facilitator_id=user.id,
        started_at=now,
        section=MeetingSection.SCORECARD,
        section_started_at=now,
        scorecard_week=last_closed_week_start(now, tz_of(team)),
    )
    try:
        # Savepoint: on conflict only the INSERT is undone; the session and its loaded objects stay usable.
        async with db.begin_nested():
            db.add(meeting)
    except IntegrityError as exc:
        if not isinstance(exc.orig, pg_errors.UniqueViolation):
            raise
        running = await active_meeting(db, team.id)
        detail = {"message": "This team already has a meeting running", "meeting_id": running and running.id}
        raise errors.conflict(detail) from exc
    await _add_attendee(db, meeting, user, now)
    return await get_meeting(db, team.id, meeting.id)


def _require_active(meeting: Meeting) -> None:
    if meeting.ended_at is not None:
        raise errors.conflict("The meeting has ended")


def _require_facilitator(meeting: Meeting, user: User) -> None:
    if meeting.facilitator_id != user.id:
        raise errors.forbidden("Only the facilitator can do this")


async def join(db: AsyncSession, *, team: Team, meeting_id: str, user: User, now: datetime) -> Meeting:
    meeting = await get_meeting(db, team.id, meeting_id, for_update=True)
    _require_active(meeting)
    await _add_attendee(db, meeting, user, now)
    return meeting


async def set_section(
    db: AsyncSession, *, team: Team, meeting_id: str, user: User, section: MeetingSection, now: datetime
) -> tuple[Meeting, bool]:
    """Move to `section` (forward or back). Returns (meeting, changed). Re-sending the current section is a no-op,
    so a double click can't skip a section or reset the timer."""
    meeting = await get_meeting(db, team.id, meeting_id, for_update=True)
    _require_facilitator(meeting, user)
    _require_active(meeting)
    if meeting.section == section:
        return meeting, False
    meeting.section = section
    meeting.section_started_at = max(now, meeting.started_at)
    await db.flush()
    return meeting, True


async def rate(db: AsyncSession, *, team: Team, meeting_id: str, user: User, rating: int, now: datetime) -> Meeting:
    """Attending Admins and Team Members rate 1-10 during Conclude, and may change it until the end."""
    meeting = await get_meeting(db, team.id, meeting_id, for_update=True)
    _require_active(meeting)
    if meeting.section != MeetingSection.CONCLUDE:
        raise errors.conflict("Ratings open in the Conclude section")
    attendee = await db.get(MeetingAttendee, (meeting.id, user.id))
    if attendee is None:
        raise errors.conflict("Join the meeting before rating it")
    stmt = pg_insert(MeetingRating).values(meeting_id=meeting.id, user_id=user.id, rating=rating, rated_at=now)
    stmt = stmt.on_conflict_do_update(
        index_elements=["meeting_id", "user_id"],
        set_={"rating": stmt.excluded.rating, "rated_at": stmt.excluded.rated_at},
    )
    await db.execute(stmt)
    return meeting


async def end(db: AsyncSession, *, team: Team, meeting_id: str, user: User, now: datetime) -> Meeting:
    meeting = await get_meeting(db, team.id, meeting_id, for_update=True)
    _require_facilitator(meeting, user)
    _require_active(meeting)
    meeting.ended_at = max(now, meeting.section_started_at)
    await db.flush()
    return meeting


async def build_summary(db: AsyncSession, meeting: Meeting) -> MeetingSummaryOut:
    """Computed from live data: Scores and the meeting's links (Issues solved / To-Dos created in it).

    Statuses are evaluated as of the meeting's start, so the reviewed week is always a closed week.
    See the decision record for how this would become an immutable snapshot.
    """
    if meeting.ended_at is None:
        raise errors.conflict("The meeting hasn't ended yet")
    team = await db.get_one(Team, meeting.team_id)
    week = meeting.scorecard_week
    current = current_week_start(meeting.started_at, tz_of(team))

    measurables = await team_measurables(db, team.id)
    score_rows = await db.execute(
        select(Score.measurable_id, Score.value).where(
            Score.measurable_id.in_([m.id for m in measurables]), Score.week_start == week
        )
    )
    scores = {measurable_id: value for measurable_id, value in score_rows}
    issues = await db.scalars(
        select(Issue).where(Issue.solved_in_meeting_id == meeting.id).order_by(Issue.solved_at, Issue.id)
    )
    todos = await db.scalars(
        select(Todo).where(Todo.created_in_meeting_id == meeting.id).order_by(Todo.created_at, Todo.id)
    )
    ratings = await _ratings(db, meeting.id)
    return MeetingSummaryOut(
        meeting_id=meeting.id,
        team_id=meeting.team_id,
        facilitator=UserRef.model_validate(meeting.facilitator),
        started_at=meeting.started_at,
        ended_at=meeting.ended_at,
        scorecard_week=week,
        measurables=[
            SummaryMeasurableOut(
                id=m.id,
                name=m.name,
                unit=m.unit,
                owner=UserRef.model_validate(m.owner),
                goal=GoalOut(
                    type=m.goal_type,
                    value=as_number(m.goal_value),
                    min=as_number(m.goal_min),
                    max=as_number(m.goal_max),
                ),
                value=as_number(scores.get(m.id)),
                status=rules.measurable_status(goal_of(m), scores.get(m.id), week, current),
            )
            for m in measurables
        ],
        issues_solved=[
            SummaryIssueOut(
                id=i.id,
                title=i.title,
                owner=UserRef.model_validate(i.owner),
                solved_at=i.solved_at,
                resolution_note=i.resolution_note,
            )
            for i in issues
            if i.solved_at is not None and i.resolution_note is not None
        ],
        todos_created=[
            SummaryTodoOut(
                id=t.id,
                title=t.title,
                owner=UserRef.model_validate(t.owner),
                due_date=t.due_date,
                source_issue_id=t.source_issue_id,
            )
            for t in todos
        ],
        attendees=[UserWithRole.model_validate(a.user) for a in await _attendees(db, meeting.id)],
        ratings=[RatingOut(user_id=r.user_id, rating=r.rating) for r in ratings],
        average_rating=_average(ratings),
    )
