"""付箋の操作（足す・動かす・消す）。DB に保存し、記録（Event）を残す。権限の確認は app/security.py。
配信（部屋の人に送る）は呼び出し側が、commit のあとにやる。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.events import record_event
from app.framework_defs import FRAMEWORKS
from app.models import NOTE_TEXT_MAX, Board, Note, Team, User, now
from app.security import BoardActionDenied, can_write_board, check_note_owner, check_note_write

# 作成者ごとの付箋の色（見本 v2 の 4 色。ユーザー番号で決まるので、同じ人はいつも同じ色）
NOTE_COLORS = ("#fff4b8", "#d8f0ff", "#ffe0ec", "#dff5d8")


def note_color(user_id: int) -> str:
    return NOTE_COLORS[user_id % len(NOTE_COLORS)]


def note_json(note: Note) -> dict:
    """画面に送る付箋。見せてよい項目だけ。"""
    return {"id": note.id, "zone_key": note.zone_key, "x": note.x, "y": note.y,
            "text": note.text, "author_id": note.author_id, "author_name": note.author.name,
            "color": note_color(note.author_id)}


def zone_keys(board: Board) -> list[str]:
    return [z["key"] for z in FRAMEWORKS[board.framework_key].get("zones", [])]


def notes_of_board(db: Session, board_id: int) -> list[Note]:
    """消されていない付箋（書かれた順）。"""
    return list(db.scalars(select(Note).where(Note.board_id == board_id, Note.deleted_at.is_(None))
                           .order_by(Note.id)))


def _event(db: Session, type: str, board: Board, user: User, **payload) -> None:
    team = db.get(Team, board.team_id)
    record_event(db, type, actor_id=user.id, course_id=team.course_id, team_id=team.id,
                 board_id=board.id, **payload)


def add_note(db: Session, board: Board, user: User, zone_key, text) -> dict:
    check_note_write(db, user, board)
    text = text.strip() if isinstance(text, str) else ""
    if not text or len(text) > NOTE_TEXT_MAX or zone_key not in zone_keys(board):
        raise BoardActionDenied("invalid")
    note = Note(board_id=board.id, author_id=user.id, zone_key=zone_key, text=text)
    db.add(note)
    db.flush()
    _event(db, "note.created", board, user, note_id=note.id, zone_key=zone_key, text=text)
    db.commit()
    return {"type": "note.created", "note": note_json(note)}


def move_note(db: Session, board: Board, user: User, note_id, zone_key) -> dict:
    check_note_write(db, user, board)
    note = db.get(Note, note_id) if isinstance(note_id, int) else None
    check_note_owner(user, board, note)
    if zone_key not in zone_keys(board):
        raise BoardActionDenied("invalid")
    _event(db, "note.moved", board, user, note_id=note.id, from_zone=note.zone_key, to_zone=zone_key)
    note.zone_key = zone_key
    note.updated_at = now()
    db.commit()
    return {"type": "note.moved", "note": note_json(note)}


def delete_note(db: Session, board: Board, user: User, note_id) -> dict:
    check_note_write(db, user, board)
    note = db.get(Note, note_id) if isinstance(note_id, int) else None
    check_note_owner(user, board, note)
    note.deleted_at = now()  # 行は残す（D-031）
    _event(db, "note.deleted", board, user, note_id=note.id, zone_key=note.zone_key)
    db.commit()
    return {"type": "note.deleted", "id": note.id}


def apply_action(db: Session, board: Board, user: User, data) -> dict:
    """画面から来た 1 つの操作を実行し、部屋に配るメッセージを返す。"""
    kind = data.get("type") if isinstance(data, dict) else None
    if kind == "note.add":
        return add_note(db, board, user, data.get("zone_key"), data.get("text"))
    if kind == "note.move":
        return move_note(db, board, user, data.get("id"), data.get("zone_key"))
    if kind == "note.delete":
        return delete_note(db, board, user, data.get("id"))
    raise BoardActionDenied("invalid")


def snapshot(db: Session, board: Board, user: User) -> dict:
    """ボードの全部（つないだとき・つなぎ直したときに送る）。writable はいまの権限。"""
    return {"type": "snapshot", "board_id": board.id, "writable": can_write_board(db, user, board),
            "me": user.id, "notes": [note_json(n) for n in notes_of_board(db, board.id)]}
