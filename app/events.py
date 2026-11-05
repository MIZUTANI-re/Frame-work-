"""記録（Event）を残す。追記だけ。"""
from sqlalchemy.orm import Session

from app.models import Event


def record_event(db: Session, type: str, actor_id: int | None = None,
                 course_id: int | None = None, team_id: int | None = None,
                 **payload) -> None:
    """Event を 1 行足す（commit は呼び出し側）。"""
    db.add(Event(type=type, actor_id=actor_id, course_id=course_id,
                 team_id=team_id, payload=payload))
