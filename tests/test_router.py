"""Block 3 測試:路由器(論點時鐘)+ 合約卡 + chain 層級 NO_DATA 降級。"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ai_radar.lenses import leverage_lens, convexity_lens  # noqa: E402
from ai_radar.router import route, build_card, scan_one, format_card  # noqa: E402

CFG = {
    "liquidity": {"min_oi": 100, "min_vol": 10, "max_spread_pct": 10},
    "leverage": {"lev_iv_pct_max": 40, "lev_delta_lo": 0.70, "lev_delta_hi": 0.85,
                 "lev_dte_min": 365, "lev_pick_metric": "min_extrinsic_per_delta"},
    "convexity": {"cvx_iv_ratio_max": 1.3, "cvx_prem_max_pct": 1.5, "cvx_otm_max_pct": 25,
                  "earn_window_days": 10, "target_move_pct": 30, "cvx_iv_pct_max": 60,
                  "racehorse_tiers": {"T1": {"cvx_iv_ratio_max": 1.1},
                                      "T2": {"cvx_iv_ratio_max": 1.5}}},
    "exposure": {"enabled": False},
    "data": {"iv_percentile_min_history_days": 60},
}


def _mk(strike, dte, mid, iv, oi=1000, volume=100, expiry="2027-06-18"):
    return {"strike": strike, "dte": dte, "mid": mid, "iv": iv,
            "oi": oi, "volume": volume, "expiry": expiry}


# ---- 路由器:論點時鐘 ----
def test_route_by_catalyst_clock():
    assert route(30) == "convexity"      # 帶日期催化劑 → 凸性
    assert route(0) == "convexity"       # 財報今天 → 仍算帶日期
    assert route(None) == "leverage"     # 無催化劑 → 槓桿
    assert route(-5) == "leverage"       # 財報已過 → 沒有「未來的」時鐘


# ---- 合約卡 ----
def test_scan_one_leverage_route_builds_card():
    S, r = 200, 0.045
    chain = [_mk(150, 550, 62, 0.42), _mk(180, 550, 40, 0.40)]
    rec = scan_one("NVDA", "加速器", S, r, chain, CFG, asof="2026-07-02T21:40")
    assert rec["route"] == "leverage" and rec["verdict"] == "PASS"
    card = rec["card"]
    assert card["ticker"] == "NVDA" and card["lens"] == "leverage"
    assert card["catalyst_t_minus"] is None
    # 損益兩平 = (K + 權利金) / S - 1
    K, mid = card["strike"], card["premium"]
    assert math.isclose(card["breakeven_pct"], (K + mid) / S * 100 - 100, abs_tol=0.06)
    assert CFG["leverage"]["lev_delta_lo"] <= card["delta"] <= CFG["leverage"]["lev_delta_hi"]
    assert card["extrinsic"] >= 0
    assert "G0 未啟用" in card["g0"]           # exposure disabled → 誠實標記 bypass
    assert "非建議" in card["note"]
    assert card["asof"] == "2026-07-02T21:40"
    assert card["ticker"] in format_card(card)  # 可印,不炸


def test_scan_one_convexity_route_builds_card():
    S, r = 100, 0.045
    chain = [_mk(112, 40, 1.2, 0.55)]
    rec = scan_one("MU", "記憶體", S, r, chain, CFG,
                   catalyst_dte=30, realized_vol_val=0.50)
    assert rec["route"] == "convexity" and rec["verdict"] == "PASS"
    card = rec["card"]
    assert card["catalyst_t_minus"] == 30
    assert math.isclose(card["breakeven_pct"], 13.2, abs_tol=0.1)
    assert card["lens_metrics"]["edge_basis"] == "iv_realized_ratio"


def test_scan_one_exclude_has_no_card():
    S, r = 200, 0.045
    rec = scan_one("X", "設備", S, r, [_mk(300, 550, 3, 0.5)], CFG)
    assert rec["verdict"] == "EXCLUDE" and rec["code"] == "LEV_NO_DELTA"
    assert rec["card"] is None


def test_scan_one_forced_lens_overrides_clock():
    """雙透鏡並行模式:lens 給定時強制用該透鏡,時鐘只印在卡上不影響評估。"""
    S, r = 200, 0.045
    chain = [_mk(150, 550, 62, 0.42), _mk(180, 550, 40, 0.40)]
    rec = scan_one("NVDA", "加速器", S, r, chain, CFG, lens="leverage",
                   catalyst_dte=30)   # 預設路由會走凸性;強制槓桿
    assert rec["route"] == "leverage" and rec["verdict"] == "PASS"
    assert rec["card"]["catalyst_t_minus"] == 30   # 時鐘照樣印在卡上給人看


def test_build_card_non_pass_returns_none():
    assert build_card("X", "設備", {"verdict": "EXCLUDE", "code": "LEV_NO_DELTA"},
                      200, 0.045) is None


# ---- chain 層級 NO_DATA 降級(真實觀察:Yahoo 時段性整批缺 OI)----
def test_all_zero_oi_is_no_data_not_exclude():
    S, r = 200, 0.045
    chain = [_mk(150, 550, 62, 0.42, oi=0), _mk(180, 550, 40, 0.40, oi=0)]
    out = leverage_lens(chain, S, r, CFG)
    assert out["verdict"] == "NO_DATA" and out["code"] == "LIQ_NO_OI_DATA"
    out2 = convexity_lens([_mk(112, 40, 1.2, 0.55, oi=0)], 100, r,
                          realized_vol_val=0.5, catalyst_dte=30, cfg=CFG)
    assert out2["verdict"] == "NO_DATA" and out2["code"] == "LIQ_NO_OI_DATA"
    # 只要有任何一張有 OI,就不是資料缺失,照常判(低 OI 是真淘汰)
    mixed = [_mk(150, 550, 62, 0.42, oi=0), _mk(180, 550, 40, 0.40, oi=1000)]
    assert leverage_lens(mixed, S, r, CFG)["verdict"] == "PASS"


def test_empty_chain_is_no_data():
    out = leverage_lens([], 200, 0.045, CFG)
    assert out["verdict"] == "NO_DATA" and out["code"] == "NO_CONTRACTS"
    rec = scan_one("X", "電力", 200, 0.045, [], CFG)
    assert rec["verdict"] == "NO_DATA" and rec["card"] is None
