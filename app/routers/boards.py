"""ボードの WebSocket（F-07・F-08、技術設計書 §3）。画面の URL は teams.py の S-10。"""
import json

from fastapi import APIRouter, WebSocket

from app.notes import apply_action, snapshot
from app.realtime import hub
from app.security import (WS_FORBIDDEN, WS_NOT_LOGGED_IN, BoardActionDenied,
                          board_audience, board_for_viewer, get_user_or_none)

router = APIRouter()


# ※ 未習: WebSocket — 最初に HTTP で「つなぎたい」と頼み、許されたらそのままつなぎっぱなしにする
# ※ 未習: async / await — この関数は await のところで待つ間、ほかの人の処理が進められる
@router.websocket("/ws/boards/{board_id}")
async def board_socket(websocket: WebSocket, board_id: int):
    factory = websocket.app.state.session_factory
    with factory() as db:
        user = get_user_or_none(websocket, db)  # セッション Cookie で「誰か」を確かめる
        board = board_for_viewer(db, user, board_id) if user else None
        # 断るときも、いったん受けてから理由のコードをつけて切る（ブラウザがコードを読めるように）
        await websocket.accept()
        if user is None:
            await websocket.close(code=WS_NOT_LOGGED_IN)
            return
        if board is None:  # 他の班・担当外・「まだ」のボード・無いボード（理由は区別しない）
            await websocket.close(code=WS_FORBIDDEN)
            return
        user_id = user.id
        snap = snapshot(db, board, user)
    # join から後は try/finally の中に入れる（つないだ直後に切れても、部屋に残らないように）
    hub.join(board_id, user_id, websocket)
    try:
        await websocket.send_json(snap)
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            data = parse_json(message.get("text"))  # 文字でないもの・読めない JSON は None
            # 合図や操作のたびに、見てよいかを DB から確かめ直す（班の移動・ログアウト・「いま」が終わった、にも対応）
            with factory() as db:
                user = get_user_or_none(websocket, db)  # セッションの版も確かめる
                board = board_for_viewer(db, user, board_id) if user else None
                if user is None:
                    await websocket.close(code=WS_NOT_LOGGED_IN)
                    return
                if board is None:
                    await websocket.close(code=WS_FORBIDDEN)
                    return
                if isinstance(data, dict) and data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue
                try:
                    out = apply_action(db, board, user, data)
                except BoardActionDenied as e:
                    await websocket.send_json({"type": "error", "code": e.code})
                    continue
                if out is None:  # 何も変わらない操作（同じ区画への移動）
                    continue
                audience = board_audience(db, board)  # 配るたびに「いま見てよい人」を DB から出す
            await hub.publish(board_id, out, to_users=audience)  # 保存と記録のあとで配る
    finally:
        hub.leave(board_id, websocket)


def parse_json(text):
    """文字を JSON として読む。読めなければ None。"""
    if not isinstance(text, str):
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None
