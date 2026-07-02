"""Block 2 測試:BSM 數學對照 + 雙透鏡邏輯(合成 chain,沙盒可跑)。"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ai_radar import bsm  # noqa: E402
from ai_radar.volatility import realized_vol, iv_percentile, event_iv_ratio  # noqa: E402
from ai_radar.lenses import leverage_lens, convexity_lens  # noqa: E402

CFG = {
    "liquidity": {"min_oi": 100, "min_vol": 10, "max_spread_pct": 10},
    "leverage": {"lev_iv_pct_max": 40, "lev_delta_lo": 0.70, "lev_delta_hi": 0.85,
                 "lev_dte_min": 365, "lev_pick_metric": "min_extrinsic_per_delta"},
    "convexity": {"cvx_iv_ratio_max": 1.3, "cvx_prem_max_pct": 1.5, "cvx_otm_max_pct": 25,
                  "earn_window_days": 10, "target_move_pct": 30,
                  "racehorse_tiers": {"T1": {"cvx_iv_ratio_max": 1.1},
                                      "T2": {"cvx_iv_ratio_max": 1.5}}},
    "data": {"iv_percentile_min_history_days": 60},
}


# ---- BSM 對照教科書值:S=100,K=100,T=1,r=5%,σ=20% ----
def test_bsm_reference_values():
    S, K, T, r, sig = 100, 100, 1.0, 0.05, 0.20
    assert math.isclose(bsm.call_price(S, K, T, r, sig), 10.4506, abs_tol=1e-3)
    g = bsm.greeks(S, K, T, r, sig)
    assert math.isclose(g["delta"], 0.6368, abs_tol=1e-3)
    assert math.isclose(g["gamma"], 0.018762, abs_tol=1e-4)
    assert math.isclose(g["vega"], 0.37524, abs_tol=1e-3)      # 每 1%
    assert math.isclose(g["theta"], -0.01757, abs_tol=1e-4)    # 每日


def test_implied_vol_roundtrip():
    S, K, T, r, sig = 120, 130, 0.75, 0.04, 0.35
    px = bsm.call_price(S, K, T, r, sig)
    iv = bsm.implied_vol(px, S, K, T, r)
    assert math.isclose(iv, sig, abs_tol=1e-4)


def test_implied_vol_below_intrinsic_returns_none():
    # 深價內、報價低於內含 → 無有效 IV
    assert bsm.implied_vol(0.5, 200, 100, 0.5, 0.05) is None


def test_realized_vol_and_insufficient():
    # 幾何等比序列 = 固定日報酬 → 變異數 0
    flat = [100 * (1.01 ** i) for i in range(30)]
    assert math.isclose(realized_vol(flat), 0.0, abs_tol=1e-9)
    assert realized_vol([100, 101]) is None  # 樣本不足


def test_iv_percentile_bootstrap():
    assert iv_percentile(0.5, [0.1] * 10, min_history=60) is None      # 不足 → NO_DATA
    hist = [i / 100 for i in range(100)]                               # 0.00..0.99
    assert math.isclose(iv_percentile(0.5, hist, min_history=60), 50.0, abs_tol=1.0)


def test_event_iv_ratio():
    assert math.isclose(event_iv_ratio(0.6, 0.4), 1.5)
    assert event_iv_ratio(0.6, None) is None


# ---- 雙透鏡 ----
def _mk(strike, dte, mid, iv, oi=1000, volume=100):
    return {"strike": strike, "dte": dte, "mid": mid, "iv": iv, "oi": oi, "volume": volume}


def test_leverage_lens_picks_cheapest_time_value():
    S, r = 200, 0.045
    chain = [
        _mk(150, 550, 62, 0.42),   # 深價內、高 delta
        _mk(180, 550, 40, 0.40),   # 價內、delta 落區間
        _mk(260, 550, 9, 0.45),    # 價外、delta 太低 → 出局
        _mk(180, 120, 20, 0.40),   # DTE 太短 → 出局
    ]
    out = leverage_lens(chain, S, r, CFG)
    assert out["verdict"] == "PASS"
    assert CFG["leverage"]["lev_delta_lo"] <= out["metrics"]["delta"] <= CFG["leverage"]["lev_delta_hi"]


def test_leverage_lens_no_qualifying_delta():
    S, r = 200, 0.045
    chain = [_mk(300, 550, 3, 0.5), _mk(320, 550, 2, 0.5)]  # 全深價外、delta 過低
    out = leverage_lens(chain, S, r, CFG)
    assert out["verdict"] == "EXCLUDE" and out["code"] == "LEV_NO_DELTA"


def test_leverage_lens_iv_high_gate():
    S, r = 200, 0.045
    chain = [_mk(180, 550, 40, 0.40)]
    hist = [0.10] * 80   # 歷史 IV 都很低 → 當前 0.40 落在極高百分位
    out = leverage_lens(chain, S, r, CFG, iv_history=hist)
    assert out["verdict"] == "EXCLUDE" and out["code"] == "LEV_IV_HIGH"


def test_convexity_lens_edge_gate_blocks_priced_iv():
    S, r = 100, 0.045
    chain = [_mk(112, 40, 1.2, 0.80)]  # 事件 IV 0.80
    # 實現波動高 → ratio 低 → 過閘;實現波動低 → ratio 高 → 擋
    out_blocked = convexity_lens(chain, S, r, realized_vol_val=0.30,
                                 catalyst_dte=30, cfg=CFG, tier="T1")
    assert out_blocked["verdict"] == "EXCLUDE" and out_blocked["code"] == "CVX_IV_PRICED"


def test_convexity_lens_pass_and_pick():
    S, r = 100, 0.045
    chain = [
        _mk(108, 40, 1.3, 0.55),
        _mk(115, 40, 0.6, 0.55),   # 更價外、更便宜 → gamma/premium 可能更高
        _mk(140, 40, 0.2, 0.55),   # 超過 OTM 25% → 出局
    ]
    out = convexity_lens(chain, S, r, realized_vol_val=0.50,
                         catalyst_dte=30, cfg=CFG, tier="T2")
    assert out["verdict"] == "PASS"
    assert out["metrics"]["otm_pct"] <= CFG["convexity"]["cvx_otm_max_pct"]


def test_convexity_lens_high_priced_stock_relative_cap():
    """MU $1154 案例:$15 的價外 call 在絕對 $1.5 上限會被誤殺,
    相對上限(1.5%×1154≈$17.3)應放行。鎖住這個修正。"""
    S, r = 1154.0, 0.045
    chain = [_mk(1250, 100, 15.0, 0.60)]   # 價外 ~8.3%、$15 權利金
    out = convexity_lens(chain, S, r, realized_vol_val=0.90,
                         catalyst_dte=84, cfg=CFG, tier="T2")
    assert out["verdict"] == "PASS", out
    # 若把上限改回絕對 $1.5,同一張會被 CVX_NO_STRIKE 擋掉
    cfg_abs = {**CFG, "convexity": {**CFG["convexity"]}}
    cfg_abs["convexity"].pop("cvx_prem_max_pct")
    cfg_abs["convexity"]["cvx_prem_max_usd"] = 1.5
    out2 = convexity_lens(chain, S, r, 0.90, 84, cfg_abs, tier="T2")
    assert out2["verdict"] == "EXCLUDE" and out2["code"] == "CVX_NO_STRIKE"


def test_convexity_lens_no_catalyst_skips():
    out = convexity_lens([_mk(110, 40, 1.0, 0.5)], 100, 0.045,
                         realized_vol_val=0.4, catalyst_dte=None, cfg=CFG)
    assert out["verdict"] == "SKIP" and out["code"] == "NO_CATALYST"


def test_convexity_lens_default_tier_uses_base_gate():
    """tier 是賽馬桶專屬:不帶 tier(如記憶體桶 MU)應走基準閘 1.3,
    而不是被賽馬 T1 的 1.1 誤擋。鎖住 tier 預設值修正。"""
    S, r = 100, 0.045
    chain = [_mk(110, 40, 1.0, 0.60)]   # ratio = 0.60/0.50 = 1.2:T1 擋、基準放行
    out_base = convexity_lens(chain, S, r, realized_vol_val=0.50,
                              catalyst_dte=30, cfg=CFG)
    assert out_base["verdict"] == "PASS", out_base
    out_t1 = convexity_lens(chain, S, r, realized_vol_val=0.50,
                            catalyst_dte=30, cfg=CFG, tier="T1")
    assert out_t1["verdict"] == "EXCLUDE" and out_t1["code"] == "CVX_IV_PRICED"


def test_spread_gate_enforced_when_quotes_present():
    """max_spread_pct:有雙邊報價才生效;bid/ask 缺(收盤後)不因此淘汰。"""
    S, r = 200, 0.045
    wide = _mk(180, 550, 40, 0.40)
    wide.update({"bid": 34.0, "ask": 46.0})       # spread 30% > 10% → 擋
    out = leverage_lens([wide], S, r, CFG)
    assert out["verdict"] == "EXCLUDE" and out["code"] == "LEV_NO_DELTA"

    tight = _mk(180, 550, 40, 0.40)
    tight.update({"bid": 39.0, "ask": 41.0})      # spread 5% → 放行
    assert leverage_lens([tight], S, r, CFG)["verdict"] == "PASS"

    no_quote = _mk(180, 550, 40, 0.40)            # 無 bid/ask → 靠 OI,放行
    assert leverage_lens([no_quote], S, r, CFG)["verdict"] == "PASS"


def test_lenses_degrade_on_bad_contract_no_crash():
    """NO_DATA 降級:iv/mid 缺失或非正的髒合約應被跳過,不讓 BSM 拋例外。"""
    S, r = 200, 0.045
    dirty = [_mk(180, 550, 40, 0.0),              # iv=0 → BSM 會炸的輸入
             _mk(180, 550, 40, None),             # iv 缺失
             _mk(180, 550, 0.0, 0.40)]            # mid=0
    out = leverage_lens(dirty, S, r, CFG)
    assert out["verdict"] == "EXCLUDE" and out["code"] == "LEV_NO_DELTA"

    dirty_otm = [_mk(112, 40, 1.2, None), _mk(112, 40, 0.0, 0.55)]
    out2 = convexity_lens(dirty_otm, 100, r, realized_vol_val=0.5,
                          catalyst_dte=30, cfg=CFG)
    assert out2["verdict"] == "EXCLUDE" and out2["code"] == "CVX_NO_STRIKE"
