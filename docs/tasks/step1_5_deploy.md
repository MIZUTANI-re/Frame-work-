# タスク票 ステップ 1.5：公開の準備（Docker・環境変数・Cloudflare Tunnel）

| 項目 | 内容 |
|---|---|
| 状態 | ステップ 1 のレビューの指摘を直したあとに実装する（本人の依頼：2026-11-05「Cloudflare を使って…移行は簡単な形に」。D-016・D-017） |
| 実装 | `implementer`（Sonnet） |
| レビュー | `reviewer`（Opus） |
| 前提 | [配置・移行設計書](../08_deployment_design.md)（特に §4 の M-1〜M-11・§5 の環境変数・§6 の動かし方）・[技術設計書](../05_technical_design.md)・D-017〜D-020 |

## 目的
アプリを Docker の箱に入れ、先生の PC で `docker compose up -d` するだけで、Cloudflare の仮の URL から複数人が使えるようにする。同時に、あとで同じ箱のまま Azure に移れる形（M-1〜M-11）にしておく。

## 作るもの
1. **`Dockerfile`**
   - 土台は `python:3.13-slim`。root ではないユーザーで動かす
   - 入れるのは本番用の依存（`requirements.txt`）だけ。テストや `.venv` は入れない
   - データは `/app/data` に置く（compose で PC の `data/` をつなぐ）
   - 起動時に「Alembic でテーブルを最新にする → uvicorn を起動する」（`scripts/start.sh` などにまとめる）
   - uvicorn は `--host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips` を `FORWARDED_ALLOW_IPS` で渡す（M-11）
2. **`docker-compose.yml`**
   - `app`：上の箱。`.env` を読む。`./data:/app/data`。ポートは `127.0.0.1:8000:8000`（PC の外には開けない）。`/healthz` で健康診断。`restart: unless-stopped`
   - `tunnel`：`cloudflare/cloudflared` のイメージ。`tunnel --no-autoupdate --url http://app:8000`。`app` が元気になってから起動。`restart: unless-stopped`
   - `cloudflared` の版は固定する。実在する版を確かめられなければ `latest` にして、その旨を報告する
3. **`.env.example`**：配置・移行設計書 §5 の環境変数を、説明つきで並べる。`.env` は Git に入れない（`.gitignore` 済み）
4. **`.dockerignore`**：`.git`・`.venv`・`data`・`__pycache__`・`tests`・`.env`
5. **依存を分ける**：`requirements.txt`（本番用）と `requirements-dev.txt`（`-r requirements.txt` + pytest・httpx）
6. **設定（`app/config.py`）**
   - `APP_ENV`（`development` / `production`。既定は `development`）
   - `COOKIE_SECURE`（`1` / `0`。既定は `0`）→ セッション Cookie の `https_only` に使う
   - `APP_ENV=production` で `SECRET_KEY` が無ければ、起動を止める（警告では済ませない）
7. **`/healthz`**：ログイン不要。DB に軽い問い合わせをして `{"status": "ok"}` を返す。DB に届かなければ 503
8. **Alembic を入れる**（M-4）
   - `alembic.ini` と `migrations/`。今のテーブル（User・Course・Enrollment・Team・TeamMember・Event）を作る最初の版を 1 つ
   - `APP_ENV=production` のときは、起動時の `create_all` をやめ、Alembic だけでテーブルを作る。`development` とテストは今のまま `create_all` でよい
   - SQLite だけの書き方は使わない（M-3）
9. **README**：「公開する（PC + Cloudflare Tunnel）」の節を足す。配置・移行設計書 §6 の手順と、§7 の注意（PC を点けている間だけ・URL が毎回変わる・バックアップ）を短く

## 作らないもの
- PostgreSQL のドライバー・Azure 用の設定ファイル（移るときに足す）
- 名前付きトンネル・Cloudflare Access（必要になったら）
- WebSocket の ping（ステップ 2 で、WebSocket と一緒に作る）

## 完了の条件
- [ ] `docker build` が通る
- [ ] `docker compose up -d app`（トンネル抜き）で起動し、`curl http://127.0.0.1:8000/healthz` が 200 と `{"status": "ok"}` を返す
- [ ] 箱の中で `python -m app.cli create-teacher` が動く（パスワードは対話入力）
- [ ] `APP_ENV=production` で `SECRET_KEY` が無いと、起動が止まる（テスト）
- [ ] `COOKIE_SECURE=1` のとき、ログイン後の `Set-Cookie` に `Secure` が付く（テスト）
- [ ] 空の SQLite に `alembic upgrade head` をかけると、モデルと同じテーブルができる（テスト）
- [ ] `docker compose down` → `up` しても、`data/` のデータが残る
- [ ] `pytest` が全部通る
- [ ] トンネルの動作（外から URL で開けるか）は、この開発環境では確かめない。本人が PC で確かめる手順を README に書く
