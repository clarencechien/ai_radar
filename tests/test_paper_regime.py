"""模擬帳本(paper)+ regime 觀察欄位 + 追蹤規則變更(依透鏡停追、bench)測試。"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ai_radar.paper import paper_book, render_paper_text  # noqa: E402
from ai_radar.regime import basket_iv_regime, basket_price_regime, describe  # noqa: E402
from ai_radar.tracer import (  # noqa: E402
    record_scan, record_card_track, open_cards, record_bench, benches, card_tracks)

TODAY = dt.date(2026, 9, 11)


def _scan(t, ts, card, route, catalyst=None, spot=None):
    return {"kind": "scan", "ticker": t, "ts": ts, "verdict": "PASS", "code": None,
            "spot": spot or card["spot"], "route": route, "card": card, "catalyst": catalyst}


def _mark(card, ts, mid, spot, dte_left, bid=None, ask=None, iv=None):
    p0 = card["premium"]
    return {"kind": "card_track", "ticker": card["ticker"], "expiry": card["expiry"],
            "strike": card["strike"], "lens": card["lens"], "ts": ts, "premium_then": p0,
            "mid_now": mid, "bid_now": bid, "ask_now": ask, "iv_now": iv, "spot_now": spot,
            "dte_left": dte_left, "option_ret_pct": round((mid / p0 - 1) * 100, 1)}


LEV = {"ticker": "NVDA", "expiry": "2028-01-21", "strike": 170.0, "lens": "leverage",
       "premium": 60.0, "bid": 59.0, "ask": 61.0, "spot": 200.0, "delta": 0.8,
       "iv": 0.45, "vega": 0.9, "theta_day": -0.05}
CVX = {"ticker": "MU", "expiry": "2026-10-02", "strike": 1200.0, "lens": "convexity",
       "premium": 10.0, "bid": 9.5, "ask": 10.5, "spot": 1000.0, "delta": 0.15,
       "iv": 0.9, "vega": 0.5, "theta_day": -0.3}
CAT = {"date": "2026-09-30", "dte": 20}


# ---- 追蹤規則:依透鏡停追 + catalyst_date 帶進標記 ----
def test_open_cards_stop_days_by_lens(tmp_path):
    p = str(tmp_path / "t.jsonl")
    record_scan(p, _scan("NVDA", "2026-09-01T14:00:00+00:00", LEV, "leverage"))
    record_scan(p, _scan("MU", "2026-09-10T14:00:00+00:00", CVX, "convexity", catalyst=CAT))
    stop = {"leverage": 21, "convexity": 0}
    # 凸性卡到期前 1 天仍追(0 = 追到到期日);槓桿卡剩 21 天停
    due = {c["ticker"]: c for c in open_cards(p, dt.date(2026, 10, 1), stop)}
    assert "MU" in due and due["MU"]["catalyst_date"] == "2026-09-30"
    assert due["MU"]["lens"] == "convexity" and due["MU"]["dte_left"] == 1
    assert "MU" not in {c["ticker"] for c in open_cards(p, dt.date(2026, 10, 2), stop)}
    assert "NVDA" not in {c["ticker"] for c in open_cards(p, dt.date(2027, 12, 31), stop)}
    # int 仍相容(全透鏡同值)
    assert "MU" not in {c["ticker"] for c in open_cards(p, dt.date(2026, 10, 1), 21)}

    rec = record_card_track(p, due["MU"], mid_now=12.0, spot_now=1050.0,
                            bid_now=11.5, ask_now=12.5, iv_now=0.95)
    assert rec["catalyst_date"] == "2026-09-30" and rec["bid_now"] == 11.5
    assert rec["iv_now"] == 0.95 and rec["option_ret_pct"] == 20.0
    assert card_tracks(p)[0]["lens"] == "convexity"


def test_record_bench_idempotent_per_day(tmp_path):
    p = str(tmp_path / "t.jsonl")
    assert record_bench(p, TODAY, {"SMH": 300.0, "SPY": None}) is not None
    assert record_bench(p, TODAY, {"SMH": 301.0}) is None          # 同日不重灌
    assert len(benches(p)) == 1 and benches(p)[0]["quotes"]["SPY"] is None


# ---- 模擬帳本 ----
def _records():
    recs = [
        _scan("NVDA", "2026-09-01T14:00:00+00:00", LEV, "leverage"),
        _scan("NVDA", "2026-09-02T14:00:00+00:00", {**LEV, "premium": 62.0}, "leverage"),
        _scan("MU", "2026-09-10T14:00:00+00:00", CVX, "convexity", catalyst=CAT),
        {"kind": "bench", "ts": "2026-09-01T14:30:00+00:00", "quotes": {"SMH": 300.0}},
        {"kind": "bench", "ts": "2026-09-11T14:30:00+00:00", "quotes": {"SMH": 306.0}},
        # 槓桿:標的 +10%(200→220),IV 0.45→0.40,10 天
        _mark(LEV, "2026-09-11T14:30:00+00:00", 70.0, 220.0, 497, bid=69.0, ask=71.0, iv=0.40),
        # 凸性:事件前一筆、事件後一筆(以事件後那筆出場)
        _mark(CVX, "2026-09-29T14:30:00+00:00", 15.0, 1100.0, 3, bid=14.0, ask=16.0, iv=1.0),
        _mark(CVX, "2026-10-01T14:30:00+00:00", 4.0, 1150.0, 1, bid=3.5, ask=4.5, iv=0.6),
    ]
    return recs


def test_paper_book_positions_and_attribution():
    book = paper_book(_records(), today=dt.date(2026, 10, 1))
    pos = {p["ticker"]: p for p in book["positions"]}
    assert len(book["positions"]) == 2                 # 同卡第二次上榜不重複開倉

    lev = pos["NVDA"]
    assert lev["status"] == "OPEN" and lev["cost_basis"] == "ask" and lev["entry_cost"] == 61.0
    assert lev["ret_mid_pct"] == round((70 / 60 - 1) * 100, 1)
    assert lev["ret_cost_pct"] == round((69 / 61 - 1) * 100, 1)   # ask 進、bid 清算
    assert lev["underlying_ret_pct"] == 10.0
    assert lev["delta_implied_ret_pct"] == round(0.8 * 20 / 60 * 100, 1)   # 26.7
    assert lev["substitute_gap"] == round(lev["ret_mid_pct"] - 26.7, 1)
    a = lev["attribution"]
    assert a["delta"] == 16.0                            # 0.8 × 20
    assert a["vega"] == -4.5                             # 0.9 × (−5 vol 點)
    assert a["theta"] == -0.5                            # −0.05 × 10 天
    assert abs(a["delta"] + a["vega"] + a["theta"] + a["residual"] - 10.0) < 1e-6
    assert lev["bench_ret_pct"] == 2.0                   # SMH 300 → 306
    assert lev["pnl_usd"] == round((69.0 - 61.0) * 100)

    cvx = pos["MU"]
    assert cvx["status"] == "CLOSED" and cvx["exit_day"] == "2026-10-01"
    assert cvx["exit_px"] == 3.5                         # CLOSED 以 bid 出場
    assert cvx["ret_mid_pct"] == -60.0
    assert cvx["ret_cost_pct"] == round((3.5 / 10.5 - 1) * 100, 1)

    s = book["summary"]
    assert s["leverage"]["n"] == 1 and s["leverage"]["by_status"] == {"OPEN": 1}
    assert s["convexity"]["post_event_n"] == 1 and s["convexity"]["post_event_mean_ret_pct"] == -60.0
    assert s["convexity"]["n_eff"] == 1
    txt = render_paper_text(book)
    assert "模擬帳本" in txt and "post-event" in txt


def test_paper_book_censored_and_no_mark_and_leverage_close():
    old_cvx = {**CVX, "expiry": "2026-08-28"}
    cat = {"date": "2026-08-26", "dte": 20}
    recs = [
        _scan("MU", "2026-08-01T14:00:00+00:00", old_cvx, "convexity", catalyst=cat),
        _mark(old_cvx, "2026-08-05T14:30:00+00:00", 20.0, 1050.0, 23),   # 舊規則:事件前停追
        _scan("AMD", "2026-08-01T14:00:00+00:00", {**CVX, "ticker": "AMD", "expiry": "2026-08-07"},
              "convexity", catalyst=cat),                                  # 從沒標記過
        _scan("NVDA", "2026-01-01T14:00:00+00:00", {**LEV, "expiry": "2026-10-16"}, "leverage"),
        _mark({**LEV, "expiry": "2026-10-16"}, "2026-09-24T14:30:00+00:00", 80.0, 230.0, 22,
              bid=79.0),
    ]
    book = paper_book(recs, today=dt.date(2026, 9, 26))
    st = {p["ticker"]: p["status"] for p in book["positions"]}
    assert st == {"MU": "CENSORED", "AMD": "NO_MARK", "NVDA": "CLOSED"}
    nv = next(p for p in book["positions"] if p["ticker"] == "NVDA")
    assert nv["exit_px"] == 79.0 and nv["ret_cost_pct"] == round((79 / 61 - 1) * 100, 1)
    s = book["summary"]["convexity"]
    assert s["scored"] == 0 and s["mean_ret_mid_pct"] is None   # CENSORED/NO_MARK 不計分
    assert s["by_status"] == {"CENSORED": 1, "NO_MARK": 1}


def test_paper_book_empty_ok():
    book = paper_book([], today=TODAY)
    assert book["positions"] == [] and book["summary"] == {}
    assert "模擬帳本" in render_paper_text(book)


# ---- regime 觀察欄位 ----
def test_basket_iv_regime_change_and_percentile():
    hist = {"A": [0.5 + 0.01 * i for i in range(70)],   # 70 筆,單調上升 → 最新在 100 分位
            "B": [0.8] * 10,                             # 不到 lookback → 不進變化率、不進 percentile
            "C": [None, None]}                           # NO_DATA
    r = basket_iv_regime(hist, lookback=20, min_history=60)
    assert r["n_tickers"] == 3 and r["pct_n"] == 1 and r["pct_avg"] == 100.0
    assert r["iv_now"] == round(0.5 + 0.69, 4) and r["iv_then"] == round(0.5 + 0.49, 4)
    assert r["iv_chg_pct"] == round((1.19 / 0.99 - 1) * 100, 1)
    empty = basket_iv_regime({}, lookback=20)
    assert empty["iv_now"] is None and empty["iv_chg_pct"] is None


def test_basket_price_regime_windows_and_no_data():
    scans = []
    for i in range(25):
        day = f"2026-08-{i + 1:02d}T14:00:00+00:00" if i < 25 else None
        for t, base in (("A", 100), ("B", 50), ("C", 20), ("D", 10), ("E", 5), ("F", 1)):
            scans.append({"kind": "scan", "ticker": t, "ts": day,
                          "spot": base * (1 + 0.01 * i) if t != "F" else base * (1 - 0.01 * i)})
    r = basket_price_regime(scans, windows=(20, 60), min_tickers=5)
    assert r["days"] == 25 and r["w60"] is None                 # 掃描日不足 → NO_DATA
    w20 = r["w20"]
    assert w20["n"] == 6 and w20["breadth"] == round(5 / 6, 2) and w20["ew_ret_pct"] > 0
    line = describe({"iv_now": 0.51, "iv_then": 0.60, "iv_chg_pct": -15.0,
                     "pct_avg": None, "pct_n": 0, "lookback": 20}, r)
    assert "觀察欄位,不裁決" in line and "自舉未滿" in line and "20 日" in line
    assert describe({"iv_now": None}, {}) == "regime:NO_DATA(樣本不足)"
