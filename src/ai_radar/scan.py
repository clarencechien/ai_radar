"""正式進入點的純邏輯:掃整個宇宙(把 Block 1–5 串成一條)。

每檔:催化劑時鐘 → 路由 → 抓對應天期的 chain → 透鏡 → (PASS)出卡。
live fetcher 全部注入(`live_yf` 提供 yfinance 版),沙盒可用 mock 離線測。
單檔失敗 → NO_DATA/FETCH_ERROR 降級,絕不讓一檔壞資料殺掉整晚掃描。
"""
from __future__ import annotations

from .catalysts import next_catalyst
from .router import route, scan_one


def scan_universe(universe, cfg, *, today, fetch_spot, fetch_chain, fetch_events,
                  fetch_rv, rate_for, iv_history=None, asof=None,
                  on_chain=None, sleep=None) -> list[dict]:
    """universe: [(ticker, bucket), ...] → scan 紀錄 list(順序保留)。

    - fetch_chain(ticker, S, min_dte, max_dte, otm_only) -> contracts
    - rate_for(dte) -> 年化無風險利率
    - on_chain(ticker, S, chain):抓到 chain 時回呼(IV 自舉記錄用)
    - sleep():每檔之間的節流(對 Yahoo 客氣點)
    """
    lookahead = cfg.get("catalyst", {}).get("lookahead_days")
    lev_min = cfg["leverage"]["lev_dte_min"]
    recs = []
    for ticker, bucket in universe:
        try:
            S = fetch_spot(ticker)
            cat = next_catalyst(fetch_events(ticker), today, lookahead)
            # 每家公司永遠有「下一次財報」——時鐘超過 lookahead 視為「現在沒在走」,
            # 本輪走槓桿(預設姿勢);時鐘仍附在紀錄上給人看(遠期)。
            cat_dte = (cat["dte"] if cat and cat.get("within_lookahead", True)
                       else None)
            if route(cat_dte) == "convexity":
                chain = fetch_chain(ticker, S, max(cat_dte, 1), cat_dte + 60, True)
                rv, r = fetch_rv(ticker), rate_for(cat_dte)
            else:
                chain = fetch_chain(ticker, S, lev_min, lev_min + 535, False)
                rv, r = None, rate_for(730)
            if on_chain:
                on_chain(ticker, S, chain)
            rec = scan_one(ticker, bucket, S, r, chain, cfg,
                           catalyst_dte=cat_dte, realized_vol_val=rv,
                           iv_history=(iv_history or {}).get(ticker), asof=asof)
            rec["catalyst"] = cat
        except Exception as e:   # 單檔炸 → 降級記錄,整晚掃描不陪葬
            rec = {"ticker": ticker, "bucket": bucket, "tier": None, "route": None,
                   "verdict": "NO_DATA", "code": "FETCH_ERROR", "spot": None,
                   "metrics": None, "card": None, "asof": asof,
                   "error": f"{type(e).__name__}: {e}"[:200]}
        recs.append(rec)
        if sleep:
            sleep()
    return recs
