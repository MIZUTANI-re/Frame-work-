"""パスワード・ログイン中のユーザー・権限チェック。
権限のチェックはすべてここにまとめ、各ルートから使う。

404 と 403 の使い分け:
- 404: 存在を知られたくないもの（他の班・担当外の授業）
- 403: 存在は知っていてよいが操作できないもの（学生がメンバー管理を開く）
"""
from datetime import timedelta

from fastapi import Depends, HTTPException, Request
from pwdlib import PasswordHash
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.events import record_event
from app.models import Course, Enrollment, Team, TeamMember, User, now

# パスワードの最低の長さ（D-029）
MIN_PASSWORD_LENGTH = {"teacher": 10, "student": 6}

# ※ 未習: argon2 のハッシュ化 — パスワードを元に戻せない文字列に変えて保存する方法
_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _hasher.verify(password, password_hash)


# ログインの総当たり対策（D-029）：5 回続けてまちがえたら 5 分止める
MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 5


def is_locked(user: User) -> bool:
    return user.locked_until is not None and user.locked_until > now()


def check_password_with_lock(db: Session, user: User, password: str) -> str:
    """パスワードを確かめる（止まりの判定つき）。パスワードを確かめる所はすべてこれを通す（D-040）。
    返す値：
      "locked" … 止まっている（正しいパスワードでも入れない）
      "ok"     … 合っている（まちがいの数をゼロに戻す）
      "wrong"  … まちがい（数を 1 増やし、5 回目で止める）。止まりが過ぎたあとの最初の確かめでは、数をゼロに戻してから始める
    数えるのは DB の 1 回の UPDATE。同時に送られても、数が取りこぼされない。"""
    db.refresh(user)  # 止まっているかは、照合の直前に DB から読み直した値で決める
    if is_locked(user):
        return "locked"
    if user.locked_until is not None:
        # 止まりの時刻が過ぎてから最初の確かめ：ここでまちがいの数をゼロに戻す
        db.execute(update(User).where(User.id == user.id, User.locked_until <= now())
                   .values(failed_logins=0, locked_until=None))
        db.commit()
        db.refresh(user)
    if verify_password(password, user.password_hash):
        if user.failed_logins or user.locked_until:
            user.failed_logins = 0
            user.locked_until = None
            db.commit()
        return "ok"
    # 読んで足して書く、ではなく「今の値に 1 を足す」を DB に任せる。足したあとの値は RETURNING で受け取る
    count = db.execute(
        update(User).where(User.id == user.id)
        .values(failed_logins=User.failed_logins + 1)
        .returning(User.failed_logins)).scalar_one()
    if count >= MAX_FAILED_LOGINS:
        # 止める。回数はここではゼロに戻さない（戻すのは成功したときと、止まりが過ぎたあと）
        db.execute(update(User).where(User.id == user.id).values(
            locked_until=now() + timedelta(minutes=LOCK_MINUTES)))
    db.commit()
    return "wrong"


def unlock_user(db: Session, user: User, actor_id: int | None = None,
                course_id: int | None = None) -> None:
    """止まりを解く（教員の操作、または unlock コマンド）。記録を残す。"""
    user.failed_logins = 0
    user.locked_until = None
    record_event(db, "user.unlocked", actor_id=actor_id, course_id=course_id,
                 user_id=user.id, name=user.name)
    db.commit()


class LoginRequired(Exception):
    """ログインしていない。main.py で /login への移動に変える。"""


def password_too_short(role: str, password: str) -> bool:
    return len(password) < MIN_PASSWORD_LENGTH[role]


def get_user_or_none(request: Request, db: Session) -> User | None:
    """セッション Cookie から、ログイン中のユーザーを返す（いなければ None）。
    Cookie に入れた「セッションの版」が DB と違えば、ログアウト済みの古い Cookie なので無効。"""
    user_id = request.session.get("user_id")
    user = db.get(User, user_id) if user_id else None
    if user is None or request.session.get("sv") != user.session_version:
        return None
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """ログイン中のユーザーを返す。いなければ LoginRequired。"""
    user = get_user_or_none(request, db)
    if user is None:
        raise LoginRequired()
    return user


def require_teacher(user: User = Depends(get_current_user)) -> User:
    """教員だけ通す。"""
    if user.role != "teacher":
        raise HTTPException(status_code=403)
    return user


# ---- 権限の判定（ルートの外からも使える普通の関数） ----

def is_enrolled(db: Session, course_id: int, user_id: int) -> bool:
    found = db.scalar(select(Enrollment.id).where(
        Enrollment.course_id == course_id, Enrollment.user_id == user_id))
    return found is not None


def team_of_student(db: Session, course_id: int, user_id: int) -> Team | None:
    """授業の中で、その学生が入っている班（いなければ None）。"""
    return db.scalar(
        select(Team).join(TeamMember, TeamMember.team_id == Team.id)
        .where(Team.course_id == course_id, TeamMember.user_id == user_id))


def _get_course_or_404(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404)
    return course


# ---- ルートで使う権限チェック ----

# ※ 未習: 404 と 403 の使い分け — 存在を隠したいものは 404、存在は見えてよいが操作できないものは 403
def require_course_member(course_id: int, user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)) -> Course:
    """授業のホームを見てよい人（担当教員と参加した学生）。それ以外は 404。"""
    course = _get_course_or_404(db, course_id)
    if user.role == "teacher" and course.teacher_id == user.id:
        return course
    if user.role == "student" and is_enrolled(db, course_id, user.id):
        return course
    raise HTTPException(status_code=404)


def require_course_teacher(course_id: int, user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)) -> Course:
    """メンバー管理・コード再発行ができる人（担当教員だけ）。
    参加済みの学生は 403、それ以外（担当外の教員・未参加の学生）は 404。"""
    course = require_course_member(course_id, user, db)  # ここで 404 が決まる
    if user.id != course.teacher_id:
        raise HTTPException(status_code=403)
    return course


def require_team_member(team_id: int, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)) -> Team:
    """班のページを見てよい人（担当教員とその班の学生）。それ以外は 404。"""
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404)
    if user.role == "teacher" and team.course.teacher_id == user.id:
        return team
    if user.role == "student":
        mine = team_of_student(db, team.course_id, user.id)
        if mine is not None and mine.id == team.id:
            return team
    raise HTTPException(status_code=404)


def require_team_teacher(team_id: int, user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)) -> Team:
    """班の編集（名前変更・メンバー操作）ができる人（担当教員だけ）。
    その班の学生は 403、それ以外は 404。"""
    team = require_team_member(team_id, user, db)  # ここで 404 が決まる
    if user.id != team.course.teacher_id:
        raise HTTPException(status_code=403)
    return team
