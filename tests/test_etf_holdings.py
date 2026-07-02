"""Block 1.5 測試:發行商 CSV 解析 + ticker 正規化 + 快照時效。"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ai_radar.etf_holdings import (  # noqa: E402
    normalize_ticker, parse_holdings_csv, is_stale)

TODAY = dt.date(2026, 7, 2)

# iShares 風格:前面幾行是基金資訊,header 在中間
ISHARES_CSV = """iShares Semiconductor ETF
Fund Holdings as of,"Jul 01, 2026"
Inception Date,"Jul 10, 2001"

Ticker,Name,Sector,Asset Class,Market Value,Weight (%)
NVDA,NVIDIA CORP,Information Technology,Equity,"1,234",10.5
AVGO,BROADCOM INC,Information Technology,Equity,"987",8.2
BRK.B,BERKSHIRE TEST,Financials,Equity,"1",0.1
USD,US DOLLAR,Cash and/or Derivatives,Cash,"5",0.0
NVDA,NVIDIA CORP DUP,Information Technology,Equity,"1",0.0
"""

# Global X 風格:header 直接在第一列、欄名不同
GLOBALX_CSV = """Date,Symbol,Name,SEDOL,Market Price,Shares Held,Percent of Net Assets
07/01/2026,MSFT,Microsoft Corp,ABC123,500.1,1000,4.2
07/01/2026,PLTR,Palantir Technologies,DEF456,80.2,2000,3.1
07/01/2026,--,U.S. Dollar,,1.0,99,0.5
"""


def test_parse_ishares_style_with_preamble():
    got = parse_holdings_csv(ISHARES_CSV)
    assert got == ["NVDA", "AVGO", "BRK-B"]   # 去重保序、BRK.B 正規化、現金列剔除


def test_parse_globalx_style_symbol_column():
    assert parse_holdings_csv(GLOBALX_CSV) == ["MSFT", "PLTR"]


def test_parse_garbage_returns_empty():
    assert parse_holdings_csv("not,a,holdings\nfile,at,all") == []
    assert parse_holdings_csv("") == []


def test_normalize_ticker():
    assert normalize_ticker(" brk.b ") == "BRK-B"
    assert normalize_ticker("NVDA*") == "NVDA"
    assert normalize_ticker("USD") is None       # 現金列
    assert normalize_ticker("--") is None
    assert normalize_ticker("A1B") is None       # 非純字母
    assert normalize_ticker("TOOLONGTICKER") is None


def test_snapshot_staleness_weekly():
    assert is_stale("2026-06-20T14:00:00+00:00", TODAY) is True     # 12 天前 → 過期
    assert is_stale("2026-06-28T14:00:00+00:00", TODAY) is False    # 4 天前 → 還新鮮
    assert is_stale("garbage", TODAY) is True                        # 時戳壞 → 視為過期
