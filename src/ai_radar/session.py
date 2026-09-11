"""美股交易時段標記(純邏輯)。

GitHub 排程 workflow 會延遲(實測 2026-07~09 延遲 1–9 小時,兩晚拖到收盤後),
同一條 cron 跑出來的樣本有盤中也有收盤後(bid/ask 空 → lastPrice)。
每筆 scan / card_track / bench 記一個 session,量測時才分得開,不用猜。

只標記不裁決:收盤後照樣掃、照樣降級,不因時段跳過(掉一晚比品質差更糟)。
"""
from __future__ import annotations

import datetime as dt

_OPEN = dt.time(9, 30)
_CLOSE = dt.time(16, 0)


def _eastern(now_utc: dt.datetime) -> dt.datetime:
    """UTC → 美東;有 tzdata 用 America/New_York(自動夏令/冬令),沒有退固定 -4。"""
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=dt.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return now_utc.astimezone(ZoneInfo("America/New_York"))
    except Exception:
        return now_utc.astimezone(dt.timezone(dt.timedelta(hours=-4)))


def market_session(now_utc: dt.datetime) -> str:
    """回 'intraday' / 'pre_open' / 'after_close' / 'weekend'(美股一般時段,不含假日)。"""
    et = _eastern(now_utc)
    if et.weekday() >= 5:
        return "weekend"
    t = et.time()
    if t < _OPEN:
        return "pre_open"
    if t >= _CLOSE:
        return "after_close"
    return "intraday"
