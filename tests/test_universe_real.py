"""真資料離線回歸測試。

用 Colab 實跑回報的真實 yfinance industry 字串,離線鎖住宇宙歸桶結果。
沙盒連不到 Yahoo,但把真實字串當 mock 就能回歸驗證邏輯 + 抓 gics_map 退化。
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ai_radar.universe import build_universe  # noqa: E402

CONF = os.path.join(os.path.dirname(__file__), "..", "config")

# 2026-07-01 Colab 實跑回報的真實 industry(SSNLF=三星,無 option)
REAL_INDUSTRY = {
    "NVDA": "Semiconductors", "AMD": "Semiconductors", "AVGO": "Semiconductors",
    "MRVL": "Semiconductors", "TSM": "Semiconductors", "INTC": "Semiconductors",
    "MU": "Semiconductors",
    "ASML": "Semiconductor Equipment & Materials",
    "AMAT": "Semiconductor Equipment & Materials",
    "LRCX": "Semiconductor Equipment & Materials",
    "KLAC": "Semiconductor Equipment & Materials",
    "VST": "Utilities - Independent Power Producers",
    "CEG": "Utilities - Independent Power Producers",
    "GEV": "Specialty Industrial Machinery",   # 寬泛 → 必須靠 refine
    "GOOGL": "Internet Content & Information",
    "META": "Internet Content & Information",
    "AMZN": "Internet Retail",
    "MSFT": "Software - Infrastructure",
    "ORCL": "Software - Infrastructure",
    "PLTR": "Software - Infrastructure",
    "SMH": None, "SOXX": None, "DRAM": None,   # ETF 無 industry → 靠 refine
    "SSNLF": "Consumer Electronics",
}
NO_OPTION = {"SSNLF"}  # 三星無美股 option

EXPECTED = {
    "TSM": "製造", "INTC": "製造",
    "NVDA": "加速器", "AMD": "加速器", "AVGO": "加速器", "MRVL": "加速器",
    "MU": "記憶體",
    "ASML": "設備", "AMAT": "設備", "LRCX": "設備", "KLAC": "設備",
    "VST": "電力", "CEG": "電力", "GEV": "電力",
    "GOOGL": "賽馬", "META": "賽馬", "AMZN": "賽馬",
    "MSFT": "賽馬", "ORCL": "賽馬", "PLTR": "賽馬",
    "SMH": "ETF代理", "SOXX": "ETF代理", "DRAM": "ETF代理",
}


def _load(name):
    d = json.load(open(os.path.join(CONF, name), encoding="utf-8"))
    return {k: v for k, v in d.items() if not k.startswith("_")}


def test_real_universe_buckets_lock():
    gics_map = _load("gics_map.json")
    refine = _load("refine.json")
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "bucket_map.jsonl")
        out = build_universe(
            etf_sources=["AIQ"],
            fetch_holdings=lambda etf: list(REAL_INDUSTRY.keys()),
            is_optionable=lambda t: t not in NO_OPTION,
            gics_lookup=lambda t: REAL_INDUSTRY.get(t),
            gics_map=gics_map,
            refine=refine,
            bucket_map_path=path,
        )
        got = {u["ticker"]: u["bucket"] for u in out["universe"]}
        assert got == EXPECTED, f"歸桶不符: {got}"
        assert out["dropped_no_option"] == ["SSNLF"]
        assert out["no_bucket"] == []


def test_gev_is_refine_not_gics():
    """GEV 的 industry 是寬泛的 Specialty Industrial Machinery,
    必須靠 refine 才對到電力;確認該寬映射沒偷偷回到 gics_map。"""
    gics_map = _load("gics_map.json")
    assert "Specialty Industrial Machinery" not in gics_map, "寬泛映射不該在 gics_map(地雷)"
    assert _load("refine.json").get("GEV") == "電力"
