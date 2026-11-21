"""Schemas and validators shared by every feature router."""

import secrets
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import Path
from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

from altri_api.models import Role

ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


def id_path(description: str) -> object:
    return Path(pattern=ID_PATTERN, description=description)


def new_id(prefix: str) -> str:
    """Ids for rows created in the app. Seeded rows keep their seed ids (`i1`, `t12`, ...)."""
    return f"{prefix}_{secrets.token_hex(6)}"


class Input(BaseModel):
    """Request bodies reject unknown fields, so a typo or an injected `owner_id` fails loudly."""

    model_config = ConfigDict(extra="forbid")


class UserRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str


class UserWithRole(UserRef):
    role: Role


def _as_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


# Every timestamp leaves the API in UTC ("...Z"), whatever the database session's time zone is.
UtcDatetime = Annotated[datetime, AfterValidator(_as_utc)]


def as_number(value: Decimal | None) -> float | None:
    """Numeric(16, 4) columns are exact in the database; JSON carries them as plain numbers."""
    return None if value is None else float(value)
