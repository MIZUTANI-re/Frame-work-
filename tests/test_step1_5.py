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

import app.routers.auth as auth_module
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
    monkeypatch.setattr(auth_module, "now", lambda: start)
    for _ in range(5):
        assert login(c, "先生A", "まちがい").status_code == 400
    assert login(c, "先生A", TEACHER_PW).status_code == 429  # 止まっている
    # 4 分後もまだ止まっている
    monkeypatch.setattr(auth_module, "now", lambda: start + timedelta(minutes=4))
    assert login(c, "先生A", TEACHER_PW).status_code == 429
    # 5 分すぎると入れる
    monkeypatch.setattr(auth_module, "now", lambda: start + timedelta(minutes=5, seconds=1))
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
    assert teacher_client.get(f"/courses/{course.id}").status_code == 200
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
