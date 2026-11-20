"""ORM models. Integrity rules are declared here so the migration puts them in the database."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, MetaData, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Deterministic constraint names so migrations can refer to them.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Role(StrEnum):
    ADMIN = "admin"
    TEAM_MEMBER = "team_member"
    OBSERVER = "observer"

    @property
    def is_admin(self) -> bool:
        return self is Role.ADMIN

    @property
    def can_write(self) -> bool:
        """Admins and Team Members change data; Observers only read."""
        return self is not Role.OBSERVER


def _enum_values(e: type[StrEnum]) -> list[str]:
    return [m.value for m in e]


ROLE_VALUES = ", ".join(f"'{r.value}'" for r in Role)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(Text)

    __table_args__ = (CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),)


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(Text)

    __table_args__ = (CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text)
    role: Mapped[Role] = mapped_column(
        # Stored as plain text; the CHECK below is the database-level guard.
        Enum(Role, native_enum=False, create_constraint=False, length=32, values_callable=_enum_values)
    )

    teams: Mapped[list[Team]] = relationship(secondary="team_memberships", order_by=Team.name, viewonly=True)

    __table_args__ = (
        CheckConstraint(f"role IN ({ROLE_VALUES})", name="role_valid"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        # Emails are stored normalized; the check keeps it that way regardless of the writer.
        CheckConstraint(r"email = lower(trim(email)) AND email ~ '^[^@\s]+@[^@\s]+$'", name="email_normalized"),
        Index("uq_users_email", "email", unique=True),
    )


class TeamMembership(Base):
    __tablename__ = "team_memberships"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True, index=True)


class AuthSession(Base):
    """A server-side login session. Only a SHA-256 hash of the bearer token is stored."""

    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="token_hash_sha256_hex"),
    )
