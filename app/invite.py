"""招待コードの生成。"""
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Course

# 紛らわしい文字（0・O・1・I・L）を除いた、英大文字と数字
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6


def generate_code() -> str:
    """6 文字のコードを 1 つ作る。"""
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def generate_unique_code(db: Session) -> str:
    """他の授業と重ならないコードを作る。"""
    while True:
        code = generate_code()
        if db.scalar(select(Course.id).where(Course.invite_code == code)) is None:
            return code
