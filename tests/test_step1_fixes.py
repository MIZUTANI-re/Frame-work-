"""ステップ 1 のレビュー指摘の修正を確かめるテスト。"""
from datetime import timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import cli
from app.models import Course, Event, Team, TeamMember, User
from tests.conftest import TEACHER_PW, join
from tests.test_step1 import join_students, make_two_teams


def members_error(client, course, key):
    """メンバー管理ページを開いて、通知の文が出ているか調べるための本文を返す。"""
    return client.get(f"/courses/{course.id}/members?error={key}").text


def test_班の数が不正だと何も変わらず通知が出る(teacher_client, make_client, course, db):
    join_students(make_client, course.invite_code, ["学生A", "学生B"])
    for count in (0, 3):  # 0 と、学生の人数より多い数
        r = teacher_client.post(f"/courses/{course.id}/teams/random", data={"count": count})
        assert r.headers["location"].endswith("error=count_invalid")
    assert db.scalar(select(Team)) is None
    assert "班の数は 1 以上" in members_error(teacher_client, course, "count_invalid")


def test_学生0人の授業ではランダム振り分けできない(teacher_client, course, db):
    r = teacher_client.post(f"/courses/{course.id}/teams/random", data={"count": 1})
    assert r.headers["location"].endswith("error=count_invalid")
    assert db.scalar(select(Team)) is None


def test_ランダム振り分けで今より少ない数を指定すると何も消えない(
        teacher_client, make_client, course, db):
    join_students(make_client, course.invite_code, [f"学生{i}" for i in range(4)])
    teacher_client.post(f"/courses/{course.id}/teams/random", data={"count": 3})
    before = sorted((m.user_id, m.team_id) for m in db.scalars(select(TeamMember)))
    r = teacher_client.post(f"/courses/{course.id}/teams/random", data={"count": 2})
    assert r.headers["location"].endswith("error=count_below_teams")
    db.expire_all()
    assert len(list(db.scalars(select(Team)))) == 3
    assert sorted((m.user_id, m.team_id) for m in db.scalars(select(TeamMember))) == before


def test_学生は班の操作ができない403(teacher_client, make_client, course, db):
    clients, t1, t2 = make_two_teams(teacher_client, make_client, course, db)
    a = clients["学生A"]
    uid = db.scalar(select(User.id).where(User.name == "学生B"))
    assert a.post(f"/courses/{course.id}/teams", data={"name": "新"}).status_code == 403
    assert a.post(f"/teams/{t1.id}/rename", data={"name": "改"}).status_code == 403
    assert a.post(f"/teams/{t1.id}/members", data={"user_id": uid}).status_code == 403
    assert a.post(f"/teams/{t1.id}/members/{uid}/remove").status_code == 403
    db.expire_all()
    assert db.get(Team, t1.id).name == "1班"
    assert len(list(db.scalars(select(Team)))) == 2


def test_courseJoinedの中身と二度目の参加で記録が増えない(make_client, course, db):
    c = make_client()
    join(c, course.invite_code, "学生A", "pw-123456")
    events = list(db.scalars(select(Event).where(Event.type == "course.joined")))
    uid = db.scalar(select(User.id).where(User.name == "学生A"))
    assert len(events) == 1
    assert events[0].course_id == course.id and events[0].actor_id == uid
    join(make_client(), course.invite_code, "学生A", "pw-123456")
    assert len(list(db.scalars(select(Event).where(Event.type == "course.joined")))) == 1


def test_1人1班がDBで守られている(teacher_client, make_client, course, db):
    clients, t1, t2 = make_two_teams(teacher_client, make_client, course, db)
    uid = db.scalar(select(User.id).where(User.name == "学生A"))
    db.add(TeamMember(team_id=t2.id, course_id=course.id, user_id=uid))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_班の作成と名前変更がEventに残る(teacher_client, course, db):
    teacher_client.post(f"/courses/{course.id}/teams", data={"name": ""})
    team = db.scalar(select(Team))
    assert team.name == "1班"
    teacher_client.post(f"/teams/{team.id}/rename", data={"name": "赤"})
    events = list(db.scalars(select(Event).where(Event.type.like("team.%")).order_by(Event.id)))
    assert [e.type for e in events] == ["team.created", "team.renamed"]
    assert [e.payload["name"] for e in events] == ["1班", "赤"]


def test_班を削除するルートは無い(teacher_client, course, db):
    teacher_client.post(f"/courses/{course.id}/teams", data={"name": ""})
    team = db.scalar(select(Team))
    assert teacher_client.post(f"/teams/{team.id}/delete").status_code in (404, 405)
    assert teacher_client.delete(f"/teams/{team.id}").status_code in (404, 405)
    assert "/delete" not in teacher_client.get(f"/courses/{course.id}/members").text
    assert db.get(Team, team.id) is not None


def test_Nの自動名は使われていない一番小さい番号(teacher_client, course, db):
    teacher_client.post(f"/courses/{course.id}/teams", data={"name": "2班"})
    teacher_client.post(f"/courses/{course.id}/teams", data={"name": ""})
    teacher_client.post(f"/courses/{course.id}/teams", data={"name": ""})
    names = sorted(t.name for t in db.scalars(select(Team)))
    assert names == ["1班", "2班", "3班"]


def test_知らない通知の鍵は何も出さない(teacher_client, course):
    text = members_error(teacher_client, course, "<script>alert(1)</script>")
    assert "<script>alert" not in text and 'class="error"' not in text


def test_長すぎる名前はエラーで戻る(teacher_client, make_client, course, db):
    r = teacher_client.post(f"/courses/{course.id}/teams", data={"name": "あ" * 101})
    assert r.headers["location"].endswith("error=name_too_long")
    assert db.scalar(select(Team)) is None
    assert teacher_client.post("/courses", data={"name": "あ" * 201}).status_code == 400
    r = join(make_client(), course.invite_code, "あ" * 101, "pw-123456")
    assert r.status_code == 400
    assert 'maxlength="100"' in teacher_client.get(f"/courses/{course.id}/members").text


def test_日時はUTCのタイムゾーン付きで読み出される(make_client, course, db):
    join(make_client(), course.invite_code, "学生A", "pw-123456")
    db.expire_all()
    assert db.get(Course, course.id).created_at.tzinfo is not None
    assert db.get(Course, course.id).created_at.utcoffset().total_seconds() == 0
    event = db.scalar(select(Event))
    assert event.at.tzinfo == timezone.utc


def test_403と404はHTMLの枠で出てhealthzはJSON(teacher_client, make_client, course, db):
    r = teacher_client.get("/courses/9999")
    assert r.status_code == 404 and "見つかりません" in r.text and "rail" in r.text
    s = join_students(make_client, course.invite_code, ["学生A"])["学生A"]
    r = s.get(f"/courses/{course.id}/members")
    assert r.status_code == 403 and "この操作はできません" in r.text
    assert make_client().get("/nothing").status_code == 404
    assert teacher_client.get("/healthz").json() == {"status": "ok"}


def test_CLIでパスワード確認が合わないと作られない(monkeypatch, capsys, db, session_factory):
    answers = iter(["pass-0123456789", "ちがう-0123456789"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(answers))
    monkeypatch.setattr(cli, "SessionLocal", session_factory)
    monkeypatch.setattr(cli, "create_tables", lambda: None)
    assert cli.main(["create-teacher", "--name", "先生D"]) == 1
    assert "一致しません" in capsys.readouterr().err
    assert db.scalar(select(User).where(User.name == "先生D")) is None


def test_CLIで確認が合えば教員が作られる(monkeypatch, db, session_factory):
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": "pass-0123456789")
    monkeypatch.setattr(cli, "SessionLocal", session_factory)
    monkeypatch.setattr(cli, "create_tables", lambda: None)
    assert cli.main(["create-teacher", "--name", "先生D"]) == 0
    assert db.scalar(select(User).where(User.name == "先生D")).role == "teacher"


def test_同時に同じ名前で登録しても500にならない(monkeypatch, make_client, course, db):
    """名前の確認のあとで別の人が先に登録した、という状況を作る。"""
    join(make_client(), course.invite_code, "学生A", "pw-123456")
    import app.routers.auth as auth_module
    real = auth_module.find_user_by_name
    calls = []

    def stale_once(db_, name):
        calls.append(name)
        return None if len(calls) <= 2 else real(db_, name)  # 最初の確認だけ「いない」と見える

    monkeypatch.setattr(auth_module, "find_user_by_name", stale_once)
    ok = join(make_client(), course.invite_code, "学生A", "pw-123456")
    assert ok.status_code == 303  # パスワードが合えばその人として参加
    calls.clear()
    bad = join(make_client(), course.invite_code, "学生A", "ちがうパスワード")
    assert bad.status_code == 400 and "その名前は使われています" in bad.text
