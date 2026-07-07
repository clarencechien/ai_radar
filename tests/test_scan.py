"""正式進入點測試:scan_universe(mock fetcher,離線走完整條)。"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ai_radar.scan import scan_universe  # noqa: E402
from ai_radar.report import render_report  # noqa: E402

CFG = {
    "liquidity": {"min_oi": 100, "min_vol": 10, "max_spread_pct": 10},
    "leverage": {"lev_iv_pct_max": 40, "lev_delta_lo": 0.70, "lev_delta_hi": 0.85,
                 "lev_dte_min": 365, "lev_pick_metric": "min_extrinsic_per_delta"},
    "convexity": {"cvx_iv_ratio_max": 1.3, "cvx_prem_max_pct": 1.5, "cvx_otm_max_pct": 25,
                  "earn_window_days": 10, "target_move_pct": 30, "cvx_iv_pct_max": 60,
                  "racehorse_tiers": {}},
    "exposure": {"enabled": False},
    "data": {"iv_percentile_min_history_days": 60},
    "catalyst": {"lookahead_days": 60},
}
TODAY = dt.date(2026, 7, 2)

LEAPS = [{"strike": 150, "dte": 550, "mid": 62, "iv": 0.42, "oi": 1000, "volume": 100,
          "expiry": "2028-01-21"},
         {"strike": 180, "dte": 550, "mid": 40, "iv": 0.40, "oi": 1000, "volume": 100,
          "expiry": "2028-01-21"}]
OTM = [{"strike": 1080, "dte": 40, "mid": 12.0, "iv": 0.55, "oi": 1000, "volume": 100,
        "expiry": "2026-08-14"}]

SPOTS = {"NVDA": 200.0, "MU": 1000.0, "FAR": 200.0}
EVENTS = {"MU": [{"date": "2026-08-01", "kind": "earnings"}],    # T-30(lookahead 內)
          "FAR": [{"date": "2026-09-23", "kind": "earnings"}]}   # T-83(超過 lookahead 60)


def _fetch_spot(t):
    if t == "BAD":
        raise ConnectionError("Yahoo timeout")
    return SPOTS[t]


def _fetch_chain(t, S, min_dte, max_dte, otm_only):
    return OTM if otm_only else LEAPS


def test_scan_universe_dual_lens_degrades_and_reports():
    seen_chains = []
    recs = scan_universe(
        [("NVDA", "加速器"), ("MU", "記憶體"), ("FAR", "設備"), ("BAD", "設備")],
        CFG, today=TODAY,
        fetch_spot=_fetch_spot, fetch_chain=_fetch_chain,
        fetch_events=lambda t: EVENTS.get(t, []),
        fetch_rv=lambda t: 0.50, rate_for=lambda dte: 0.045,
        on_chain=lambda t, S, c: seen_chains.append(t))

    # 雙透鏡:每檔 1 筆槓桿;時鐘在走(MU T-30)再加 1 筆凸性。順序保留。
    assert [(r["ticker"], r["route"]) for r in recs] == [
        ("NVDA", "leverage"), ("MU", "leverage"), ("MU", "convexity"),
        ("FAR", "leverage"), ("BAD", None)]

    nvda, mu_lev, mu_cvx, far, bad = recs
    # NVDA 無時鐘 → 只有槓桿 → PASS
    assert nvda["verdict"] == "PASS" and nvda["catalyst"] is None
    # MU 槓桿照跑(S=1000 下 LEAPS 全深價內 → delta 出帶 → 誠實排除)
    assert mu_lev["verdict"] == "EXCLUDE" and mu_lev["code"] == "LEV_NO_DELTA"
    # MU 凸性:財報 T-30 → PASS,催化劑資訊兩筆都帶
    assert mu_cvx["verdict"] == "PASS"
    assert mu_cvx["catalyst"]["dte"] == 30 and mu_lev["catalyst"]["dte"] == 30
    assert mu_cvx["card"]["multiple_at_target"] == 18.3
    # FAR:T-83 超過 lookahead → 凸性不跑,槓桿照評(不再全盲);遠期時鐘印在卡上
    assert far["verdict"] == "PASS"
    assert far["catalyst"]["within_lookahead"] is False
    assert far["card"]["catalyst_t_minus"] == 83
    # BAD 抓取炸掉 → 降級,不殺整晚
    assert bad["verdict"] == "NO_DATA" and bad["code"] == "FETCH_ERROR"
    assert "ConnectionError" in bad["error"] and bad["card"] is None

    # IV 自舉回呼:固定收 LEAPS chain(天期一致),每檔一次
    assert seen_chains == ["NVDA", "MU", "FAR"]

    # 報告吃得下整批紀錄:4 檔 5 筆、3 張卡、1 筆排除、1 筆缺資料
    md = render_report(recs, asof="2026-07-02T22:00")
    assert "掃描 **4 檔**" in md and "雙透鏡共 5 筆" in md
    assert "出卡 **3 張**" in md and "NO_DATA(1)" in md
    assert "抓取失敗" in md and "ConnectionError" in md


def test_scan_universe_empty_universe():
    recs = scan_universe([], CFG, today=TODAY, fetch_spot=None, fetch_chain=None,
                         fetch_events=None, fetch_rv=None, rate_for=None)
    assert recs == []
