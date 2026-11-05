"""授業の作成・ホーム・メンバー管理・招待コード（F-03・F-05 の画面）。"""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.invite import generate_unique_code
from app.messages import error_text
from app.models import COURSE_NAME_MAX, Course, User
from app.queries import students_of
from app.routers.auth import redirect
from app.security import (get_current_user, is_enrolled, is_locked, require_course_member,
                          require_course_teacher, require_teacher, team_of_student, unlock_user)
from app.templating import render

router = APIRouter()


@router.get("/courses/new")
def new_course_form(request: Request, user: User = Depends(require_teacher),
                    db: Session = Depends(get_db)):
    return render(request, db, "course_new.html", user=user, error=None, form={})


@router.post("/courses")
def create_course(request: Request, name: str = Form(""),
                  user: User = Depends(require_teacher), db: Session = Depends(get_db)):
    """授業を作る。6 文字の招待コードが自動で付く。"""
    name = name.strip()
    error = None
    if not name:
        error = "授業の名前を入力してください"
    elif len(name) > COURSE_NAME_MAX:
        error = f"授業の名前は {COURSE_NAME_MAX} 文字までです"
    if error:
        return render(request, db, "course_new.html", user=user, error=error,
                      form={"name": name}, status_code=400)
    course = Course(name=name, teacher_id=user.id, invite_code=generate_unique_code(db))
    db.add(course)
    db.commit()
    return redirect(f"/courses/{course.id}")


@router.get("/courses/{course_id}")
def course_home(request: Request, course: Course = Depends(require_course_member),
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """授業のホーム。先生は「⚙ 準備 / 授業の設定」へ移す。学生には自分の班だけが見える。"""
    if user.role == "teacher":
        return redirect(f"/courses/{course.id}/settings")
    my_team = team_of_student(db, course.id, user.id)
    return render(request, db, "course_home.html", user=user, course=course, my_team=my_team)


@router.get("/courses/{course_id}/members")
def members_page(request: Request, error: str | None = None,
                 course: Course = Depends(require_course_teacher),
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """メンバー管理（班分け・招待コード）。担当教員だけ。"""
    students = students_of(db, course.id)
    in_team = {m.user_id for team in course.teams for m in team.members}
    unassigned = [s for s in students if s.id not in in_team]
    locked = [s for s in students if is_locked(s)]
    return render(request, db, "members.html", user=user, course=course, students=students, active="members",
                  unassigned=unassigned, locked=locked, msg=error_text(error, len(course.teams), len(students)))


@router.post("/courses/{course_id}/invite-code/regenerate")
def regenerate_code(course: Course = Depends(require_course_teacher),
                    db: Session = Depends(get_db)):
    """招待コードを作り直す。古いコードは使えなくなる（参加済みの学生はそのまま）。"""
    course.invite_code = generate_unique_code(db)
    db.commit()
    return redirect(f"/courses/{course.id}/members")


@router.post("/courses/{course_id}/students/{student_id}/unlock")
def unlock_student(student_id: int, user: User = Depends(get_current_user),
                   course: Course = Depends(require_course_teacher),
                   db: Session = Depends(get_db)):
    """ログインが止まっている学生の止まりを解く。担当教員が、その授業の学生にだけできる。"""
    student = db.get(User, student_id)
    if student is None or not is_enrolled(db, course.id, student_id):
        raise HTTPException(status_code=404)
    unlock_user(db, student, actor_id=user.id, course_id=course.id)
    return redirect(f"/courses/{course.id}/members")
