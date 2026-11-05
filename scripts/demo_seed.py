"""見本のデータを入れる（start-windows.bat / start-mac.command から、はじめての起動のときに呼ぶ）。

作るもの：
  先生A（パスワード teacherpass123）
  学生A〜学生F（パスワード student123）
  授業「プロジェクト演習（見本）」・2 つの班・授業の流れ（ブレインストーミング → SWOT 分析）を全班に配った状態

すでに先生A がいれば、何もしない（2 回目からの起動でデータを消したり重ねたりしない）。
画面と同じ道（URL）を通して作るので、アプリの決まり（権限・記録）がそのまま効く。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # どこから呼んでも app を読めるように

from fastapi.testclient import TestClient  # noqa: E402  （httpx が要る。requirements-dev.txt に入っている）

from app.cli import create_teacher  # noqa: E402
from app.db import SessionLocal, upgrade_database  # noqa: E402
from app.queries import find_user_by_name  # noqa: E402

TEACHER = ("先生A", "teacherpass123")
STUDENTS = [f"学生{c}" for c in "ABCDEF"]
STUDENT_PASSWORD = "student123"
COURSE_NAME = "プロジェクト演習（見本）"
FLOW = ["brainstorm", "swot"]


def main() -> int:
    upgrade_database()
    with SessionLocal() as db:
        if find_user_by_name(db, TEACHER[0]) is not None:
            print("見本のデータはもう入っています。")
            return 0
        create_teacher(db, *TEACHER)

    from app.main import app

    teacher = TestClient(app)
    teacher.post("/login", data={"name": TEACHER[0], "password": TEACHER[1]})
    r = teacher.post("/courses", data={"name": COURSE_NAME}, follow_redirects=False)
    course_id = int(re.search(r"/courses/(\d+)", r.headers["location"]).group(1))

    members_page = teacher.get(f"/courses/{course_id}/members").text
    code = re.search(r"\b([A-HJKMNP-Z2-9]{6})\b", members_page).group(1)

    for name in STUDENTS:
        TestClient(app).post("/join", data={"code": code, "name": name, "password": STUDENT_PASSWORD})

    teacher.post(f"/courses/{course_id}/teams/random", data={"count": "2"})
    for key in FLOW:
        teacher.post(f"/courses/{course_id}/flow/add", data={"framework_key": key, "q": ""})
    teacher.post(f"/courses/{course_id}/flow/deal")

    print("見本のデータを入れました。")
    print(f"  先生：{TEACHER[0]} / {TEACHER[1]}")
    print(f"  学生：{STUDENTS[0]}〜{STUDENTS[-1]} / {STUDENT_PASSWORD}")
    print(f"  授業「{COURSE_NAME}」の招待コード：{code}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
