"""配信係。部屋 = ボード 1 つ。いまはメモリの中の部屋（サーバーは 1 つで動かす前提）。
サーバーを複数台にするときは、このファイルだけを Redis などに差し替える（M-7）。"""
import logging
from collections.abc import Iterable

from starlette.websockets import WebSocketDisconnect

logger = logging.getLogger(__name__)
# 相手が切れたときの例外。これだけ部屋から外す
DISCONNECTED = (WebSocketDisconnect, ConnectionError, RuntimeError)

# ※ 未習: WebSocket — ブラウザとサーバーがつなぎっぱなしになり、どちらからでもいつでも送れる通信。
#   ふつうの HTTP は「聞かれたら答える」だけなので、他の人が足した付箋をすぐ出すのに使う
# ※ 未習: async / await — 「待っている間に別の仕事をしてよい」書き方。送る・受け取るなど待つ処理の前に await を付ける


class Hub:
    """ボードごとの部屋に、つながっている人（WebSocket）を覚えておき、メッセージを配る。"""

    def __init__(self) -> None:
        # board_id → [(user_id, websocket), ...]
        self._rooms: dict[int, list[tuple[int, object]]] = {}

    def join(self, board_id: int, user_id: int, websocket) -> None:
        self._rooms.setdefault(board_id, []).append((user_id, websocket))

    def leave(self, board_id: int, websocket) -> None:
        room = [c for c in self._rooms.get(board_id, []) if c[1] is not websocket]
        if room:
            self._rooms[board_id] = room
        else:
            self._rooms.pop(board_id, None)

    def user_ids(self, board_id: int) -> set[int]:
        """いま部屋にいる人。"""
        return {u for u, _ in self._rooms.get(board_id, [])}

    async def close_user(self, user_id: int, code: int) -> None:
        """その人のつなぎを全部、理由のコードをつけて切る（ログアウトのとき）。"""
        for board_id, room in list(self._rooms.items()):
            for uid, websocket in list(room):
                if uid == user_id:
                    self.leave(board_id, websocket)
                    try:
                        await websocket.close(code=code)
                    except DISCONNECTED:
                        pass

    async def publish(self, board_id: int, message: dict, to_users: Iterable[int] | None = None) -> None:
        """部屋に配る。to_users を渡すと、その人たちにだけ送る（個人ワークで使う。ステップ 3）。
        None なら部屋の全員。切れていた人は部屋から外す。"""
        only = None if to_users is None else set(to_users)
        for user_id, websocket in list(self._rooms.get(board_id, [])):
            if only is not None and user_id not in only:
                continue
            try:
                await websocket.send_json(message)
            except DISCONNECTED:  # 切れた相手は部屋から外す
                self.leave(board_id, websocket)
            except Exception:  # それ以外は原因を調べたいので、ログに出す
                logger.exception("配信に失敗しました（board=%s user=%s）", board_id, user_id)


hub = Hub()  # アプリで使う配信係は、この 1 つだけ
