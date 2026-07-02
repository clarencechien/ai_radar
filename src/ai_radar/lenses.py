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
    # OI 是硬門檻(每日結算、收盤後仍在,LEAPS 的主要流動性訊號)
    if c.get("oi", 0) < liq["min_oi"]:
        return False
    # volume 僅在「有記錄到成交」時才生效;收盤後 volume=0 不因此淘汰,靠 OI
    vol = c.get("volume", 0) or 0
    if vol > 0 and vol < liq["min_vol"]:
        return False
    # 價差閘僅在「有雙邊報價」時才生效;收盤後 bid/ask 空 → 跳過,靠 OI
    bid, ask = c.get("bid", 0) or 0, c.get("ask", 0) or 0
    if bid > 0 and ask > 0:
        mid = (bid + ask) / 2.0
        if (ask - bid) / mid * 100.0 > liq["max_spread_pct"]:
            return False
    return True


def _valid_contract(c) -> bool:
    # NO_DATA 降級:iv/mid/dte 缺失或非正 → 跳過該張,不讓 BSM 拋例外崩潰
    return (c.get("iv") or 0) > 0 and (c.get("mid") or 0) > 0 and (c.get("dte") or 0) > 0


def leverage_lens(contracts, S, r, cfg, iv_history=None):
    """槓桿透鏡:DTE>門檻、delta∈區間、選每單位 delta 時間價值最低。"""
    lev, liq = cfg["leverage"], cfg["liquidity"]
    ivp_min = cfg["data"]["iv_percentile_min_history_days"]

    cands = []
    for c in contracts:
        if not _valid_contract(c):
            continue
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


def convexity_lens(contracts, S, r, realized_vol_val, catalyst_dte, cfg, tier=None,
                   iv_history=None):
    """凸性透鏡:帶日期催化劑、便宜價外、過 edge 閘、選 max gamma/權利金。

    edge 閘基準(HANDOFF §8.3 改良):
    - IV 自身歷史夠(自舉完成)→ 用 IV percentile 當基準,不受實現波動失真影響
      (拋物線行情把 realized vol 灌到 130%+ 時,舊 ratio 閘永遠說「便宜」)。
    - 歷史不足 → 後備:IV ÷ 實現波動 ratio(原行為)。
    tier 只給賽馬桶用(T1/T2 各有自己的 edge 閘);其他桶傳 None 走基準閘。
    """
    cvx, liq = cfg["convexity"], cfg["liquidity"]
    tier_cfg = cvx.get("racehorse_tiers", {}).get(tier, {})
    ratio_max = tier_cfg.get("cvx_iv_ratio_max", cvx["cvx_iv_ratio_max"])
    pct_max = tier_cfg.get("cvx_iv_pct_max", cvx.get("cvx_iv_pct_max", 100.0))
    ivp_min = cfg["data"]["iv_percentile_min_history_days"]

    if catalyst_dte is None:
        return {"lens": "convexity", "verdict": "SKIP", "code": "NO_CATALYST"}

    cands = []
    for c in contracts:
        if not _valid_contract(c) or not _passes_liquidity(c, liq):
            continue
        if c["strike"] <= S:                       # 只價外
            continue
        otm_pct = (c["strike"] - S) / S * 100.0
        if otm_pct > cvx["cvx_otm_max_pct"]:
            continue
        # 權利金上限:相對股價(%),隨股價縮放。$1154 的股票 $1.5 絕對上限沒意義。
        prem_cap_pct = cvx.get("cvx_prem_max_pct")
        if prem_cap_pct is not None:
            if c["mid"] > prem_cap_pct / 100.0 * S:
                continue
        elif c["mid"] > cvx.get("cvx_prem_max_usd", float("inf")):  # 後備:舊式絕對上限
            continue
        # 到期需在催化劑之後、且不遠(用 earn_window 當寬容)
        if not (catalyst_dte <= c["dte"] <= catalyst_dte + cvx["earn_window_days"] + 45):
            continue
        cands.append((c, otm_pct))

    if not cands:
        return {"lens": "convexity", "verdict": "EXCLUDE", "code": "CVX_NO_STRIKE"}

    # edge 閘:事件 IV = 最接近 ATM 的價外 IV;percentile 優先、ratio 後備
    event_iv = min(cands, key=lambda x: x[1])[0]["iv"]
    ratio = event_iv_ratio(event_iv, realized_vol_val)
    pct = iv_percentile(event_iv, iv_history or [], ivp_min)
    if pct is not None:
        edge_basis = "iv_percentile"
        if pct > pct_max:
            return {"lens": "convexity", "verdict": "EXCLUDE", "code": "CVX_IV_PRICED",
                    "metrics": {"edge_basis": edge_basis, "iv_percentile": round(pct, 1),
                                "pct_max": pct_max,
                                "iv_realized_ratio": None if ratio is None else round(ratio, 2)}}
    else:
        edge_basis = None if ratio is None else "iv_realized_ratio"
        if ratio is not None and ratio > ratio_max:
            return {"lens": "convexity", "verdict": "EXCLUDE", "code": "CVX_IV_PRICED",
                    "metrics": {"edge_basis": edge_basis,
                                "iv_realized_ratio": round(ratio, 2), "ratio_max": ratio_max}}

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
                    "edge_basis": edge_basis,
                    "iv_percentile": None if pct is None else round(pct, 1),
                    "iv_realized_ratio": None if ratio is None else round(ratio, 2),
                    "otm_pct": round((best["strike"] - S) / S * 100, 1),
                    "tier": tier},
    }
