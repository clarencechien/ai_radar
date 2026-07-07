"""RADAR.md 報告渲染測試(人看的輸出)。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ai_radar.report import render_report  # noqa: E402


def _pass_rec():
    return {"ticker": "NVDA", "bucket": "加速器", "tier": None, "route": "leverage",
            "verdict": "PASS", "code": None, "spot": 197.58, "metrics": {},
            "card": {"ticker": "NVDA", "bucket": "加速器", "tier": None,
                     "lens": "leverage", "catalyst_t_minus": None,
                     "expiry": "2028-12-15", "strike": 160.0, "premium": 77.12,
                     "delta": 0.792, "extrinsic": 39.54, "eff_leverage": 2.03,
                     "breakeven_pct": 20.1, "spot": 197.58}}


def _exclude_rec():
    return {"ticker": "MU", "bucket": "記憶體", "tier": None, "route": "convexity",
            "verdict": "EXCLUDE", "code": "CVX_NO_STRIKE", "spot": 1032.28,
            "metrics": None, "card": None}


def _no_data_rec():
    return {"ticker": "PLTR", "bucket": "賽馬", "tier": None, "route": "leverage",
            "verdict": "NO_DATA", "code": "LIQ_NO_OI_DATA", "spot": 150.0,
            "metrics": None, "card": None}


def test_render_report_two_tier_layout():
    md = render_report(
        [_pass_rec(), _exclude_rec(), _no_data_rec()],
        asof="2026-07-02T22:00", r_short=0.03663, r_long=0.0413,
        iv_counts={"NVDA": 1, "MU": 1}, ivp_min=60,
        universe_note="ETF 持股(SMH、SOXX;42 檔)",
        attention=["歸桶未決,請補 refine:XYZ"],
        tracer_report={"scan_count": 3, "outcome_count": 2, "min_samples": 30,
                       "tuning_unlocked": False, "mode": "collect_only",
                       "by_verdict": {"PASS": {"T+5": {"n": 2, "avg_ret_pct": 6.0,
                                                       "min_ret_pct": 4.0,
                                                       "max_ret_pct": 8.0}}}})
    # --- 上半:外行人看得懂 ---
    assert "今晚結論" in md
    assert "掃描 **3 檔**" in md and "出卡 **1 張**" in md and "排除 **1 筆**" in md
    assert "ETF 持股(SMH、SOXX;42 檔)" in md            # 宇宙來源
    assert "長期槓桿" in md and "一張約 **$7,712**" in md   # 白話卡:透鏡人話+每張成本
    assert "+20.1%" in md                                    # 損益兩平白話
    assert "排除了誰(一句話)" in md and "沒有夠便宜的樂透型合約" in md
    assert "不是投資建議" in md                              # 永印警語
    # 上半在 Details 之前
    assert md.index("今晚結論") < md.index("## Details")
    # --- 下半:開發者 Details ---
    assert "存活者技術表(1)" in md and "2028-12-15 $160C" in md
    assert "排除清單(1)" in md and "CVX_NO_STRIKE" in md and "無便宜合格價外" in md
    assert "NO_DATA(1)" in md and "資料缺失,非判斷" in md
    assert "G0 曝險護欄未啟用" in md
    assert "需人工處理" in md and "XYZ" in md
    assert "1/60" in md and "ratio 後備" in md
    assert "調參解鎖:否" in md and "avg +6.0%" in md
    assert "3.663%" in md and "4.130%" in md


def test_render_report_empty_run_does_not_crash():
    md = render_report([], asof="2026-07-02T22:00")
    assert "沒有任何標的通過濾網" in md and "不動作」也是一種結論" in md
    assert "不是投資建議" in md


def test_render_report_convexity_plain_card():
    rec = _pass_rec()
    rec["card"].update({"lens": "convexity", "catalyst_t_minus": 30, "premium": 12.0,
                        "target_move_pct": 30, "multiple_at_target": 18.3,
                        "breakeven_pct": 13.2})
    md = render_report([rec], asof="x")
    # 白話卡:事件凸性 + 大賠率語感 + 每張成本
    assert "事件凸性" in md and "T-30" in md
    assert "一張約 **$1,200**" in md
    assert "**18.3 倍**" in md and "輸的上限就是那一張的錢" in md
    # 技術表照舊
    assert "若+30% 內含 18.3×" in md
