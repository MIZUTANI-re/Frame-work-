"""ステップ 2b：ゾーン型のボード・付箋・リアルタイム同期のテスト。"""
import anyio.from_thread
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, select
from starlette.websockets import WebSocketDisconnect

from app.db import Base
from app.models import Board, CourseFramework, Event, Note, Team, User
from app.notes import NOTE_COLORS, note_color
from app.realtime import Hub
from app.security import WS_FORBIDDEN, WS_NOT_LOGGED_IN
from tests.test_step1 import join_students, make_two_teams
from tests.test_step2a import ROOT, add, events


def ws_url(board_id):
    return f"/ws/boards/{board_id}"


@pytest.fixture
def world(teacher_client, make_client, course, db):
    """1班（学生A・学生C）と 2班（学生B）。ブレスト=いま、SWOT=まだ。配り済み。"""
    clients, t1, t2 = make_two_teams(teacher_client, make_client, course, db)
    clients.update(join_students(make_client, course.invite_code, ["学生C"]))
    uid = {u.name: u.id for u in db.scalars(select(User))}
    teacher_client.post(f"/teams/{t1.id}/members", data={"user_id": uid["学生C"]})
    for k in ("brainstorm", "swot"):
        add(teacher_client, course, k)
    teacher_client.post(f"/courses/{course.id}/flow/deal")
    db.expire_all()
    boards = {(b.team_id, b.framework_key): b for b in db.scalars(select(Board))}

    class W:
        pass
    w = W()
    # 本物のサーバーは 1 つのイベントループで動く。TestClient は接続ごとにループを作ってしまい、
    # 別の接続へ送った知らせが届かないので、全員で 1 つのループ（portal）を共有させる
    with anyio.from_thread.start_blocking_portal() as portal:
        for c in [*clients.values(), teacher_client]:
            c.portal = portal
        yield from _world_body(w, clients, t1, t2, course, uid, teacher_client, boards)


def _world_body(w, clients, t1, t2, course, uid, teacher_client, boards):
    w.clients, w.t1, w.t2, w.course, w.uid = clients, t1, t2, course, uid
    w.teacher = teacher_client
    w.bs1, w.bs2 = boards[(t1.id, "brainstorm")], boards[(t2.id, "brainstorm")]
    w.swot1 = boards[(t1.id, "swot")]
    yield w


def set_status(db, course, key, status):
    item = db.scalar(select(CourseFramework).where(CourseFramework.course_id == course.id,
                                                   CourseFramework.framework_key == key))
    item.status = status
    db.commit()


def notes_in_db(db, board_id=None):
    db.expire_all()
    q = select(Note).order_by(Note.id)
    if board_id:
        q = q.where(Note.board_id == board_id)
    return list(db.scalars(q))


def add_note(ws, text="案1", zone="main"):
    ws.send_json({"type": "note.add", "zone_key": zone, "text": text})


def expect_closed(client, url, code):
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(url) as ws:
            ws.receive_json()
    assert e.value.code == code


# ---- 完了の条件 ----

def test_同じ班の2人がつなぐと片方の付箋がもう片方に届く(world):
    a, c = world.clients["学生A"], world.clients["学生C"]
    with a.websocket_connect(ws_url(world.bs1.id)) as wa, c.websocket_connect(ws_url(world.bs1.id)) as wc:
        assert wa.receive_json()["type"] == "snapshot"
        assert wc.receive_json()["type"] == "snapshot"
        add_note(wa, "屋台")
        got = wc.receive_json()
        assert got["type"] == "note.created"
        assert got["note"]["text"] == "屋台" and got["note"]["author_name"] == "学生A"
        assert got["note"]["color"] == note_color(world.uid["学生A"])
        assert wa.receive_json()["note"]["id"] == got["note"]["id"]  # 書いた本人にも届く


def test_他の班の学生と担当外の先生と未ログインはつなげない(world, make_client, db):
    expect_closed(world.clients["学生B"], ws_url(world.bs1.id), WS_FORBIDDEN)
    expect_closed(make_client(), ws_url(world.bs1.id), WS_NOT_LOGGED_IN)
    from app.cli import create_teacher
    create_teacher(db, "先生B", "pass-b-0123456")
    other = make_client()
    other.post("/login", data={"name": "先生B", "password": "pass-b-0123456"})
    expect_closed(other, ws_url(world.bs1.id), WS_FORBIDDEN)
    expect_closed(world.clients["学生A"], ws_url(99999), WS_FORBIDDEN)  # 無いボードも同じ扱い


def test_先生はつなげるが書き込みは断られる(world, db):
    with world.teacher.websocket_connect(ws_url(world.bs1.id)) as ws:
        snap = ws.receive_json()
        assert snap["type"] == "snapshot" and snap["writable"] is False
        add_note(ws)
        assert ws.receive_json() == {"type": "error", "code": "read_only"}
    assert notes_in_db(db) == []


def test_他の人の付箋は動かせないし消せない(world, db):
    a, c = world.clients["学生A"], world.clients["学生C"]
    with a.websocket_connect(ws_url(world.bs1.id)) as wa, c.websocket_connect(ws_url(world.bs1.id)) as wc:
        wa.receive_json(); wc.receive_json()
        add_note(wa, "Aの案")
        nid = wa.receive_json()["note"]["id"]; wc.receive_json()
        wc.send_json({"type": "note.delete", "id": nid})
        assert wc.receive_json() == {"type": "error", "code": "not_yours"}
        wc.send_json({"type": "note.move", "id": nid, "zone_key": "main"})
        assert wc.receive_json() == {"type": "error", "code": "not_yours"}
    assert notes_in_db(db)[0].deleted_at is None


def test_自分の付箋は区画をまたいで動かせる(world, db):
    # SWOT を「いま」にして試す
    set_status(db, world.course, "brainstorm", "done")
    set_status(db, world.course, "swot", "active")
    with world.clients["学生A"].websocket_connect(ws_url(world.swot1.id)) as ws:
        ws.receive_json()
        add_note(ws, "強み", "S")
        nid = ws.receive_json()["note"]["id"]
        ws.send_json({"type": "note.move", "id": nid, "zone_key": "T"})
        assert ws.receive_json()["note"]["zone_key"] == "T"
        add_note(ws, "変な区画", "Z")
        assert ws.receive_json()["code"] == "invalid"
    assert notes_in_db(db)[0].zone_key == "T"


def test_消した付箋は画面から消えるがDBの行は残る(world, db):
    a, c = world.clients["学生A"], world.clients["学生C"]
    with a.websocket_connect(ws_url(world.bs1.id)) as wa, c.websocket_connect(ws_url(world.bs1.id)) as wc:
        wa.receive_json(); wc.receive_json()
        add_note(wa, "消す案")
        nid = wa.receive_json()["note"]["id"]; wc.receive_json()
        wa.send_json({"type": "note.delete", "id": nid})
        assert wa.receive_json() == {"type": "note.deleted", "id": nid}
        assert wc.receive_json() == {"type": "note.deleted", "id": nid}
        wa.send_json({"type": "note.delete", "id": nid})  # 二度目は見つからない
        assert wa.receive_json()["code"] == "not_found"
    rows = notes_in_db(db)
    assert len(rows) == 1 and rows[0].deleted_at is not None
    with c.websocket_connect(ws_url(world.bs1.id)) as ws:  # つなぎ直しても出ない
        assert ws.receive_json()["notes"] == []


def test_付箋の操作がすべてEventに残る(world, db):
    with world.clients["学生A"].websocket_connect(ws_url(world.bs1.id)) as ws:
        ws.receive_json()
        add_note(ws, "案")
        nid = ws.receive_json()["note"]["id"]
        ws.send_json({"type": "note.move", "id": nid, "zone_key": "main"})
        ws.receive_json()
        ws.send_json({"type": "note.delete", "id": nid})
        ws.receive_json()
    for t in ("note.created", "note.moved", "note.deleted"):
        ev = events(db, t)
        assert len(ev) == 1
        assert ev[0].actor_id == world.uid["学生A"] and ev[0].board_id == world.bs1.id
        assert ev[0].team_id == world.t1.id and ev[0].payload["note_id"] == nid


def test_つなぎ直すとボードの全部を取り直せる(world, db):
    a = world.clients["学生A"]
    with a.websocket_connect(ws_url(world.bs1.id)) as ws:
        ws.receive_json()
        for t in ("1", "2"):
            add_note(ws, t); ws.receive_json()
    with world.clients["学生C"].websocket_connect(ws_url(world.bs1.id)) as ws:
        snap = ws.receive_json()
        assert snap["type"] == "snapshot" and [n["text"] for n in snap["notes"]] == ["1", "2"]
        assert snap["writable"] is True and snap["me"] == world.uid["学生C"]


def test_pingにはpongが返る(world):
    with world.clients["学生A"].websocket_connect(ws_url(world.bs1.id)) as ws:
        ws.receive_json()
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


# ---- B-7：いま・終わり・まだ ----

def test_終わりのボードは学生は見るだけで書けない(world, db):
    with world.clients["学生A"].websocket_connect(ws_url(world.bs1.id)) as ws:
        ws.receive_json()
        add_note(ws, "終わる前の案"); ws.receive_json()
    set_status(db, world.course, "brainstorm", "done")
    with world.clients["学生A"].websocket_connect(ws_url(world.bs1.id)) as ws:
        snap = ws.receive_json()
        assert snap["writable"] is False and len(snap["notes"]) == 1
        add_note(ws)
        assert ws.receive_json() == {"type": "error", "code": "read_only"}
    assert len(notes_in_db(db)) == 1


def test_つないだあとに終わりになったら書けなくなる(world, db):
    with world.clients["学生A"].websocket_connect(ws_url(world.bs1.id)) as ws:
        ws.receive_json()
        set_status(db, world.course, "brainstorm", "done")
        add_note(ws)
        assert ws.receive_json()["code"] == "read_only"
    assert notes_in_db(db) == []


def test_まだのボードには学生はつなげず先生はつなげる(world, db):
    expect_closed(world.clients["学生A"], ws_url(world.swot1.id), WS_FORBIDDEN)
    with world.teacher.websocket_connect(ws_url(world.swot1.id)) as ws:
        assert ws.receive_json()["writable"] is False


def test_ボードの画面のURLと権限(world):
    a = world.clients["学生A"]
    ok = a.get(f"/teams/{world.t1.id}/boards/{world.bs1.id}")
    assert ok.status_code == 200 and 'data-zone="main"' in ok.text and "＋ 付箋を足す" in ok.text
    assert a.get(f"/teams/{world.t1.id}/boards/{world.swot1.id}").status_code == 403  # まだ
    assert a.get(f"/teams/{world.t1.id}/boards/{world.bs2.id}").status_code == 404  # 他の班のボード
    assert world.clients["学生B"].get(f"/teams/{world.t1.id}/boards/{world.bs1.id}").status_code == 404
    t = world.teacher.get(f"/teams/{world.t1.id}/boards/{world.swot1.id}")
    assert t.status_code == 200 and t.text.count('class="zone"') == 4
    assert "閲覧中" in t.text and "付箋を足す" not in t.text  # 先生には書き込みの部品を出さない


def test_付箋の中身はHTMLに入らない(world):
    with world.clients["学生A"].websocket_connect(ws_url(world.bs1.id)) as ws:
        ws.receive_json()
        add_note(ws, "秘密っぽい案"); ws.receive_json()
    assert "秘密っぽい案" not in world.clients["学生A"].get(f"/teams/{world.t1.id}").text


def test_作成者ごとに決まった色(world):
    assert note_color(1) == note_color(1) and note_color(1) != note_color(2)
    assert all(note_color(i) in NOTE_COLORS for i in range(20))


def test_本文が空や長すぎるのは断る(world, db):
    with world.clients["学生A"].websocket_connect(ws_url(world.bs1.id)) as ws:
        ws.receive_json()
        add_note(ws, "   ")
        assert ws.receive_json()["code"] == "invalid"
        add_note(ws, "あ" * 201)
        assert ws.receive_json()["code"] == "invalid"
        ws.send_json({"type": "unknown"})
        assert ws.receive_json()["code"] == "invalid"
    assert notes_in_db(db) == []


# ---- 配信係 ----

class FakeSocket:
    def __init__(self):
        self.sent = []

    async def send_json(self, m):
        self.sent.append(m)


def test_配信係は人ごとに送り先を選べる():
    import asyncio
    hub, a, b = Hub(), FakeSocket(), FakeSocket()
    hub.join(1, 10, a); hub.join(1, 20, b)
    asyncio.run(hub.publish(1, {"n": 1}))
    asyncio.run(hub.publish(1, {"n": 2}, to_users=[10]))
    assert a.sent == [{"n": 1}, {"n": 2}] and b.sent == [{"n": 1}]
    hub.leave(1, a)
    assert hub.user_ids(1) == {20}


# ---- 版 0003 ----

def test_版0003を流したDBとモデルが一致する(tmp_path, monkeypatch):
    db_path = tmp_path / "m.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    cfg = Config(str(ROOT / "alembic.ini"))
    command.upgrade(cfg, "head")
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        tables = {r[0] for r in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "notes" in tables
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
    command.downgrade(cfg, "0002")
    command.upgrade(cfg, "head")
