# 配置・移行設計書

| 項目 | 内容 |
|---|---|
| 文書番号 | FW-08 |
| 版 | 1.0（本人レビュー待ち） |
| 更新日 | 2026-11-05 |
| 関連文書 | [技術設計書](05_technical_design.md)・[開発計画書](07_development_plan.md)・[決定ログ](decisions.md) |

## 1. 決めたこと
- **今（無料）**：1 台の PC でアプリを動かし、Cloudflare Tunnel で外から入れる URL を作る（D-017）。
- **URL**：まずは Quick Tunnel の仮の URL。アカウントもドメインも要らない（D-018）。
- **置き場所は 1 か所**：複数の先生と授業が、1 つのアプリに入る（D-019）。
- **後で**：同じ箱（Docker のイメージ）のまま Azure に移す。そのために §4 の決まりを守る（D-020）。

## 2. 今の形
```
学生・先生のブラウザ
   │  https://xxxx.trycloudflare.com   ← HTTPS は Cloudflare が受け持つ
   ▼
Cloudflare（入口）
   │  トンネル（PC の側から外へつなぐので、ルーターの設定は要らない）
   ▼
PC の中（docker compose）
   ├─ tunnel：cloudflared ──────┐
   └─ app：アプリの箱（FastAPI） <┘ ──> DB（SQLite のファイル。PC の data/ に残る）
```

## 3. 後の形（Azure）
```
ブラウザ ──> Azure Container Apps（同じ箱） ──> Azure Database for PostgreSQL（pgvector）
```
変わるのは「箱を置く場所」と「環境変数（特に `DATABASE_URL`）」だけ。アプリのコードは変えない。

## 4. 移行を簡単にする決まり
| # | 決まり | なぜ | 移行のとき |
|---|---|---|---|
| M-1 | アプリは 1 つの Docker イメージで動く | PC でも Azure でも、同じ物が同じように動く | イメージをそのまま Azure に置く |
| M-2 | 置き場所で変わる値は、環境変数だけで変える | 置き場所ごとの違いをコードに書かない | Azure の画面で環境変数を入れる |
| M-3 | DB は SQLAlchemy 経由だけ。SQLite だけの書き方は使わない | 接続先を変えるだけで PostgreSQL に移れる | `DATABASE_URL` を変える |
| M-4 | テーブルの変更は Alembic で管理する（クラウドに置く前に入れる） | 入っているデータを消さずにテーブルを変えられる | 同じ手順を Azure で流す |
| M-5 | クラウド会社だけの機能をアプリの中で使わない。Cloudflare は入口（HTTPS と URL）だけに使う | 入口を差し替えるだけで済む | 入口を Azure に変える |
| M-6 | 大事な状態をサーバーのメモリに持たない。正しい状態はいつも DB | 再起動しても、台数を増やしても壊れない | — |
| M-7 | WebSocket の配信は「配信係」1 か所に閉じ込める | 台数を増やすとき、そこだけ差し替えればよい（Redis や Azure Web PubSub） | 配信係の中身だけ差し替える |
| M-8 | タイマーは DB に保存した終了予定時刻で決める | 再起動しても続きができる | — |
| M-9 | ファイルを保存するときは「保存係」を通す（今は保存するファイルがない） | ローカル → R2 / Azure Blob の差し替えだけで済む | 保存係の中身だけ差し替える |
| M-10 | ログは標準出力に出す。`/healthz` で生きているか分かる | どのクラウドも標準出力を集め、健康診断に `/healthz` のような URL を使う | — |
| M-11 | HTTPS は入口に任せる。アプリは「入口の前では https だった」という知らせ（プロキシヘッダー）を受け取る | Cookie の `Secure` や、リンクの URL が正しくなる | 設定はそのまま |

## 5. 環境変数
| 名前 | 意味 | 今（PC） | 後（Azure） |
|---|---|---|---|
| `DATABASE_URL` | DB の場所 | `sqlite:////app/data/app.db` | `postgresql+psycopg://…` |
| `SECRET_KEY` | Cookie に署名する鍵 | `.env` に書く | Azure のシークレット |
| `APP_ENV` | `development` / `production` | `production`（トンネル経由で使うとき） | `production` |
| `COOKIE_SECURE` | Cookie を HTTPS のときだけ送る | `1`（手元で http で試すときは `0`） | `1` |
| `PORT` | 待ち受けるポート | `8000` | Azure が決める |
| `FORWARDED_ALLOW_IPS` | プロキシヘッダーを信じる相手 | `*`（アプリのポートは PC の中にしか開けないため） | `*`（Azure の入口の裏だけで動くため） |

`APP_ENV=production` のときに `SECRET_KEY` が無ければ、起動を止める（開発用の鍵のまま公開しないため）。`APP_ENV` が `development` / `production` 以外なら、打ちまちがいとみなして起動を止める。開発用の鍵は、起動のたびに作る乱数にする。

**設定ファイルの分け方（D-038）**：箱で使う設定は `deploy.env`（`deploy.env.example` を写して作る）。手元の開発は `.env`。2 つを分けるのは、箱用の値（`COOKIE_SECURE=1` など）を手元の開発やテストが読んで壊れるのを防ぐため。テストは `.env` も環境変数も読まない。

**`PORT` について**：`docker compose` で動かすときは 8000 のままにする（ポートの公開・健康診断・トンネルの行き先が 8000 で決まっているため）。変えるのは Azure に移るときだけ。

**`FORWARDED_ALLOW_IPS=*` の注意**：このとき、アプリが「接続元」と思う IP（`X-Forwarded-For` の一番左）は、利用者が自分で書けるので信用できない。あとで「接続元ごとの制限」などに IP を使うときは、Cloudflare が付ける `Cf-Connecting-Ip` を使うか、トンネルの IP だけを信じる設定にする。

**テーブルを作るのは Alembic だけ（D-039）**：開発の起動も、`create-teacher` も、箱の起動も、`alembic upgrade head` でテーブルを作る。`create_all` を使うのはテストだけ。2 つが同じ DB のファイルに混ざると、Alembic が「もうある」で止まるため。

## 6. 動かし方（今）
1. PC に Docker Desktop を入れる
2. `.env.example` を写して `.env` を作り、`SECRET_KEY` を書く
3. `docker compose up -d`：アプリ（app）とトンネル（tunnel）が起動する
4. `docker compose logs tunnel` に出る `https://xxxx.trycloudflare.com` を学生に配る
5. 教員アカウント：`docker compose exec app python -m app.cli create-teacher --name <名前>`
6. 終わったら `docker compose down`。データは `data/` に残る

## 7. 今の形の注意
| 注意 | 中身 | 対策 |
|---|---|---|
| PC を点けている間だけ使える | 置き場所が 1 か所（D-019）なので、その PC が止まると全員が使えない | 授業中は PC をスリープさせない。いつでも使えるようにしたくなったら Azure へ |
| URL が毎回変わる | Quick Tunnel は起動のたびに URL が変わる | 起動したら URL を配り直す。固定したくなったら、ドメインを買って名前付きトンネルへ（コードは変えない） |
| 同時に 200 リクエストまで | Quick Tunnel の上限。超えると 429 が返る | 1 授業 40 人（NFR-02）なら足りる見込み。足りなければ名前付きトンネルへ |
| 本番向けではない | Cloudflare は Quick Tunnel を試験・開発用としていて、動き続ける保証がない | 本番で使うときは名前付きトンネルか Azure へ |
| 何も流れない WebSocket は切られる | Cloudflare は、しばらく何も流れない WebSocket を切る | 画面から 30 秒ごとに合図（ping）を送る（ステップ 2 で入れる） |
| SSE は使えない | Quick Tunnel は Server-Sent Events に対応していない | リアルタイムは WebSocket で作る（もとの設計どおり） |
| データはその PC にだけある | SQLite のファイルが `data/` にある | 授業のあとに `data/` をコピーしてバックアップする |
| URL を知っていれば誰でも開ける | ログイン画面までは誰でも見られる | ログインと権限で守る。必要なら Cloudflare Access（無料。50 人まで）を足す |

## 8. Azure への移り方（後で）
1. Alembic で、今のテーブルを PostgreSQL に作る
2. SQLite のデータを PostgreSQL に移す（移し替えのスクリプトは、そのときに作る）
3. 同じ Docker イメージを Azure Container Registry に置く
4. Azure Container Apps で起動し、§5 の環境変数を入れる
5. Azure の URL（または自分のドメイン）を配る

学生向けの Azure for Students は、カード不要で $100 分・12 か月の無料枠があるとされている。使う前に Microsoft の公式ページで確かめる。

## 9. 選ばなかった案
| 案 | 選ばなかった理由 |
|---|---|
| Cloudflare Workers（Python） | 無料で PC も要らない。しかし WebSocket を Durable Objects、DB を D1 に書き直す必要があり、Cloudflare 専用になって Azure に移りにくい（M-5 に反する） |
| Cloudflare Containers | 今の箱のまま置けるが、有料（Workers Paid で月 $5〜） |
| Render の無料枠 | 15 分使わないと眠り、起きるのに約 1 分かかる。SQLite は消えるので外の DB が要る |
| 最初から Azure | 無料枠を使い切ると止まる。まず PC で試してから移る |

## 10. 調べた資料（2026-11-05）
- Cloudflare：[Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)（200 リクエストまで・SSE 非対応・アカウント不要・試験用）
- Cloudflare：[WebSocket の扱い](https://developers.cloudflare.com/support/network/using-cloudflare-with-websockets/)（全プランで対応・無通信で切断）
- Cloudflare：[Workers の料金](https://developers.cloudflare.com/workers/platform/pricing/)・[Durable Objects の制限](https://developers.cloudflare.com/durable-objects/platform/limits)
- Cloudflare：[Python Workers の一般提供（2026-09）](https://blog.cloudflare.com/python-workers-ga/)
- Containers が有料であること：[Sliplane の解説](https://sliplane.io/blog/cloudflare-released-containers-everything-you-need-to-know)
- Render：[無料枠の説明](https://render.com/docs/free)
- Azure for Students：[Microsoft 公式](https://azure.microsoft.com/free/students)（この調べでは公式ページを開けていないので、使う前に確かめる）

## 改訂履歴
| 版 | 日付 | 内容 |
|---|---|---|
| 1.0 | 2026-11-05 | 新しく作成。PC + Cloudflare Tunnel・移行の決まり M-1〜M-11 |
