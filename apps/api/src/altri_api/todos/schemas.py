from datetime import date

from pydantic import BaseModel, Field

from altri_api.models import Todo
from altri_api.rules import TODO_COMPLETION_TARGET_PERCENT, Completion
from altri_api.schemas import Input, UserRef, UtcDatetime


class IssueRef(BaseModel):
    id: str
    title: str


class TodoOut(BaseModel):
    id: str
    team_id: str
    title: str
    owner: UserRef
    due_date: date = Field(description="Calendar date in company time")
    created_at: UtcDatetime
    done_at: UtcDatetime | None
    overdue: bool = Field(description="Not done and due before today (company time)")
    source_issue: IssueRef | None
    created_in_meeting_id: str | None

    @classmethod
    def of(cls, todo: Todo, *, overdue: bool) -> TodoOut:
        src = todo.source_issue
        return cls(
            id=todo.id,
            team_id=todo.team_id,
            title=todo.title,
            owner=UserRef.model_validate(todo.owner),
            due_date=todo.due_date,
            created_at=todo.created_at,
            done_at=todo.done_at,
            overdue=overdue,
            source_issue=IssueRef(id=src.id, title=src.title) if src else None,
            created_in_meeting_id=todo.created_in_meeting_id,
        )


class CompletionOut(BaseModel):
    week_start: date
    due: int
    done: int = Field(description="Of those due, how many were done by the end of the week")
    rate_percent: int | None = Field(description="Whole percent, half up; null when nothing was due")
    meets_target: bool | None = Field(description="Exact ratio >= 90%; null when nothing was due")
    target_percent: int = TODO_COMPLETION_TARGET_PERCENT

    @classmethod
    def of(cls, week: date, completion: Completion | None) -> CompletionOut:
        if completion is None:
            return cls(week_start=week, due=0, done=0, rate_percent=None, meets_target=None)
        return cls(
            week_start=week,
            due=completion.due,
            done=completion.done,
            rate_percent=completion.rate_percent,
            meets_target=completion.meets_target,
        )


class TodoListOut(BaseModel):
    todos: list[TodoOut]
    last_closed_week: CompletionOut = Field(description="To-Do completion rate for the last closed week")


class TodoUpdateIn(Input):
    done: bool = Field(strict=True, description="true marks done (keeps the first done time); false undoes it")
