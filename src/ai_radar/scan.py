"""正式進入點的純邏輯:掃整個宇宙(把 Block 1–5 串成一條)。

每檔:催化劑時鐘 → 路由 → 抓對應天期的 chain → 透鏡 → (PASS)出卡。
live fetcher 全部注入(`live_yf` 提供 yfinance 版),沙盒可用 mock 離線測。
單檔失敗 → NO_DATA/FETCH_ERROR 降級,絕不讓一檔壞資料殺掉整晚掃描。
"""
from __future__ import annotations

from .catalysts import next_catalyst
from .router import scan_one


def _err_rec(ticker, bucket, route, asof, e):
    return {"ticker": ticker, "bucket": bucket, "tier": None, "route": route,
            "verdict": "NO_DATA", "code": "FETCH_ERROR", "spot": None,
            "metrics": None, "card": None, "asof": asof,
            "error": f"{type(e).__name__}: {e}"[:200]}


def scan_universe(universe, cfg, *, today, fetch_spot, fetch_chain, fetch_events,
                  fetch_rv, rate_for, iv_history=None, asof=None,
                  on_chain=None, sleep=None) -> list[dict]:
    """universe: [(ticker, bucket), ...] → scan 紀錄 list(每檔 1–2 筆,順序保留)。

    雙透鏡並行(2026-07-07 設計決策,回到 HANDOFF §1 原意「同一檔各看一次」):
    - **槓桿透鏡每檔永遠跑**(大象的預設姿勢)。單透鏡路由的實測成本:
      NVDA/AMD 財報前 60 天全被路由去凸性再被權利金閘排除,槓桿視角整季全盲。
    - **凸性透鏡只在時鐘「現在在走」(催化劑 ≤ lookahead)時加跑**,沒時鐘跑它無意義。
    - 同檔可同晚出兩張卡(兩種玩法、兩個條件式答案),tracer 各自追蹤。

    - fetch_chain(ticker, S, min_dte, max_dte, otm_only) -> contracts
    - on_chain(ticker, S, chain):LEAPS chain 回呼(IV 自舉;固定 LEAPS 天期,序列一致)
    - sleep():每檔之間的節流(對 Yahoo 客氣點)
    """
    lookahead = cfg.get("catalyst", {}).get("lookahead_days")
    lev_min = cfg["leverage"]["lev_dte_min"]
    recs = []
    for ticker, bucket in universe:
        hist = (iv_history or {}).get(ticker)
        try:
            S = fetch_spot(ticker)
            cat = next_catalyst(fetch_events(ticker), today, lookahead)
        except Exception as e:   # spot/事件都拿不到 → 這檔整晚降級
            recs.append(_err_rec(ticker, bucket, None, asof, e))
            if sleep:
                sleep()
            continue
        cat_dte = cat["dte"] if cat else None
        near = bool(cat) and cat.get("within_lookahead", True)

        # 槓桿透鏡:永遠跑(時鐘遠近只印在卡上,不影響評估)
        try:
            chain = fetch_chain(ticker, S, lev_min, lev_min + 535, False)
            if on_chain:
                on_chain(ticker, S, chain)
            rec = scan_one(ticker, bucket, S, rate_for(730), chain, cfg,
                           lens="leverage", catalyst_dte=cat_dte,
                           iv_history=hist, asof=asof)
        except Exception as e:
            rec = _err_rec(ticker, bucket, "leverage", asof, e)
        rec["catalyst"] = cat
        recs.append(rec)

        # 凸性透鏡:時鐘在走才加跑
        if near:
            try:
                chain = fetch_chain(ticker, S, max(cat_dte, 1), cat_dte + 60, True)
                rec2 = scan_one(ticker, bucket, S, rate_for(cat_dte), chain, cfg,
                                lens="convexity", catalyst_dte=cat_dte,
                                realized_vol_val=fetch_rv(ticker),
                                iv_history=hist, asof=asof)
            except Exception as e:
                rec2 = _err_rec(ticker, bucket, "convexity", asof, e)
            rec2["catalyst"] = cat
            recs.append(rec2)
        if sleep:
            sleep()
    return recs
