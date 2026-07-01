# =====================================================================
# AI Radar — Block 2 雙透鏡 · Colab 驗證
# 沙盒連不到 Yahoo,這段只能 Colab/本地跑。
# 重點:不信 yfinance 的 IV,用我們的 implied_vol 從 mid 價自算。
# =====================================================================
import datetime as dt
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
            if bid <= 0 or ask <= 0:
                continue
            if otm_only and K <= S:
                continue
            mid = (bid + ask) / 2
            iv = bsm.implied_vol(mid, S, K, d / 365.0, R)
            if iv is None:
                continue
            out.append({"strike": float(K), "dte": d, "mid": float(mid), "iv": iv,
                        "oi": int(row.get("openInterest") or 0),
                        "volume": int(row.get("volume") or 0), "expiry": exp})
    return out


if __name__ == "__main__":
    # --- 槓桿透鏡:NVDA LEAPS(DTE 365–900)---
    print("=== 槓桿透鏡 · NVDA ===")
    S = spot("NVDA")
    chain = build_contracts("NVDA", S, 365, 900)
    print(f"spot={S:.2f}  合格 LEAPS 合約 {len(chain)} 張")
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
    print(f"spot={S:.2f}  財報 T-{cat_dte}  20d 實現波動={rv:.3f}" if cat_dte
          else f"spot={S:.2f}  查無財報日")
    if cat_dte:
        chain = build_contracts("MU", S, max(cat_dte, 1), cat_dte + 60, otm_only=True)
        out = convexity_lens(chain, S, R, rv, cat_dte, CFG, tier="T1")
        print("verdict:", out["verdict"], out.get("code") or "")
        if out["verdict"] == "PASS":
            c = out["contract"]
            print(f"  → {c['expiry']} ${c['strike']:.0f}C  mid≈${c['mid']:.2f}")
            print(f"     {out['metrics']}")

    print("\n注意:IV 全由 implied_vol 從 mid 自算;若合約數為 0,多半是 bid/ask 為空(收盤後)。")
