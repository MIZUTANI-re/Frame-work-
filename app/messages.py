"""画面に出す短い通知。URL には決まった鍵（?error=...）だけを載せ、文はここで決める。
知らない鍵は何も出さない（URL の文をそのまま画面に出さないため）。"""

ERRORS = {
    "count_invalid": "班の数は 1 以上、学生の人数以下にしてください",
    "count_below_teams": "指定した数が今の班の数より少ないです（班は消せません）。今の班の数以上にしてください",
    "not_enrolled": "その学生はこの授業に参加していません",
    "conflict": "ほかの操作と重なりました。もう一度やり直してください",
    "name_empty": "名前を入力してください",
    "name_too_long": "名前が長すぎます",
}


def error_text(key: str | None) -> str | None:
    return ERRORS.get(key) if key else None
