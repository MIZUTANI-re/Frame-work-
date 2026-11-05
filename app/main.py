"""入口。ミドルウェアとルーターを登録する。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import BASE_DIR, get_secret_key
from app.db import create_tables
from app.routers import auth, courses, teams
from app.security import LoginRequired


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()  # 起動時にテーブルを作る
    yield


app = FastAPI(title="Frame-work", lifespan=lifespan)

# セッション Cookie（署名つき）。JavaScript から読めない・他サイトからの POST では送られない設定
app.add_middleware(SessionMiddleware, secret_key=get_secret_key(),
                   session_cookie="session", same_site="lax", https_only=False,
                   max_age=60 * 60 * 24 * 14)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")
app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(teams.router)


@app.exception_handler(LoginRequired)
def login_required_handler(request: Request, exc: LoginRequired):
    """ログインしていない人はログイン画面へ移す。"""
    return RedirectResponse("/login", status_code=303)
