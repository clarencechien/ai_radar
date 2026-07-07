"""Block 4(催化劑 helper)+ Block 5(shadow tracer)測試。"""
import datetime as dt
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ai_radar.catalysts import next_catalyst, format_clock  # noqa: E402
from ai_radar.tracer import (  # noqa: E402
    record_scan, record_outcome, due_backfills, report, scans, outcomes, scanned_on,
    open_cards, record_card_track, card_report)

TODAY = dt.date(2026, 7, 2)


# ---- Block 4:催化劑 helper(只呈現不裁決)----
def test_next_catalyst_picks_earliest_future():
    events = [{"date": "2026-09-23", "kind": "earnings"},
              {"date": "2026-08-15", "kind": "product_launch"},
              {"date": "2026-05-01", "kind": "earnings"}]   # 已過 → 不算時鐘
    cat = next_catalyst(events, TODAY)
    assert cat["date"] == "2026-08-15" and cat["dte"] == 44
    assert cat["kind"] == "product_launch"


def test_next_catalyst_no_clock_cases():
    assert next_catalyst([], TODAY) is None
    assert next_catalyst(None, TODAY) is None
    assert next_catalyst([{"date": "2026-01-01"}], TODAY) is None   # 全已過
    assert next_catalyst([{"date": "not-a-date"}], TODAY) is None   # 日期壞 → NO_DATA 跳過
    # 今天的事件仍算帶日期時鐘(dte=0)
    assert next_catalyst([{"date": "2026-07-02"}], TODAY)["dte"] == 0


def test_next_catalyst_lookahead_annotates_not_judges():
    events = [{"date": "2026-09-23", "kind": "earnings"}]   # T-83
    cat = next_catalyst(events, TODAY, lookahead_days=60)
    assert cat is not None and cat["dte"] == 83              # 照樣回傳,不裁決
    assert cat["within_lookahead"] is False
    assert "遠期" in format_clock(cat)
    near = next_catalyst([{"date": "2026-07-20"}], TODAY, lookahead_days=60)
    assert near["within_lookahead"] is True
    assert "T-18" in format_clock(near)
    assert "無帶日期時鐘" in format_clock(None)


# ---- Block 5:shadow tracer(collect_only)----
def _scan(ticker, verdict, code=None, spot=100.0, ts=None, card=None, route="leverage"):
    rec = {"ticker": ticker, "bucket": "測試", "route": route,
           "verdict": verdict, "code": code, "spot": spot, "card": card}
    if ts:
        rec["ts"] = ts
    return rec


def test_record_and_due_backfills(tmp_path):
    p = str(tmp_path / "tracer.jsonl")
    record_scan(p, _scan("NVDA", "PASS", spot=200.0, ts="2026-06-20T21:40:00+00:00",
                         card={"premium": 77.12}))
    record_scan(p, _scan("MU", "EXCLUDE", code="CVX_NO_STRIKE", spot=1032.0,
                         ts="2026-06-25T21:40:00+00:00"))
    assert len(scans(p)) == 2

    due = due_backfills(p, TODAY, [5, 10, 20])
    # NVDA 掃描 12 天前 → T+5/T+10 到期;MU 7 天前 → 只 T+5
    keys = {(d["ticker"], d["horizon_days"]) for d in due}
    assert keys == {("NVDA", 5), ("NVDA", 10), ("MU", 5)}
    nvda5 = next(d for d in due if d["ticker"] == "NVDA" and d["horizon_days"] == 5)
    assert nvda5["spot_then"] == 200.0 and nvda5["option_mid_then"] == 77.12

    # 回填後不再 due(冪等)
    record_outcome(p, "NVDA", nvda5["scan_ts"], 5, 200.0, 210.0,
                   option_mid_then=77.12, option_mid_now=90.0)
    keys2 = {(d["ticker"], d["horizon_days"]) for d in due_backfills(p, TODAY, [5, 10, 20])}
    assert keys2 == {("NVDA", 10), ("MU", 5)}
    o = outcomes(p)[0]
    assert math.isclose(o["underlying_ret_pct"], 5.0)
    assert math.isclose(o["option_ret_pct"], 16.7)


def test_report_two_way_and_lock(tmp_path):
    p = str(tmp_path / "tracer.jsonl")
    s1 = record_scan(p, _scan("A", "PASS", spot=100.0))
    s2 = record_scan(p, _scan("B", "EXCLUDE", code="LEV_IV_HIGH", spot=50.0))
    record_outcome(p, "A", s1["ts"], 5, 100.0, 108.0)       # 存活者 +8% → 放對
    record_outcome(p, "B", s2["ts"], 5, 50.0, 65.0)         # 被排除者 +30% → 事後噴
    rep = report(p, min_samples=30)
    assert rep["scan_count"] == 2 and rep["outcome_count"] == 2
    assert rep["by_verdict"]["PASS"]["T+5"]["avg_ret_pct"] == 8.0
    assert rep["by_verdict"]["EXCLUDE:LEV_IV_HIGH"]["T+5"]["max_ret_pct"] == 30.0
    assert rep["tuning_unlocked"] is False                   # 2 < 30 → 凍結
    assert rep["mode"] == "collect_only"


def test_no_data_scans_not_backfilled(tmp_path):
    """NO_DATA 掃描沒做出判斷 → 不進回填佇列(回答不了放對/砍錯)。"""
    p = str(tmp_path / "tracer.jsonl")
    record_scan(p, _scan("NVDA", "NO_DATA", code="LIQ_NO_OI_DATA", spot=197.58,
                         ts="2026-06-20T21:40:00+00:00"))
    assert due_backfills(p, TODAY, [5, 10, 20]) == []


def test_scanned_on_for_same_day_dedup(tmp_path):
    p = str(tmp_path / "tracer.jsonl")
    record_scan(p, _scan("NVDA", "NO_DATA", code="LIQ_NO_OI_DATA",
                         ts="2026-07-02T10:00:00+00:00"))
    record_scan(p, _scan("MU", "EXCLUDE", code="CVX_NO_STRIKE", route="convexity",
                         ts="2026-07-02T10:00:00+00:00"))
    record_scan(p, _scan("MU", "PASS", route="leverage",
                         ts="2026-07-02T10:00:00+00:00"))   # 雙透鏡:同檔不同透鏡並存
    record_scan(p, _scan("MU", "PASS", ts="2026-07-01T21:40:00+00:00"))   # 昨天 → 不算
    seen = scanned_on(p, TODAY)
    assert seen == {("NVDA", "leverage"): {"NO_DATA"},
                    ("MU", "convexity"): {"EXCLUDE"},
                    ("MU", "leverage"): {"PASS"}}
    # 呼叫端規則:NVDA 槓桿今天只有 NO_DATA → 盤中補到實判可收;MU 兩路都有實判 → 跳過


def test_card_tracking_lifecycle(tmp_path):
    """合約卡追蹤:第一次上榜為基準 → 每晚標記 → 同日冪等 → 到期前 21 天停追。"""
    p = str(tmp_path / "tracer.jsonl")
    card = {"ticker": "NVDA", "expiry": "2028-01-21", "strike": 170.0,
            "lens": "leverage", "premium": 57.98, "spot": 194.83}
    record_scan(p, _scan("NVDA", "PASS", spot=194.83,
                         ts="2026-07-06T14:30:00+00:00", card=card))
    # 隔天又上榜(premium 變了)→ 基準仍是第一次的 57.98
    record_scan(p, _scan("NVDA", "PASS", spot=200.0,
                         ts="2026-07-07T14:30:00+00:00",
                         card={**card, "premium": 60.10}))

    due = open_cards(p, dt.date(2026, 7, 8))
    assert len(due) == 1
    c = due[0]
    assert c["premium_then"] == 57.98 and c["scan_ts"].startswith("2026-07-06")
    assert c["dte_left"] == (dt.date(2028, 1, 21) - dt.date(2026, 7, 8)).days

    rec = record_card_track(p, c, mid_now=63.2, spot_now=205.0)
    assert rec["option_ret_pct"] == 9.0                       # 57.98 → 63.2
    # 同日冪等:剛記過 → 不再 due(ts 是今天 UTC,用今天查)
    assert open_cards(p, dt.datetime.fromisoformat(rec["ts"]).date()) == []

    # 到期前 21 天內 → 停追
    assert open_cards(p, dt.date(2028, 1, 5)) == []
    # 恰好剩 21 天 → 也不追(> 才追)
    assert open_cards(p, dt.date(2027, 12, 31)) == []

    rep = card_report(p)
    assert len(rep) == 1
    assert rep[0]["mid_now"] == 63.2 and rep[0]["n_marks"] == 1
    assert rep[0]["option_ret_pct"] == 9.0


def test_card_track_no_data_mid(tmp_path):
    p = str(tmp_path / "tracer.jsonl")
    card = {"ticker": "MU", "expiry": "2026-12-18", "strike": 1200.0,
            "premium": 12.0, "spot": 1000.0}
    record_scan(p, _scan("MU", "PASS", ts="2026-07-06T14:30:00+00:00", card=card))
    c = open_cards(p, dt.date(2026, 7, 7))[0]
    rec = record_card_track(p, c, mid_now=None, spot_now=1010.0)  # 市價缺 → NO_DATA
    assert rec["option_ret_pct"] is None
    assert card_report(p)[0]["mid_now"] is None


def test_outcome_no_data_degrades(tmp_path):
    p = str(tmp_path / "tracer.jsonl")
    s = record_scan(p, _scan("X", "NO_DATA", code="LIQ_NO_OI_DATA", spot=None))
    record_outcome(p, "X", s["ts"], 5, None, 123.0)          # spot_then 缺 → 報酬 None
    assert outcomes(p)[0]["underlying_ret_pct"] is None
    rep = report(p, min_samples=30)
    assert rep["outcome_count"] == 0                         # None 報酬不進統計
