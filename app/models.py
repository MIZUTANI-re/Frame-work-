"""テーブルの定義（データ設計書 §2）。ステップ 1 は User・Course・Enrollment・Team・TeamMember・Event。"""
from datetime import datetime, timezone

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime

# 文字数の上限（String の長さと同じ。アプリでも確かめる）
USER_NAME_MAX = 100
COURSE_NAME_MAX = 200
TEAM_NAME_MAX = 100


def now() -> datetime:
    """いまの時刻（UTC のタイムゾーン付き）。"""
    return datetime.now(timezone.utc)


# ※ 未習: SQLAlchemy の ORM — テーブルを Python のクラスとして書き、行をオブジェクトとして扱う仕組み
class User(Base):
    """利用者。name はログイン名を兼ねるので全体で重複不可。"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(USER_NAME_MAX), unique=True)
    role: Mapped[str] = mapped_column(String(10))  # "teacher" か "student"
    password_hash: Mapped[str] = mapped_column(String(255))  # 平文は持たない
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    # ログインの総当たり対策（メモリではなく DB に持つ。M-6）
    failed_logins: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    # ログアウトで上げる。Cookie に入れた版と違えば、前の Cookie は使えない
    session_version: Mapped[int] = mapped_column(default=0)


class Course(Base):
    """授業。invite_code は参加用の 6 文字。"""
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(COURSE_NAME_MAX))
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    invite_code: Mapped[str] = mapped_column(String(6), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)

    teacher: Mapped[User] = relationship()
    teams: Mapped[list["Team"]] = relationship(
        back_populates="course", cascade="all, delete-orphan", order_by="Team.id"
    )


class Enrollment(Base):
    """学生が授業に参加している、という関係。"""
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("course_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    joined_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)

    user: Mapped[User] = relationship()
    course: Mapped[Course] = relationship()


class Team(Base):
    """班。"""
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    name: Mapped[str] = mapped_column(String(TEAM_NAME_MAX))

    course: Mapped[Course] = relationship(back_populates="teams")
    members: Mapped[list["TeamMember"]] = relationship(
        back_populates="team", cascade="all, delete-orphan"
    )


class TeamMember(Base):
    """班のメンバー。
    course_id を持たせて (course_id, user_id) を重複不可にし、
    「1 つの授業で学生が入る班は 1 つだけ」を DB で守る（D-026）。"""
    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("course_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    team: Mapped[Team] = relationship(back_populates="members")
    user: Mapped[User] = relationship()


class Event(Base):
    """記録。追記だけで、書き換え・削除はしない。
    班を消しても記録は残すため、actor_id などは外部キーにしていない（D-025）。"""
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    actor_id: Mapped[int | None] = mapped_column(default=None)
    course_id: Mapped[int | None] = mapped_column(default=None)
    team_id: Mapped[int | None] = mapped_column(default=None)
    board_id: Mapped[int | None] = mapped_column(default=None)
    type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
