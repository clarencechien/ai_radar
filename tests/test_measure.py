"""量測模組測試(合成資料)。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ai_radar.measure import (  # noqa: E402
    effective_n, verdict_table, card_returns_by_lens, convexity_event_coverage,
    iv_trend, regime_prototype, measure_all, render_text)


def _scan(t, ts, verdict, spot, card=None, route="leverage", catalyst=None):
    return {"kind": "scan", "ticker": t, "ts": ts, "verdict": verdict,
            "code": None if verdict == "PASS" else "X", "spot": spot, "route": route,
            "card": card, "catalyst": catalyst}


def _out(t, ts, h, ret):
    return {"kind": "outcome", "ticker": t, "scan_ts": ts, "horizon_days": h,
            "underlying_ret_pct": ret}


def test_effective_n_is_windows_times_clusters():
    assert effective_n(49, 20, 12) == 3 * 12
    assert effective_n(0, 20, 12) == 0
    assert effective_n(5, 20, 1) == 1


def test_verdict_table_has_universe_baseline_and_n_eff():
    recs = [
        _scan("A", "2026-07-01T10:00", "PASS", 100),
        _scan("B", "2026-07-01T10:00", "EXCLUDE", 50),
        _scan("A", "2026-07-02T10:00", "PASS", 101),
        _out("A", "2026-07-01T10:00", 5, 8.0),
        _out("B", "2026-07-01T10:00", 5, -4.0),
        _out("A", "2026-07-02T10:00", 5, 6.0),
    ]
    vt = verdict_table(recs, horizons=(5,))["T+5"]
    assert vt["PASS"]["n"] == 2 and vt["PASS"]["mean"] == 7.0
    assert vt["EXCLUDE"]["n"] == 1 and vt["EXCLUDE"]["mean"] == -4.0
    # 全宇宙:3 筆 (ticker, day) 去重 → (8 − 4 + 6)/3
    assert vt["UNIVERSE"]["n"] == 3 and abs(vt["UNIVERSE"]["mean"] - 3.33) < 0.01
    assert abs(vt["pass_minus_universe"] - 3.67) < 0.01
    assert vt["PASS"]["n_eff"] == 1 * 1          # 2 天 / 5 天窗 = 1 視窗 × 1 群
    assert vt["PASS"]["per_ticker_mean"] == {"A": 7.0}


def test_card_returns_substitute_gap_and_n_eff():
    lev = {"ticker": "A", "expiry": "2028-01-21", "strike": 100.0, "lens": "leverage",
           "premium": 50.0, "spot": 120.0, "delta": 0.8}
    lev2 = {**lev, "strike": 110.0, "premium": 40.0}
    cvx = {"ticker": "B", "expiry": "2026-09-18", "strike": 260.0, "lens": "convexity",
           "premium": 2.0, "spot": 230.0, "delta": 0.15}
    recs = [
        _scan("A", "2026-07-01T10:00", "PASS", 120, lev),
        _scan("A", "2026-07-02T10:00", "PASS", 121, lev2),
        _scan("B", "2026-07-01T10:00", "PASS", 230, cvx, route="convexity"),
        # 標的 +10%(120→132),delta 0.8 應得 = 0.8×12/50 = 19.2%;實際只 +5% → 缺口 −14.2
        {"kind": "card_track", "ticker": "A", "expiry": "2028-01-21", "strike": 100.0,
         "ts": "2026-07-20T10:00", "mid_now": 52.5, "spot_now": 132.0, "dte_left": 500,
         "option_ret_pct": 5.0},
        {"kind": "card_track", "ticker": "A", "expiry": "2028-01-21", "strike": 110.0,
         "ts": "2026-07-20T10:00", "mid_now": 44.0, "spot_now": 132.0, "dte_left": 500,
         "option_ret_pct": 10.0},
        {"kind": "card_track", "ticker": "B", "expiry": "2026-09-18", "strike": 260.0,
         "ts": "2026-07-20T10:00", "mid_now": 1.0, "spot_now": 225.0, "dte_left": 60,
         "option_ret_pct": -50.0},
    ]
    cr = card_returns_by_lens(recs)
    assert cr["leverage"]["n"] == 2 and cr["leverage"]["n_eff"] == 1   # 同檔兩張 = 1 群
    assert cr["leverage"]["rows"][0]["substitute_gap"] == -14.2
    assert cr["leverage"]["underlying_mean"] == 10.0
    assert cr["leverage"]["substitute_gap_neg_pct"] == 100.0
    assert cr["convexity"]["n"] == 1 and cr["convexity"]["mean"] == -50.0


def test_convexity_coverage_flags_tracks_stopped_before_event():
    cvx = {"ticker": "B", "expiry": "2026-09-18", "strike": 260.0, "lens": "convexity",
           "premium": 2.0, "spot": 230.0, "delta": 0.15}
    cat = {"date": "2026-08-26", "dte": 56}
    recs = [
        _scan("B", "2026-07-01T10:00", "PASS", 230, cvx, route="convexity", catalyst=cat),
        _scan("B", "2026-07-01T10:00", "PASS", 230, {**cvx, "expiry": "2026-08-28"},
              route="convexity", catalyst=cat),
        {"kind": "card_track", "ticker": "B", "expiry": "2026-09-18", "strike": 260.0,
         "ts": "2026-08-27T10:00", "mid_now": 1.0, "spot_now": 225.0, "dte_left": 22,
         "option_ret_pct": -50.0},
        {"kind": "card_track", "ticker": "B", "expiry": "2026-08-28", "strike": 260.0,
         "ts": "2026-08-05T10:00", "mid_now": 3.0, "spot_now": 240.0, "dte_left": 23,
         "option_ret_pct": 50.0},
    ]
    cv = convexity_event_coverage(recs)
    assert cv["n"] == 2 and cv["covered"] == 1
    flags = {r["expiry"]: r["covered"] for r in cv["rows"]}
    assert flags["2026-09-18"] is True and flags["2026-08-28"] is False


def test_iv_trend_basket_change():
    ivs = [{"ticker": "A", "iv": 0.8, "ts": "2026-07-01T10:00"},
           {"ticker": "B", "iv": 0.6, "ts": "2026-07-01T10:00"},
           {"ticker": "A", "iv": 0.6, "ts": "2026-08-01T10:00"},
           {"ticker": "B", "iv": 0.4, "ts": "2026-08-01T10:00"},
           {"ticker": "C", "iv": None, "ts": "2026-08-01T10:00"}]   # NO_DATA 不進樣本
    t = iv_trend(ivs)
    assert t["days"] == 2 and t["basket_first"] == 0.7 and t["basket_last"] == 0.5
    assert abs(t["basket_chg_pct"] - (-28.6)) < 0.1
    assert t["per_ticker"]["A"]["chg_pct"] == -25.0 and "C" not in t["per_ticker"]


def test_regime_prototype_labels_and_conditional():
    recs = []
    # 6 檔、14 天:前 10 天平盤,第 11 天起漲 → 第 11–14 天 TAIL
    for i in range(14):
        day = f"2026-07-{i + 1:02d}T10:00"
        for t in "ABCDEF":
            px = 100.0 + (5.0 if i >= 10 else 0.0)
            recs.append(_scan(t, day, "PASS" if t == "A" else "EXCLUDE", px))
            recs.append(_out(t, day, 10, -3.0 if i >= 10 else 2.0))
    rg = regime_prototype(recs, horizons=(10,), window=10, min_history=10)
    assert rg["days_by_label"] == {"TAIL": 4}          # 第 11 天前無 10 日窗
    cond = rg["conditional"]["T+10"]
    assert cond["TAIL/PASS"]["mean"] == -3.0 and cond["TAIL/EXCLUDE"]["n"] == 20


def test_session_breakdown_counts_unstamped_as_none():
    from ai_radar.measure import session_breakdown
    recs = [_scan("A", "2026-07-01T10:00", "PASS", 100),
            {**_scan("A", "2026-09-12T10:00", "PASS", 100), "session": "after_close"},
            {"kind": "bench", "ts": "2026-09-12T10:00", "quotes": {}, "session": "intraday"}]
    sb = session_breakdown(recs)
    assert sb["scan"] == {"None": 1, "after_close": 1} and sb["bench"] == {"intraday": 1}


def test_measure_all_and_render_do_not_crash_on_empty():
    m = measure_all([], [])
    txt = render_text(m)
    assert "濾網" in txt and "凸性卡" in txt
