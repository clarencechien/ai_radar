"""人看的掃描報告(markdown)。

把 scan_one 的紀錄 + 自舉/tracer 進度組成一份 RADAR.md(repo root),
nightly Action 跑完自動 commit——人看報告,不用去翻 Actions log。
輸出永遠印:via negativa 非建議、G0 狀態。純字串組裝,無外部相依。
"""
from __future__ import annotations

# 排除/降級代碼 → 人話
CODE_TEXT = {
    "LEV_NO_DELTA": "無 delta 落區間的合格 LEAPS",
    "LEV_IV_HIGH": "IV 落在自身歷史高檔(現在買貴)",
    "CVX_NO_STRIKE": "無便宜合格價外(權利金上限/OTM 上限/到期窗內全滅)",
    "CVX_IV_PRICED": "事件 IV 已被市場定價(無 edge)",
    "NO_CATALYST": "無帶日期催化劑(凸性透鏡不適用)",
    "LIQ_NO_OI_DATA": "Yahoo 時段性缺 OI —— 資料缺失非判斷,盤中重跑",
    "NO_CONTRACTS": "建不出合約(bid/ask 全空)—— 資料缺失非判斷",
}


def _fmt_pct(x, digits=3):
    return f"{x:.{digits}%}" if x is not None else "NO_DATA"


def _card_row(rec) -> str:
    c = rec["card"]
    cat = f"T-{c['catalyst_t_minus']}" if c["catalyst_t_minus"] is not None else "—"
    scenario = (f"若+{c['target_move_pct']:g}% 內含 {c['multiple_at_target']}×"
                if c.get("target_move_pct") else "—")
    return (f"| {c['ticker']} | {c['bucket']}{('/' + c['tier']) if c['tier'] else ''} "
            f"| {c['lens']} | {cat} | {c['expiry']} ${c['strike']:g}C "
            f"| ${c['premium']} | {c['delta']} | {c['eff_leverage']}x "
            f"| +{c['breakeven_pct']}% | {scenario} |")


def render_report(recs, *, asof, r_short=None, r_long=None, r_default=0.045,
                  iv_counts=None, ivp_min=60, tracer_report=None) -> str:
    """組報告。recs = scan_one 紀錄清單;其餘皆選填(缺就不印該段)。"""
    survivors = [r for r in recs if r.get("card")]
    excluded = [r for r in recs if not r.get("card") and r.get("verdict") != "NO_DATA"]
    no_data = [r for r in recs if r.get("verdict") == "NO_DATA"]

    L = [
        "# AI Radar 掃描報告",
        "",
        f"> 資料時戳 {asof} · 無風險利率 短 {_fmt_pct(r_short)} / 長 {_fmt_pct(r_long)}"
        f"(缺→{r_default:.2%})",
        "> ⚠️ **via negativa 過濾器輸出,非投資建議;扣不扣板機永遠是人。**",
        "> G0 曝險護欄未啟用 —— 曝險/地緣左尾自行判斷。",
        "",
        f"## 存活者({len(survivors)})—— 若動手,該買哪張",
        "",
    ]
    if survivors:
        L += ["| 標的 | 桶 | 透鏡 | 催化劑 | 合約 | 估權利金 | delta | 倍數 | 損益兩平 | 情境 |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        L += [_card_row(r) for r in survivors]
    else:
        L.append("(本次無存活者出卡)")

    L += ["", f"## 排除清單({len(excluded)})—— 理由", ""]
    if excluded:
        L += ["| 標的 | 桶 | 透鏡 | 代碼 | 說明 | 指標 |", "|---|---|---|---|---|---|"]
        for r in excluded:
            m = r.get("metrics") or {}
            metrics = "、".join(f"{k}={v}" for k, v in m.items() if v is not None) or "—"
            L.append(f"| {r['ticker']} | {r['bucket']} | {r['route']} | `{r['code']}` "
                     f"| {CODE_TEXT.get(r['code'], '')} | {metrics} |")
    else:
        L.append("(無)")

    if no_data:
        L += ["", f"## NO_DATA({len(no_data)})—— 資料缺失,非判斷", ""]
        L += [f"- **{r['ticker']}**(route={r['route']}):`{r['code']}` —— "
              f"{CODE_TEXT.get(r['code'], '')}" for r in no_data]

    if iv_counts:
        L += ["", "## IV percentile 自舉進度", ""]
        L += [f"- {t}:{n}/{ivp_min} 筆"
              f"{'(已啟用 percentile 閘)' if n >= ivp_min else '(未滿 → edge 閘用 ratio 後備)'}"
              for t, n in sorted(iv_counts.items())]

    if tracer_report:
        tr = tracer_report
        L += ["", "## shadow tracer(collect_only)", "",
              f"- 掃描累計 {tr['scan_count']} 筆、outcome 回填 {tr['outcome_count']} 筆",
              f"- 調參解鎖:{'是' if tr['tuning_unlocked'] else '否'}"
              f"(需 outcome ≥{tr['min_samples']},解鎖後仍人工週審拍板)"]
        for group, hs in sorted((tr.get("by_verdict") or {}).items()):
            stats = "、".join(f"{h} n={s['n']} avg {s['avg_ret_pct']:+.1f}%"
                              f"({s['min_ret_pct']:+.1f}%~{s['max_ret_pct']:+.1f}%)"
                              for h, s in sorted(hs.items()))
            L.append(f"  - `{group}`:{stats}")

    L += ["", "---", "*由 nightly-live Action 自動生成(`src/ai_radar/report.py`);"
          "歷史紀錄見 `state/tracer.jsonl`。*", ""]
    return "\n".join(L)
