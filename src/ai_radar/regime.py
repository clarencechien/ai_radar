"""市場 regime 觀察欄位(順風/逆風的**候選**指標;只記錄不裁決)。

MEASURE.md §4:對「買權利金」的策略,真正的順風/逆風是 IV 水位與 IV 方向,不是價格方向;
短窗價格動能在 2026-07~09 樣本裡是均值回歸(順風日之後更差),所以**不當閘**。
這裡每晚算一組數字、append 進 tracer(kind=regime),兩季後拿條件式報酬決定要不要當閘。

- basket_iv_regime:籃子 LEAPS ATM IV 現值、N 日變化、各檔自身 percentile 的平均
  (percentile 需自舉滿 min_history,不足 → None)。
- basket_price_regime:籃子等權 N 掃描日報酬與漲家數比例(20/60 日,長窗才有意義)。
純邏輯;輸入序列由呼叫端從 state 讀出。
"""
from __future__ import annotations

import statistics as st
from collections import defaultdict

from .volatility import iv_percentile


def basket_iv_regime(iv_series: dict, lookback: int = 20, min_history: int = 60) -> dict:
    """iv_series: {ticker: [iv, ...](依 append 順序,每天一筆)}。

    回傳 {n_tickers, iv_now, iv_then, iv_chg_pct, pct_avg, pct_n}:
    - iv_now/iv_then:各檔最新 / lookback 筆前的 IV 平均(只算兩者都有的檔)。
    - pct_avg:各檔「最新 IV 在自身歷史的 percentile」平均;自舉未滿的檔不算(pct_n = 算了幾檔)。
    """
    now, then, pcts = [], [], []
    for t, seq in (iv_series or {}).items():
        seq = [x for x in seq if x is not None]
        if not seq:
            continue
        cur = seq[-1]
        now.append(cur)
        if len(seq) > lookback:
            then.append(seq[-1 - lookback])
        else:
            now.pop()          # 沒有 lookback 前的值 → 不進變化率樣本
            now.append(None)
        p = iv_percentile(cur, seq[:-1], min_history)
        if p is not None:
            pcts.append(p)
    paired_now = [x for x in now if x is not None]
    out = {"n_tickers": sum(1 for _ in (iv_series or {})), "lookback": lookback,
           "iv_now": round(st.mean(paired_now), 4) if paired_now else None,
           "iv_then": round(st.mean(then), 4) if then else None,
           "iv_chg_pct": None, "pct_avg": round(st.mean(pcts), 1) if pcts else None,
           "pct_n": len(pcts)}
    if out["iv_now"] and out["iv_then"]:
        out["iv_chg_pct"] = round((out["iv_now"] / out["iv_then"] - 1) * 100, 1)
    return out


def basket_price_regime(scans: list[dict], windows=(20, 60), min_tickers: int = 5) -> dict:
    """scans: tracer 的 scan 紀錄(含 ticker/ts/spot)。

    對每個 window(掃描日數,不是日曆日):籃子等權報酬 % 與漲家數比例。
    掃描日不足 window+1 天 → 該窗 None(NO_DATA,不猜)。
    """
    panel = defaultdict(dict)
    for s in scans:
        if s.get("spot"):
            panel[s["ticker"]][str(s["ts"])[:10]] = s["spot"]
    days = sorted({str(s["ts"])[:10] for s in scans if s.get("spot")})
    out = {"days": len(days)}
    for w in windows:
        key = f"w{w}"
        if len(days) <= w:
            out[key] = None
            continue
        d1, d0 = days[-1], days[-1 - w]
        rets = [panel[t][d1] / panel[t][d0] - 1 for t in panel
                if d1 in panel[t] and d0 in panel[t]]
        if len(rets) < min_tickers:
            out[key] = None
            continue
        out[key] = {"ew_ret_pct": round(st.mean(rets) * 100, 1),
                    "breadth": round(sum(r > 0 for r in rets) / len(rets), 2),
                    "n": len(rets)}
    return out


def describe(iv_reg: dict, px_reg: dict) -> str:
    """一行人話(RADAR.md 頂端用)。永遠標「觀察欄位,不裁決」。"""
    parts = []
    if iv_reg.get("iv_now") is not None:
        s = f"籃子 IV {iv_reg['iv_now']:.3f}"
        if iv_reg.get("iv_chg_pct") is not None:
            s += f"({iv_reg['lookback']} 日 {iv_reg['iv_chg_pct']:+.1f}%)"
        if iv_reg.get("pct_avg") is not None:
            s += f"、自身 percentile 平均 {iv_reg['pct_avg']:.0f}({iv_reg['pct_n']} 檔)"
        else:
            s += "、percentile 自舉未滿"
        parts.append(s)
    for w in ("w20", "w60"):
        r = (px_reg or {}).get(w)
        if r:
            parts.append(f"籃子 {w[1:]} 日 {r['ew_ret_pct']:+.1f}%、漲家 {r['breadth']:.0%}")
    if not parts:
        return "regime:NO_DATA(樣本不足)"
    return "regime(觀察欄位,不裁決):" + " · ".join(parts)
