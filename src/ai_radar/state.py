"""Append-only state helpers.

家族原則:state 檔只追加、不覆寫,供回測與審計。
所有 state 以 JSONL(每行一筆 JSON)存放於 state/ 目錄。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Iterator


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def append_record(path: str, record: dict) -> dict:
    """追加一筆紀錄(自動補上 ts)。回傳實際寫入的 record。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rec = dict(record)
    rec.setdefault("ts", _utc_now())
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def read_records(path: str) -> Iterator[dict]:
    """逐行讀出所有紀錄(檔案不存在則回空)。"""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def latest_by_key(path: str, key: str = "ticker") -> dict:
    """把 append-only 紀錄摺疊成「每個 key 的最新一筆」。

    因為是 append-only,後寫的覆蓋前讀的,得到目前有效狀態。
    """
    out: dict = {}
    for rec in read_records(path):
        if key in rec:
            out[rec[key]] = rec
    return out
