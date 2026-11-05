"""画面（Jinja2）の共通部分。レールと 2 列目に出す情報をここで集める。"""
from fastapi import Request
from fastapi.responses import HTMLResponse
# ※ 未習: Jinja2 テンプレート — HTML の中に {{ 変数 }} や {% if %} を書いて、Python の値を埋め込む仕組み
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import BASE_DIR
from app.models import Course, Enrollment, Team, User
from app.security import team_of_student

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


def courses_of(db: Session, user: User) -> list[Course]:
    """左端のレールに出す、参加している授業（教員は担当の授業）。"""
    if user.role == "teacher":
        query = select(Course).where(Course.teacher_id == user.id)
    else:
        query = (select(Course).join(Enrollment, Enrollment.course_id == Course.id)
                 .where(Enrollment.user_id == user.id))
    return list(db.scalars(query.order_by(Course.id)))


def teams_visible_to(db: Session, user: User, course: Course) -> list[Team]:
    """2 列目に出す班。教員は全班、学生は自分の班だけ。"""
    if user.role == "teacher":
        return list(course.teams)
    mine = team_of_student(db, course.id, user.id)
    return [mine] if mine else []


def render(request: Request, db: Session, name: str, user: User | None = None,
           course: Course | None = None, team: Team | None = None,
           status_code: int = 200, **context) -> HTMLResponse:
    """ページを描く。user があれば Teams 風の枠（レール・2 列目）の情報も渡す。"""
    context.update(user=user, course=course, team=team)
    if user is not None:
        context["rail_courses"] = courses_of(db, user)
        context["side_teams"] = teams_visible_to(db, user, course) if course else []
    return templates.TemplateResponse(request, name, context, status_code=status_code)
