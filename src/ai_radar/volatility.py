"""波動模組。

- realized_vol:從歷史股價自算實現波動(免費,凸性透鏡 edge 閘的分母)。
- iv_percentile:自舉——歷史 IV 樣本不足時回 None(NO_DATA),交給呼叫端用代理。
"""
from __future__ import annotations

import math

TRADING_DAYS = 252


def realized_vol(prices: list[float], window: int | None = None) -> float | None:
    """年化實現波動 = 日對數報酬標準差 × √252。

    prices:由舊到新的收盤價。樣本不足回 None(NO_DATA)。
    """
    if window is not None:
        prices = prices[-(window + 1):]
    if len(prices) < 3:
        return None
    rets = [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices))]
    n = len(rets)
    mean = sum(rets) / n
    var = sum((x - mean) ** 2 for x in rets) / (n - 1)  # 樣本變異數
    return math.sqrt(var) * math.sqrt(TRADING_DAYS)


def iv_percentile(current_iv: float, iv_history: list[float],
                  min_history: int = 60) -> float | None:
    """current_iv 在歷史 IV 分布的百分位(0–100)。

    歷史樣本 < min_history → 回 None(自舉未完成,呼叫端改用代理)。
    """
    hist = [x for x in iv_history if x is not None]
    if len(hist) < min_history:
        return None
    below = sum(1 for x in hist if x < current_iv)
    return 100.0 * below / len(hist)


def event_iv_ratio(event_iv: float, rv: float | None) -> float | None:
    """事件 IV ÷ 歷史實現波動。rv 缺 → None。"""
    if rv is None or rv <= 0:
        return None
    return event_iv / rv
