"""DB への接続。"""
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Request
from sqlalchemy import DateTime, MetaData, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from app.config import BASE_DIR, database_url


# 制約の名前の決まり。名前が決まっていると、あとで Alembic が制約を変えたり消したりできる
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """全テーブルの親クラス。"""
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# ※ 未習: SQLAlchemy の TypeDecorator — 列の型に「書き込む前・読み出した後」の変換を足す仕組み
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


def make_migration_engine(url: str):
    """Alembic 用の engine。外部キーの確かめ（PRAGMA）は ON にしない。
    SQLite で「表を作り直す」版（batch 方式）を流すとき、ON のままだと参照している行があって止まるため。
    アプリの接続（make_engine）は ON のままでよい。"""
    return create_engine(url)


def make_engine(url: str):
    """URL から engine を作る。"""
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(dbapi_connection, _):
            # SQLite は外部キーを確かめないのが初期設定なので、PostgreSQL と同じに確かめさせる
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        return engine
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


def upgrade_database() -> None:
    """テーブルを最新にする（alembic upgrade head をプログラムから呼ぶ）。
    テーブルを作るのは Alembic だけ（D-039）。create_all はテストだけで使う。"""
    from alembic import command
    from alembic.config import Config

    config = Config(str(BASE_DIR / "alembic.ini"))
    config.attributes["configure_logger"] = False  # 起動中のアプリのログ設定を壊さない
    command.upgrade(config, "head")
