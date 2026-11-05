@echo off
chcp 65001 > nul
rem Windows 用：ダブルクリックすると「準備 → 見本のデータ → 起動 → ブラウザ」まで自動でやる。
rem 止めるときは、開いた黒い画面で Ctrl+C を押す。
rem 日本語のファイルを UTF-8 で読ませる（Windows の既定は Shift_JIS 系のため）
set "PYTHONUTF8=1"
cd /d "%~dp0"

set "PY=python"
where py > nul 2>&1 && set "PY=py -3"

if not exist ".venv" (
  echo 仮想環境を作ります…（はじめての起動だけ。1〜2 分かかります）
  %PY% -m venv .venv || goto nopython
)
call ".venv\Scripts\activate.bat"
python -m pip install -q -r requirements-dev.txt || goto failed

if not exist ".env" copy ".env.example" ".env" > nul
python scripts\make_env_key.py || goto failed
python scripts\demo_seed.py || goto failed

start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; Start-Process 'http://127.0.0.1:8000/login'"
echo.
echo ブラウザで http://127.0.0.1:8000/login を開きます。止めるときは、この画面で Ctrl+C。
python -m uvicorn app.main:app --port 8000
goto end

:nopython
echo.
echo Python 3.12 以上を入れてください。https://www.python.org/downloads/
echo 入れるときに「Add python.exe to PATH」に印を付けてください。
pause
goto end

:failed
echo.
echo うまくいきませんでした。上に出ているエラーの文を確かめてください。
pause

:end
