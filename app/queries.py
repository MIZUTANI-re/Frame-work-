"""よく使う問い合わせ。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Enrollment, User


def find_user_by_name(db: Session, name: str) -> User | None:
    return db.scalar(select(User).where(User.name == name))


def students_of(db: Session, course_id: int) -> list[User]:
    """授業に参加している学生の一覧（参加が早い順）。"""
    return list(db.scalars(
        select(User).join(Enrollment, Enrollment.user_id == User.id)
        .where(Enrollment.course_id == course_id).order_by(User.id)))
