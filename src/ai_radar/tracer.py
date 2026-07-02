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


def _scan_date(rec: dict) -> date:
    return datetime.fromisoformat(rec["ts"]).date()


def due_backfills(path: str, today: date, horizons: list[int]) -> list[dict]:
    """哪些 (scan, horizon) 已到期且還沒回填。回傳含回填所需的 then 值。"""
    done = {(o["ticker"], o["scan_ts"], o["horizon_days"]) for o in outcomes(path)}
    due = []
    for s in scans(path):
        age = (today - _scan_date(s)).days
        for h in horizons:
            if age >= h and (s["ticker"], s["ts"], h) not in done:
                due.append({"ticker": s["ticker"], "scan_ts": s["ts"],
                            "horizon_days": h, "spot_then": s.get("spot"),
                            "option_mid_then": (s.get("card") or {}).get("premium")})
    return due


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
