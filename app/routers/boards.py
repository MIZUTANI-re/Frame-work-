"""ボードの WebSocket（F-07・F-08、技術設計書 §3）。画面の URL は teams.py の S-10。"""
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.notes import apply_action, snapshot
from app.realtime import hub
from app.security import (WS_FORBIDDEN, WS_NOT_LOGGED_IN, BoardActionDenied,
                          board_for_viewer, get_user_or_none)

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
        hub.join(board_id, user_id, websocket)
        await websocket.send_json(snapshot(db, board, user))
    try:
        while True:
            text = await websocket.receive_text()
            try:
                data = json.loads(text)
            except ValueError:
                data = None
            if isinstance(data, dict) and data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            # 操作のたびに DB から読み直す（途中で「いま」が終わった・班が変わった、にも対応）
            with factory() as db:
                user = get_user_or_none(websocket, db)
                board = board_for_viewer(db, user, board_id) if user else None
                try:
                    if board is None:
                        raise BoardActionDenied("read_only")
                    message = apply_action(db, board, user, data)
                except BoardActionDenied as e:
                    await websocket.send_json({"type": "error", "code": e.code})
                    continue
            await hub.publish(board_id, message)  # 保存と記録のあとで、部屋の全員に配る
    except WebSocketDisconnect:
        pass
    finally:
        hub.leave(board_id, websocket)
