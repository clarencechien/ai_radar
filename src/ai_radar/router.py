"""Block 3 — 路由器 + 造合約(條件式單腿 call 合約卡)。

- 路由靠**論點時鐘**(SPEC §2、§6.5):某檔現在有沒有帶日期的催化劑
  → 有進凸性透鏡、沒有進槓桿透鏡。
- 合約卡永遠是「**若**動手該買哪張」,不是「該買」;扣板機永遠是人(SPEC §6)。
- 純邏輯:chain / spot / 催化劑 / IV 歷史全由呼叫端注入,沙盒可測。
- 待補(roadmap):賽馬 T1 軟催化劑規則(CVX_SOFT_CATALYST,需破壞線基建)、
  tier_map(yfinance 分不出 T1/T2,需手動清單)。
"""
from __future__ import annotations

from . import bsm
from .lenses import convexity_lens, leverage_lens

YEAR = 365.0
DISCLAIMER = "⚠️ 條件式合約卡,非建議;go/no-go 由你"


def route(catalyst_dte) -> str:
    """論點時鐘:帶日期催化劑(今天含以後)→ 凸性;否則 → 槓桿。"""
    return "convexity" if (catalyst_dte is not None and catalyst_dte >= 0) else "leverage"


def build_card(ticker, bucket, lens_result, S, r, *, tier=None, catalyst_dte=None,
               g0_enabled=False, asof=None):
    """透鏡 PASS 的 verdict → 合約卡(SPEC §6 卡欄位);非 PASS 回 None。

    欄位:標的·桶·子層·透鏡·催化劑 T-N·到期·strike·估權利金·delta·
    時間價值·倍數·損益兩平%·G0 狀態·資料時戳·條件式聲明。
    """
    if lens_result.get("verdict") != "PASS":
        return None
    c = lens_result["contract"]
    K, mid, dte = c["strike"], c["mid"], c["dte"]
    g = bsm.greeks(S, K, dte / YEAR, r, c["iv"])
    intrinsic = max(S - K, 0.0)
    return {
        "ticker": ticker, "bucket": bucket, "tier": tier,
        "lens": lens_result["lens"],
        "catalyst_t_minus": catalyst_dte,
        "expiry": c.get("expiry"), "dte": dte, "strike": K,
        "premium": round(mid, 2),
        "delta": round(g["delta"], 3),
        "extrinsic": round(max(mid - intrinsic, 0.0), 2),
        "eff_leverage": round(S / mid * g["delta"], 2),
        "breakeven_pct": round((K + mid) / S * 100.0 - 100.0, 1),
        "spot": round(S, 2),
        "lens_metrics": lens_result.get("metrics", {}),
        "g0": "ENABLED" if g0_enabled else "BYPASS(G0 未啟用,曝險/左尾自行判斷)",
        "asof": asof,
        "note": DISCLAIMER,
    }


def scan_one(ticker, bucket, S, r, contracts, cfg, *, catalyst_dte=None,
             realized_vol_val=None, iv_history=None, tier=None, asof=None) -> dict:
    """單一標的走完:路由 → 透鏡 → (PASS 時)出卡。

    回傳掃描紀錄(存活者含 card、排除者含 code),欄位即 tracer 要收的格式
    (Block 5 collect_only 可直接 append)。
    """
    lens = route(catalyst_dte)
    if lens == "convexity":
        res = convexity_lens(contracts, S, r, realized_vol_val, catalyst_dte, cfg,
                             tier=tier, iv_history=iv_history)
    else:
        res = leverage_lens(contracts, S, r, cfg, iv_history=iv_history)
    card = build_card(ticker, bucket, res, S, r, tier=tier, catalyst_dte=catalyst_dte,
                      g0_enabled=cfg.get("exposure", {}).get("enabled", False), asof=asof)
    return {"ticker": ticker, "bucket": bucket, "tier": tier, "route": lens,
            "verdict": res["verdict"], "code": res.get("code"),
            "spot": round(S, 2),   # tracer 回填 T+N 報酬的基準
            "metrics": res.get("metrics"), "card": card, "asof": asof}


def format_card(card) -> str:
    """人看的多行卡片(notebook / CLI 用)。"""
    cat = f"T-{card['catalyst_t_minus']}" if card["catalyst_t_minus"] is not None else "—"
    tier = f"/{card['tier']}" if card["tier"] else ""
    return "\n".join([
        f"┌ {card['ticker']}({card['bucket']}{tier})· {card['lens']} 透鏡 · 催化劑 {cat}",
        f"│ 若動手:{card['expiry']} ${card['strike']:g}C @ ~${card['premium']}"
        f"(spot {card['spot']})",
        f"│ delta {card['delta']} · 時間價值 ${card['extrinsic']} · "
        f"倍數 {card['eff_leverage']}x · 損益兩平 +{card['breakeven_pct']}%",
        f"│ G0:{card['g0']}",
        f"└ {card['note']}(資料時戳 {card['asof']})",
    ])
