"""ログイン・ログアウト・授業への参加（F-02・F-04）。"""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.events import record_event
from app.models import USER_NAME_MAX, Course, Enrollment, User
from app.queries import find_user_by_name
from app.security import (MIN_PASSWORD_LENGTH, check_password_with_lock, get_user_or_none,
                          hash_password, password_too_short)
from app.templating import courses_of, render

router = APIRouter()

LOCKED_MESSAGE = "何度もまちがえたため、しばらくログインできません。時間をおいてやり直してください"

def redirect(url: str) -> RedirectResponse:
    # 303 にすると、POST のあとブラウザが GET で移動してくれる
    return RedirectResponse(url, status_code=303)


def login_user(request: Request, user: User) -> None:
    """ログイン状態にする。前のセッションの中身は捨てる。版を入れておき、ログアウトで古い Cookie を無効にする。"""
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["sv"] = user.session_version


# ※ 未習: FastAPI のルーティング — @router.get / @router.post で「この URL に来たらこの関数」を決める
@router.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    """ログイン後の最初の行き先を決める。"""
    user = get_user_or_none(request, db)
    if user is None:
        return redirect("/login")
    courses = courses_of(db, user)
    if courses:
        return redirect(f"/courses/{courses[0].id}")
    return redirect("/courses/new" if user.role == "teacher" else "/join")


@router.get("/login")
def login_form(request: Request, db: Session = Depends(get_db)):
    return render(request, db, "login.html", error=None)


def login_error(request: Request, db: Session, message: str, status_code: int = 400):
    return render(request, db, "login.html", error=message, status_code=status_code)


@router.post("/login")
def login(request: Request, name: str = Form(""), password: str = Form(""),
          db: Session = Depends(get_db)):
    user = find_user_by_name(db, name.strip())
    result = check_password_with_lock(db, user, password) if user is not None else "wrong"
    if result == "locked":
        # 止まっている間は、正しいパスワードでも入れない
        return login_error(request, db, LOCKED_MESSAGE, status_code=429)
    if result == "wrong":
        # 名前が無いのかパスワードが違うのかは教えない
        return login_error(request, db, "名前かパスワードが違います")
    login_user(request, user)
    return redirect("/")


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    """ログアウト。セッションの版を上げて、前の Cookie も使えなくする。"""
    user = get_user_or_none(request, db)
    if user is not None:
        user.session_version += 1
        db.commit()
    request.session.clear()
    return redirect("/login")


@router.get("/join")
def join_form(request: Request, db: Session = Depends(get_db)):
    return render(request, db, "join.html", error=None, form={})


def join_error(request: Request, db: Session, message: str, code: str, name: str,
               status_code: int = 400):
    return render(request, db, "join.html", error=message,
                  form={"code": code, "name": name}, status_code=status_code)


def get_or_create_student(db: Session, name: str, password: str) -> tuple[User | None, str | None]:
    """名前の学生を返す。いなければ登録する。(学生, 問題) を返し、問題は次のどれか。
      None      … 問題なし
      "taken"   … 名前が使われている（教員、またはパスワードが違う）
      "locked"  … その学生はログインが止まっている
    同時に同じ名前で登録しようとして一意制約に当たったら、名前の確認からやり直す。"""
    user = find_user_by_name(db, name)
    if user is None:
        try:
            user = User(name=name, role="student", password_hash=hash_password(password))
            db.add(user)
            db.commit()
            return user, None
        # ※ 未習: IntegrityError と rollback — 一意制約に当たった失敗を捕まえ、DB の変更を取り消してやり直す
        except IntegrityError:
            db.rollback()
            user = find_user_by_name(db, name)
    if user is None or user.role != "student":
        return None, "taken"
    # すでにいる学生のパスワード確認も、ログインと同じ止まりの判定を通す（D-040）
    result = check_password_with_lock(db, user, password)
    if result == "locked":
        return None, "locked"
    return (user, None) if result == "ok" else (None, "taken")


def enroll(db: Session, course_id: int, user_id: int) -> None:
    """授業に参加させる。すでに参加済み（同時の参加を含む）なら何もしない。"""
    already = db.scalar(select(Enrollment.id).where(
        Enrollment.course_id == course_id, Enrollment.user_id == user_id))
    if already is not None:
        return
    try:
        db.add(Enrollment(course_id=course_id, user_id=user_id))
        record_event(db, "course.joined", actor_id=user_id, course_id=course_id)
        db.commit()
    except IntegrityError:
        db.rollback()  # 同時に参加済みになった。記録も取り消す（記録は相手が残している）


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
    if len(name) > USER_NAME_MAX:
        return join_error(request, db, f"名前は {USER_NAME_MAX} 文字までです", code, name)
    course_id = course.id
    # 長さを確かめるのは、新しく登録する人だけ。すでにいる人は、昔の決まりで作ったパスワードかもしれず、
    # ここで長さを理由に断ると、合っているパスワードでも入れなくなるため。
    if find_user_by_name(db, name) is None and password_too_short("student", password):
        return join_error(request, db,
                          f"パスワードは {MIN_PASSWORD_LENGTH['student']} 文字以上にしてください", code, name)

    user, problem = get_or_create_student(db, name, password)
    if problem == "locked":
        return join_error(request, db, LOCKED_MESSAGE, code, name, status_code=429)
    if user is None:
        return join_error(request, db, "その名前は使われています", code, name)
    enroll(db, course_id, user.id)

    login_user(request, user)
    return redirect(f"/courses/{course_id}")
