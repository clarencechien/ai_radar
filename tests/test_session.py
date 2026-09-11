"""交易時段標記 + session 寫進紀錄 + regime 同日冪等。"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ai_radar.session import market_session  # noqa: E402
from ai_radar.tracer import (  # noqa: E402
    record_bench, record_regime, record_card_track, read_records)

UTC = dt.timezone.utc


def test_market_session_summer_and_winter():
    # 2026-09-11(週五,夏令 EDT=UTC-4)
    assert market_session(dt.datetime(2026, 9, 11, 14, 23, tzinfo=UTC)) == "intraday"   # 10:23 ET
    assert market_session(dt.datetime(2026, 9, 11, 13, 0, tzinfo=UTC)) == "pre_open"    # 09:00 ET
    assert market_session(dt.datetime(2026, 9, 11, 23, 20, tzinfo=UTC)) == "after_close"  # 19:20 ET(8/27 實例)
    assert market_session(dt.datetime(2026, 9, 11, 19, 45, tzinfo=UTC)) == "intraday"   # 15:45 ET(8/31 實例)
    assert market_session(dt.datetime(2026, 9, 12, 15, 0, tzinfo=UTC)) == "weekend"
    # 2026-11-02(週一,冬令 EST=UTC-5):14:23 UTC = 09:23 ET 開盤前 → cron 要改 15:23
    assert market_session(dt.datetime(2026, 11, 2, 14, 23, tzinfo=UTC)) == "pre_open"
    assert market_session(dt.datetime(2026, 11, 2, 15, 23, tzinfo=UTC)) == "intraday"
    # naive datetime 視為 UTC
    assert market_session(dt.datetime(2026, 9, 11, 14, 23)) == "intraday"


def test_session_stamped_on_records_and_regime_idempotent(tmp_path):
    p = str(tmp_path / "t.jsonl")
    today = dt.date(2026, 9, 11)
    card_ref = {"ticker": "NVDA", "expiry": "2028-01-21", "strike": 170.0, "lens": "leverage",
                "premium_then": 60.0, "dte_left": 497, "session": "after_close"}
    rec = record_card_track(p, card_ref, mid_now=61.0, spot_now=201.0)
    assert rec["session"] == "after_close"
    assert record_bench(p, today, {"SMH": 300.0}, session="intraday")["session"] == "intraday"
    assert record_regime(p, today, {"iv_now": 0.5}, {"days": 1}, session="intraday") is not None
    assert record_regime(p, today, {"iv_now": 0.6}, {"days": 1}, session="intraday") is None  # 同日不重灌
    kinds = [r["kind"] for r in read_records(p)]
    assert kinds == ["card_track", "bench", "regime"]
