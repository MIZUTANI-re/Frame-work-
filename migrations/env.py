"""Alembic の実行環境。DB の場所は環境変数 DATABASE_URL から読み、
テーブルの形は app/models.py と比べて作る。"""
# ※ 未習: Alembic — テーブルの変更を「版」のファイルにして順に流す仕組み。入っているデータを消さずにテーブルを変えられる
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app import models  # noqa: F401  （テーブル定義を読み込む）
from app.config import database_url
from app.db import Base, ensure_db_dir

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_online() -> None:
    url = database_url()
    ensure_db_dir(url)
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations_online()
