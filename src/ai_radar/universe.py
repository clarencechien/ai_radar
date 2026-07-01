"""Block 1 — 宇宙管線 (universe pipeline)

流程:ETF 成分聯集 → 濾可 option → 自動歸桶(GICS 粗桶 + refine 細桶,append-only) → 宇宙清單

設計:
- live 抓取(ETF CSV、GICS 查詢、option 檢查)以「可注入的 fetcher」傳入,
  讓純邏輯在沙盒可測、真資料在 Colab 跑。
- 歸桶 append-only:已歸桶不覆寫,只追加新 ticker;refine 優先於 GICS 粗桶。
- 缺資料一律降級為 NO_DATA,不崩潰。
"""
from __future__ import annotations

import json
from typing import Callable, Iterable

from .state import append_record, latest_by_key

NO_DATA = "NO_DATA"


# ---------------------------------------------------------------------------
# 純邏輯(沙盒可測)
# ---------------------------------------------------------------------------
def union_dedup(holdings: dict[str, list[str]]) -> list[str]:
    """把各 ETF 的成分聯集去重。holdings = {etf: [tickers]}。回傳排序後清單。"""
    seen: set[str] = set()
    for tickers in holdings.values():
        for t in tickers:
            t = (t or "").strip().upper()
            if t:
                seen.add(t)
    return sorted(seen)


def assign_bucket(
    ticker: str,
    gics_sub: str | None,
    gics_map: dict[str, str],
    refine: dict[str, str],
) -> tuple[str, str]:
    """決定 ticker 的桶。

    優先序:refine 細桶 > GICS 粗桶 > NO_DATA。
    回傳 (bucket, source),source ∈ {"refine", "gics", "NO_DATA"}。
    """
    if ticker in refine:
        return refine[ticker], "refine"
    if gics_sub and gics_sub in gics_map:
        return gics_map[gics_sub], "gics"
    return NO_DATA, NO_DATA


def append_new_buckets(
    tickers: Iterable[str],
    gics_lookup: Callable[[str], str | None],
    gics_map: dict[str, str],
    refine: dict[str, str],
    bucket_map_path: str,
) -> dict[str, dict]:
    """對尚未歸桶的 ticker 自動歸桶並 append。

    已在 bucket_map(且非 NO_DATA)者不動(append-only、不覆寫)。
    refine 若把某 ticker 從 NO_DATA 修正過來,視為新資訊會被追加。
    回傳這次實際追加的 {ticker: record}。
    """
    current = latest_by_key(bucket_map_path, key="ticker")
    added: dict[str, dict] = {}
    for t in tickers:
        prev = current.get(t)
        # 已成功歸桶就跳過;但若之前是 NO_DATA 而現在 refine/gics 有解,允許補寫
        if prev and prev.get("bucket") not in (None, NO_DATA):
            continue
        gics_sub = gics_lookup(t)
        bucket, source = assign_bucket(t, gics_sub, gics_map, refine)
        # NO_DATA 也照樣記錄一筆,方便之後看哪些沒歸到桶(可審計)
        rec = append_record(
            bucket_map_path,
            {"ticker": t, "bucket": bucket, "source": source, "gics_sub": gics_sub},
        )
        added[t] = rec
    return added


# ---------------------------------------------------------------------------
# live 抓取(在 Colab 注入真實實作;此處給 stub 以利測試/示意)
# ---------------------------------------------------------------------------
def build_universe(
    etf_sources: list[str],
    fetch_holdings: Callable[[str], list[str]],
    is_optionable: Callable[[str], bool],
    gics_lookup: Callable[[str], str | None],
    gics_map: dict[str, str],
    refine: dict[str, str],
    bucket_map_path: str,
) -> dict:
    """組裝宇宙。所有 live 相依以參數注入。

    回傳:
      {
        "universe": [ {ticker, bucket, source}, ... ],  # 通過 option 濾網者
        "dropped_no_option": [tickers],
        "no_bucket": [tickers],   # 歸桶失敗(NO_DATA),需人工補 refine
      }
    """
    holdings = {etf: fetch_holdings(etf) for etf in etf_sources}
    all_tickers = union_dedup(holdings)

    optionable, dropped = [], []
    for t in all_tickers:
        (optionable if is_optionable(t) else dropped).append(t)

    append_new_buckets(optionable, gics_lookup, gics_map, refine, bucket_map_path)
    bmap = latest_by_key(bucket_map_path, key="ticker")

    universe, no_bucket = [], []
    for t in optionable:
        rec = bmap.get(t, {})
        bucket = rec.get("bucket", NO_DATA)
        if bucket == NO_DATA:
            no_bucket.append(t)
        universe.append({"ticker": t, "bucket": bucket, "source": rec.get("source", NO_DATA)})

    return {"universe": universe, "dropped_no_option": dropped, "no_bucket": no_bucket}


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
