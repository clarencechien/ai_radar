# =====================================================================
# AI Radar — Block 1 宇宙管線 · Colab 驗證腳本
# 目的:在能連 Yahoo 的環境(Colab)驗證 live fetchers,
#      沙盒連不到 yahoo.com,所以這段只能在 Colab / 本地跑。
#
# 用法:把整個 repo 上傳 Colab(或 git clone),然後執行本檔。
#   !pip install yfinance
#   !python notebooks/colab_verify_block1.py
# =====================================================================
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import yfinance as yf  # noqa: E402
from ai_radar.universe import build_universe, load_json  # noqa: E402

HERE = os.path.dirname(__file__)
CONF = os.path.join(HERE, "..", "config")
STATE = os.path.join(HERE, "..", "state")

# --- STEP 0:先用 seed 清單驗 pipeline,ETF 持股抓取留待 Block 1.5 ---
# 這一步只驗「option 檢查 + industry 歸桶 + append-only」的 live 行為。
SEED = ["NVDA", "AMD", "AVGO", "MRVL", "TSM", "INTC", "MU",
        "ASML", "AMAT", "LRCX", "KLAC", "VST", "CEG", "GEV",
        "GOOGL", "MSFT", "META", "AMZN", "ORCL", "PLTR",
        "SMH", "SOXX", "DRAM", "SSNLF"]  # SSNLF=三星,預期無美股 option→被濾掉


# --- live fetchers(注入 build_universe)---
def fetch_holdings(etf: str):
    # Block 1.5 再換成真 ETF 持股 CSV;先回傳 seed 讓 pipeline 跑通
    return SEED if etf == "AIQ" else []


_info_cache = {}
def _info(t):
    if t not in _info_cache:
        try:
            _info_cache[t] = yf.Ticker(t).info or {}
        except Exception:
            _info_cache[t] = {}
        time.sleep(0.3)  # 溫柔一點,避免被限流
    return _info_cache[t]


def is_optionable(t: str) -> bool:
    try:
        return len(yf.Ticker(t).options) > 0
    except Exception:
        return False


def gics_lookup(t: str):
    return _info(t).get("industry")  # yfinance 的 industry 字串


# --- 跑起來 ---
if __name__ == "__main__":
    gics_map = {k: v for k, v in load_json(os.path.join(CONF, "gics_map.json")).items()
                if not k.startswith("_")}
    refine = load_json(os.path.join(CONF, "refine.json"))
    bmap_path = os.path.join(STATE, "bucket_map.jsonl")

    # (A) 先 dump 每檔真實 industry,方便校準 gics_map
    print("=== yfinance industry dump(校準 gics_map 用)===")
    for t in SEED:
        ind = gics_lookup(t)
        hit = "✅" if (ind in gics_map or t in refine) else "❌未對到"
        print(f"  {t:6} industry={ind!r:45} {hit}")

    # (B) 跑宇宙管線
    print("\n=== build_universe ===")
    out = build_universe(
        etf_sources=["AIQ"],
        fetch_holdings=fetch_holdings,
        is_optionable=is_optionable,
        gics_lookup=gics_lookup,
        gics_map=gics_map,
        refine=refine,
        bucket_map_path=bmap_path,
    )
    print(f"宇宙 {len(out['universe'])} 檔:")
    for u in out["universe"]:
        print(f"  {u['ticker']:6} → {u['bucket']}  ({u['source']})")
    print(f"\n被濾(無 option): {out['dropped_no_option']}")
    print(f"歸桶失敗(需補 refine): {out['no_bucket']}")

    # (C) 驗 append-only:再跑一次,不應新增
    before = sum(1 for _ in open(bmap_path)) if os.path.exists(bmap_path) else 0
    build_universe(["AIQ"], fetch_holdings, is_optionable, gics_lookup,
                   gics_map, refine, bmap_path)
    after = sum(1 for _ in open(bmap_path))
    print(f"\nappend-only 檢查:第一次寫 {before} 筆,第二次後 {after} 筆 "
          f"({'✅ 未覆寫' if before == after else '❌ 有重覆寫'})")
