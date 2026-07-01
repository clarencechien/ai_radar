"""Block 1 單元測試(純邏輯,沙盒可跑;不碰 live 網路)。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ai_radar.universe import (  # noqa: E402
    NO_DATA,
    append_new_buckets,
    assign_bucket,
    build_universe,
    union_dedup,
)
from ai_radar.state import read_records  # noqa: E402

GICS_MAP = {"Semiconductors": "半導體", "Systems Software": "賽馬"}
REFINE = {"NVDA": "加速器", "MU": "記憶體", "TSM": "製造"}


def test_union_dedup_normalises_and_sorts():
    holdings = {"AIQ": ["nvda", "MSFT ", "NVDA"], "SMH": ["nvda", "TSM", ""]}
    assert union_dedup(holdings) == ["MSFT", "NVDA", "TSM"]


def test_assign_bucket_priority():
    # refine 優先於 GICS 粗桶
    assert assign_bucket("NVDA", "Semiconductors", GICS_MAP, REFINE) == ("加速器", "refine")
    # 無 refine → 落 GICS 粗桶
    assert assign_bucket("AMAT", "Semiconductors", GICS_MAP, REFINE) == ("半導體", "gics")
    # 都沒有 → NO_DATA
    assert assign_bucket("ZZZZ", None, GICS_MAP, REFINE) == (NO_DATA, NO_DATA)


def test_append_only_does_not_overwrite():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "bucket_map.jsonl")
        gics = {"NVDA": "Semiconductors", "MSFT": "Systems Software"}

        added1 = append_new_buckets(["NVDA", "MSFT"], gics.get, GICS_MAP, REFINE, path)
        assert set(added1) == {"NVDA", "MSFT"}

        # 再跑一次:已歸桶者不應再追加
        added2 = append_new_buckets(["NVDA", "MSFT"], gics.get, GICS_MAP, REFINE, path)
        assert added2 == {}

        # 檔案仍是 append-only,共 2 筆
        assert sum(1 for _ in read_records(path)) == 2


def test_no_data_ticker_can_be_backfilled_later():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "bucket_map.jsonl")
        # 第一次:GICS 查不到、也沒 refine → NO_DATA
        append_new_buckets(["NEWCO"], lambda t: None, GICS_MAP, {}, path)
        # 之後補了 refine → 允許再追加補寫
        added = append_new_buckets(["NEWCO"], lambda t: None, GICS_MAP, {"NEWCO": "賽馬"}, path)
        assert added["NEWCO"]["bucket"] == "賽馬"


def test_build_universe_with_mock_fetchers():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "bucket_map.jsonl")
        holdings = {"AIQ": ["NVDA", "MSFT", "SSNLF"], "SMH": ["NVDA", "MU"]}
        gics = {"NVDA": "Semiconductors", "MSFT": "Systems Software", "MU": "Semiconductors"}

        # SSNLF(三星)當作無美股 option → 應被濾掉
        def is_optionable(t):
            return t != "SSNLF"

        out = build_universe(
            etf_sources=["AIQ", "SMH"],
            fetch_holdings=lambda etf: holdings[etf],
            is_optionable=is_optionable,
            gics_lookup=gics.get,
            gics_map=GICS_MAP,
            refine=REFINE,
            bucket_map_path=path,
        )
        tickers = {u["ticker"]: u["bucket"] for u in out["universe"]}
        assert tickers == {"MSFT": "賽馬", "MU": "記憶體", "NVDA": "加速器"}
        assert out["dropped_no_option"] == ["SSNLF"]
        assert out["no_bucket"] == []
