"""DB への接続。"""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import BASE_DIR, DATABASE_URL


class Base(DeclarativeBase):
    """全テーブルの親クラス。"""


def make_engine(url: str):
    """URL から engine を作る。SQLite のときは data/ フォルダも用意する。"""
    if url.startswith("sqlite"):
        (BASE_DIR / "data").mkdir(exist_ok=True)
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url)


engine = make_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """リクエストごとに DB セッションを渡し、終わったら閉じる。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    """テーブルが無ければ作る（起動時に呼ぶ）。"""
    from app import models  # noqa: F401  （テーブル定義を読み込むために必要）

    Base.metadata.create_all(engine)
