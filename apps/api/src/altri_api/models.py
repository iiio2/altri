"""ORM models. Integrity rules are declared here so the migration puts them in the database."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from altri_api.rules import GoalType, RockStatus

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

    company: Mapped[Company] = relationship(lazy="joined")

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


# --- Domain ---------------------------------------------------------------------------------------
# Every team-scoped child carries `team_id`, and links between them are composite foreign keys on
# (id, team_id), so the database itself refuses e.g. a To-Do in team A sourced from an Issue in team B.
# Ownership rules that span tables (owner is not an Observer and belongs to the team, or is an Admin) are
# enforced by the `altri_check_owner` trigger created in migration 0002.

TITLE_CHECK = "length(trim(title)) > 0 AND length(title) <= 200"
IDS = String(64)


class MeetingSection(StrEnum):
    SCORECARD = "scorecard"
    IDS = "ids"
    CONCLUDE = "conclude"

    @property
    def duration_seconds(self) -> int:
        return {"scorecard": 5 * 60, "ids": 60 * 60, "conclude": 10 * 60}[self.value]

    @property
    def label(self) -> str:
        return {"scorecard": "Scorecard", "ids": "IDS", "conclude": "Conclude"}[self.value]


def _values_check(column: str, e: type[StrEnum]) -> str:
    return f"{column} IN ({', '.join(f"'{m.value}'" for m in e)})"


def _str_enum(e: type[StrEnum]) -> Enum:
    return Enum(e, native_enum=False, create_constraint=False, length=32, values_callable=_enum_values)


class Measurable(Base):
    __tablename__ = "measurables"

    id: Mapped[str] = mapped_column(IDS, primary_key=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(Text)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    unit: Mapped[str] = mapped_column(Text)
    goal_type: Mapped[GoalType] = mapped_column(_str_enum(GoalType))
    goal_value: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))
    goal_min: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))
    goal_max: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))
    position: Mapped[int] = mapped_column(Integer, server_default="0")

    owner: Mapped[User] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("id", "team_id", name="uq_measurables_id_team_id"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint(_values_check("goal_type", GoalType), name="goal_type_valid"),
        CheckConstraint(
            "(goal_type = 'between' AND goal_value IS NULL AND goal_min IS NOT NULL AND goal_max IS NOT NULL"
            " AND goal_min <= goal_max)"
            " OR (goal_type <> 'between' AND goal_value IS NOT NULL AND goal_min IS NULL AND goal_max IS NULL)",
            name="goal_shape",
        ),
    )


class Score(Base):
    """One Measurable's value for one week. Weeks are named by their Monday in company time."""

    __tablename__ = "scores"

    measurable_id: Mapped[str] = mapped_column(ForeignKey("measurables.id", ondelete="CASCADE"), primary_key=True)
    week_start: Mapped[date] = mapped_column(Date, primary_key=True)
    value: Mapped[Decimal] = mapped_column(Numeric(16, 4))
    # Bumped on every write; lets clients opt into lost-update protection.
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (
        CheckConstraint("extract(isodow FROM week_start) = 1", name="week_start_is_monday"),
        CheckConstraint("value <> 'NaN'::numeric", name="value_is_number"),
        CheckConstraint("version > 0", name="version_positive"),
    )


class Rock(Base):
    __tablename__ = "rocks"

    id: Mapped[str] = mapped_column(IDS, primary_key=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"), index=True)
    title: Mapped[str] = mapped_column(Text)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    quarter: Mapped[str] = mapped_column(String(7))
    # The seeded status. The displayed status is computed (rules.rock_status) from this and the Milestones.
    status: Mapped[RockStatus] = mapped_column(_str_enum(RockStatus))

    owner: Mapped[User] = relationship(lazy="joined")
    milestones: Mapped[list[Milestone]] = relationship(
        order_by="(Milestone.due_date, Milestone.id)", lazy="selectin", viewonly=True
    )

    __table_args__ = (
        UniqueConstraint("id", "team_id", name="uq_rocks_id_team_id"),
        CheckConstraint(TITLE_CHECK, name="title_valid"),
        CheckConstraint(r"quarter ~ '^\d{4}-Q[1-4]$'", name="quarter_format"),
        CheckConstraint(_values_check("status", RockStatus), name="status_valid"),
    )


class Milestone(Base):
    __tablename__ = "milestones"

    id: Mapped[str] = mapped_column(IDS, primary_key=True)
    rock_id: Mapped[str] = mapped_column(ForeignKey("rocks.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(Text)
    due_date: Mapped[date] = mapped_column(Date)
    done: Mapped[bool] = mapped_column(Boolean, server_default="false")

    __table_args__ = (CheckConstraint(TITLE_CHECK, name="title_valid"),)


class Meeting(Base):
    """A Level 10 Meeting. The row is the single source of truth for live meeting state (section, timer)."""

    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(IDS, primary_key=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"), index=True)
    facilitator_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    section: Mapped[MeetingSection] = mapped_column(_str_enum(MeetingSection))
    section_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # The last closed week at start time: the week the Scorecard section reviews.
    scorecard_week: Mapped[date] = mapped_column(Date)

    facilitator: Mapped[User] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("id", "team_id", name="uq_meetings_id_team_id"),
        CheckConstraint(_values_check("section", MeetingSection), name="section_valid"),
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="ends_after_start"),
        CheckConstraint("section_started_at >= started_at", name="section_after_start"),
        CheckConstraint("extract(isodow FROM scorecard_week) = 1", name="scorecard_week_is_monday"),
        # One active meeting per team.
        Index("uq_meetings_active_per_team", "team_id", unique=True, postgresql_where=text("ended_at IS NULL")),
    )


class MeetingAttendee(Base):
    __tablename__ = "meeting_attendees"

    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True, index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(lazy="joined")


class MeetingRating(Base):
    __tablename__ = "meeting_ratings"

    meeting_id: Mapped[str] = mapped_column(IDS, primary_key=True)
    user_id: Mapped[str] = mapped_column(IDS, primary_key=True)
    rating: Mapped[int] = mapped_column(SmallInteger)
    rated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # Only attendees rate. Observers are refused by the `altri_check_rater` trigger.
        ForeignKeyConstraint(
            ["meeting_id", "user_id"],
            ["meeting_attendees.meeting_id", "meeting_attendees.user_id"],
            name="fk_meeting_ratings_attendee",
            ondelete="CASCADE",
        ),
        CheckConstraint("rating BETWEEN 1 AND 10", name="rating_range"),
    )


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[str] = mapped_column(IDS, primary_key=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"), index=True)
    title: Mapped[str] = mapped_column(Text)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    priority: Mapped[int | None] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    solved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    solved_in_meeting_id: Mapped[str | None] = mapped_column(IDS)
    # Where the Issue came from (at most one): an off-track Score, an off-track Rock or an overdue To-Do.
    source_measurable_id: Mapped[str | None] = mapped_column(IDS)
    source_week_start: Mapped[date | None] = mapped_column(Date)
    source_rock_id: Mapped[str | None] = mapped_column(IDS)
    source_todo_id: Mapped[str | None] = mapped_column(IDS)
    version: Mapped[int] = mapped_column(Integer, server_default="1")

    owner: Mapped[User] = relationship(lazy="joined")
    source_measurable: Mapped[Measurable | None] = relationship(
        lazy="joined",
        viewonly=True,
        foreign_keys=[source_measurable_id],
        primaryjoin="Issue.source_measurable_id == Measurable.id",
    )
    source_rock: Mapped[Rock | None] = relationship(
        lazy="joined",
        viewonly=True,
        foreign_keys=[source_rock_id],
        primaryjoin="Issue.source_rock_id == Rock.id",
    )
    source_todo: Mapped[Todo | None] = relationship(
        lazy="joined", viewonly=True, foreign_keys=[source_todo_id], primaryjoin="Issue.source_todo_id == Todo.id",
    )  # fmt: skip

    __table_args__ = (
        UniqueConstraint("id", "team_id", name="uq_issues_id_team_id"),
        ForeignKeyConstraint(
            ["source_measurable_id", "team_id"], ["measurables.id", "measurables.team_id"],
            name="fk_issues_source_measurable", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_rock_id", "team_id"], ["rocks.id", "rocks.team_id"],
            name="fk_issues_source_rock", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_todo_id", "team_id"], ["todos.id", "todos.team_id"],
            name="fk_issues_source_todo", ondelete="RESTRICT", use_alter=True,
        ),
        ForeignKeyConstraint(
            ["solved_in_meeting_id", "team_id"], ["meetings.id", "meetings.team_id"],
            name="fk_issues_solved_in_meeting", ondelete="RESTRICT",
        ),
        CheckConstraint(TITLE_CHECK, name="title_valid"),
        CheckConstraint("priority IS NULL OR priority BETWEEN 1 AND 5", name="priority_range"),
        CheckConstraint("(solved_at IS NULL) = (resolution_note IS NULL)", name="solved_has_note"),
        CheckConstraint(
            "resolution_note IS NULL OR (length(trim(resolution_note)) > 0 AND length(resolution_note) <= 2000)",
            name="resolution_note_valid",
        ),
        CheckConstraint("solved_in_meeting_id IS NULL OR solved_at IS NOT NULL", name="meeting_only_when_solved"),
        CheckConstraint("(source_measurable_id IS NULL) = (source_week_start IS NULL)", name="score_source_pair"),
        CheckConstraint(
            "source_week_start IS NULL OR extract(isodow FROM source_week_start) = 1", name="source_week_is_monday"
        ),
        CheckConstraint("num_nonnulls(source_measurable_id, source_rock_id, source_todo_id) <= 1", name="one_source"),
        CheckConstraint("version > 0", name="version_positive"),
        # "No duplicate Issues": at most one unsolved Issue per source. Make it an Issue relies on these.
        Index(
            "uq_issues_open_per_score", "source_measurable_id", "source_week_start", unique=True,
            postgresql_where=text("solved_at IS NULL AND source_measurable_id IS NOT NULL"),
        ),
        Index(
            "uq_issues_open_per_rock", "source_rock_id", unique=True,
            postgresql_where=text("solved_at IS NULL AND source_rock_id IS NOT NULL"),
        ),
        Index(
            "uq_issues_open_per_todo", "source_todo_id", unique=True,
            postgresql_where=text("solved_at IS NULL AND source_todo_id IS NOT NULL"),
        ),
    )  # fmt: skip


class Todo(Base):
    __tablename__ = "todos"

    id: Mapped[str] = mapped_column(IDS, primary_key=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"), index=True)
    title: Mapped[str] = mapped_column(Text)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    due_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_issue_id: Mapped[str | None] = mapped_column(IDS, index=True)
    created_in_meeting_id: Mapped[str | None] = mapped_column(IDS, index=True)

    owner: Mapped[User] = relationship(lazy="joined")
    source_issue: Mapped[Issue | None] = relationship(
        lazy="joined", viewonly=True, foreign_keys=[source_issue_id], primaryjoin="Todo.source_issue_id == Issue.id"
    )

    __table_args__ = (
        UniqueConstraint("id", "team_id", name="uq_todos_id_team_id"),
        ForeignKeyConstraint(
            ["source_issue_id", "team_id"], ["issues.id", "issues.team_id"],
            name="fk_todos_source_issue", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["created_in_meeting_id", "team_id"], ["meetings.id", "meetings.team_id"],
            name="fk_todos_created_in_meeting", ondelete="RESTRICT",
        ),
        CheckConstraint(TITLE_CHECK, name="title_valid"),
    )  # fmt: skip
