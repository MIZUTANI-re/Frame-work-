"""手元の開発用の .env に、Cookie の署名の鍵（SECRET_KEY）を入れる。
鍵が空のままだと、起動のたびに鍵が変わり、再起動するとログインが外れるため。
すでに鍵が入っていれば何もしない。"""
import re
import secrets
from pathlib import Path

path = Path(__file__).resolve().parent.parent / ".env"
text = path.read_text(encoding="utf-8") if path.exists() else ""
if re.search(r"(?m)^SECRET_KEY=\S+", text):
    raise SystemExit(0)
key = "SECRET_KEY=" + secrets.token_urlsafe(48)
if re.search(r"(?m)^SECRET_KEY=", text):
    text = re.sub(r"(?m)^SECRET_KEY=.*$", key, text)
else:
    text = text.rstrip("\n") + "\n" + key + "\n"
path.write_text(text, encoding="utf-8")
print(".env に SECRET_KEY を入れました。")
