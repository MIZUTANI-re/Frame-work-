# Frame-work（仮の名前）

グループワーク用の Web アプリ。設計書は `docs/` を参照。現在はステップ 1（土台）まで。

## 起動のしかた
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 教員アカウントを作る（パスワードは対話で入力）
python -m app.cli create-teacher --name 山田

# 起動（http://127.0.0.1:8000/login を開く）
uvicorn app.main:app --reload
```
- `SECRET_KEY` を環境変数か `.env` に書く（例：`SECRET_KEY=ながいランダムな文字列`）。無いと警告が出て開発用の値になる。
- DB は `data/app.db`（Git に入れない）。起動時にテーブルが自動で作られる。

## 使い方
1. 教員がログインして「授業を作る」→ 6 文字の招待コードが出る。
2. 学生は `/join` で「招待コード + 名前 + パスワード」を入れて参加する（2 回目以降は `/login`）。
3. 教員は「メンバー管理」で班を作る（手動 / ランダム）。

## テスト
```bash
pytest
```
テストは一時ファイルの DB を使うので `data/app.db` には触れない。
