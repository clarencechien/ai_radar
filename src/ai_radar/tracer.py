"""Block 5 — shadow tracer(collect_only)。

啟動階段 = 純收數據對準,凍結所有閾值(SPEC §8):
- 收集(append-only):scan_one 的紀錄——存活者含假設卡、排除者含理由、NO_DATA 含原因。
- 回填:T+5/10/20 標的表現(選擇權 mid 可選)。
- 雙向檢查(只觀察不動作):存活者放對沒、被排除者事後噴沒(false exclusion 率)。
- 樣本 ≥ tracer.min_samples 且人工週審後才「建議」調參;tracer 永不自動改 config。
"""
from __future__ import annotations

from datetime import date, datetime

from .state import append_record, read_records


def record_scan(path: str, scan_record: dict) -> dict:
    """收一筆 scan_one 的紀錄(kind=scan,ts 自動補)。"""
    rec = dict(scan_record)
    rec["kind"] = "scan"
    return append_record(path, rec)


def record_outcome(path: str, ticker: str, scan_ts: str, horizon_days: int,
                   spot_then, spot_now,
                   option_mid_then=None, option_mid_now=None) -> dict:
    """回填一筆 T+N 表現(kind=outcome)。spot_then 缺 → 報酬 None(NO_DATA)。"""
    ret = (round((spot_now / spot_then - 1) * 100.0, 2)
           if spot_then and spot_now else None)
    rec = {"kind": "outcome", "ticker": ticker, "scan_ts": scan_ts,
           "horizon_days": horizon_days, "spot_then": spot_then, "spot_now": spot_now,
           "underlying_ret_pct": ret}
    if option_mid_then and option_mid_now is not None:
        rec["option_ret_pct"] = round((option_mid_now / option_mid_then - 1) * 100.0, 1)
    return append_record(path, rec)


def scans(path: str) -> list[dict]:
    return [r for r in read_records(path) if r.get("kind") == "scan"]


def outcomes(path: str) -> list[dict]:
    return [r for r in read_records(path) if r.get("kind") == "outcome"]


def card_tracks(path: str) -> list[dict]:
    return [r for r in read_records(path) if r.get("kind") == "card_track"]


def _scan_date(rec: dict) -> date:
    return datetime.fromisoformat(rec["ts"]).date()


def scanned_on(path: str, day: date) -> dict:
    """指定日期已收的掃描:{(ticker, route): {verdicts}}。

    供呼叫端同日去重(雙透鏡並行後以「檔×透鏡」為單位):
    已有實判(非 NO_DATA)當日不重收;只有 NO_DATA 時,盤中補到實判仍可收。
    """
    out: dict = {}
    for s in scans(path):
        if _scan_date(s) == day:
            out.setdefault((s["ticker"], s.get("route")), set()).add(s["verdict"])
    return out


def due_backfills(path: str, today: date, horizons: list[int]) -> list[dict]:
    """哪些 (scan, horizon) 已到期且還沒回填。回傳含回填所需的 then 值。

    NO_DATA 掃描跳過:沒做出判斷,T+N 報酬回答不了「放對沒/砍錯沒」。
    """
    done = {(o["ticker"], o["scan_ts"], o["horizon_days"]) for o in outcomes(path)}
    due = []
    for s in scans(path):
        if s.get("verdict") == "NO_DATA":
            continue
        age = (today - _scan_date(s)).days
        for h in horizons:
            if age >= h and (s["ticker"], s["ts"], h) not in done:
                due.append({"ticker": s["ticker"], "scan_ts": s["ts"],
                            "horizon_days": h, "spot_then": s.get("spot"),
                            "option_mid_then": (s.get("card") or {}).get("premium")})
    return due


def open_cards(path: str, today: date, stop_before_expiry_days: int = 21) -> list[dict]:
    """該追蹤的合約卡:曾上榜的每張(ticker, expiry, strike)去重取**第一次**上榜為基準,
    追到「到期前 N 天」為止(之後 theta 加速,照紀律早該離場,追了只會扭曲統計)。
    同一天已記過的不重複(冪等)。回傳含回填基準(掛牌價/掛牌日)。
    """
    today_iso = today.isoformat()
    marked = {(c["ticker"], c["expiry"], c["strike"]) for c in card_tracks(path)
              if str(c.get("ts", ""))[:10] == today_iso}
    first: dict = {}
    for s in scans(path):
        card = s.get("card") or {}
        if not card.get("expiry"):
            continue
        key = (card["ticker"], card["expiry"], card["strike"])
        if key not in first:
            first[key] = {"ticker": card["ticker"], "expiry": card["expiry"],
                          "strike": card["strike"], "lens": card.get("lens"),
                          "premium_then": card.get("premium"),
                          "spot_then": card.get("spot"), "scan_ts": s.get("ts")}
    due = []
    for key, c in first.items():
        try:
            dte_left = (date.fromisoformat(c["expiry"]) - today).days
        except ValueError:
            continue
        if dte_left > stop_before_expiry_days and key not in marked:
            due.append({**c, "dte_left": dte_left})
    return due


def record_card_track(path: str, card_ref: dict, mid_now, spot_now) -> dict:
    """記一筆合約卡的市價標記(kind=card_track)。mid 缺 → 報酬 None(NO_DATA)。"""
    p0 = card_ref.get("premium_then")
    ret = (round((mid_now / p0 - 1) * 100.0, 1) if p0 and mid_now else None)
    return append_record(path, {
        "kind": "card_track", "ticker": card_ref["ticker"],
        "expiry": card_ref["expiry"], "strike": card_ref["strike"],
        "scan_ts": card_ref.get("scan_ts"), "premium_then": p0,
        "mid_now": mid_now, "spot_now": spot_now,
        "dte_left": card_ref.get("dte_left"), "option_ret_pct": ret})


def card_report(path: str) -> list[dict]:
    """每張追蹤中合約卡的最新標記(掛牌價 → 最新市價,追了幾筆)。"""
    latest: dict = {}
    counts: dict = {}
    for c in card_tracks(path):
        key = (c["ticker"], c["expiry"], c["strike"])
        latest[key] = c          # append-only:後者即最新
        counts[key] = counts.get(key, 0) + 1
    out = []
    for key, c in sorted(latest.items()):
        out.append({"ticker": c["ticker"], "expiry": c["expiry"], "strike": c["strike"],
                    "premium_then": c["premium_then"], "mid_now": c["mid_now"],
                    "option_ret_pct": c["option_ret_pct"],
                    "dte_left": c["dte_left"], "n_marks": counts[key]})
    return out


def _stats(vals: list[float]) -> dict:
    return {"n": len(vals), "avg_ret_pct": round(sum(vals) / len(vals), 2),
            "min_ret_pct": min(vals), "max_ret_pct": max(vals)}


def report(path: str, min_samples: int = 30) -> dict:
    """雙向檢查報表(只觀察):依 verdict(:code) × T+N 分組的標的報酬分布。

    存活者(PASS)組 = 放對沒;EXCLUDE:<code> 組 = 砍錯沒(事後噴 = false exclusion)。
    解鎖只是旗標:達標後仍由人工週審拍板,tracer 不改 config。
    """
    smap = {(s["ticker"], s["ts"]): s for s in scans(path)}
    groups: dict = {}
    n_out = 0
    for o in outcomes(path):
        s = smap.get((o["ticker"], o["scan_ts"]))
        if s is None or o.get("underlying_ret_pct") is None:
            continue
        n_out += 1
        key = s["verdict"] + (f":{s['code']}" if s.get("code") else "")
        groups.setdefault(key, {}).setdefault(f"T+{o['horizon_days']}", []).append(
            o["underlying_ret_pct"])
    return {
        "scan_count": len(smap), "outcome_count": n_out,
        "by_verdict": {k: {h: _stats(v) for h, v in hs.items()}
                       for k, hs in groups.items()},
        "min_samples": min_samples, "tuning_unlocked": n_out >= min_samples,
        "mode": "collect_only",
        "note": "解鎖後也只產建議,人工週審拍板;tracer 永不自動改 config",
    }
