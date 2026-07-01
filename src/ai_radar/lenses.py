"""雙透鏡(中性,對所有標的同規則)。

輸入:某標的的 call chain(list of contract dict)+ 標的現況。
輸出:verdict dict {lens, verdict(PASS/EXCLUDE), code, contract, metrics}。

contract dict 需含:strike, dte(日), mid(權利金), iv(小數), oi, volume。
造合約(挑出那張)在此完成;是否動手仍是人。
"""
from __future__ import annotations

from . import bsm
from .volatility import event_iv_ratio, iv_percentile

YEAR = 365.0


def _passes_liquidity(c, liq) -> bool:
    if c.get("oi", 0) < liq["min_oi"]:
        return False
    if c.get("volume", 0) < liq["min_vol"]:
        return False
    return True


def leverage_lens(contracts, S, r, cfg, iv_history=None):
    """槓桿透鏡:DTE>門檻、delta∈區間、選每單位 delta 時間價值最低。"""
    lev, liq = cfg["leverage"], cfg["liquidity"]
    ivp_min = cfg["data"]["iv_percentile_min_history_days"]

    cands = []
    for c in contracts:
        if c["dte"] < lev["lev_dte_min"] or not _passes_liquidity(c, liq):
            continue
        T = c["dte"] / YEAR
        g = bsm.greeks(S, c["strike"], T, r, c["iv"])
        if not (lev["lev_delta_lo"] <= g["delta"] <= lev["lev_delta_hi"]):
            continue
        intrinsic = max(S - c["strike"], 0.0)
        extrinsic = max(c["mid"] - intrinsic, 0.0)
        cands.append((c, g, extrinsic / g["delta"]))  # 每單位 delta 時間價值

    if not cands:
        return {"lens": "leverage", "verdict": "EXCLUDE", "code": "LEV_NO_DELTA"}

    # IV percentile 閘(自舉;不足則 NO_DATA 跳過)
    atm_iv = min(cands, key=lambda x: abs(x[0]["strike"] - S))[0]["iv"]
    pct = iv_percentile(atm_iv, iv_history or [], ivp_min)
    if pct is not None and pct > lev["lev_iv_pct_max"]:
        return {"lens": "leverage", "verdict": "EXCLUDE", "code": "LEV_IV_HIGH",
                "metrics": {"iv_percentile": round(pct, 1)}}

    c, g, metric = min(cands, key=lambda x: x[2])
    return {
        "lens": "leverage", "verdict": "PASS", "code": None, "contract": c,
        "metrics": {"delta": round(g["delta"], 3), "theta_day": round(g["theta"], 4),
                    "extrinsic_per_delta": round(metric, 3),
                    "eff_leverage": round(S / c["mid"] * g["delta"], 2),
                    "iv_percentile": None if pct is None else round(pct, 1)},
    }


def convexity_lens(contracts, S, r, realized_vol_val, catalyst_dte, cfg, tier="T1"):
    """凸性透鏡:帶日期催化劑、便宜價外、過 IV÷實現波動 edge 閘、選 max gamma/權利金。"""
    cvx, liq = cfg["convexity"], cfg["liquidity"]
    ratio_max = cvx.get("racehorse_tiers", {}).get(tier, {}).get(
        "cvx_iv_ratio_max", cvx["cvx_iv_ratio_max"])

    if catalyst_dte is None:
        return {"lens": "convexity", "verdict": "SKIP", "code": "NO_CATALYST"}

    cands = []
    for c in contracts:
        if not _passes_liquidity(c, liq):
            continue
        if c["strike"] <= S:                       # 只價外
            continue
        otm_pct = (c["strike"] - S) / S * 100.0
        if otm_pct > cvx["cvx_otm_max_pct"]:
            continue
        if c["mid"] > cvx["cvx_prem_max_usd"]:
            continue
        # 到期需在催化劑之後、且不遠(用 earn_window 當寬容)
        if not (catalyst_dte <= c["dte"] <= catalyst_dte + cvx["earn_window_days"] + 45):
            continue
        cands.append((c, otm_pct))

    if not cands:
        return {"lens": "convexity", "verdict": "EXCLUDE", "code": "CVX_NO_STRIKE"}

    # edge 閘:事件 IV(取最接近 ATM 的價外 IV) ÷ 實現波動
    event_iv = min(cands, key=lambda x: x[1])[0]["iv"]
    ratio = event_iv_ratio(event_iv, realized_vol_val)
    if ratio is not None and ratio > ratio_max:
        return {"lens": "convexity", "verdict": "EXCLUDE", "code": "CVX_IV_PRICED",
                "metrics": {"iv_realized_ratio": round(ratio, 2), "ratio_max": ratio_max}}

    best, best_metric, best_g = None, -1.0, None
    for c, _ in cands:
        T = c["dte"] / YEAR
        g = bsm.greeks(S, c["strike"], T, r, c["iv"])
        m = g["gamma"] / c["mid"]                   # 每塊錢凸性
        if m > best_metric:
            best, best_metric, best_g = c, m, g

    return {
        "lens": "convexity", "verdict": "PASS", "code": None, "contract": best,
        "metrics": {"gamma_per_premium": round(best_metric, 5),
                    "iv_realized_ratio": None if ratio is None else round(ratio, 2),
                    "otm_pct": round((best["strike"] - S) / S * 100, 1),
                    "tier": tier},
    }
