# Frame-work（仮の名前）

グループワーク用の Web アプリ。設計書は `docs/` を参照。現在はステップ 1（土台）まで。

## 起動のしかた
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# 教員アカウントを作る（パスワードは対話で入力）
python -m app.cli create-teacher --name 山田

# 起動（http://127.0.0.1:8000/login を開く）
uvicorn app.main:app --reload
```
- Python 3.12 以上が必要。
- 開発の設定は `.env.example` を `.env` に写して使う（任意）。`SECRET_KEY` が無いと、起動のたびに変わる開発用の鍵になる（再起動するとログインが外れる）。
- DB は `data/app.db`（Git に入れない）。テーブルは起動時に Alembic（`alembic upgrade head`）が作る。`create_all` はテストだけ。
- **前の `data/app.db`（Alembic を入れる前に作ったもの）があるときは、退けてから始める**（`mv data/app.db data/app.db.old`）。混ざると Alembic が「もうある」で止まる。

## 使い方
1. 教員がログインして「授業を作る」→ 6 文字の招待コードが出る。
2. 学生は `/join` で「招待コード + 名前 + パスワード」を入れて参加する（2 回目以降は `/login`）。
3. 教員は「メンバー管理」で班を作る（手動 / ランダム）。

## テスト
```bash
pytest
```
テストは一時ファイルの DB を使うので `data/app.db` には触れない。

## 公開する（PC + Cloudflare Tunnel）
アプリを Docker の箱に入れ、Cloudflare の仮の URL から複数人が使えるようにする（設計は `docs/08_deployment_design.md`）。

1. PC に Docker Desktop を入れる。
2. `cp deploy.env.example deploy.env` して、`SECRET_KEY` を書く（`python -c "import secrets; print(secrets.token_urlsafe(48))"` で作れる）。
3. `docker compose up -d`：アプリ（app）とトンネル（tunnel）が起動する。起動時に Alembic でテーブルが最新になる。
4. `docker compose logs tunnel` に出る `https://xxxx.trycloudflare.com` を学生に配る。
5. 教員アカウント：`docker compose exec app python -m app.cli create-teacher --name <名前>`（パスワードは対話入力。10 文字以上）。
6. 学生がパスワードを何度もまちがえて止まったとき：メンバー管理の「止まりを解く」ボタン、または `docker compose exec app python -m app.cli unlock --name <名前>`。
7. 終わったら `docker compose down`。データは PC の `data/` に残る。

Linux では、箱の中のユーザー（uid 1000）が `data/` に書けるよう `mkdir -p data && sudo chown 1000 data` しておく。

**本人が PC で確かめること**：トンネルが動くか（別の端末・スマホで URL を開いて `/login` が出るか）は、この開発環境では確かめていない。

### 環境変数（`deploy.env.example` に説明あり）
箱（docker compose）の設定は `deploy.env`、手元で `uvicorn` を直接動かす開発の設定は `.env`（`.env.example` を写す）。2 つは別のファイル。テストはどちらも読まない。
| 名前 | 意味 | 既定 |
|---|---|---|
| `SECRET_KEY` | Cookie の署名鍵。production では必須 | なし |
| `APP_ENV` | `development` / `production`（production は `/docs` なし・Alembic でテーブル作成） | `development` |
| `COOKIE_SECURE` | `1` で Cookie を HTTPS のときだけ送る | `0` |
| `DATABASE_URL` | DB の場所 | `data/app.db` |
| `PORT` | 待ち受けポート | `8000` |
| `FORWARDED_ALLOW_IPS` | プロキシヘッダーを信じる相手 | `127.0.0.1` |

### 注意
- PC を点けている間だけ使える。授業中はスリープさせない。
- Quick Tunnel の URL は起動のたびに変わる。起動したら配り直す。
- データは PC の `data/` にだけある。授業のあとにコピーしてバックアップする。
- テーブルを変えるとき：`alembic revision --autogenerate -m "説明"` → `alembic upgrade head`。
