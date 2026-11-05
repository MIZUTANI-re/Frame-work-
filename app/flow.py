"""授業の流れ（F-06・F-17 の「並べる・配る」まで）の処理。権限と決まりの確認は app/security.py。"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.events import record_event
from app.framework_defs import FRAMEWORKS
from app.models import Board, Course, CourseFramework, Team, User, now


# ※ 未習: 人気順（よく使われている順）— 選ばれた回数を数えて、多い順に並べる
def usage_counts(db: Session) -> dict[str, int]:
    """フレームワークごとの、授業で選ばれた回数（全部の授業。D-022）。"""
    rows = db.execute(select(CourseFramework.framework_key, func.count())
                      .group_by(CourseFramework.framework_key))
    return {key: n for key, n in rows}


def flow_items(db: Session, course_id: int) -> list[CourseFramework]:
    return list(db.scalars(select(CourseFramework).where(CourseFramework.course_id == course_id)
                           .order_by(CourseFramework.position, CourseFramework.id)))


def add_to_flow(db: Session, course: Course, key: str, query: str, actor: User) -> CourseFramework | None:
    """流れの最後に足す。すでに入っていれば何もしない（None）。"""
    items = flow_items(db, course.id)
    if any(i.framework_key == key for i in items):
        return None
    phases = [p["key"] for p in FRAMEWORKS[key]["phases"]]
    item = CourseFramework(course_id=course.id, framework_key=key, phases=phases,
                           position=len(items) + 1, status="waiting", created_by=actor.id)
    db.add(item)
    record_event(db, "framework.selected", actor_id=actor.id, course_id=course.id,
                 framework_key=key, query=query, phases=phases)
    return item


def renumber(items: list[CourseFramework]) -> None:
    for n, item in enumerate(items, start=1):
        item.position = n


def move(db: Session, course_id: int, item: CourseFramework, direction: str) -> bool:
    """1 つ上（up）か下（down）へ。入れ替える相手も始まっていないときだけ動かす。"""
    items = flow_items(db, course_id)
    i = items.index(next(x for x in items if x.id == item.id))
    j = i - 1 if direction == "up" else i + 1
    if not 0 <= j < len(items) or items[i].status != "waiting" or items[j].status != "waiting":
        return False
    items[i], items[j] = items[j], items[i]
    renumber(items)
    return True


def remove(db: Session, course_id: int, item: CourseFramework) -> None:
    db.delete(item)
    db.flush()
    renumber(flow_items(db, course_id))


def _make_board(db: Session, team: Team, item: CourseFramework, actor: User) -> Board:
    board = Board(team_id=team.id, course_framework_id=item.id, framework_key=item.framework_key,
                  chosen_by="teacher", created_by=actor.id, phase=item.phases[0])
    db.add(board)
    db.flush()
    record_event(db, "board.created", actor_id=actor.id, course_id=team.course_id, team_id=team.id,
                 board_id=board.id, framework_key=item.framework_key, chosen_by="teacher")
    return board


def deal(db: Session, course: Course, actor: User) -> int:
    """全部の班に、流れのフレームワークごとのボードを作る（まだ無いものだけ）。作った数を返す。
    まだ誰も始めていなければ、① を active、ほかを waiting にする。"""
    items = flow_items(db, course.id)
    if items and all(i.status == "waiting" for i in items):
        items[0].status = "active"
        items[0].started_at = now()
    made = 0
    for team in course.teams:
        have = set(db.scalars(select(Board.course_framework_id).where(Board.team_id == team.id)))
        for item in items:
            if item.id not in have:
                _make_board(db, team, item, actor)
                made += 1
    return made


def give_boards_to_new_team(db: Session, team: Team, actor: User) -> None:
    """あとから作った班にも、すでに配られた流れのボードを作る。
    「配られた」＝その行のボードがどこかの班にすでにある。まだ配っていなければ何もしない。"""
    for item in flow_items(db, team.course_id):
        dealt = db.scalar(select(Board.id).where(Board.course_framework_id == item.id).limit(1))
        if dealt is not None:
            _make_board(db, team, item, actor)


def boards_of_team(db: Session, team_id: int) -> list[Board]:
    """班のボード（授業の流れの順）。"""
    return list(db.scalars(select(Board).join(CourseFramework, CourseFramework.id == Board.course_framework_id)
                           .where(Board.team_id == team_id)
                           .order_by(CourseFramework.position, Board.id)))
