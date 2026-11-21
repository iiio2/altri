from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field

from altri_api.rules import GoalType, ScoreStatus
from altri_api.schemas import Input, UserRef

ScoreValue = Annotated[Decimal, Field(max_digits=16, decimal_places=4, allow_inf_nan=False)]


class GoalOut(BaseModel):
    type: GoalType
    value: float | None = Field(description="Target for at_least / at_most / exactly")
    min: float | None = Field(description="Lower bound for between (inclusive)")
    max: float | None = Field(description="Upper bound for between (inclusive)")


class CellOut(BaseModel):
    measurable_id: str
    week_start: date
    value: float | None
    status: ScoreStatus
    version: int = Field(description="0 when there is no score yet. Echo as `expected_version` for lost-update checks")
    open_issue_id: str | None = Field(description="The unsolved Issue raised from this cell, if any")


class MeasurableRowOut(BaseModel):
    id: str
    name: str
    unit: str
    owner: UserRef
    goal: GoalOut
    cells: list[CellOut] = Field(description="One per week in `weeks`, same order")


class ScorecardOut(BaseModel):
    current_week: date
    last_closed_week: date
    weeks: list[date] = Field(
        description="Week starts (Mondays, company time), oldest first, ending with the current week"
    )
    measurables: list[MeasurableRowOut]


class ScoreIn(Input):
    value: ScoreValue | None = Field(description="null clears the score")
    expected_version: int | None = Field(
        default=None,
        ge=0,
        description="Optional lost-update guard: the `version` you edited (0 = there was no score). "
        "Omit for last-save-wins",
    )
