"""授業の作成・ホーム・メンバー管理・招待コード（F-03・F-05 の画面）。"""
from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.invite import generate_unique_code
from app.models import Course, Enrollment, TeamMember, User
from app.routers.auth import redirect
from app.security import (get_current_user, require_course_member,
                          require_course_teacher, require_teacher, team_of_student)
from app.templating import render

router = APIRouter()


@router.get("/courses/new")
def new_course_form(request: Request, user: User = Depends(require_teacher),
                    db: Session = Depends(get_db)):
    return render(request, db, "course_new.html", user=user, error=None)


@router.post("/courses")
def create_course(request: Request, name: str = Form(""),
                  user: User = Depends(require_teacher), db: Session = Depends(get_db)):
    """授業を作る。6 文字の招待コードが自動で付く。"""
    name = name.strip()
    if not name:
        return render(request, db, "course_new.html", user=user,
                      error="授業の名前を入力してください", status_code=400)
    course = Course(name=name, teacher_id=user.id, invite_code=generate_unique_code(db))
    db.add(course)
    db.commit()
    return redirect(f"/courses/{course.id}")


@router.get("/courses/{course_id}")
def course_home(request: Request, course: Course = Depends(require_course_member),
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """授業のホーム。学生には自分の班だけが見える。"""
    my_team = team_of_student(db, course.id, user.id) if user.role == "student" else None
    return render(request, db, "course_home.html", user=user, course=course, my_team=my_team)


@router.get("/courses/{course_id}/members")
def members_page(request: Request, msg: str | None = None,
                 course: Course = Depends(require_course_teacher),
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """メンバー管理（班分け・招待コード）。担当教員だけ。"""
    students = list(db.scalars(
        select(User).join(Enrollment, Enrollment.user_id == User.id)
        .where(Enrollment.course_id == course.id).order_by(User.id)))
    in_team = {m.user_id for team in course.teams for m in team.members}
    unassigned = [s for s in students if s.id not in in_team]
    return render(request, db, "members.html", user=user, course=course,
                  students=students, unassigned=unassigned, msg=msg)


@router.post("/courses/{course_id}/invite-code/regenerate")
def regenerate_code(course: Course = Depends(require_course_teacher),
                    db: Session = Depends(get_db)):
    """招待コードを作り直す。古いコードは使えなくなる（参加済みの学生はそのまま）。"""
    course.invite_code = generate_unique_code(db)
    db.commit()
    return redirect(f"/courses/{course.id}/members")
