# =====================================================================
# AI Radar — Block 2 雙透鏡 · Colab 驗證
# 沙盒連不到 Yahoo,這段只能 Colab/本地跑。
# 重點:不信 yfinance 的 IV,用我們的 implied_vol 從 mid 價自算。
# =====================================================================
import datetime as dt
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import yfinance as yf  # noqa: E402
from ai_radar import bsm  # noqa: E402
from ai_radar.universe import load_json  # noqa: E402
from ai_radar.volatility import realized_vol  # noqa: E402
from ai_radar.lenses import leverage_lens, convexity_lens  # noqa: E402

CFG = load_json(os.path.join(os.path.dirname(__file__), "..", "config", "config.json"))
R = 0.045          # 無風險利率(之後可接 T-bill;先固定)
TODAY = dt.date.today()


def _safe_int(x):
    """pandas 缺值是 NaN(float 且 truthy),int(NaN) 會炸 → 一律歸 0。"""
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return 0
        return int(x)
    except (ValueError, TypeError):
        return 0


def spot(t):
    return float(yf.Ticker(t).history(period="1d")["Close"].iloc[-1])


def realized_20d(t):
    px = yf.Ticker(t).history(period="3mo")["Close"].tolist()
    return realized_vol(px, window=CFG["data"]["realized_vol_window_days"])


def next_earnings_dte(t):
    try:
        cal = yf.Ticker(t).calendar
        ed = cal.get("Earnings Date")
        d = ed[0] if isinstance(ed, list) else ed
        if isinstance(d, dt.datetime):
            d = d.date()
        return (d - TODAY).days
    except Exception:
        return None


def build_contracts(t, S, min_dte, max_dte, otm_only=False):
    """抓相關到期的 call,mid=(bid+ask)/2,IV 自算(implied_vol)。"""
    tk = yf.Ticker(t)
    out = []
    for exp in tk.options:
        d = (dt.date.fromisoformat(exp) - TODAY).days
        if not (min_dte <= d <= max_dte):
            continue
        calls = tk.option_chain(exp).calls
        for _, row in calls.iterrows():
            bid, ask, K = row["bid"], row["ask"], row["strike"]
            if otm_only and K <= S:
                continue
            # 盤中用 mid;收盤後 bid/ask 常為 0 → 退回 lastPrice
            if bid > 0 and ask > 0:
                mid = (bid + ask) / 2
            elif (row.get("lastPrice") or 0) > 0:
                mid = float(row["lastPrice"])
            else:
                continue
            iv = bsm.implied_vol(mid, S, K, d / 365.0, R)
            if iv is None:
                continue
            out.append({"strike": float(K), "dte": d, "mid": float(mid), "iv": iv,
                        "bid": float(bid or 0), "ask": float(ask or 0),
                        "oi": _safe_int(row.get("openInterest")),
                        "volume": _safe_int(row.get("volume")), "expiry": exp})
    return out


if __name__ == "__main__":
    # --- 槓桿透鏡:NVDA LEAPS(DTE 365–900)---
    print("=== 槓桿透鏡 · NVDA ===")
    S = spot("NVDA")
    chain = build_contracts("NVDA", S, 365, 900)
    print(f"spot={S:.2f}  合格 LEAPS 合約 {len(chain)} 張")

    # 診斷:逐關淘汰數,讓 EXCLUDE 不再是黑盒
    liq = CFG["liquidity"]
    pass_oi = [c for c in chain if c["oi"] >= liq["min_oi"]]
    deltas = []
    for c in pass_oi:
        g = bsm.greeks(S, c["strike"], c["dte"] / 365.0, R, c["iv"])
        deltas.append(g["delta"])
    in_band = [d for d in deltas
               if CFG["leverage"]["lev_delta_lo"] <= d <= CFG["leverage"]["lev_delta_hi"]]
    print(f"  診斷:過 OI({liq['min_oi']}) {len(pass_oi)} 張 | "
          f"其中 delta∈[{CFG['leverage']['lev_delta_lo']},{CFG['leverage']['lev_delta_hi']}] {len(in_band)} 張")
    if deltas:
        print(f"  delta 範圍 {min(deltas):.2f}–{max(deltas):.2f}")

    out = leverage_lens(chain, S, R, CFG)
    print("verdict:", out["verdict"], out.get("code") or "")
    if out["verdict"] == "PASS":
        c = out["contract"]
        print(f"  → {c['expiry']} ${c['strike']:.0f}C  mid≈${c['mid']:.2f}")
        print(f"     {out['metrics']}")

    # --- 凸性透鏡:MU,催化劑=下次財報 ---
    print("\n=== 凸性透鏡 · MU(催化劑=財報)===")
    S = spot("MU")
    cat_dte = next_earnings_dte("MU")
    rv = realized_20d("MU")
    rv_txt = f"{rv:.3f}" if rv is not None else "NO_DATA"
    if cat_dte is not None and cat_dte >= 0:
        print(f"spot={S:.2f}  財報 T-{cat_dte}  20d 實現波動={rv_txt}")
    else:
        print(f"spot={S:.2f}  查無(未來)財報日  20d 實現波動={rv_txt}")
        cat_dte = None
    if cat_dte is not None:
        chain = build_contracts("MU", S, max(cat_dte, 1), cat_dte + 60, otm_only=True)
        # MU 是記憶體桶(收費員),不是賽馬 → 不帶 tier,走基準 edge 閘
        out = convexity_lens(chain, S, R, rv, cat_dte, CFG)
        print("verdict:", out["verdict"], out.get("code") or "")
        if out["verdict"] == "PASS":
            c = out["contract"]
            print(f"  → {c['expiry']} ${c['strike']:.0f}C  mid≈${c['mid']:.2f}")
            print(f"     {out['metrics']}")

    print("\n注意:IV 全由 implied_vol 從 mid 自算;若合約數為 0,多半是 bid/ask 為空(收盤後)。")
