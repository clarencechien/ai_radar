# =====================================================================
# AI Radar — 量測:讀 state/(離線),印「有沒有 edge、有效樣本多少」。
# 跑法:python notebooks/measure.py   (任何環境;不碰網路、不改 state/config)
# 一個月後再跑一次,對照 MEASURE.md 的基準數字。
# =====================================================================
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ai_radar.measure import measure_all, render_text  # noqa: E402
from ai_radar.state import read_records  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
STATE = os.path.join(ROOT, "state")

if __name__ == "__main__":
    recs = list(read_records(os.path.join(STATE, "tracer.jsonl")))
    ivs = list(read_records(os.path.join(STATE, "iv_history.jsonl")))
    m = measure_all(recs, ivs)
    print(render_text(m))
    try:
        from ai_radar.paper import paper_book, render_paper_text  # noqa: E402
        print("")
        print(render_paper_text(paper_book(recs)))
    except ImportError:
        pass
