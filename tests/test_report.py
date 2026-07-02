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


def test_render_report_sections_and_human_text():
    md = render_report(
        [_pass_rec(), _exclude_rec(), _no_data_rec()],
        asof="2026-07-02T22:00", r_short=0.03663, r_long=0.0413,
        iv_counts={"NVDA": 1, "MU": 1}, ivp_min=60,
        tracer_report={"scan_count": 3, "outcome_count": 2, "min_samples": 30,
                       "tuning_unlocked": False, "mode": "collect_only",
                       "by_verdict": {"PASS": {"T+5": {"n": 2, "avg_ret_pct": 6.0,
                                                       "min_ret_pct": 4.0,
                                                       "max_ret_pct": 8.0}}}})
    # 三段各就各位
    assert "存活者(1)" in md and "2028-12-15 $160C" in md
    assert "排除清單(1)" in md and "CVX_NO_STRIKE" in md
    assert "無便宜合格價外" in md            # 代碼有翻成人話
    assert "NO_DATA(1)" in md and "資料缺失非判斷" in md
    # 永印的警語與 G0 狀態
    assert "非投資建議" in md and "G0 曝險護欄未啟用" in md
    # 自舉/tracer 進度
    assert "1/60" in md and "ratio 後備" in md
    assert "調參解鎖:否" in md and "avg +6.0%" in md
    # 利率
    assert "3.663%" in md and "4.130%" in md


def test_render_report_empty_run_does_not_crash():
    md = render_report([], asof="2026-07-02T22:00")
    assert "存活者(0)" in md and "本次無存活者出卡" in md
    assert "非投資建議" in md


def test_render_report_convexity_scenario_column():
    rec = _pass_rec()
    rec["card"].update({"lens": "convexity", "catalyst_t_minus": 30,
                        "target_move_pct": 30, "multiple_at_target": 18.3})
    md = render_report([rec], asof="x")
    assert "T-30" in md and "若+30% 內含 18.3×" in md
