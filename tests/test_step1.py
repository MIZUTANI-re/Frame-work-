"""ステップ 1 の完了の条件をテストで確かめる。"""
import pytest
from sqlalchemy import select

from app.cli import create_teacher
from app.invite import ALPHABET
from app.models import Course, Event, Team, TeamMember, User
from tests.conftest import TEACHER_PW, join, login


def join_students(make_client, code, names):
    """学生を何人か参加させ、名前 → クライアントの辞書を返す。"""
    clients = {}
    for name in names:
        c = make_client()
        assert join(c, code, name, f"pw-{name}").status_code == 303
        clients[name] = c
    return clients


def test_教員が授業を作ると6文字の招待コードが付く(course):
    assert len(course.invite_code) == 6
    assert all(ch in ALPHABET for ch in course.invite_code)
    assert not set("0O1IL") & set(course.invite_code)


def test_学生が正しいコードで参加できる(make_client, course):
    c = make_client()
    r = join(c, course.invite_code, "学生A", "pw-123456")
    assert r.status_code == 303
    assert c.get(f"/courses/{course.id}").status_code == 200


def test_間違ったコードでは参加できない(make_client, course, db):
    c = make_client()
    r = join(c, "ZZZZZZ", "学生A", "pw-123456")
    assert r.status_code == 400
    assert db.scalar(select(User).where(User.name == "学生A")) is None
    assert c.get(f"/courses/{course.id}").status_code == 303  # ログインしていない


def test_同じ名前で別のパスワードでは参加できない(make_client, course):
    join_students(make_client, course.invite_code, ["学生A"])
    other = make_client()
    r = join(other, course.invite_code, "学生A", "ちがうパスワード")
    assert r.status_code == 400
    assert "その名前は使われています" in r.text
    # 同じパスワードなら同じ人として入れる
    assert join(make_client(), course.invite_code, "学生A", "pw-学生A").status_code == 303


def test_教員の名前では学生として参加できない(make_client, course):
    r = join(make_client(), course.invite_code, "先生A", TEACHER_PW)
    assert r.status_code == 400


def test_ランダム振り分けで全員がどれか1つの班に入り人数差は1以下(
        teacher_client, make_client, course, db):
    join_students(make_client, course.invite_code, [f"学生{i}" for i in range(7)])
    r = teacher_client.post(f"/courses/{course.id}/teams/random", data={"count": 3})
    assert r.status_code == 303
    teams = list(db.scalars(select(Team).where(Team.course_id == course.id)))
    assert len(teams) == 3
    members = list(db.scalars(select(TeamMember)))
    assert len(members) == 7
    assert len({m.user_id for m in members}) == 7  # 1 人が複数の班に入っていない
    sizes = [sum(1 for m in members if m.team_id == t.id) for t in teams]
    assert max(sizes) - min(sizes) <= 1


def test_ランダム振り分けをやり直しても1人1班(teacher_client, make_client, course, db):
    join_students(make_client, course.invite_code, [f"学生{i}" for i in range(5)])
    teacher_client.post(f"/courses/{course.id}/teams/random", data={"count": 2})
    teacher_client.post(f"/courses/{course.id}/teams/random", data={"count": 3})
    db.expire_all()
    assert len(list(db.scalars(select(Team)))) == 3
    members = list(db.scalars(select(TeamMember)))
    assert len({m.user_id for m in members}) == 5 == len(members)


def make_two_teams(teacher_client, make_client, course, db):
    """学生A・B を 2 つの班に分ける。(クライアント辞書, 班A, 班B) を返す。"""
    clients = join_students(make_client, course.invite_code, ["学生A", "学生B"])
    teacher_client.post(f"/courses/{course.id}/teams", data={"name": "1班"})
    teacher_client.post(f"/courses/{course.id}/teams", data={"name": "2班"})
    t1, t2 = list(db.scalars(select(Team).order_by(Team.id)))
    ids = {u.name: u.id for u in db.scalars(select(User))}
    teacher_client.post(f"/teams/{t1.id}/members", data={"user_id": ids["学生A"]})
    teacher_client.post(f"/teams/{t2.id}/members", data={"user_id": ids["学生B"]})
    return clients, t1, t2


def test_学生は自分の班は開けるが他の班は404(teacher_client, make_client, course, db):
    clients, t1, t2 = make_two_teams(teacher_client, make_client, course, db)
    a = clients["学生A"]
    assert a.get(f"/teams/{t1.id}").status_code == 200
    assert a.get(f"/teams/{t2.id}").status_code == 404
    assert t2.name not in a.get(f"/courses/{course.id}").text  # 他の班の名前も出さない


def test_学生は担当外の授業を開けない(make_client, course, db, teacher_client):
    # 別の授業を作り、そこには入っていない学生が開こうとする
    r = teacher_client.post("/courses", data={"name": "別の授業"})
    other_id = int(r.headers["location"].rsplit("/", 1)[1])
    clients = join_students(make_client, course.invite_code, ["学生A"])
    assert clients["学生A"].get(f"/courses/{other_id}").status_code == 404
    assert clients["学生A"].get(f"/courses/{other_id}/members").status_code == 404


def test_学生はメンバー管理とコード再発行ができない403(
        teacher_client, make_client, course, db):
    clients, t1, t2 = make_two_teams(teacher_client, make_client, course, db)
    a = clients["学生A"]
    old_code = course.invite_code
    assert a.get(f"/courses/{course.id}/members").status_code == 403
    assert a.post(f"/courses/{course.id}/invite-code/regenerate").status_code == 403
    assert a.post(f"/courses/{course.id}/teams/random", data={"count": 1}).status_code == 403
    assert a.post(f"/teams/{t1.id}/rename", data={"name": "x"}).status_code == 403  # 自分の班の操作も 403
    assert a.post(f"/teams/{t2.id}/rename", data={"name": "x"}).status_code == 404  # 他の班は存在も隠す
    db.expire_all()
    assert db.get(Course, course.id).invite_code == old_code
    assert db.get(Team, t1.id) is not None


def test_担当外の教員は他の教員の授業を開けない(make_client, course, db):
    create_teacher(db, "先生B", "pass-b-0123456")
    b = make_client()
    login(b, "先生B", "pass-b-0123456")
    assert b.get(f"/courses/{course.id}").status_code == 404
    assert b.get(f"/courses/{course.id}/members").status_code == 404
    assert b.post(f"/courses/{course.id}/invite-code/regenerate").status_code == 404


def test_担当外の教員は他の教員の班を開けない(teacher_client, make_client, course, db):
    teacher_client.post(f"/courses/{course.id}/teams", data={"name": "1班"})
    team = db.scalar(select(Team))
    create_teacher(db, "先生B", "pass-b-0123456")
    b = make_client()
    login(b, "先生B", "pass-b-0123456")
    assert b.get(f"/teams/{team.id}").status_code == 404
    assert b.post(f"/teams/{team.id}/rename", data={"name": "x"}).status_code == 404


def test_コード再発行で古いコードは使えず参加済みはそのまま(
        teacher_client, make_client, course, db):
    clients = join_students(make_client, course.invite_code, ["学生A"])
    old = course.invite_code
    teacher_client.post(f"/courses/{course.id}/invite-code/regenerate")
    db.expire_all()
    assert db.get(Course, course.id).invite_code != old
    assert join(make_client(), old, "学生B", "pw-123456").status_code == 400
    assert clients["学生A"].get(f"/courses/{course.id}").status_code == 200


def test_パスワードがDBに平文で入っていない(make_client, course, db):
    join_students(make_client, course.invite_code, ["学生A"])
    for user in db.scalars(select(User)):
        assert user.password_hash.startswith("$argon2")
        assert TEACHER_PW not in user.password_hash and "pw-学生A" not in user.password_hash


def test_参加と班への追加がEventに記録される(teacher_client, make_client, course, db):
    clients, t1, t2 = make_two_teams(teacher_client, make_client, course, db)
    types = [e.type for e in db.scalars(select(Event).order_by(Event.id))]
    assert types.count("course.joined") == 2
    assert types.count("team.member_added") == 2
    ids = {u.name: u.id for u in db.scalars(select(User))}
    # 学生A を 2 班へ移すと「外した」記録が残る
    teacher_client.post(f"/teams/{t2.id}/members", data={"user_id": ids["学生A"]})
    removed = list(db.scalars(select(Event).where(Event.type == "team.member_removed")))
    assert len(removed) == 1 and removed[0].team_id == t1.id
    assert removed[0].payload["user_id"] == ids["学生A"]


def test_ログイン前は保護された画面からログインへ移る(make_client, course):
    c = make_client()
    r = c.get(f"/courses/{course.id}")
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_ログアウトするとセッションが消える(teacher_client, course):
    assert teacher_client.get(f"/courses/{course.id}/settings").status_code == 200
    teacher_client.post("/logout")
    assert teacher_client.get(f"/courses/{course.id}").status_code == 303


def test_ログイン画面とログイン失敗(make_client, teacher):
    c = make_client()
    assert c.get("/login").status_code == 200
    assert login(c, "先生A", "まちがい").status_code == 400


def test_学生は教員専用の授業作成ができない(make_client, course):
    c = join_students(make_client, course.invite_code, ["学生A"])["学生A"]
    assert c.get("/courses/new").status_code == 403
    assert c.post("/courses", data={"name": "x"}).status_code == 403


def test_教員作成コマンドの関数(db):
    user = create_teacher(db, "先生C", "pw-0123456789")
    assert user.role == "teacher"
    with pytest.raises(ValueError):
        create_teacher(db, "先生C", "pw2-0123456789")  # 同じ名前は作れない
