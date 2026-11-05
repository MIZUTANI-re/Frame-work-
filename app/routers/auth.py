"""ログイン・ログアウト・授業への参加（F-02・F-04）。"""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.events import record_event
from app.models import Course, Enrollment, User
from app.security import get_current_user, hash_password, verify_password
from app.templating import courses_of, render

router = APIRouter()


def redirect(url: str) -> RedirectResponse:
    # 303 にすると、POST のあとブラウザが GET で移動してくれる
    return RedirectResponse(url, status_code=303)


def login_user(request: Request, user: User) -> None:
    """ログイン状態にする。前のセッションの中身は捨てる。"""
    request.session.clear()
    request.session["user_id"] = user.id


# ※ 未習: FastAPI のルーティング — @router.get / @router.post で「この URL に来たらこの関数」を決める
@router.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    """ログイン後の最初の行き先を決める。"""
    user_id = request.session.get("user_id")
    user = db.get(User, user_id) if user_id else None
    if user is None:
        return redirect("/login")
    courses = courses_of(db, user)
    if courses:
        return redirect(f"/courses/{courses[0].id}")
    return redirect("/courses/new" if user.role == "teacher" else "/join")


@router.get("/login")
def login_form(request: Request, db: Session = Depends(get_db)):
    return render(request, db, "login.html", error=None)


@router.post("/login")
def login(request: Request, name: str = Form(""), password: str = Form(""),
          db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.name == name.strip()))
    if user is None or not verify_password(password, user.password_hash):
        # 名前が無いのかパスワードが違うのかは教えない
        return render(request, db, "login.html", error="名前かパスワードが違います",
                      status_code=400)
    login_user(request, user)
    return redirect("/")


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return redirect("/login")


@router.get("/join")
def join_form(request: Request, db: Session = Depends(get_db)):
    return render(request, db, "join.html", error=None, form={})


def join_error(request: Request, db: Session, message: str, code: str, name: str):
    return render(request, db, "join.html", error=message,
                  form={"code": code, "name": name}, status_code=400)


@router.post("/join")
def join(request: Request, code: str = Form(""), name: str = Form(""),
         password: str = Form(""), db: Session = Depends(get_db)):
    """招待コード + 名前 + パスワードで授業に参加する（初めてなら学生として登録）。"""
    code = code.strip().upper()
    name = name.strip()
    course = db.scalar(select(Course).where(Course.invite_code == code))
    if course is None:
        return join_error(request, db, "招待コードが正しくありません", code, name)
    if not name or not password:
        return join_error(request, db, "名前とパスワードを入力してください", code, name)

    user = db.scalar(select(User).where(User.name == name))
    if user is None:
        user = User(name=name, role="student", password_hash=hash_password(password))
        db.add(user)
        db.flush()  # id を確定させる
    elif user.role != "student" or not verify_password(password, user.password_hash):
        return join_error(request, db, "その名前は使われています", code, name)

    already = db.scalar(select(Enrollment.id).where(
        Enrollment.course_id == course.id, Enrollment.user_id == user.id))
    if already is None:
        db.add(Enrollment(course_id=course.id, user_id=user.id))
        record_event(db, "course.joined", actor_id=user.id, course_id=course.id)
    db.commit()

    login_user(request, user)
    return redirect(f"/courses/{course.id}")
