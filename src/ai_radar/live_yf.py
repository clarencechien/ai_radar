"""yfinance live 轉接層(需能連 Yahoo;開發沙盒不行,Colab / GitHub Actions 可)。

只做「抓資料 → 標準格式」,不做判斷;失敗丟例外或回空,由 scan_universe 降級。
yfinance 延遲載入,離線測試 import 本模組不會炸。
"""
from __future__ import annotations

import datetime as dt
import math

from . import bsm
from .rates import yield_quote_to_decimal
from .volatility import realized_vol


def _yf():
    import yfinance
    return yfinance


def _safe_int(x):
    """pandas 缺值是 NaN(float 且 truthy),int(NaN) 會炸 → 一律歸 0。"""
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return 0
        return int(x)
    except (ValueError, TypeError):
        return 0


def fetch_spot(t: str) -> float:
    return float(_yf().Ticker(t).history(period="1d")["Close"].iloc[-1])


def fetch_rv(t: str, window: int = 20):
    px = _yf().Ticker(t).history(period="3mo")["Close"].tolist()
    return realized_vol(px, window=window)


def fetch_events(t: str) -> list[dict]:
    """財報日 → 事件清單(餵催化劑 helper);抓不到 → [](無時鐘)。"""
    try:
        cal = _yf().Ticker(t).calendar
        ed = cal.get("Earnings Date")
        ds = ed if isinstance(ed, list) else [ed]
        return [{"date": d, "kind": "earnings"} for d in ds if d is not None]
    except Exception:
        return []


def fetch_yields() -> tuple:
    """(短率 ^IRX 13週, 長率 ^FVX 5年),年化小數;抓不到 → None(降級回預設)。"""
    out = []
    for sym in ("^IRX", "^FVX"):
        try:
            q = _yf().Ticker(sym).history(period="5d")["Close"].iloc[-1]
            out.append(yield_quote_to_decimal(float(q)))
        except Exception:
            out.append(None)
    return out[0], out[1]


def make_chain_fetcher(rate_for, today: dt.date):
    """回傳 fetch_chain(t, S, min_dte, max_dte, otm_only) -> contracts。

    mid=(bid+ask)/2、收盤後退 lastPrice;IV 不信 yfinance,用自家 implied_vol
    以對應天期利率自算;bid/ask 傳入供價差閘。
    """
    def fetch_chain(t, S, min_dte, max_dte, otm_only=False):
        tk = _yf().Ticker(t)
        out = []
        for exp in tk.options:
            d = (dt.date.fromisoformat(exp) - today).days
            if not (min_dte <= d <= max_dte):
                continue
            calls = tk.option_chain(exp).calls
            for _, row in calls.iterrows():
                bid, ask, K = row["bid"], row["ask"], row["strike"]
                if otm_only and K <= S:
                    continue
                if bid > 0 and ask > 0:
                    mid = (bid + ask) / 2
                elif (row.get("lastPrice") or 0) > 0:
                    mid = float(row["lastPrice"])
                else:
                    continue
                iv = bsm.implied_vol(mid, S, K, d / 365.0, rate_for(d))
                if iv is None:
                    continue
                out.append({"strike": float(K), "dte": d, "mid": float(mid), "iv": iv,
                            "bid": float(bid or 0), "ask": float(ask or 0),
                            "oi": _safe_int(row.get("openInterest")),
                            "volume": _safe_int(row.get("volume")), "expiry": exp})
        return out
    return fetch_chain
