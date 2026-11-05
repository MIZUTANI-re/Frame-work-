#!/bin/sh
# 箱の起動スクリプト：テーブルを最新にしてから、アプリを起動する。
set -e

alembic upgrade head

# ※ 未習: プロキシヘッダー — 入口（Cloudflare など）が「元は https だった」「元のアクセス元はこの IP」と付ける知らせ。--forwarded-allow-ips で、信じる相手を決める
exec uvicorn app.main:app \
  --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"
