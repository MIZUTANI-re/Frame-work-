# ※ 未習: Docker — アプリと必要な物を 1 つの「箱（イメージ）」にまとめ、どこでも同じように動かす仕組み
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# root ではないユーザーで動かす
RUN useradd --create-home --uid 1000 app

WORKDIR /app

# 先に依存だけ入れる（アプリのコードを変えても、ここは作り直さずに済む）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts ./scripts
COPY app ./app

# データ（SQLite）の置き場。compose で PC の data/ をつなぐ
RUN mkdir -p /app/data && chown -R app:app /app/data
USER app

EXPOSE 8000
CMD ["sh", "scripts/start.sh"]
