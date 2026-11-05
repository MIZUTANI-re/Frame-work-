"""ステップ 1.5（公開の準備）の完了の条件を確かめるテスト。"""
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select

import app.security as security_module
from app import cli
from app.config import get_secret_key
from app.db import Base
from app.main import create_app
from app.models import User, now
from tests.conftest import TEACHER_PW, join, login

ROOT = Path(__file__).resolve().parent.parent


def test_productionでSECRET_KEYが無いと起動が止まる(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setattr("app.config._read_dotenv", lambda: {})
    with pytest.raises(RuntimeError):
        get_secret_key()
    with pytest.raises(RuntimeError):
        create_app()


def test_productionでSECRET_KEYがあれば起動できる(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    create_app()


def test_COOKIE_SECUREが1ならSet_CookieにSecureが付く(monkeypatch, session_factory, teacher):
    monkeypatch.setenv("COOKIE_SECURE", "1")
    secure_app = create_app()
    secure_app.state.session_factory = session_factory
    client = TestClient(secure_app, follow_redirects=False)
    r = login(client, "先生A", TEACHER_PW)
    assert r.status_code == 303
    assert "secure" in r.headers["set-cookie"].lower()


def test_COOKIE_SECUREが0ならSecureは付かない(teacher_client, make_client, teacher):
    r = login(make_client(), "先生A", TEACHER_PW)
    assert "secure" not in r.headers["set-cookie"].lower()


def test_productionでは_docsが404(monkeypatch, session_factory):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    prod = create_app()
    prod.state.session_factory = session_factory
    client = TestClient(prod)
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/healthz").status_code == 200


def test_developmentでは_docsが開ける(make_client):
    assert make_client().get("/docs").status_code == 200


def test_healthzはログイン不要でokを返す(make_client):
    r = make_client().get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_healthzはDBに届かないと503(make_client, session_factory):
    from app.main import app
    from sqlalchemy.orm import sessionmaker
    bad = sessionmaker(bind=create_engine("sqlite:////nonexistent-dir/x/y.db"))
    app.state.session_factory = bad
    try:
        assert make_client().get("/healthz").status_code == 503
    finally:
        app.state.session_factory = session_factory


def test_alembicで空のDBにモデルと同じテーブルができる(tmp_path, monkeypatch):
    db_path = tmp_path / "migrated.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    engine = create_engine(f"sqlite:///{db_path}")
    tables = set(inspect(engine).get_table_names())
    assert set(Base.metadata.tables) <= tables
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []  # モデルと食い違いが無い


def test_パスワードの最低の長さ(db, make_client, course):
    with pytest.raises(ValueError):
        cli.create_teacher(db, "先生X", "a" * 9)
    cli.create_teacher(db, "先生X", "a" * 10)
    assert join(make_client(), course.invite_code, "学生X", "12345").status_code == 400
    assert join(make_client(), course.invite_code, "学生X", "123456").status_code == 303


def test_5回まちがえると5分止まり正しいパスワードでも入れない(
        monkeypatch, make_client, teacher, db):
    c = make_client()
    start = now()
    monkeypatch.setattr(security_module, "now", lambda: start)
    for _ in range(5):
        assert login(c, "先生A", "まちがい").status_code == 400
    assert login(c, "先生A", TEACHER_PW).status_code == 429  # 止まっている
    # 4 分後もまだ止まっている
    monkeypatch.setattr(security_module, "now", lambda: start + timedelta(minutes=4))
    assert login(c, "先生A", TEACHER_PW).status_code == 429
    # 5 分すぎると入れる
    monkeypatch.setattr(security_module, "now", lambda: start + timedelta(minutes=5, seconds=1))
    assert login(c, "先生A", TEACHER_PW).status_code == 303
    db.expire_all()
    assert db.scalar(select(User).where(User.name == "先生A")).failed_logins == 0


def test_4回まちがえても成功すれば数え直す(make_client, teacher):
    c = make_client()
    for _ in range(4):
        login(c, "先生A", "まちがい")
    assert login(c, "先生A", TEACHER_PW).status_code == 303
    for _ in range(4):
        login(c, "先生A", "まちがい")
    assert login(c, "先生A", TEACHER_PW).status_code == 303


def test_ログアウトしたあと前のCookieでは開けない(make_client, teacher_client, course):
    old_cookies = dict(teacher_client.cookies)
    assert teacher_client.get(f"/courses/{course.id}/settings").status_code == 200
    teacher_client.post("/logout")
    replay = make_client()
    for k, v in old_cookies.items():
        replay.cookies.set(k, v)
    r = replay.get(f"/courses/{course.id}")
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_DBのフォルダはimportでは作られない(tmp_path):
    target = tmp_path / "sub"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{target}/a.db"}
    out = subprocess.run([sys.executable, "-c", "import app.db, app.main"], cwd=ROOT,
                         env=env, capture_output=True, text=True)
    assert out.returncode == 0
    assert not target.exists()


# ---- 2 回目のレビューの修正 ----
import threading

from app.models import Event, TeamMember
from app.security import check_password_with_lock, unlock_user
from tests.test_step1 import join_students


def student_in(db, name):
    return db.scalar(select(User).where(User.name == name))


def test_joinでまちがえても数えられる(make_client, course, db):
    join_students(make_client, course.invite_code, ["学生A"])
    for _ in range(3):
        assert join(make_client(), course.invite_code, "学生A", "ちがう-123456").status_code == 400
    db.expire_all()
    assert student_in(db, "学生A").failed_logins == 3


def test_joinで5回まちがえると止まり正しいパスワードでも入れない(make_client, course, db):
    join_students(make_client, course.invite_code, ["学生A"])
    for _ in range(5):
        join(make_client(), course.invite_code, "学生A", "ちがう-123456")
    r = join(make_client(), course.invite_code, "学生A", "pw-学生A")
    assert r.status_code == 429
    assert login(make_client(), "学生A", "pw-学生A").status_code == 429


def test_loginで止まった学生は正しいパスワードのjoinでも入れない(make_client, course, db):
    join_students(make_client, course.invite_code, ["学生A"])
    for _ in range(5):
        login(make_client(), "学生A", "ちがう-123456")
    assert join(make_client(), course.invite_code, "学生A", "pw-学生A").status_code == 429


def test_同時のまちがいが取りこぼされず数えられる(session_factory, teacher):
    n = 4  # 止まる回数（5）より少なくして、数だけを確かめる
    barrier = threading.Barrier(n)
    results = []

    def attempt():
        with session_factory() as s:
            user = s.scalar(select(User).where(User.name == "先生A"))
            barrier.wait()
            results.append(check_password_with_lock(s, user, "まちがい"))

    threads = [threading.Thread(target=attempt) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == ["wrong"] * n
    with session_factory() as s:
        assert s.scalar(select(User.failed_logins).where(User.name == "先生A")) == n


def test_班が学生より多くても同じ数なら振り分けられる(teacher_client, make_client, course, db):
    join_students(make_client, course.invite_code, ["学生A", "学生B"])
    for _ in range(3):
        teacher_client.post(f"/courses/{course.id}/teams", data={"name": ""})
    r = teacher_client.post(f"/courses/{course.id}/teams/random", data={"count": 3})
    assert r.headers["location"] == f"/courses/{course.id}/members"
    db.expire_all()
    assert len(list(db.scalars(select(TeamMember)))) == 2
    # 4 は学生の人数より多く、今の班の数とも違うので断る
    r = teacher_client.post(f"/courses/{course.id}/teams/random", data={"count": 4})
    assert r.headers["location"].endswith("error=count_over_students")
    # 2 は今の班の数（3）より少ないので断る
    r = teacher_client.post(f"/courses/{course.id}/teams/random", data={"count": 2})
    assert r.headers["location"].endswith("error=count_below_teams")


def test_教員が学生の止まりを解ける(teacher_client, make_client, course, db):
    join_students(make_client, course.invite_code, ["学生A"])
    for _ in range(5):
        login(make_client(), "学生A", "ちがう-123456")
    page = teacher_client.get(f"/courses/{course.id}/members").text
    assert "止まりを解く" in page
    uid = student_in(db, "学生A").id
    assert teacher_client.post(f"/courses/{course.id}/students/{uid}/unlock").status_code == 303
    assert login(make_client(), "学生A", "pw-学生A").status_code == 303
    event = db.scalar(select(Event).where(Event.type == "user.unlocked"))
    assert event.payload["user_id"] == uid and event.course_id == course.id


def test_学生と担当外の教員は止まりを解けない(teacher_client, make_client, course, db):
    clients = join_students(make_client, course.invite_code, ["学生A", "学生B"])
    uid = student_in(db, "学生B").id
    assert clients["学生A"].post(f"/courses/{course.id}/students/{uid}/unlock").status_code == 403
    cli.create_teacher(db, "先生B", "pass-b-0123456")
    other = make_client()
    login(other, "先生B", "pass-b-0123456")
    assert other.post(f"/courses/{course.id}/students/{uid}/unlock").status_code == 404
    # その授業の学生でない人は、担当の教員でも解けない
    outsider = cli.create_teacher(db, "先生C", "pass-c-0123456")
    assert teacher_client.post(f"/courses/{course.id}/students/{outsider.id}/unlock").status_code == 404


def test_unlockコマンド(db, teacher, monkeypatch, session_factory):
    for _ in range(5):
        check_password_with_lock(db, teacher, "まちがい")
    db.expire_all()
    assert security_module.is_locked(db.get(User, teacher.id))
    monkeypatch.setattr(cli, "SessionLocal", session_factory)
    monkeypatch.setattr(cli, "upgrade_database", lambda: None)
    assert cli.main(["unlock", "--name", "先生A"]) == 0
    assert cli.main(["unlock", "--name", "いない人"]) == 1
    db.expire_all()
    assert not security_module.is_locked(db.get(User, teacher.id))
    assert db.scalar(select(Event).where(Event.type == "user.unlocked")) is not None


def test_開発用の鍵は呼ぶたびに変わる乱数(monkeypatch):
    monkeypatch.setattr("app.config._read_dotenv", lambda: {})
    monkeypatch.delenv("SECRET_KEY")
    with pytest.warns(UserWarning):
        a = get_secret_key()
        b = get_secret_key()
    assert a != b and len(a) >= 32


def test_APP_ENVが知らない値なら起動が止まる(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    with pytest.raises(RuntimeError):
        create_app()


def test_405も画面の枠で出る(teacher_client):
    r = teacher_client.get("/logout")
    assert r.status_code == 405 and "見つかりません" in r.text


def test_AlembicだけでテーブルができCLIとlifespanが使える(tmp_path, monkeypatch):
    from app.db import upgrade_database
    path = tmp_path / "d" / "x.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{path}")
    upgrade_database()
    upgrade_database()  # 2 回かけても落ちない
    assert "users" in inspect(create_engine(f"sqlite:///{path}")).get_table_names()


def test_外部キーがSQLiteでも確かめられる(session_factory):
    from app.models import Enrollment
    from sqlalchemy.exc import IntegrityError
    with session_factory() as s:
        s.add(Enrollment(course_id=999, user_id=999))
        with pytest.raises(IntegrityError):
            s.flush()


# ---- 3 回目のレビューの修正 ----
def test_外部キーONの接続だと表の作り直しで止まるがAlembic用の接続なら通り行が残る(tmp_path, monkeypatch):
    import sqlalchemy as sa
    from alembic import op
    from alembic.operations import Operations
    from app.db import make_engine, make_migration_engine

    def prepare(name):
        """0001 まで上げ、users と courses に行を入れた DB の URL を返す。"""
        url = f"sqlite:///{tmp_path / name}"
        monkeypatch.setenv("DATABASE_URL", url)
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
        with make_migration_engine(url).begin() as conn:
            conn.execute(sa.text("INSERT INTO users (name, role, password_hash, created_at, failed_logins, session_version)"
                                 " VALUES ('先生', 'teacher', 'h', '2026-01-01 00:00:00', 0, 0)"))
            conn.execute(sa.text("INSERT INTO courses (name, teacher_id, invite_code, created_at)"
                                 " VALUES ('授業', 1, 'ABCDEF', '2026-01-01 00:00:00')"))
        return url

    def rebuild_users(engine):
        """users を作り直す（batch 方式）。Alembic の env.py と同じ流れ。"""
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn, opts={"render_as_batch": True})
            with ctx.begin_transaction():
                with Operations.context(ctx):
                    with op.batch_alter_table("users", recreate="always") as batch:
                        batch.add_column(sa.Column("tmp_col", sa.Integer(), nullable=True))

    with pytest.raises(Exception):
        rebuild_users(make_engine(prepare("fk_on.db")))  # 外部キー ON（アプリの接続）では止まる
    url = prepare("fk_off.db")
    plain = make_migration_engine(url)
    rebuild_users(plain)  # Alembic 用の接続なら通る
    with plain.connect() as conn:
        assert conn.execute(sa.text("SELECT name FROM users")).scalar() == "先生"
        assert conn.execute(sa.text("SELECT name FROM courses")).scalar() == "授業"


def test_止まるときは回数を戻さず過ぎたあとの最初の確かめで戻す(monkeypatch, make_client, teacher, db):
    c = make_client()
    start = now()
    monkeypatch.setattr(security_module, "now", lambda: start)
    for _ in range(5):
        login(c, "先生A", "まちがい")
    db.expire_all()
    u = db.scalar(select(User).where(User.name == "先生A"))
    assert u.failed_logins == 5 and u.locked_until is not None
    monkeypatch.setattr(security_module, "now", lambda: start + timedelta(minutes=6))
    assert login(c, "先生A", "まちがい").status_code == 400  # 止まりは終わり、数え直して 1 回目
    db.expire_all()
    u = db.scalar(select(User).where(User.name == "先生A"))
    assert u.failed_logins == 1 and u.locked_until is None


def test_止まりの判定は照合の直前にDBから読み直す(session_factory, teacher):
    """古い User オブジェクトを持っていても、別の取引で止められていれば locked になる。"""
    with session_factory() as a, session_factory() as b:
        stale = a.scalar(select(User).where(User.name == "先生A"))
        for _ in range(5):
            check_password_with_lock(b, b.scalar(select(User).where(User.name == "先生A")), "x")
        assert stale.locked_until is None  # a の手元はまだ古い
        assert check_password_with_lock(a, stale, TEACHER_PW) == "locked"


def test_別のフォルダにいてもupgrade_databaseが動く(tmp_path, monkeypatch):
    from app.db import upgrade_database
    path = tmp_path / "cwd.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{path}")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    upgrade_database()
    assert "users" in inspect(create_engine(f"sqlite:///{path}")).get_table_names()


def test_班の数の通知には今の数が入る(teacher_client, make_client, course):
    join_students(make_client, course.invite_code, ["学生A", "学生B"])
    for _ in range(3):
        teacher_client.post(f"/courses/{course.id}/teams", data={"name": ""})
    text = teacher_client.get(f"/courses/{course.id}/members?error=count_below_teams").text
    assert "今の班は 3 つ、学生は 2 人です" in text and "3 を指定すると振り分けられます" in text


def test_SECRET_KEYが無いときの文に置き場所が出る(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SECRET_KEY")
    monkeypatch.setattr("app.config._read_dotenv", lambda: {})
    with pytest.raises(RuntimeError, match="deploy.env"):
        get_secret_key()
