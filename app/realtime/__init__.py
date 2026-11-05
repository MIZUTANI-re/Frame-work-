"""リアルタイム配信（技術設計書 §3）。部屋の管理と配信は、ここの「配信係」1 か所に閉じ込める。"""
from app.realtime.hub import Hub, hub

__all__ = ["Hub", "hub"]
