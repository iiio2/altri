from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from altri_api.models import Issue
from altri_api.schemas import ID_PATTERN, Input, Note, Title, UserRef, UtcDatetime

Priority = Annotated[int, Field(ge=1, le=5, strict=True, description="5 is most urgent")]


class ScoreSourceOut(BaseModel):
    kind: Literal["score"] = "score"
    measurable_id: str
    measurable_name: str
    week_start: date


class RockSourceOut(BaseModel):
    kind: Literal["rock"] = "rock"
    rock_id: str
    rock_title: str


class TodoSourceOut(BaseModel):
    kind: Literal["todo"] = "todo"
    todo_id: str
    todo_title: str


IssueSource = Annotated[ScoreSourceOut | RockSourceOut | TodoSourceOut, Field(discriminator="kind")]


class IssueOut(BaseModel):
    id: str
    team_id: str
    title: str
    owner: UserRef
    priority: int | None
    created_at: UtcDatetime
    solved_at: UtcDatetime | None
    resolution_note: str | None
    solved_in_meeting_id: str | None
    source: IssueSource | None = Field(description="What the Issue was raised from; null when created directly")
    version: int = Field(description="Send back as `expected_version` to refuse overwriting someone else's change")

    @classmethod
    def of(cls, issue: Issue) -> IssueOut:
        source: ScoreSourceOut | RockSourceOut | TodoSourceOut | None = None
        if issue.source_measurable is not None and issue.source_week_start is not None:
            source = ScoreSourceOut(
                measurable_id=issue.source_measurable.id,
                measurable_name=issue.source_measurable.name,
                week_start=issue.source_week_start,
            )
        elif issue.source_rock is not None:
            source = RockSourceOut(rock_id=issue.source_rock.id, rock_title=issue.source_rock.title)
        elif issue.source_todo is not None:
            source = TodoSourceOut(todo_id=issue.source_todo.id, todo_title=issue.source_todo.title)
        return cls(
            id=issue.id,
            team_id=issue.team_id,
            title=issue.title,
            owner=UserRef.model_validate(issue.owner),
            priority=issue.priority,
            created_at=issue.created_at,
            solved_at=issue.solved_at,
            resolution_note=issue.resolution_note,
            solved_in_meeting_id=issue.solved_in_meeting_id,
            source=source,
            version=issue.version,
        )


class IssueCreateIn(Input):
    title: Title
    priority: Priority | None = None


class IssueUpdateIn(Input):
    priority: Priority | None = Field(description="1-5, or null to clear")
    expected_version: int | None = Field(
        default=None, ge=1, description="Optional lost-update guard: 409 if the Issue's version differs"
    )


class IssueSolveIn(Input):
    resolution_note: Note


class IssueTodoIn(Input):
    title: Title
    owner_id: str = Field(pattern=ID_PATTERN, description="One of the team's `owner_candidates`")
