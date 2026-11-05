"""入口。ミドルウェアとルーターを登録する。"""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.config import BASE_DIR, cookie_secure, get_secret_key, is_production
from app.db import SessionLocal, get_db, upgrade_database
from app import framework_defs  # noqa: F401  （定義ファイルを読む。仕様に合わなければここで起動が止まる）
from app.routers import auth, boards, courses, frameworks, teams
from app.security import LoginRequired, get_user_or_none
from app.templating import render

# JSON のまま返す URL（画面ではないもの）
JSON_PATHS = ("/healthz", "/openapi.json", "/docs")
ERROR_TEXTS = {
    403: ("この操作はできません", "この操作をする権限がありません。"),
    404: ("見つかりません", "ページが見つからないか、見る権限がありません。"),
    405: ("見つかりません", "ページが見つからないか、見る権限がありません。"),
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not is_production():
        upgrade_database()  # 開発中は起動時に Alembic でテーブルを最新にする（production は scripts/start.sh がやる）
    yield


def create_app() -> FastAPI:
    """アプリを組み立てる。設定（環境変数）はここで読む。"""
    production = is_production()
    app = FastAPI(title="Frame-work", lifespan=lifespan,
                  docs_url=None if production else "/docs",
                  redoc_url=None if production else "/redoc",
                  openapi_url=None if production else "/openapi.json")
    app.state.session_factory = SessionLocal

    # セッション Cookie（署名つき）。JavaScript から読めない・他サイトからの POST では送られない設定。
    # COOKIE_SECURE=1 のときは HTTPS のときだけ Cookie を送る
    app.add_middleware(SessionMiddleware, secret_key=get_secret_key(),
                       session_cookie="session", same_site="lax",
                       https_only=cookie_secure(), max_age=60 * 60 * 24 * 14)

    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")
    app.include_router(auth.router)
    app.include_router(courses.router)
    app.include_router(frameworks.router)
    app.include_router(teams.router)
    app.include_router(boards.router)

    @app.get("/healthz")
    def healthz(db: Session = Depends(get_db)):
        """生きているかの確認（ログイン不要）。DB に軽い問い合わせをする。"""
        try:
            db.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse({"status": "error"}, status_code=503)
        return {"status": "ok"}

    @app.exception_handler(LoginRequired)
    def login_required_handler(request: Request, exc: LoginRequired):
        """ログインしていない人はログイン画面へ移す。"""
        return RedirectResponse("/login", status_code=303)

    @app.exception_handler(StarletteHTTPException)
    def http_error_handler(request: Request, exc: StarletteHTTPException):
        """403・404・405 は Teams 風の枠の中に出す。それ以外と JSON の URL は標準のまま。"""
        if exc.status_code not in ERROR_TEXTS or request.url.path.startswith(JSON_PATHS):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code,
                                headers=getattr(exc, "headers", None))
        title, message = ERROR_TEXTS[exc.status_code]
        with request.app.state.session_factory() as db:
            user = get_user_or_none(request, db)
            return render(request, db, "error.html", user=user, title=title,
                          message=message, status_code=exc.status_code)

    return app


app = create_app()
