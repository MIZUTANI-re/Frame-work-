#!/bin/sh
# Mac・Linux 用：これを実行すると「準備 → 見本のデータ → 起動 → ブラウザ」まで自動でやる。
# Mac ではダブルクリックで動く（止めるときは、開いた画面で Ctrl+C）。
# Linux では  sh start-mac.command  で動かす。
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"

if [ ! -d .venv ]; then
  echo "仮想環境を作ります…（はじめての起動だけ。1〜2 分かかります）"
  "$PY" -m venv .venv || { echo "Python 3.12 以上を入れてください（https://www.python.org/downloads/）"; exit 1; }
fi
. .venv/bin/activate
python -m pip install -q -r requirements-dev.txt

if [ ! -f .env ]; then
  cp .env.example .env
fi
python scripts/make_env_key.py
python scripts/demo_seed.py

URL="http://127.0.0.1:8000/login"
( sleep 3; if command -v open >/dev/null 2>&1; then open "$URL"; elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"; fi ) >/dev/null 2>&1 &
echo ""
echo "ブラウザで $URL を開きます（開かなければ自分で開いてください）。止めるときは Ctrl+C。"
exec python -m uvicorn app.main:app --port 8000
