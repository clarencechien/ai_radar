"""Block 2.5 測試:T-bill 利率純邏輯 + IV 歷史時間序列。"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ai_radar.rates import yield_quote_to_decimal, pick_rate, resolve_rate  # noqa: E402
from ai_radar.state import append_record, series_by_key  # noqa: E402


def test_yield_quote_to_decimal():
    assert math.isclose(yield_quote_to_decimal(4.35), 0.0435)
    assert yield_quote_to_decimal(None) is None
    assert yield_quote_to_decimal(float("nan")) is None
    assert yield_quote_to_decimal(0) is None
    assert yield_quote_to_decimal(-1.2) is None
    assert yield_quote_to_decimal("abc") is None


def test_pick_rate_by_tenor():
    assert pick_rate(90, 0.04, 0.05) == 0.04     # 短天期 → 短率
    assert pick_rate(500, 0.04, 0.05) == 0.05    # LEAPS → 長率
    assert pick_rate(500, 0.04, None) == 0.04    # 長率缺 → 退用短率
    assert pick_rate(90, None, 0.05) == 0.05     # 短率缺 → 退用長率
    assert pick_rate(90, None, None) is None     # 都缺 → None


def test_resolve_rate_degrades_to_default():
    assert resolve_rate(90, None, None, 0.045) == 0.045   # NO_DATA 降級,不崩潰
    assert resolve_rate(90, 0.041, None, 0.045) == 0.041


def test_series_by_key_for_iv_bootstrap(tmp_path):
    p = str(tmp_path / "iv_history.jsonl")
    append_record(p, {"ticker": "MU", "iv": 0.8})
    append_record(p, {"ticker": "MU", "iv": 0.9})
    append_record(p, {"ticker": "NVDA", "iv": 0.5})
    append_record(p, {"ticker": "MU", "iv": None})   # NO_DATA 不進樣本
    s = series_by_key(p, field="iv")
    assert s["MU"] == [0.8, 0.9]
    assert s["NVDA"] == [0.5]
    assert series_by_key(str(tmp_path / "missing.jsonl")) == {}
