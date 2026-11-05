# Frame-work（仮の名前）

グループワーク用の Web アプリです。班のみんながフレームワーク（ブレスト・SWOT など）の上に付箋で考えを書き、先生がそれを見られます。画面は Teams のイメージです。

## はじめに（このフォルダを受け取った人へ）
- **いまの段階**：ステップ 2 まで（2026-11-05）。「見た目」と「最低限の中身」だけを作っています。
- **できること**
  - 先生：授業を作る・招待コードを配る・班に分ける・フレームワークを言葉で探して「授業の流れ」に並べる・全班に配る・授業の設定（成果を全班で共有するか）
  - 学生：招待コードで参加する・自分の班のボード（ブレスト・SWOT）に付箋を書く。書いた付箋は班の全員の画面にすぐ出る
  - 先生は全部の班のボードを見られる（書き込みはしない）
- **まだできないこと**
  - 「個人ワーク」で他の人の付箋を隠す・タイマー・まとめる・投票・結論（ステップ 3）
  - ペイオフマトリクスの盤面（ステップ 4）、まとめシートと画像で残す（ステップ 5）
  - LLM（チャット欄は枠だけ。返事は「LLM はまだつながっていません」）
  - **ステップ 3 が入るまでは、本番の授業では使わない**（今は個人ワーク中も全員の付箋が見えるため）
- **読むもの**
  - `docs/README.md`：設計書の一覧（要件・機能・画面・データ・技術・フレームワーク・開発計画・公開と移行）
  - `docs/decisions.md`：決めたこと（D-番号）
  - `docs/open_questions.md`：まだ決めていないこと。「まとめて聞くこと」に仮の決定が並んでいる
  - `docs/mockups/frameworks.html`：これから作る画面の見本（ブラウザで開くだけで動く）
  - `docs/learning/`：使っている技術の勉強メモ
- パソコンのブラウザ（Chrome・Edge）で使う前提です。スマホは考えていません。

## 別のパソコンに移して動かす（はじめての人向け）
用意するもの：**Python 3.12 以上**（3.13 で確かめ済み）だけ。https://www.python.org/downloads/ から入れる。Windows では、入れるときに「Add python.exe to PATH」に印を付ける。

### いちばん簡単：ダブルクリックで動かす
- **Windows**：フォルダの中の `start-windows.bat` をダブルクリック。
- **Mac**：`start-mac.command` をダブルクリック（Linux は `sh start-mac.command`）。

自動でやること：仮想環境とライブラリの準備（はじめてだけ 1〜2 分）→ 設定ファイルと鍵 → 見本のデータ → 起動 → ブラウザでログイン画面を開く。止めるときは、開いた黒い画面で Ctrl+C。2 回目からは同じファイルをダブルクリックするだけ（データは `data/app.db` に残る）。

見本のデータ（はじめての起動で自動で入る）：
| 誰 | 名前 | パスワード |
|---|---|---|
| 先生 | 先生A | teacherpass123 |
| 学生 | 学生A〜学生F | student123 |

授業「プロジェクト演習（見本）」に 6 人が参加し、2 つの班に分かれ、ブレスト → SWOT の流れが配られた状態から始まる。2 つのブラウザ（または片方をシークレットウィンドウ）で同じ班の学生としてログインすると、付箋が同時に出るのを試せる。

**Windows で止められたとき**
- 「Windows によって PC が保護されました」と出たら：「詳細情報」→「実行」。
- それでも動かないとき：zip を右クリック →「プロパティ」→ 下の「許可する」に印 → もう一度展開してから実行。

### 手で準備する（中身を知りたい人・続きを作る人向け）
**Windows（PowerShell）**
```powershell
cd Frame-work
$env:PYTHONUTF8 = "1"             # 日本語のファイルを UTF-8 で読ませる（Windows の既定は Shift_JIS 系）
py -3.13 -m venv .venv            # 3.12 なら py -3.12
.venv\Scripts\Activate.ps1        # 止められたら：Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements-dev.txt
copy .env.example .env
python -m app.cli create-teacher --name 先生A   # パスワードを 2 回入れる（10 文字以上）
uvicorn app.main:app --reload
```

**Mac・Linux**
```bash
cd Frame-work
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python -m app.cli create-teacher --name 先生A
uvicorn app.main:app --reload
```

ブラウザで http://127.0.0.1:8000/login を開く。テストは `pytest`（1〜2 分）。

**続きを作るとき**
- このフォルダには Git の履歴が入っている。いまの作業のブランチは `step/2-setup-flow`（`git log --oneline` で流れが見える）。
- GitHub：https://github.com/MIZUTANI-re/Frame-work-（同じ中身がある）。
- Claude Code でこのフォルダを開くと、`CLAUDE.md`（決まり）・`.claude/agents/`（実装・レビュー・フレームワーク作成の役割）・`.claude/skills/organize-request/`（話し言葉の指示を整理するスキル）がそのまま使える。
- 次にやることは `docs/07_development_plan.md` のステップ 3。まだ決めていないことは `docs/open_questions.md` の「まとめて聞くこと」。

## 起動のしかた
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# 教員アカウントを作る（パスワードは対話で入力）
python -m app.cli create-teacher --name 先生A

# 起動（http://127.0.0.1:8000/login を開く）
uvicorn app.main:app --reload
```
- Python 3.12 以上が必要。
- 開発の設定は `.env.example` を `.env` に写して使う（任意）。`SECRET_KEY` が無いと、起動のたびに変わる開発用の鍵になる（再起動するとログインが外れる）。
- DB は `data/app.db`（Git に入れない）。テーブルは起動時に Alembic（`alembic upgrade head`）が作る。`create_all` はテストだけ。
- **前の `data/app.db`（Alembic を入れる前に作ったもの）があるときは、退けてから始める**（`mv data/app.db data/app.db.old`）。混ざると Alembic が「もうある」で止まる。

## 使い方（先生の流れ）
1. 教員がログインして「授業を作る」→ 6 文字の招待コードが出る（パスワードは教員 10 文字以上・学生 6 文字以上）。
2. 学生は `/join` で「招待コード + 名前 + パスワード」を入れて参加する（2 回目以降は `/login`）。
3. 教員は「⚙ 準備 / メンバーと班」で班を作る（手動 / ランダム）。
4. 「⚙ 準備 / フレームワークを探す」で言葉を打って探し（例：「ぶれ」「ＳＷＯＴ」「ゆうせん」）、「流れに足す」。
5. 「⚙ 準備 / 授業の流れ」で順番と進め方を決め、「全班に配る」。
6. 「▶ 授業中」の班を開くと、ボードに付箋を書ける（学生）・見られる（先生）。
7. 2 つのブラウザ（または片方をシークレットウィンドウ）で別々の学生としてログインすると、付箋が同時に出るのを試せる。

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
