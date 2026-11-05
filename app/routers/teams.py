"""班の操作と班のページ（F-05・S-06）。"""
import random
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.events import record_event
from app.models import Course, Enrollment, Team, TeamMember, User
from app.routers.auth import redirect
from app.security import (get_current_user, is_enrolled, require_course_teacher,
                          require_team_member, require_team_teacher, team_of_student)
from app.templating import render

router = APIRouter()


def members_url(course_id: int, msg: str | None = None) -> str:
    """メンバー管理ページの URL（メッセージ付きにもできる）。"""
    url = f"/courses/{course_id}/members"
    return f"{url}?msg={quote(msg)}" if msg else url


def remove_from_team(db: Session, team: Team, user_id: int, actor: User) -> None:
    """班からメンバーを外し、記録を残す。"""
    for member in list(team.members):
        if member.user_id == user_id:
            db.delete(member)
            record_event(db, "team.member_removed", actor_id=actor.id,
                         course_id=team.course_id, team_id=team.id, user_id=user_id)


def add_to_team(db: Session, team: Team, user_id: int, actor: User) -> None:
    """班にメンバーを入れる。同じ授業の別の班にいたら、そこから移す。"""
    old = team_of_student(db, team.course_id, user_id)
    if old is not None and old.id == team.id:
        return
    if old is not None:
        remove_from_team(db, old, user_id, actor)
    db.add(TeamMember(team_id=team.id, user_id=user_id))
    record_event(db, "team.member_added", actor_id=actor.id,
                 course_id=team.course_id, team_id=team.id, user_id=user_id)


@router.get("/teams/{team_id}")
def team_page(request: Request, team: Team = Depends(require_team_member),
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """班のページ。ボードはステップ 2 で追加する（今は枠だけ）。"""
    return render(request, db, "team.html", user=user, course=team.course, team=team)


@router.post("/courses/{course_id}/teams")
def create_team(name: str = Form(""), course: Course = Depends(require_course_teacher),
                db: Session = Depends(get_db)):
    """班を 1 つ作る。名前が空なら「N班」にする。"""
    name = name.strip() or f"{len(course.teams) + 1}班"
    db.add(Team(course_id=course.id, name=name))
    db.commit()
    return redirect(members_url(course.id))


@router.post("/courses/{course_id}/teams/random")
def assign_randomly(count: int = Form(...), user: User = Depends(get_current_user),
                    course: Course = Depends(require_course_teacher),
                    db: Session = Depends(get_db)):
    """班の数を count にそろえ、全学生をランダムに振り分ける（人数の差は 1 以下）。
    今ある班は番号順に使い回し、足りなければ作り、余ったら消す。"""
    students = list(db.scalars(
        select(User).join(Enrollment, Enrollment.user_id == User.id)
        .where(Enrollment.course_id == course.id)))
    if count < 1 or count > len(students):
        return redirect(members_url(course.id, "班の数は 1 以上、学生の人数以下にしてください"))

    teams = list(course.teams)[:count]
    for extra in list(course.teams)[count:]:
        for member in list(extra.members):
            remove_from_team(db, extra, member.user_id, user)
        db.delete(extra)
    while len(teams) < count:
        team = Team(course_id=course.id, name=f"{len(teams) + 1}班")
        db.add(team)
        db.flush()
        teams.append(team)

    random.shuffle(students)
    for i, student in enumerate(students):
        add_to_team(db, teams[i % count], student.id, user)  # 順に配るので人数差は 1 以下
    db.commit()
    return redirect(members_url(course.id))


@router.post("/teams/{team_id}/rename")
def rename_team(name: str = Form(""), team: Team = Depends(require_team_teacher),
                db: Session = Depends(get_db)):
    if name.strip():
        team.name = name.strip()
        db.commit()
    return redirect(members_url(team.course_id))


@router.post("/teams/{team_id}/delete")
def delete_team(user: User = Depends(get_current_user),
                team: Team = Depends(require_team_teacher), db: Session = Depends(get_db)):
    course_id = team.course_id
    for member in list(team.members):
        remove_from_team(db, team, member.user_id, user)
    db.delete(team)
    db.commit()
    return redirect(members_url(course_id))


@router.post("/teams/{team_id}/members")
def add_member(user_id: int = Form(...), user: User = Depends(get_current_user),
               team: Team = Depends(require_team_teacher), db: Session = Depends(get_db)):
    """学生を班に入れる（手動）。その授業に参加している学生だけ。"""
    if not is_enrolled(db, team.course_id, user_id):
        return redirect(members_url(team.course_id, "その学生はこの授業に参加していません"))
    add_to_team(db, team, user_id, user)
    db.commit()
    return redirect(members_url(team.course_id))


@router.post("/teams/{team_id}/members/{user_id}/remove")
def remove_member(user_id: int, user: User = Depends(get_current_user),
                  team: Team = Depends(require_team_teacher), db: Session = Depends(get_db)):
    remove_from_team(db, team, user_id, user)
    db.commit()
    return redirect(members_url(team.course_id))
