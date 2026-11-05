"""DB への接続。"""
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Request
from sqlalchemy import DateTime, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from app.config import database_url


class Base(DeclarativeBase):
    """全テーブルの親クラス。"""


class UTCDateTime(TypeDecorator):
    """日時はすべて UTC で持つ型（D-027）。
    書き込むときは UTC にそろえ、読み出すときは必ず「UTC のタイムゾーン付き」にする。
    SQLite はタイムゾーンを覚えないので、付けていない値は UTC とみなす。"""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def ensure_db_dir(url: str) -> None:
    """SQLite のファイルを置くフォルダを用意する（import 時ではなく起動時に呼ぶ）。"""
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite" and parsed.database not in (None, "", ":memory:"):
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)


def make_engine(url: str):
    """URL から engine を作る。"""
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url)


engine = make_engine(database_url())
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db(request: Request) -> Iterator[Session]:
    """リクエストごとに DB セッションを渡し、終わったら閉じる。
    使うセッション工場は app.state にある（テストでは差し替える）。"""
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    """テーブルが無ければ作る（development の起動時。production は Alembic が作る）。"""
    from app import models  # noqa: F401  （テーブル定義を読み込むために必要）

    ensure_db_dir(str(engine.url))
    Base.metadata.create_all(engine)
