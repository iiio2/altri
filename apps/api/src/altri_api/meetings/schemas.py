from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from altri_api.models import MeetingSection
from altri_api.rules import ScoreStatus
from altri_api.schemas import Input, UserRef, UserWithRole, UtcDatetime
from altri_api.scorecard.schemas import GoalOut


class AgendaItemOut(BaseModel):
    section: MeetingSection
    label: str
    duration_seconds: int


AGENDA = [AgendaItemOut(section=s, label=s.label, duration_seconds=s.duration_seconds) for s in MeetingSection]


class AttendeeOut(UserWithRole):
    joined_at: UtcDatetime


class RatingOut(BaseModel):
    user_id: str
    rating: int


class MeetingStateOut(BaseModel):
    """Everything a client needs to render the meeting. Pushed over the live socket on every change.

    The server owns the timer: clients display `section_elapsed_seconds` advanced by their local clock from the
    moment they received `server_now`, so all browsers agree regardless of their own clock skew.
    """

    id: str
    team_id: str
    status: Literal["active", "ended"]
    facilitator: UserRef
    started_at: UtcDatetime
    ended_at: UtcDatetime | None
    scorecard_week: date = Field(description="The week the Scorecard section reviews (last closed week at start)")
    agenda: list[AgendaItemOut]
    section: MeetingSection
    section_started_at: UtcDatetime
    section_duration_seconds: int
    section_elapsed_seconds: int = Field(description="As of `server_now` (or of the end, once ended)")
    over_time: bool = Field(description="The section ran past its time box. Sections never advance on their own")
    server_now: UtcDatetime
    attendees: list[AttendeeOut]
    ratings: list[RatingOut]
    average_rating: float | None = Field(description="One decimal, half up; null when no one rated")


class MeetingListItemOut(BaseModel):
    id: str
    status: Literal["active", "ended"]
    facilitator: UserRef
    started_at: UtcDatetime
    ended_at: UtcDatetime | None
    average_rating: float | None


class SummaryMeasurableOut(BaseModel):
    id: str
    name: str
    unit: str
    owner: UserRef
    goal: GoalOut
    value: float | None
    status: ScoreStatus


class SummaryIssueOut(BaseModel):
    id: str
    title: str
    owner: UserRef
    solved_at: UtcDatetime
    resolution_note: str


class SummaryTodoOut(BaseModel):
    id: str
    title: str
    owner: UserRef
    due_date: date
    source_issue_id: str | None


class MeetingSummaryOut(BaseModel):
    meeting_id: str
    team_id: str
    facilitator: UserRef
    started_at: UtcDatetime
    ended_at: UtcDatetime
    scorecard_week: date
    measurables: list[SummaryMeasurableOut] = Field(description="Statuses for `scorecard_week`")
    issues_solved: list[SummaryIssueOut]
    todos_created: list[SummaryTodoOut]
    attendees: list[UserWithRole]
    ratings: list[RatingOut]
    average_rating: float | None


class SectionIn(Input):
    section: MeetingSection = Field(description="Section to move to. Moving to the current section is a no-op")


class RatingIn(Input):
    rating: Annotated[int, Field(ge=1, le=10, strict=True)]
