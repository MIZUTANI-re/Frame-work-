"""テストの共通部品。DB は一時ファイルの SQLite を使い、data/app.db には触らない。"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.cli import create_teacher
from app.db import Base, make_engine
from app.main import app
from app import models  # noqa: F401  （テーブル定義を読み込む）


@pytest.fixture
def session_factory(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def db(session_factory):
    with session_factory() as session:
        yield session


@pytest.fixture
def make_client(session_factory):
    """ブラウザ 1 台ぶんのクライアントを作る関数。台ごとに Cookie が別になる。"""
    original = app.state.session_factory
    app.state.session_factory = session_factory  # 一時ファイルの DB を使わせる
    clients = []

    def make() -> TestClient:
        # with を使わない → 起動処理（本物の DB へのテーブル作成）は走らない
        client = TestClient(app, follow_redirects=False)
        clients.append(client)
        return client

    yield make
    for c in clients:
        c.close()
    app.state.session_factory = original


TEACHER_PW = "pass-a-0123456"


def login(client, name, password):
    return client.post("/login", data={"name": name, "password": password})


def join(client, code, name, password):
    return client.post("/join", data={"code": code, "name": name, "password": password})


@pytest.fixture
def teacher(db):
    return create_teacher(db, "先生A", TEACHER_PW)


@pytest.fixture
def teacher_client(make_client, teacher):
    client = make_client()
    assert login(client, "先生A", TEACHER_PW).status_code == 303
    return client


@pytest.fixture
def course(teacher_client, db):
    """先生A が作った授業。"""
    from app.models import Course
    r = teacher_client.post("/courses", data={"name": "経営戦略論"})
    assert r.status_code == 303
    return db.get(Course, int(r.headers["location"].rsplit("/", 1)[1]))
