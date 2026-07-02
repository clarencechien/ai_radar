"""Block 2.5 — 無風險利率(真 T-bill)。

live 抓取(yfinance ^IRX=13週 T-bill、^FVX=5年期)在 notebook 注入;
此處只有純邏輯:報價轉換、按合約天期挑利率、NO_DATA 降級回 config 預設。
慣例:Yahoo 殖利率指數報「百分比數字」(4.35 代表 4.35%),轉年化小數後才進 BSM。
"""
from __future__ import annotations

import math


def yield_quote_to_decimal(quote) -> float | None:
    """百分比報價 → 年化小數(4.35 → 0.0435)。缺失/NaN/非正 → None(NO_DATA)。"""
    if quote is None:
        return None
    try:
        q = float(quote)
    except (TypeError, ValueError):
        return None
    if math.isnan(q) or q <= 0:
        return None
    return q / 100.0


def pick_rate(dte_days: float, short_rate: float | None, long_rate: float | None,
              cutoff_days: float = 365) -> float | None:
    """按合約天期挑利率:≤cutoff 用短率、>cutoff 用長率(LEAPS)。

    挑中的那個缺 → 退用另一個;都缺 → None(交給 resolve_rate 降級)。
    """
    primary, backup = ((short_rate, long_rate) if dte_days <= cutoff_days
                       else (long_rate, short_rate))
    return primary if primary is not None else backup


def resolve_rate(dte_days: float, short_rate: float | None, long_rate: float | None,
                 default: float, cutoff_days: float = 365) -> float:
    """pick_rate 的 NO_DATA 降級版:都抓不到就回 config 預設,不崩潰。"""
    r = pick_rate(dte_days, short_rate, long_rate, cutoff_days)
    return default if r is None else r
