"""設定。環境変数か、プロジェクト直下の .env から読む。"""
import os
import warnings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEV_SECRET_KEY = "dev-only-secret-key-change-me"


def _read_dotenv() -> dict[str, str]:
    """.env の「キー=値」の行を読む（簡易版）。"""
    path = BASE_DIR / ".env"
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _get(name: str, default: str) -> str:
    """環境変数 → .env → 既定値 の順に探す。"""
    return os.environ.get(name) or _read_dotenv().get(name) or default


def get_secret_key() -> str:
    key = _get("SECRET_KEY", "")
    if not key:
        warnings.warn("SECRET_KEY が設定されていません。開発用の値を使います（本番では必ず設定してください）。")
        return DEV_SECRET_KEY
    return key


DATABASE_URL = _get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'app.db'}")
