"""コマンド。教員アカウントはここから作る（画面から教員になれる穴を作らないため）。

使い方: python -m app.cli create-teacher --name 山田
"""
import argparse
import getpass
import sys

from sqlalchemy.orm import Session

from app.db import SessionLocal, create_tables
from app.models import USER_NAME_MAX, User
from app.queries import find_user_by_name
from app.security import MIN_PASSWORD_LENGTH, hash_password, password_too_short


def create_teacher(db: Session, name: str, password: str) -> User:
    """教員を 1 人作る。テストからも直接呼べるよう、入力の処理とは分けてある。"""
    name = name.strip()
    if not name or not password:
        raise ValueError("名前とパスワードを入力してください")
    if len(name) > USER_NAME_MAX:
        raise ValueError(f"名前は {USER_NAME_MAX} 文字までです")
    if password_too_short("teacher", password):
        raise ValueError(f"パスワードは {MIN_PASSWORD_LENGTH['teacher']} 文字以上にしてください")
    if find_user_by_name(db, name) is not None:
        raise ValueError("その名前は使われています")
    user = User(name=name, role="teacher", password_hash=hash_password(password))
    db.add(user)
    db.commit()
    return user


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    teacher = sub.add_parser("create-teacher", help="教員アカウントを作る")
    teacher.add_argument("--name", required=True, help="教員の名前（ログイン名）")
    args = parser.parse_args(argv)

    # パスワードは画面に出さずに対話で入力する（コマンドの履歴に残さない）
    password = getpass.getpass("パスワード: ")
    if password != getpass.getpass("パスワード（確認）: "):
        print("パスワードが一致しません", file=sys.stderr)
        return 1

    create_tables()
    with SessionLocal() as db:
        try:
            create_teacher(db, args.name, password)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 1
    print(f"教員「{args.name.strip()}」を作りました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
