"""画面に出す短い通知。URL には決まった鍵（?error=...）だけを載せ、文はここで決める。
知らない鍵は何も出さない（URL の文をそのまま画面に出さないため）。"""

ERRORS = {
    "no_students": "まだ学生がいません。学生が参加してから振り分けてください",
    "count_invalid": "班の数は 1 以上にしてください",
    # 班の数の通知には、今の班と学生の数を入れる
    "count_below_teams": "今の班は {teams} つ、学生は {students} 人です。班は消せないので、{hint}",
    "count_over_students": "今の班は {teams} つ、学生は {students} 人です。{hint}",
    "not_enrolled": "その学生はこの授業に参加していません",
    "conflict": "ほかの操作と重なりました。もう一度やり直してください",
    "name_empty": "名前を入力してください",
    "name_too_long": "名前が長すぎます",
}


def count_hint(teams: int, students: int) -> str:
    """班の数として指定してよい数の案内（D-041：今の班の数以上で、学生の人数以下か今の班の数と同じ）。"""
    if teams >= students:
        return f"{teams} を指定すると振り分けられます"
    return f"{max(teams, 1)} 以上 {students} 以下を指定してください"


def error_text(key: str | None, teams: int = 0, students: int = 0) -> str | None:
    template = ERRORS.get(key) if key else None
    if template is None:
        return None
    return template.format(teams=teams, students=students, hint=count_hint(teams, students))
