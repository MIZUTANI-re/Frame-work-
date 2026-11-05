"""授業の中の「準備」と「成果」の画面（S-07a・S-07b・授業の設定・チャット）。
どれも担当の先生だけ（require_course_teacher）。成果の置き場は学生も開ける。"""
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import flow
from app.course_settings import SETTINGS, effective_settings
from app.db import get_db
from app.events import record_event
from app.framework_defs import FRAMEWORKS, LOCKED_PHASES, PHASE_NAMES, PURPOSE_LABELS, THINKING_LABELS
from app.messages import flow_notice
from app.models import ChatMessage, Course, User
from app.routers.auth import redirect
from app.security import (get_current_user, get_flow_item_or_404, phases_to_save,
                          has_boards, require_course_member, require_course_teacher,
                          require_not_started, require_removable)
from app.templating import render

router = APIRouter()

CHAT_REPLY = "LLM はまだつながっていません"  # 決まった返事（D-016・D-037）
CHAT_MAX = 2000


# ---- ⚙ 授業の設定（D-045）。画面は GET /courses/{id}（courses.py）----

@router.post("/courses/{course_id}/settings")
async def save_settings(request: Request, user: User = Depends(get_current_user),
                        course: Course = Depends(require_course_teacher),
                        db: Session = Depends(get_db)):
    """授業の設定を保存する。変わったものだけ course.settings_changed を残す。"""
    form = await request.form()
    old = effective_settings(course.settings)
    new = dict(old)
    for name in SETTINGS:
        if name in form:
            new[name] = form[name] == "true"
    changes = {n: {"old": old[n], "new": new[n]} for n in SETTINGS if old[n] != new[n]}
    if changes:
        course.settings = new
        record_event(db, "course.settings_changed", actor_id=user.id, course_id=course.id,
                     changes=changes)
        db.commit()
    return redirect(f"/courses/{course.id}/settings?saved=1")


@router.get("/courses/{course_id}/settings")
def settings_page(request: Request, user: User = Depends(get_current_user),
                  course: Course = Depends(require_course_teacher), db: Session = Depends(get_db)):
    """⚙ 準備 / 授業の設定。担当の先生だけ（学生は 403）。"""
    return render(request, db, "settings.html", user=user, course=course, active="settings",
                  settings_defs=SETTINGS, settings=effective_settings(course.settings),
                  saved=request.query_params.get("saved") == "1")


# ---- S-07a フレームワークを探す ----

def search_data(db: Session, course: Course) -> list[dict]:
    """画面に埋め込む候補の一覧（ブラウザの JavaScript で絞る）。カタログの順。"""
    uses = flow.usage_counts(db)
    in_flow = {i.framework_key for i in flow.flow_items(db, course.id)}
    return [{
        "key": f["key"], "name": f["name"], "aliases": f["aliases"], "yomi": f["yomi"],
        "tags": f["tags"], "description": f["meta"]["description"],
        "purpose_label": PURPOSE_LABELS[f["meta"]["purpose"]],
        "thinking_label": THINKING_LABELS[f["meta"]["thinking"]],
        "uses": uses.get(f["key"], 0), "in_flow": f["key"] in in_flow,
    } for f in FRAMEWORKS.values()]


@router.get("/courses/{course_id}/frameworks/search")
def search_page(request: Request, q: str = "", user: User = Depends(get_current_user),
                course: Course = Depends(require_course_teacher), db: Session = Depends(get_db)):
    messages = list(db.scalars(select(ChatMessage).where(ChatMessage.course_id == course.id)
                               .order_by(ChatMessage.id)))
    return render(request, db, "search.html", user=user, course=course, active="search",
                  candidates=search_data(db, course), query=q[:100], messages=messages,
                  notice=flow_notice(request.query_params.get("msg")))


@router.post("/courses/{course_id}/flow/add")
def add_to_flow(framework_key: str = Form(""), q: str = Form(""),
                user: User = Depends(get_current_user),
                course: Course = Depends(require_course_teacher), db: Session = Depends(get_db)):
    """「流れに足す」。流れの最後に入る。そのとき打っていた言葉も記録に入れる。"""
    if framework_key not in FRAMEWORKS:
        raise HTTPException(status_code=404)
    added = flow.add_to_flow(db, course, framework_key, q.strip()[:100], user)
    try:
        db.commit()
    except IntegrityError:  # 2 度押しなどで同時に足された。戻して「すでに入っています」にする
        db.rollback()
        added = None
    return redirect(f"/courses/{course.id}/frameworks/search?q={quote(q.strip()[:100])}"
                    f"&msg={'added' if added else 'already'}")


# ---- F-20 チャット（LLM は呼ばない）----

@router.post("/courses/{course_id}/chat")
def post_chat(text: str = Form(""), user: User = Depends(get_current_user),
              course: Course = Depends(require_course_teacher), db: Session = Depends(get_db)):
    """送った文と、決まった返事の 2 行を保存して返す。"""
    text = text.strip()
    if not text or len(text) > CHAT_MAX:
        raise HTTPException(status_code=400)
    mine = ChatMessage(course_id=course.id, user_id=user.id, role="user", text=text)
    reply = ChatMessage(course_id=course.id, user_id=None, role="assistant", text=CHAT_REPLY)
    db.add_all([mine, reply])
    db.flush()
    record_event(db, "chat.posted", actor_id=user.id, course_id=course.id, message_id=mine.id)
    db.commit()
    return JSONResponse({"messages": [{"role": m.role, "text": m.text} for m in (mine, reply)]})


# ---- S-07b 授業の流れ ----

@router.get("/courses/{course_id}/flow")
def flow_page(request: Request, user: User = Depends(get_current_user),
              course: Course = Depends(require_course_teacher), db: Session = Depends(get_db)):
    items = flow.flow_items(db, course.id)
    rows = [{"item": i, "fw": FRAMEWORKS[i.framework_key],
             "all_phases": [p["key"] for p in FRAMEWORKS[i.framework_key]["phases"]],
             "can_up": flow.can_move(items, n, "up"), "can_down": flow.can_move(items, n, "down"),
             "can_remove": i.status == "waiting" and not has_boards(db, i)}
            for n, i in enumerate(items)]
    return render(request, db, "flow.html", user=user, course=course, active="flow", rows=rows,
                  phase_names=PHASE_NAMES, locked=LOCKED_PHASES,
                  notice=flow_notice(request.query_params.get("msg")))


def flow_url(course_id: int, msg: str | None = None) -> str:
    return f"/courses/{course_id}/flow" + (f"?msg={msg}" if msg else "")


@router.post("/courses/{course_id}/flow/{item_id}/move")
def move_item(item_id: int, direction: str = Form(""), user: User = Depends(get_current_user),
              course: Course = Depends(require_course_teacher),
              db: Session = Depends(get_db)):
    if direction not in ("up", "down"):
        raise HTTPException(status_code=400)
    item = get_flow_item_or_404(db, course, item_id)
    if not flow.move(db, course, item, direction, user):
        raise HTTPException(status_code=409)  # 始まったものは動かせない・端は動かせない
    db.commit()
    return redirect(flow_url(course.id))


@router.post("/courses/{course_id}/flow/{item_id}/remove")
def remove_item(item_id: int, user: User = Depends(get_current_user),
                course: Course = Depends(require_course_teacher), db: Session = Depends(get_db)):
    """まだ始まっていなくて、配られてもいない（ボードが無い）ものだけ、流れから外せる（B-6）。"""
    item = get_flow_item_or_404(db, course, item_id)
    require_removable(db, item)
    flow.remove(db, course, item, user)
    db.commit()
    return redirect(flow_url(course.id))


@router.post("/courses/{course_id}/flow/{item_id}/phases")
async def save_phases(request: Request, item_id: int, user: User = Depends(get_current_user),
                      course: Course = Depends(require_course_teacher), db: Session = Depends(get_db)):
    """使う進め方を保存する。個人ワークと公開が入っていなければ 400（画面を通さなくても外せない）。"""
    item = get_flow_item_or_404(db, course, item_id)
    require_not_started(item)
    requested = (await request.form()).getlist("phase")
    flow.change_phases(db, item, phases_to_save(FRAMEWORKS[item.framework_key], requested), user)
    db.commit()
    return redirect(flow_url(course.id, "phases_saved"))


@router.post("/courses/{course_id}/flow/deal")
def deal(user: User = Depends(get_current_user), course: Course = Depends(require_course_teacher),
         db: Session = Depends(get_db)):
    """全班に配る。班が無い・流れが空のときは何もしない。"""
    if not flow.flow_items(db, course.id):
        return redirect(flow_url(course.id, "flow_empty"))
    if not course.teams:
        return redirect(flow_url(course.id, "no_teams"))
    flow.deal(db, course, user)
    db.commit()
    return redirect(flow_url(course.id, "dealt"))


# ---- 📄 成果の置き場（ステップ 5 で作る）----

@router.get("/courses/{course_id}/summary")
def summary_page(request: Request, user: User = Depends(get_current_user),
                 course: Course = Depends(require_course_member), db: Session = Depends(get_db)):
    return render(request, db, "placeholder.html", user=user, course=course, active="summary",
                  title="まとめシート")


@router.get("/courses/{course_id}/dashboard")
def dashboard_page(request: Request, user: User = Depends(get_current_user),
                   course: Course = Depends(require_course_teacher), db: Session = Depends(get_db)):
    return render(request, db, "placeholder.html", user=user, course=course, active="dashboard",
                  title="ダッシュボード")
