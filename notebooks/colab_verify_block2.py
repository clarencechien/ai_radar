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
from ai_radar.rates import yield_quote_to_decimal, resolve_rate  # noqa: E402
from ai_radar.state import append_record, latest_by_key, series_by_key  # noqa: E402
from ai_radar.lenses import (  # noqa: E402
    leverage_lens, convexity_lens, _passes_liquidity, _valid_contract)
from ai_radar.router import scan_one, format_card  # noqa: E402

CFG = load_json(os.path.join(os.path.dirname(__file__), "..", "config", "config.json"))
TODAY = dt.date.today()
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "state")
IV_HISTORY = os.path.join(STATE_DIR, "iv_history.jsonl")

# --- Block 2.5:真 T-bill 利率(^IRX=13週、^FVX=5年;抓不到 → 降級回預設)---
R_DEFAULT = CFG["data"].get("risk_free_rate_default", 0.045)
R_CUTOFF = CFG["data"].get("rate_tenor_cutoff_days", 365)


def _fetch_yield(sym):
    try:
        q = yf.Ticker(sym).history(period="5d")["Close"].iloc[-1]
        return yield_quote_to_decimal(float(q))
    except Exception:
        return None


R_SHORT, R_LONG = _fetch_yield("^IRX"), _fetch_yield("^FVX")


def rf(dte):
    return resolve_rate(dte, R_SHORT, R_LONG, R_DEFAULT, R_CUTOFF)


def record_atm_iv(t, S, chain):
    """IV percentile 自舉:追加一筆 ATM IV(append-only;同一天重跑不重複灌樣本)。"""
    if not chain:
        return None
    atm_iv = min(chain, key=lambda c: abs(c["strike"] - S))["iv"]
    last = latest_by_key(IV_HISTORY).get(t)
    if last and str(last.get("ts", "")).startswith(TODAY.isoformat()):
        return atm_iv
    append_record(IV_HISTORY, {"ticker": t, "iv": round(atm_iv, 4)})
    return atm_iv


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
            iv = bsm.implied_vol(mid, S, K, d / 365.0, rf(d))
            if iv is None:
                continue
            out.append({"strike": float(K), "dte": d, "mid": float(mid), "iv": iv,
                        "bid": float(bid or 0), "ask": float(ask or 0),
                        "oi": _safe_int(row.get("openInterest")),
                        "volume": _safe_int(row.get("volume")), "expiry": exp})
    return out


if __name__ == "__main__":
    _fmt = lambda x: f"{x:.3%}" if x is not None else "NO_DATA"  # noqa: E731
    print(f"無風險利率:短(^IRX)={_fmt(R_SHORT)}  長(^FVX)={_fmt(R_LONG)}  "
          f"(缺 → 預設 {R_DEFAULT:.3%})")
    iv_hist = series_by_key(IV_HISTORY)
    print(f"IV 自舉樣本:NVDA {len(iv_hist.get('NVDA', []))} / MU {len(iv_hist.get('MU', []))}"
          f"(<{CFG['data']['iv_percentile_min_history_days']} → edge 閘退用 ratio)")

    # --- 槓桿透鏡:NVDA LEAPS(DTE 365–900)---
    print("\n=== 槓桿透鏡 · NVDA ===")
    S = spot("NVDA")
    R = rf(730)   # LEAPS 全在 cutoff 之上 → 長率
    chain = build_contracts("NVDA", S, 365, 900)
    record_atm_iv("NVDA", S, chain)
    print(f"spot={S:.2f}  合格 LEAPS 合約 {len(chain)} 張  r={R:.3%}")

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

    out = leverage_lens(chain, S, R, CFG, iv_history=iv_hist.get("NVDA"))
    print("verdict:", out["verdict"], out.get("code") or "")
    if out["verdict"] == "PASS":
        c = out["contract"]
        print(f"  → {c['expiry']} ${c['strike']:.0f}C  mid≈${c['mid']:.2f}")
        print(f"     {out['metrics']}")
    nvda_S, nvda_r, nvda_chain = S, R, chain

    # --- 凸性透鏡:MU,催化劑=下次財報 ---
    print("\n=== 凸性透鏡 · MU(催化劑=財報)===")
    S = spot("MU")
    cat_dte = next_earnings_dte("MU")
    R = rf(cat_dte or 90)   # 財報窗在 cutoff 之下 → 短率
    rv = realized_20d("MU")
    rv_txt = f"{rv:.3f}" if rv is not None else "NO_DATA"
    if cat_dte is not None and cat_dte >= 0:
        print(f"spot={S:.2f}  財報 T-{cat_dte}  20d 實現波動={rv_txt}")
    else:
        print(f"spot={S:.2f}  查無(未來)財報日  20d 實現波動={rv_txt}")
        cat_dte = None
    if cat_dte is not None:
        chain = build_contracts("MU", S, max(cat_dte, 1), cat_dte + 60, otm_only=True)
        record_atm_iv("MU", S, chain)

        # 診斷:逐關淘汰數,讓 CVX 的 EXCLUDE 不再是黑盒
        cvx = CFG["convexity"]
        prem_cap = cvx["cvx_prem_max_pct"] / 100.0 * S
        dte_hi = cat_dte + cvx["earn_window_days"] + 45
        liq_ok = [c for c in chain
                  if _valid_contract(c) and _passes_liquidity(c, CFG["liquidity"])]
        otm_ok = [c for c in liq_ok
                  if 0 < (c["strike"] - S) / S * 100.0 <= cvx["cvx_otm_max_pct"]]
        prem_ok = [c for c in otm_ok if c["mid"] <= prem_cap]
        dte_ok = [c for c in prem_ok if cat_dte <= c["dte"] <= dte_hi]
        print(f"  診斷:抓到 {len(chain)} 張 | 過流動性 {len(liq_ok)} | "
              f"價外≤{cvx['cvx_otm_max_pct']}% {len(otm_ok)} | "
              f"權利金≤${prem_cap:.1f} {len(prem_ok)} | 到期窗[{cat_dte},{dte_hi}] {len(dte_ok)}")
        if otm_ok and not prem_ok:
            cheapest = min(c["mid"] for c in otm_ok)
            print(f"  最便宜的合格價外要 ${cheapest:.1f},上限 ${prem_cap:.1f} → "
                  f"高波動下「便宜價外」不存在,權利金閘照設計排除")

        # MU 是記憶體桶(收費員),不是賽馬 → 不帶 tier,走基準 edge 閘
        out = convexity_lens(chain, S, R, rv, cat_dte, CFG,
                             iv_history=iv_hist.get("MU"))
        print("verdict:", out["verdict"], out.get("code") or "")
        if out["verdict"] == "PASS":
            c = out["contract"]
            print(f"  → {c['expiry']} ${c['strike']:.0f}C  mid≈${c['mid']:.2f}")
            print(f"     {out['metrics']}")
    mu_S, mu_r = S, R
    mu_chain = chain if cat_dte is not None else []

    # --- Block 3:路由器 + 條件式合約卡(重用上面抓好的資料)---
    print("\n=== Block 3 · 路由器 + 合約卡 ===")
    asof = dt.datetime.now().isoformat(timespec="minutes")
    recs = [
        # NVDA 無帶日期催化劑 → 論點時鐘路由到槓桿透鏡
        scan_one("NVDA", "加速器", nvda_S, nvda_r, nvda_chain, CFG,
                 iv_history=iv_hist.get("NVDA"), asof=asof),
        # MU 有財報時鐘 → 凸性透鏡(記憶體桶,不帶 tier)
        scan_one("MU", "記憶體", mu_S, mu_r, mu_chain, CFG,
                 catalyst_dte=cat_dte, realized_vol_val=rv,
                 iv_history=iv_hist.get("MU"), asof=asof),
    ]
    for rec in recs:
        if rec["card"]:
            print(format_card(rec["card"]))
        else:
            print(f"{rec['ticker']}(route={rec['route']}): "
                  f"{rec['verdict']} {rec['code'] or ''}  {rec['metrics'] or ''}")
            if rec["code"] == "LIQ_NO_OI_DATA":
                print("  ↳ Yahoo 這個時段 OI 整批缺 → 資料缺失非真淘汰,美股盤中重跑")

    print("\n注意:IV 全由 implied_vol 從 mid 自算;若合約數為 0,多半是 bid/ask 為空(收盤後)。")
