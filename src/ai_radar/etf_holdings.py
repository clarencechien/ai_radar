"""Block 1.5 — 真 ETF 持股(發行商每日/每週公布 CSV;各家格式不一、會改版,是髒活)。

純邏輯:CSV 解析(容忍前導雜訊)、ticker 正規化、快照時效。
live 下載在 live_yf;抓取鏈逐級降級:
issuer CSV → yfinance 前十大後備 → 前次快照 → universe_seed。
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime

# 常見的 ticker 欄位名(各發行商叫法不一,全轉小寫比對)
TICKER_HEADERS = ("ticker", "symbol", "holding ticker", "stockticker", "identifier")
# 非個股列(現金/保證金/衍生性部位)
NOT_EQUITY = {"USD", "CASH", "CASHUSD", "MARGIN", "SWAP", "FUT", "N-A", "NA", "--"}


def normalize_ticker(raw) -> str | None:
    """'BRK.B'→'BRK-B'、去星號空白;現金列/非個股/怪字串 → None。"""
    t = (raw or "").strip().upper().replace("/", "-").replace(".", "-").strip("*")
    if not t or t in NOT_EQUITY or len(t) > 6:
        return None
    return t if t.replace("-", "").isalpha() else None


def parse_holdings_csv(text: str) -> list[str]:
    """從發行商 CSV 抓成分 ticker(iShares 這類前面有幾行基金資訊 → 掃著找 header 列)。

    找不到 ticker 欄 → 回 [](交給呼叫端降級)。順序保留、去重。
    """
    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error:
        return []
    for i, row in enumerate(rows):
        low = [c.strip().lower() for c in row]
        for j, cell in enumerate(low):
            if cell in TICKER_HEADERS:
                out = []
                for r in rows[i + 1:]:
                    t = normalize_ticker(r[j]) if j < len(r) else None
                    if t:
                        out.append(t)
                return list(dict.fromkeys(out))
    return []


def is_stale(ts_iso: str, today: date, max_age_days: int = 7) -> bool:
    """宇宙快照是否過期(spec:ETF 週更)。時戳壞 → 視為過期。"""
    try:
        return (today - datetime.fromisoformat(ts_iso).date()).days > max_age_days
    except (ValueError, TypeError):
        return True
