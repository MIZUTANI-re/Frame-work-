"""ステップ 2a の完了の条件をテストで確かめる。"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, select

from app.cli import create_teacher
from app.db import Base
from app.framework_defs import FRAMEWORKS, FRAMEWORKS_DIR, FrameworkDefError, load_frameworks
from app.models import Board, ChatMessage, Course, CourseFramework, Event, Team, User
from tests.conftest import join, login
from tests.test_step1 import join_students, make_two_teams

ROOT = Path(__file__).resolve().parent.parent


def add(client, course, key, q=""):
    return client.post(f"/courses/{course.id}/flow/add", data={"framework_key": key, "q": q})


def events(db, type):
    db.expire_all()
    return list(db.scalars(select(Event).where(Event.type == type).order_by(Event.id)))


def items(db, course):
    db.expire_all()
    return list(db.scalars(select(CourseFramework).where(CourseFramework.course_id == course.id)
                           .order_by(CourseFramework.position)))


# ---- 画面を 3 つの場所に分ける ----

def test_学生の2列目に準備が出ず準備のURLは開けない(teacher_client, make_client, course, db):
    clients, t1, t2 = make_two_teams(teacher_client, make_client, course, db)
    a = clients["学生A"]
    page = a.get(f"/courses/{course.id}").text
    assert "⚙ 準備" not in page and "フレームワークを探す" not in page
    assert "▶ 授業中" in page and "📄 成果" in page
    for path in ("/members", "/frameworks/search", "/flow"):
        assert a.get(f"/courses/{course.id}{path}").status_code in (403, 404)
    assert a.post(f"/courses/{course.id}/flow/deal").status_code in (403, 404)
    assert a.get(f"/courses/{course.id}/dashboard").status_code in (403, 404)
    assert a.get(f"/courses/{course.id}/settings").status_code == 403
    r = teacher_client.get(f"/courses/{course.id}")
    assert r.status_code == 303 and r.headers["location"] == f"/courses/{course.id}/settings"
    assert "⚙ 準備" in teacher_client.get(f"/courses/{course.id}/settings").text


# ---- 定義ファイル ----

def test_同梱の定義3本が読める():
    assert list(FRAMEWORKS) == ["brainstorm", "swot", "payoff_matrix"]


def make_defs(tmp_path, mutate=None, name="swot"):
    d = tmp_path / "defs"
    shutil.copytree(FRAMEWORKS_DIR, d)
    if mutate:
        data = json.loads((d / f"{name}.json").read_text(encoding="utf-8"))
        mutate(data)
        (d / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return d


def test_正しい定義なら読める(tmp_path):
    assert len(load_frameworks(make_defs(tmp_path))) == 3


@pytest.mark.parametrize("mutate", [
    lambda d: d.pop("yomi"),                          # 必須の項目が無い
    lambda d: d.update(board_type="table"),           # zone / axis 以外
    lambda d: d.update(key="other"),                  # key とファイル名が違う
    lambda d: d["meta"].pop("source"),                # meta の項目が無い
    lambda d: d.pop("zones"),                         # zone なのに区画が無い
    lambda d: d.update(phases=[{"key": "individual"}]),  # 公開が無い
])
def test_仕様に合わない定義は起動が止まる(tmp_path, mutate):
    with pytest.raises(FrameworkDefError):
        load_frameworks(make_defs(tmp_path, mutate))


def test_壊れたJSONでも止まる(tmp_path):
    d = make_defs(tmp_path)
    (d / "swot.json").write_text("{ 壊れている", encoding="utf-8")
    with pytest.raises(FrameworkDefError):
        load_frameworks(d)


# ---- 探す ----

def test_空のときはよく使われている順に並ぶ(teacher_client, db, course):
    # 選ばれた回数を作る：SWOT 2 回・ペイオフ 1 回（別の授業で選ばれた分も数える）
    other = create_teacher(db, "先生B", "pass-b-0123456")
    c2 = Course(name="別の授業", teacher_id=other.id, invite_code="ABCDEF")
    db.add(c2)
    db.flush()
    for course_id, key, pos in ((c2.id, "swot", 1), (course.id, "swot", 1), (course.id, "payoff_matrix", 2)):
        db.add(CourseFramework(course_id=course_id, framework_key=key, phases=["individual", "reveal"],
                               position=pos, created_by=other.id))
    db.commit()
    html = teacher_client.get(f"/courses/{course.id}/frameworks/search").text
    data = json.loads(html.split('id="fw-data">')[1].split("</script>")[0])
    uses = {d["key"]: d["uses"] for d in data}
    assert uses == {"brainstorm": 0, "swot": 2, "payoff_matrix": 1}
    # 並べるのは JS（search_logic.js）。空の検索で回数順になることを node で確かめる
    assert run_search(data, "") == ["swot", "payoff_matrix", "brainstorm"]


def run_search(data, q):
    """search_logic.js の search() を node で動かし、出た key の並びを返す。"""
    if shutil.which("node") is None:
        pytest.skip("node が無いので探す画面の JS は確かめていない")
    script = ("import {search} from %r; const [d,q]=JSON.parse(process.argv[1]);"
              "console.log(JSON.stringify(search(d,q).map(f=>f.key)))") % (
        (ROOT / "app/static/js/search_logic.js").as_uri(),)
    out = subprocess.run(["node", "--input-type=module", "-e", script, json.dumps([data, q])],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


@pytest.fixture
def candidates():
    from app.routers.frameworks import PURPOSE_LABELS, THINKING_LABELS
    return [{"key": k, "name": f["name"], "aliases": f["aliases"], "yomi": f["yomi"], "tags": f["tags"],
             "description": f["meta"]["description"], "purpose_label": PURPOSE_LABELS[f["meta"]["purpose"]],
             "thinking_label": THINKING_LABELS[f["meta"]["thinking"]], "uses": 0}
            for k, f in FRAMEWORKS.items()]


@pytest.mark.parametrize("q, key", [("ﾌﾞﾚ", "brainstorm"), ("ﾍﾟｲｵﾌ", "payoff_matrix"), ("ブレ ", "brainstorm"),
                                    ("ブレ\u3000", "brainstorm"), ("ぶれ", "brainstorm"), ("ゆうせん", "payoff_matrix"),
                                    ("ＳＷＯＴ", "swot"), ("swot", "swot"), ("すうぉっと", "swot")])
def test_文字をそろえて探せる(candidates, q, key):
    found = run_search(candidates, q)
    assert key in found
    assert found[0] == key  # 合い方が強いので先頭に来る


def test_合わない言葉では出ない(candidates):
    assert run_search(candidates, "ぜんぜん関係ない言葉") == []


# ---- 流れに足す ----

def test_流れに足すと最後に入りframework_selectedが記録される(teacher_client, db, course):
    add(teacher_client, course, "swot", "ＳＷＯ")
    add(teacher_client, course, "brainstorm", "ぶれ")
    assert [i.framework_key for i in items(db, course)] == ["swot", "brainstorm"]
    assert [i.position for i in items(db, course)] == [1, 2]
    ev = events(db, "framework.selected")
    assert [e.payload["framework_key"] for e in ev] == ["swot", "brainstorm"]
    assert ev[0].payload["query"] == "ＳＷＯ"
    assert ev[0].payload["phases"] == ["individual", "reveal", "cluster", "vote", "conclusion"]
    add(teacher_client, course, "swot")  # 同じものは二重に入らない
    assert len(items(db, course)) == 2


def test_知らないフレームワークは足せない(teacher_client, db, course):
    assert add(teacher_client, course, "nothing").status_code == 404
    assert items(db, course) == []


def test_並べ替えと外す(teacher_client, db, course):
    for k in ("brainstorm", "swot", "payoff_matrix"):
        add(teacher_client, course, k)
    swot = items(db, course)[1]
    teacher_client.post(f"/courses/{course.id}/flow/{swot.id}/move", data={"direction": "up"})
    assert [i.framework_key for i in items(db, course)] == ["swot", "brainstorm", "payoff_matrix"]
    teacher_client.post(f"/courses/{course.id}/flow/{swot.id}/remove")
    assert [(i.framework_key, i.position) for i in items(db, course)] == [("brainstorm", 1), ("payoff_matrix", 2)]


def test_個人ワークと公開は画面を通さずに送っても外せない(teacher_client, db, course):
    add(teacher_client, course, "swot")
    item = items(db, course)[0]
    url = f"/courses/{course.id}/flow/{item.id}/phases"
    for phases in (["reveal", "cluster"], ["individual", "cluster"], [], ["individual", "reveal", "bogus"]):
        assert teacher_client.post(url, data={"phase": phases}).status_code == 400
    assert items(db, course)[0].phases == ["individual", "reveal", "cluster", "vote", "conclusion"]
    # まとめる・投票・結論は外せる
    assert teacher_client.post(url, data={"phase": ["individual", "reveal", "conclusion"]}).status_code == 303
    assert items(db, course)[0].phases == ["individual", "reveal", "conclusion"]


def test_流れの画面にも個人ワークと公開は外せない形で出る(teacher_client, course):
    add(teacher_client, course, "swot")
    html = teacher_client.get(f"/courses/{course.id}/flow").text
    assert 'name="phase" value="individual"' in html and 'name="phase" value="reveal"' in html


# ---- チャット ----

def test_チャットは送った文と決まった返事の2行が保存される(teacher_client, db, course):
    r = teacher_client.post(f"/courses/{course.id}/chat", data={"text": "新商品の授業に合うのは？"})
    assert r.status_code == 200
    assert [m["role"] for m in r.json()["messages"]] == ["user", "assistant"]
    db.expire_all()
    rows = list(db.scalars(select(ChatMessage).order_by(ChatMessage.id)))
    assert [(m.role, m.text) for m in rows] == [("user", "新商品の授業に合うのは？"),
                                                 ("assistant", "LLM はまだつながっていません")]
    assert rows[1].user_id is None
    assert len(events(db, "chat.posted")) == 1
    assert "新商品の授業に合うのは？" in teacher_client.get(f"/courses/{course.id}/frameworks/search").text


def test_学生と担当外の先生はチャットを送れない(teacher_client, make_client, db, course):
    s = join_students(make_client, course.invite_code, ["学生A"])["学生A"]
    assert s.post(f"/courses/{course.id}/chat", data={"text": "こんにちは"}).status_code == 403
    create_teacher(db, "先生C", "pass-c-0123456")
    other = make_client()
    login(other, "先生C", "pass-c-0123456")
    assert other.post(f"/courses/{course.id}/chat", data={"text": "こんにちは"}).status_code == 404
    db.expire_all()
    assert list(db.scalars(select(ChatMessage))) == []


def test_空のチャットは送れない(teacher_client, course):
    assert teacher_client.post(f"/courses/{course.id}/chat", data={"text": "  "}).status_code == 400


# ---- 配る ----

def setup_flow(teacher_client, make_client, course, db):
    clients, t1, t2 = make_two_teams(teacher_client, make_client, course, db)
    for k in ("brainstorm", "swot", "payoff_matrix"):
        add(teacher_client, course, k)
    return clients, t1, t2


def test_全班に配ると流れの数だけボードができ1番目だけactive(teacher_client, make_client, course, db):
    clients, t1, t2 = setup_flow(teacher_client, make_client, course, db)
    assert teacher_client.post(f"/courses/{course.id}/flow/deal").status_code == 303
    db.expire_all()
    for t in (t1, t2):
        boards = list(db.scalars(select(Board).where(Board.team_id == t.id).order_by(Board.id)))
        assert [b.framework_key for b in boards] == ["brainstorm", "swot", "payoff_matrix"]
        assert all(b.phase == "individual" and b.chosen_by == "teacher" for b in boards)
    assert [i.status for i in items(db, course)] == ["active", "waiting", "waiting"]
    assert len(events(db, "board.created")) == 6
    teacher_client.post(f"/courses/{course.id}/flow/deal")  # 押し直しても二重にならない
    db.expire_all()
    assert len(list(db.scalars(select(Board)))) == 6


def test_班のページに流れの帯とタブが出る(teacher_client, make_client, course, db):
    clients, t1, t2 = setup_flow(teacher_client, make_client, course, db)
    assert "まだボードは配られていません" in clients["学生A"].get(f"/teams/{t1.id}").text
    teacher_client.post(f"/courses/{course.id}/flow/deal")
    html = clients["学生A"].get(f"/teams/{t1.id}").text
    assert "① ブレインストーミング" in html and "② SWOT 分析" in html and "③ ペイオフマトリクス" in html
    assert 'class="fl active' in html and html.count('class="tab ') == 3
    assert f'href="/teams/{t1.id}/boards/' in html and "?board=" not in html
    assert 'id="board"' in html
    assert teacher_client.get(f"/teams/{t1.id}").status_code == 200
    assert clients["学生A"].get(f"/teams/{t2.id}").status_code == 404  # 他の班は今までどおり


def test_あとから作った班にもボードができる(teacher_client, make_client, course, db):
    setup_flow(teacher_client, make_client, course, db)
    # 配る前に作った班にはボードができない
    teacher_client.post(f"/courses/{course.id}/teams", data={"name": "早い班"})
    db.expire_all()
    assert list(db.scalars(select(Board).join(Team).where(Team.name == "早い班"))) == []
    teacher_client.post(f"/courses/{course.id}/flow/deal")
    teacher_client.post(f"/courses/{course.id}/teams", data={"name": "遅い班"})
    db.expire_all()
    late = db.scalar(select(Team).where(Team.name == "遅い班"))
    boards = list(db.scalars(select(Board).where(Board.team_id == late.id)))
    assert sorted(b.framework_key for b in boards) == ["brainstorm", "payoff_matrix", "swot"]


def test_始まったものは外せず進め方も変えられない(teacher_client, make_client, course, db):
    setup_flow(teacher_client, make_client, course, db)
    teacher_client.post(f"/courses/{course.id}/flow/deal")
    first = items(db, course)[0]
    assert teacher_client.post(f"/courses/{course.id}/flow/{first.id}/remove").status_code == 409
    assert teacher_client.post(f"/courses/{course.id}/flow/{first.id}/phases",
                               data={"phase": ["individual", "reveal"]}).status_code == 409
    assert len(items(db, course)) == 3


def test_流れが空や班が無いときは配らない(teacher_client, course, db):
    r = teacher_client.post(f"/courses/{course.id}/flow/deal")
    assert "flow_empty" in r.headers["location"]
    add(teacher_client, course, "swot")
    r = teacher_client.post(f"/courses/{course.id}/flow/deal")
    assert "no_teams" in r.headers["location"]
    assert items(db, course)[0].status == "waiting"


def test_他の授業の流れの行は操作できない(teacher_client, db, course):
    other = create_teacher(db, "先生B", "pass-b-0123456")
    c2 = Course(name="別", teacher_id=other.id, invite_code="ZZZZZ2")
    db.add(c2)
    db.flush()
    item = CourseFramework(course_id=c2.id, framework_key="swot", phases=["individual", "reveal"],
                           position=1, created_by=other.id)
    db.add(item)
    db.commit()
    assert teacher_client.post(f"/courses/{course.id}/flow/{item.id}/remove").status_code == 404


# ---- 授業の設定 ----

def test_授業の設定を切り替えると保存されeventが残る(teacher_client, db, course):
    page = teacher_client.get(f"/courses/{course.id}/settings").text
    assert "成果（まとめシート）を全班で共有する" in page
    assert 'value="false" checked' in page  # 既定は「しない」
    r = teacher_client.post(f"/courses/{course.id}/settings", data={"share_outputs_across_teams": "true"})
    assert r.status_code == 303
    db.expire_all()
    assert db.get(Course, course.id).settings == {"share_outputs_across_teams": True}
    assert 'value="true" checked' in teacher_client.get(f"/courses/{course.id}/settings").text
    ev = events(db, "course.settings_changed")
    assert len(ev) == 1
    assert ev[0].payload["changes"]["share_outputs_across_teams"] == {"old": False, "new": True}
    teacher_client.post(f"/courses/{course.id}/settings", data={"share_outputs_across_teams": "true"})
    assert len(events(db, "course.settings_changed")) == 1  # 変わらなければ記録しない


def test_学生は授業の設定を変えられない(teacher_client, make_client, db, course):
    s = join_students(make_client, course.invite_code, ["学生A"])["学生A"]
    assert s.post(f"/courses/{course.id}/settings", data={"share_outputs_across_teams": "true"}).status_code == 403
    db.expire_all()
    assert not db.get(Course, course.id).settings
    assert events(db, "course.settings_changed") == []


# ---- 版 0002 ----

def test_版0002を流したDBとモデルが一致する(tmp_path, monkeypatch):
    db_path = tmp_path / "m2.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    cfg = Config(str(ROOT / "alembic.ini"))
    command.upgrade(cfg, "0001")
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:  # 0001 の時点の授業が 1 つあっても流せる
        conn.exec_driver_sql("INSERT INTO users (name, role, password_hash, created_at, failed_logins, session_version)"
                             " VALUES ('t','teacher','x','2026-01-01',0,0)")
        conn.exec_driver_sql("INSERT INTO courses (name, teacher_id, invite_code, created_at)"
                             " VALUES ('c',1,'AAAAAA','2026-01-01')")
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert {"course_frameworks", "boards", "chat_messages"} <= set(
            r[0] for r in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'"))
        assert conn.exec_driver_sql("SELECT settings FROM courses").scalar() == "{}"
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []


# ---- レビューの修正 ----

def test_配ったものは外せず409でボードも残る(teacher_client, make_client, course, db):
    setup_flow(teacher_client, make_client, course, db)
    teacher_client.post(f"/courses/{course.id}/flow/deal")
    swot = items(db, course)[1]
    assert swot.status == "waiting"  # 「まだ」でも、ボードがあれば外せない（B-6）
    assert teacher_client.post(f"/courses/{course.id}/flow/{swot.id}/remove").status_code == 409
    db.expire_all()
    assert len(list(db.scalars(select(Board)))) == 6 and len(items(db, course)) == 3
    html = teacher_client.get(f"/courses/{course.id}/flow").text
    assert html.count("disabled>外す") == 3  # 画面の「外す」も押せない


def test_学生は_まだ_のボードを開けない(teacher_client, make_client, course, db):
    clients, t1, t2 = setup_flow(teacher_client, make_client, course, db)
    teacher_client.post(f"/courses/{course.id}/flow/deal")
    waiting = list(db.scalars(select(Board).where(Board.team_id == t1.id).order_by(Board.id)))[1]
    url = f"/teams/{t1.id}/boards/{waiting.id}"
    assert clients["学生A"].get(url).status_code == 403  # 開けない（B-7）
    html = clients["学生A"].get(f"/teams/{t1.id}").text
    assert html.count('<a class="tab') == 1 and html.count('class="tab waiting"') == 2  # 見えるが押せない
    # 先生は「まだ」も開ける
    assert 'data-zone="S"' in teacher_client.get(url).text


def test_学生の帯には配ったものだけ出て先生には全部出る(teacher_client, make_client, course, db):
    clients, t1, t2 = make_two_teams(teacher_client, make_client, course, db)
    for k in ("brainstorm", "swot"):
        add(teacher_client, course, k)
    teacher_client.post(f"/courses/{course.id}/flow/deal")
    add(teacher_client, course, "payoff_matrix")  # 配ったあとに足した（配っていない）
    student = clients["学生A"].get(f"/teams/{t1.id}").text
    assert student.count('class="fl ') == 2 and "ペイオフマトリクス" not in student
    assert teacher_client.get(f"/teams/{t1.id}").text.count('class="fl ') == 3


def test_流れの操作が記録に残る(teacher_client, make_client, course, db):
    for k in ("brainstorm", "swot", "payoff_matrix"):
        add(teacher_client, course, k)
    swot = items(db, course)[1]
    teacher_client.post(f"/courses/{course.id}/flow/{swot.id}/move", data={"direction": "up"})
    ev = events(db, "flow.reordered")
    assert ev[0].payload == {"before": ["brainstorm", "swot", "payoff_matrix"],
                             "after": ["swot", "brainstorm", "payoff_matrix"]}
    teacher_client.post(f"/courses/{course.id}/flow/{swot.id}/phases",
                        data={"phase": ["individual", "reveal", "conclusion"]})
    ev = events(db, "flow.phases_changed")
    assert ev[0].payload["before"] == ["individual", "reveal", "cluster", "vote", "conclusion"]
    assert ev[0].payload["after"] == ["individual", "reveal", "conclusion"]
    pay = items(db, course)[2]
    teacher_client.post(f"/courses/{course.id}/flow/{pay.id}/remove")
    ev = events(db, "flow.removed")
    assert ev[0].payload["framework_key"] == "payoff_matrix" and ev[0].payload["position"] == 3


def test_board_createdにflowの番号が入る(teacher_client, make_client, course, db):
    setup_flow(teacher_client, make_client, course, db)
    teacher_client.post(f"/courses/{course.id}/flow/deal")
    ev = events(db, "board.created")
    it = {i.framework_key: i for i in items(db, course)}
    for e in ev:
        assert e.payload["course_framework_id"] == it[e.payload["framework_key"]].id
        assert e.payload["position"] == it[e.payload["framework_key"]].position


def test_足す操作が重なって失敗しても500にならない(teacher_client, db, course, monkeypatch):
    from app import flow as flow_mod
    add(teacher_client, course, "swot")
    # 「すでに入っているか」の確認をすり抜けた 2 度押しを作る（DB の一意制約で止まる）
    monkeypatch.setattr(flow_mod, "flow_items", lambda db_, cid: [])
    r = add(teacher_client, course, "swot")
    assert r.status_code == 303 and "msg=already" in r.headers["location"]
    assert len(items(db, course)) == 1


def test_動かせない並べ替えは409(teacher_client, make_client, course, db):
    setup_flow(teacher_client, make_client, course, db)
    teacher_client.post(f"/courses/{course.id}/flow/deal")
    first, second, third = items(db, course)
    url = lambda i: f"/courses/{course.id}/flow/{i.id}/move"
    assert teacher_client.post(url(first), data={"direction": "down"}).status_code == 409  # ① は動かせない
    assert teacher_client.post(url(second), data={"direction": "up"}).status_code == 409   # ② は ↑ できない
    assert teacher_client.post(url(third), data={"direction": "down"}).status_code == 409  # 端
    assert teacher_client.post(url(second), data={"direction": "down"}).status_code == 303  # ②③ は入れ替えられる
    html = teacher_client.get(f"/courses/{course.id}/flow").text
    assert "disabled" in html
