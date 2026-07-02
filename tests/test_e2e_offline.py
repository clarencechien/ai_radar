"""離線端到端整合測試(回歸用):
宇宙管線 → 歸桶 → 催化劑時鐘 → 路由 → 透鏡 → 合約卡 → tracer 收集/回填/報表。
全部合成資料 + mock fetcher,不碰網路——CI 手動觸發的回歸就是全套單元測試 + 這條。
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ai_radar.universe import build_universe  # noqa: E402
from ai_radar.catalysts import next_catalyst  # noqa: E402
from ai_radar.rates import resolve_rate  # noqa: E402
from ai_radar.router import scan_one, format_card  # noqa: E402
from ai_radar.tracer import (  # noqa: E402
    record_scan, record_outcome, due_backfills, report)

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
    "tracer": {"horizons_days": [5, 10, 20], "min_samples": 30},
}

TODAY = dt.date(2026, 7, 2)


def _c(strike, dte, mid, iv, oi=1000, volume=100, expiry="2028-01-21"):
    return {"strike": strike, "dte": dte, "mid": mid, "iv": iv,
            "oi": oi, "volume": volume, "expiry": expiry}


def test_full_pipeline_offline(tmp_path):
    # ---- Block 1:宇宙(mock fetcher 注入)----
    holdings = {"SMH": ["NVDA", "MU", "NOOPT"], "AIQ": ["PLTR", "NVDA"]}
    uni = build_universe(
        etf_sources=["SMH", "AIQ"],
        fetch_holdings=lambda etf: holdings[etf],
        is_optionable=lambda t: t != "NOOPT",
        gics_lookup=lambda t: {"NVDA": "Semiconductors", "MU": "Semiconductors",
                               "PLTR": "Software - Infrastructure"}.get(t),
        gics_map={"Semiconductors": "半導體", "Software - Infrastructure": "賽馬"},
        refine={"NVDA": "加速器", "MU": "記憶體"},
        bucket_map_path=str(tmp_path / "bucket_map.jsonl"),
    )
    buckets = {u["ticker"]: u["bucket"] for u in uni["universe"]}
    assert buckets == {"NVDA": "加速器", "MU": "記憶體", "PLTR": "賽馬"}
    assert uni["dropped_no_option"] == ["NOOPT"]

    # ---- Block 4:催化劑時鐘(MU 財報 T-30;NVDA/PLTR 無)----
    clocks = {"MU": next_catalyst([{"date": "2026-08-01", "kind": "earnings"}], TODAY),
              "NVDA": next_catalyst([], TODAY), "PLTR": None}
    assert clocks["MU"]["dte"] == 30 and clocks["NVDA"] is None

    # ---- Block 2.5:利率(短/長按天期)----
    r_short, r_long = 0.037, 0.041
    market = {  # 合成市場:spot / chain / 實現波動
        "NVDA": (200.0, [_c(150, 550, 62, 0.42), _c(180, 550, 40, 0.40)], None),
        "MU": (1000.0, [_c(1080, 40, 12.0, 0.55, expiry="2026-08-08")], 0.50),
        "PLTR": (150.0, [], None),   # 建不出合約 → NO_DATA
    }

    # ---- Block 3:路由 → 透鏡 → 出卡 ----
    asof = "2026-07-02T21:40"
    recs = {}
    for t, (S, chain, rv) in market.items():
        cat = clocks[t]
        cat_dte = cat["dte"] if cat else None
        r = resolve_rate(cat_dte or 550, r_short, r_long, 0.045)
        recs[t] = scan_one(t, buckets[t], S, r, chain, CFG,
                           catalyst_dte=cat_dte, realized_vol_val=rv, asof=asof)

    # NVDA:無時鐘 → 槓桿 → PASS 出卡(delta 落帶內,挑每單位 delta 時間價值最低)
    assert recs["NVDA"]["route"] == "leverage" and recs["NVDA"]["verdict"] == "PASS"
    nvda_card = recs["NVDA"]["card"]
    assert nvda_card["strike"] in (150, 180)
    assert CFG["leverage"]["lev_delta_lo"] <= nvda_card["delta"] <= CFG["leverage"]["lev_delta_hi"]
    assert nvda_card.get("target_move_pct") is None   # 情境倍數是凸性卡專屬
    # MU:財報時鐘 → 凸性 → PASS 出卡,含 +30% 情境倍數
    mu_card = recs["MU"]["card"]
    assert recs["MU"]["route"] == "convexity" and mu_card is not None
    #(1000×1.3 − 1080)/ 12 ≈ 18.3×
    assert mu_card["multiple_at_target"] == 18.3
    assert "若+30% 內含 18.3×" in format_card(mu_card)
    # PLTR:空 chain → NO_DATA 降級
    assert recs["PLTR"]["verdict"] == "NO_DATA" and recs["PLTR"]["code"] == "NO_CONTRACTS"

    # ---- Block 5:tracer 收集 → T+5 回填 → 雙向報表 ----
    tracer_path = str(tmp_path / "tracer.jsonl")
    for t, rec in recs.items():
        rec = dict(rec)
        rec["ts"] = "2026-07-02T21:40:00+00:00"   # 固定掃描時間,測回填到期
        record_scan(tracer_path, rec)

    later = TODAY + dt.timedelta(days=6)
    due = due_backfills(tracer_path, later, CFG["tracer"]["horizons_days"])
    # 只有兩筆實判 × T+5 到期;NO_DATA(PLTR)不回填
    assert {(d["ticker"], d["horizon_days"]) for d in due} == {("NVDA", 5), ("MU", 5)}
    moved = {"NVDA": 212.0, "MU": 1150.0}   # T+5 現價(合成)
    for d in due:
        record_outcome(tracer_path, d["ticker"], d["scan_ts"], d["horizon_days"],
                       d["spot_then"], moved[d["ticker"]],
                       option_mid_then=d["option_mid_then"])

    rep = report(tracer_path, CFG["tracer"]["min_samples"])
    assert rep["scan_count"] == 3 and rep["outcome_count"] == 2
    assert rep["by_verdict"]["PASS"]["T+5"]["n"] == 2
    assert rep["tuning_unlocked"] is False      # 2 < 30 → 閾值仍凍結
    assert rep["mode"] == "collect_only"
