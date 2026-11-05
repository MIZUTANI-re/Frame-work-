"""班の操作と班のページ（F-05・S-06）。"""
import random
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.events import record_event
from app.models import TEAM_NAME_MAX, Course, Team, TeamMember, User
from app.queries import students_of
from app.routers.auth import redirect
from app.security import (get_current_user, is_enrolled, require_course_teacher,
                          require_team_member, require_team_teacher, team_of_student)
from app.templating import render

router = APIRouter()


def members_url(course_id: int, error: str | None = None) -> str:
    """メンバー管理ページの URL（通知の鍵を付けることもできる）。"""
    url = f"/courses/{course_id}/members"
    return f"{url}?error={quote(error)}" if error else url


def next_team_name(existing: set[str]) -> str:
    """使われていない一番小さい番号の「N班」。"""
    n = 1
    while f"{n}班" in existing:
        n += 1
    return f"{n}班"


def name_error(name: str) -> str | None:
    """班の名前の確認。問題があれば通知の鍵を返す。"""
    if len(name) > TEAM_NAME_MAX:
        return "name_too_long"
    return None


def remove_from_team(db: Session, team: Team, user_id: int, actor: User) -> None:
    """班からメンバーを外し、記録を残す。"""
    for member in list(team.members):
        if member.user_id == user_id:
            db.delete(member)
            record_event(db, "team.member_removed", actor_id=actor.id,
                         course_id=team.course_id, team_id=team.id, user_id=user_id)
    db.flush()  # 新しい班へ入れる前に、外す側を先に DB へ反映する


def add_to_team(db: Session, team: Team, user_id: int, actor: User) -> None:
    """班にメンバーを入れる。同じ授業の別の班にいたら、同じ取引の中で先にそこから外す。
    2 つの班に入る操作が重なったら、DB の一意制約が IntegrityError で止める。"""
    old = team_of_student(db, team.course_id, user_id)
    if old is not None and old.id == team.id:
        return
    if old is not None:
        remove_from_team(db, old, user_id, actor)
    db.add(TeamMember(team_id=team.id, course_id=team.course_id, user_id=user_id))
    db.flush()
    record_event(db, "team.member_added", actor_id=actor.id,
                 course_id=team.course_id, team_id=team.id, user_id=user_id)


def create_team_record(db: Session, course_id: int, name: str, actor: User) -> Team:
    """班を作り、記録を残す。"""
    team = Team(course_id=course_id, name=name)
    db.add(team)
    db.flush()  # id を確定させる
    record_event(db, "team.created", actor_id=actor.id, course_id=course_id,
                 team_id=team.id, name=name)
    return team


@router.get("/teams/{team_id}")
def team_page(request: Request, team: Team = Depends(require_team_member),
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """班のページ。ボードはステップ 2 で追加する（今は枠だけ）。"""
    return render(request, db, "team.html", user=user, course=team.course, team=team)


@router.post("/courses/{course_id}/teams")
def create_team(name: str = Form(""), user: User = Depends(get_current_user),
                course: Course = Depends(require_course_teacher),
                db: Session = Depends(get_db)):
    """班を 1 つ作る。名前が空なら、使われていない一番小さい番号の「N班」にする。"""
    name = name.strip()
    if name_error(name):
        return redirect(members_url(course.id, name_error(name)))
    name = name or next_team_name({t.name for t in course.teams})
    create_team_record(db, course.id, name, user)
    db.commit()
    return redirect(members_url(course.id))


@router.post("/courses/{course_id}/teams/random")
def assign_randomly(count: int = Form(...), user: User = Depends(get_current_user),
                    course: Course = Depends(require_course_teacher),
                    db: Session = Depends(get_db)):
    """全学生をランダムに count 個の班へ振り分ける（学生が班より多ければ人数の差は 1 以下）。
    班は消さない（D-028・D-030）。count が今の班より少なければ何も変えない。足りない分は作る。"""
    students = students_of(db, course.id)
    # 班の数は「今の班の数以上」。学生の人数以下か、今の班の数と同じなら通す（空の班があってよい。D-041）
    if count < 1:
        return redirect(members_url(course.id, "count_invalid"))
    if count < len(course.teams):
        return redirect(members_url(course.id, "count_below_teams"))
    if count > len(students) and count != len(course.teams):
        return redirect(members_url(course.id, "count_over_students"))

    course_id = course.id
    try:
        teams = list(course.teams)
        names = {t.name for t in teams}
        while len(teams) < count:
            name = next_team_name(names)
            names.add(name)
            teams.append(create_team_record(db, course_id, name, user))
        random.shuffle(students)
        for i, student in enumerate(students):
            add_to_team(db, teams[i % count], student.id, user)  # 順に配るので人数差は 1 以下
        db.commit()
    except IntegrityError:
        db.rollback()
        return redirect(members_url(course_id, "conflict"))
    return redirect(members_url(course_id))


@router.post("/teams/{team_id}/rename")
def rename_team(name: str = Form(""), user: User = Depends(get_current_user),
                team: Team = Depends(require_team_teacher), db: Session = Depends(get_db)):
    name = name.strip()
    error = name_error(name) or ("name_empty" if not name else None)
    if error:
        return redirect(members_url(team.course_id, error))
    record_event(db, "team.renamed", actor_id=user.id, course_id=team.course_id,
                 team_id=team.id, old_name=team.name, name=name)
    team.name = name
    db.commit()
    return redirect(members_url(team.course_id))


@router.post("/teams/{team_id}/members")
def add_member(user_id: int = Form(...), user: User = Depends(get_current_user),
               team: Team = Depends(require_team_teacher), db: Session = Depends(get_db)):
    """学生を班に入れる（手動）。その授業に参加している学生だけ。"""
    if not is_enrolled(db, team.course_id, user_id):
        return redirect(members_url(team.course_id, "not_enrolled"))
    course_id = team.course_id
    try:
        add_to_team(db, team, user_id, user)
        db.commit()
    except IntegrityError:
        db.rollback()
        return redirect(members_url(course_id, "conflict"))
    return redirect(members_url(course_id))


@router.post("/teams/{team_id}/members/{user_id}/remove")
def remove_member(user_id: int, user: User = Depends(get_current_user),
                  team: Team = Depends(require_team_teacher), db: Session = Depends(get_db)):
    remove_from_team(db, team, user_id, user)
    db.commit()
    return redirect(members_url(team.course_id))
