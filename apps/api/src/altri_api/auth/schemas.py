from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from altri_api.models import Role


def _normalize_email(v: str) -> str:
    v = v.strip().lower()
    local, sep, domain = v.partition("@")
    if not (sep and local and domain) or any(c.isspace() for c in v):
        raise ValueError("must be an email address")
    return v


# Not pydantic.EmailStr: it rejects reserved TLDs such as `.test`, which the seed users use.
Email = Annotated[str, Field(min_length=3, max_length=254), AfterValidator(_normalize_email)]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: str
    role: Role


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Email


class MeOut(BaseModel):
    user: UserOut
    teams: list[TeamOut] = Field(description="Teams the user can open: every team for Admins, own teams otherwise")
    can_write: bool = Field(description="False for Observers. Informational only; the server enforces it")


class LoginOut(MeOut):
    access_token: str = Field(description="Also set as an HttpOnly cookie. Use as `Authorization: Bearer <token>`")
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - OAuth token type, not a secret
    expires_at: datetime
