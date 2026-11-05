"""設定。環境変数か、プロジェクト直下の .env から読む。
置き場所（PC・Azure）で変わる値は、すべて環境変数だけで変える（M-2）。"""
# ※ 未習: 環境変数 — プログラムの外（OS・Docker）から渡す設定値。コードを変えずに置き場所ごとの違いを渡せる
import os
import secrets
import warnings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
APP_ENVS = ("development", "production")


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
    """環境変数 → .env → 既定値 の順に探す（呼ばれるたびに読む）。"""
    return os.environ.get(name) or _read_dotenv().get(name) or default


def app_env() -> str:
    """development か production。それ以外は打ちまちがいとみなして止める。"""
    env = _get("APP_ENV", "development")
    if env not in APP_ENVS:
        raise RuntimeError(f"APP_ENV は {' か '.join(APP_ENVS)} にしてください（今: {env!r}）")
    return env


def is_production() -> bool:
    return app_env() == "production"


def cookie_secure() -> bool:
    """Cookie を HTTPS のときだけ送るか（COOKIE_SECURE=1）。"""
    return _get("COOKIE_SECURE", "0") == "1"


def database_url() -> str:
    return _get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'app.db'}")


def get_secret_key() -> str:
    """Cookie の署名鍵。production で無ければ起動を止める。"""
    key = _get("SECRET_KEY", "")
    if key:
        return key
    if is_production():
        raise RuntimeError("APP_ENV=production では SECRET_KEY が必要です。箱（docker compose）で動かすなら deploy.env、手元なら .env か環境変数に書いてください")
    # 開発用の鍵は起動のたびに作る乱数（固定の値を公開リポジトリに置かない）。再起動するとログインは外れる
    warnings.warn("SECRET_KEY が設定されていません。起動のたびに変わる開発用の鍵を使います。")
    return secrets.token_urlsafe(32)
