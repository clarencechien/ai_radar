"""Block 4 — 催化劑 helper:對標的標時鐘,只呈現不裁決(SPEC §6.5)。

- 事件由呼叫端注入([{date, kind, label}]);live 抓取(yfinance calendar)在 notebook。
- 餵路由器:`next_catalyst()` 的 dte 直接給 route()/convexity_lens 用。
- 餵人:`format_clock()` 出 T-N 天標記(卡旁)。
- lookahead 只標注不裁決:超過 lookahead_days 的事件照樣回傳(加 within_lookahead=False),
  砍不砍遠期時鐘是呼叫端/人的事,helper 不裁。
"""
from __future__ import annotations

from datetime import date


def _to_date(x) -> date | None:
    """ISO 字串 / date / datetime → date;解析不了 → None(NO_DATA 跳過)。"""
    if isinstance(x, date):
        return x
    try:
        return date.fromisoformat(str(x)[:10])
    except ValueError:
        return None


def next_catalyst(events, today: date, lookahead_days: int | None = None) -> dict | None:
    """最近的未來事件(含今天)。無事件/全已過/日期壞 → None(無時鐘)。

    events: [{"date": "2026-09-23" | date, "kind": "earnings", "label": ...}, ...]
    回傳 {"date", "dte", "kind", "label", ("within_lookahead")}。
    """
    future = []
    for e in events or []:
        d = _to_date(e.get("date"))
        if d is not None and d >= today:
            future.append((d, e))
    if not future:
        return None
    d, e = min(future, key=lambda x: x[0])
    out = {"date": d.isoformat(), "dte": (d - today).days,
           "kind": e.get("kind", "event"), "label": e.get("label")}
    if lookahead_days is not None:
        out["within_lookahead"] = out["dte"] <= lookahead_days
    return out


def format_clock(cat: dict | None) -> str:
    """人看的時鐘標記(卡旁/清單用)。"""
    if cat is None:
        return "催化劑:—(無帶日期時鐘)"
    far = "" if cat.get("within_lookahead", True) else "(遠期)"
    return f"催化劑:T-{cat['dte']} {cat['kind']} {cat['date']}{far}"
