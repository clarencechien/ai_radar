"""人看的掃描報告(markdown,寫到 repo root 的 RADAR.md)。

版面兩段式:
- 上半:外行人一看就懂——今晚結論、存活者白話卡、排除一句話總結。
- 下半 Details:開發者看的——技術表格、代碼、指標、自舉/tracer 進度。
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
    "FETCH_ERROR": "抓取失敗(網路/來源異常)—— 資料缺失非判斷",
}

# 排除代碼 → 給外行人的一句話
CODE_PLAIN = {
    "LEV_NO_DELTA": "找不到條件合適的長期買權",
    "LEV_IV_HIGH": "選擇權現在太貴(波動率在高檔)",
    "CVX_NO_STRIKE": "沒有夠便宜的樂透型合約",
    "CVX_IV_PRICED": "市場已把事件行情反映進價格,沒便宜可撿",
}

LENS_PLAIN = {"leverage": "長期槓桿", "convexity": "事件凸性"}


def _fmt_pct(x, digits=3):
    return f"{x:.{digits}%}" if x is not None else "NO_DATA"


def _bucket_label(b):
    return "未歸桶" if b in (None, "NO_DATA") else b


def _plain_card(rec) -> list[str]:
    """一位外行人也看得懂的存活者小卡(3–4 行)。"""
    c = rec["card"]
    lens = LENS_PLAIN.get(c["lens"], c["lens"])
    per_contract = c["premium"] * 100
    cat_txt = (f"財報/事件 T-{c['catalyst_t_minus']} 天"
               if c["catalyst_t_minus"] is not None else "無近期事件時鐘")
    L = [f"### {c['ticker']}({_bucket_label(c['bucket'])}桶)· {lens}",
         f"- 規則挑的合約:**{c['expiry']} 到期、履約價 ${c['strike']:g} 的買權**,"
         f"一張約 **${per_contract:,.0f}**(報價 ${c['premium']}×100)。"]
    if c["lens"] == "convexity":
        line = (f"- 白話:{cat_txt}的小額大賠率——股價需漲過 **+{c['breakeven_pct']}%** 才開始賺")
        if c.get("target_move_pct"):
            line += (f";若事件把股價推到 **+{c['target_move_pct']:g}%**,"
                     f"光內含價值就是本金的 **{c['multiple_at_target']} 倍**")
        L.append(line + "。輸的上限就是那一張的錢。")
    else:
        L.append(f"- 白話:用約 {c['eff_leverage']} 倍槓桿參與 {c['ticker']} 的長期走勢"
                 f"(深價內、時間站在你這邊較久);股價漲過 **+{c['breakeven_pct']}%** 開始賺。"
                 f"{cat_txt}。")
    return L + [""]


def _card_row(rec) -> str:
    c = rec["card"]
    cat = f"T-{c['catalyst_t_minus']}" if c["catalyst_t_minus"] is not None else "—"
    scenario = (f"若+{c['target_move_pct']:g}% 內含 {c['multiple_at_target']}×"
                if c.get("target_move_pct") else "—")
    return (f"| {c['ticker']} | {_bucket_label(c['bucket'])}"
            f"{('/' + c['tier']) if c['tier'] else ''} "
            f"| {c['lens']} | {cat} | {c['expiry']} ${c['strike']:g}C "
            f"| ${c['premium']} | {c['delta']} | {c['eff_leverage']}x "
            f"| +{c['breakeven_pct']}% | {scenario} |")


def render_report(recs, *, asof, r_short=None, r_long=None, r_default=0.045,
                  iv_counts=None, ivp_min=60, tracer_report=None,
                  universe_note=None, attention=None, card_tracking=None) -> str:
    """組報告。recs = scan_one 紀錄清單;其餘皆選填(缺就不印該段)。"""
    survivors = [r for r in recs if r.get("card")]
    excluded = [r for r in recs if not r.get("card") and r.get("verdict") != "NO_DATA"]
    no_data = [r for r in recs if r.get("verdict") == "NO_DATA"]

    # ============ 上半:外行人看的 ============
    L = [
        "# AI Radar 掃描報告",
        "",
        f"> {asof} · 這是**排除法濾網**:只負責剔掉「不能買/不要買」,"
        "留下的交給人判斷。**不是投資建議;要不要出手、出多少,永遠由人決定。**",
        "",
        "## 今晚結論",
        "",
        f"掃描 **{len(recs)} 檔** AI 相關股 → 通過濾網 **{len(survivors)} 檔**、"
        f"排除 **{len(excluded)} 檔**、資料缺失 **{len(no_data)} 檔**。"
        + (f"(宇宙來源:{universe_note})" if universe_note else ""),
        "",
    ]
    if survivors:
        L += ["以下每檔附「若要動手,規則會挑哪一張合約」——**是條件式答案,不是買進訊號**:", ""]
        for r in survivors:
            L += _plain_card(r)
    else:
        L += ["**今晚沒有任何標的通過濾網——「不動作」也是一種結論。**", ""]

    if excluded:
        counts: dict = {}
        for r in excluded:
            counts[r["code"]] = counts.get(r["code"], 0) + 1
        plain = "、".join(f"{n} 檔「{CODE_PLAIN.get(code, CODE_TEXT.get(code, code))}」"
                          for code, n in sorted(counts.items(), key=lambda x: -x[1]))
        L += ["## 排除了誰(一句話)", "", f"被剔掉的 {len(excluded)} 檔:{plain}。"
              "明細見下方 Details。", ""]
    if no_data:
        L += [f"另有 {len(no_data)} 檔今晚**拿不到完整資料**(不是被淘汰),明日自動重試。", ""]

    # ============ 下半:開發者 Details ============
    L += [
        "---",
        "",
        "## Details(開發者)",
        "",
        f"- 資料時戳 {asof} · 無風險利率 短 {_fmt_pct(r_short)} / 長 {_fmt_pct(r_long)}"
        f"(缺→{r_default:.2%})",
        "- G0 曝險護欄未啟用(bypass)—— 曝險/地緣左尾自行判斷。",
        "",
        f"### 存活者技術表({len(survivors)})",
        "",
    ]
    if survivors:
        L += ["| 標的 | 桶 | 透鏡 | 催化劑 | 合約 | 估權利金 | delta | 倍數 | 損益兩平 | 情境 |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        L += [_card_row(r) for r in survivors]
    else:
        L.append("(無)")

    L += ["", f"### 排除清單({len(excluded)})", ""]
    if excluded:
        L += ["| 標的 | 桶 | 透鏡 | 代碼 | 說明 | 指標 |", "|---|---|---|---|---|---|"]
        for r in excluded:
            m = r.get("metrics") or {}
            metrics = "、".join(f"{k}={v}" for k, v in m.items() if v is not None) or "—"
            L.append(f"| {r['ticker']} | {_bucket_label(r['bucket'])} | {r['route']} | `{r['code']}` "
                     f"| {CODE_TEXT.get(r['code'], '')} | {metrics} |")
    else:
        L.append("(無)")

    if no_data:
        L += ["", f"### NO_DATA({len(no_data)})—— 資料缺失,非判斷", ""]
        L += [f"- **{r['ticker']}**(route={r['route'] or '—'}):`{r['code']}` —— "
              f"{CODE_TEXT.get(r['code'], '')}"
              + (f"(`{r['error']}`)" if r.get("error") else "")
              for r in no_data]

    if attention:
        L += ["", "### 需人工處理", ""]
        L += [f"- {a}" for a in attention]

    if iv_counts:
        L += ["", "### IV percentile 自舉進度", ""]
        L += [f"- {t}:{n}/{ivp_min} 筆"
              f"{'(已啟用 percentile 閘)' if n >= ivp_min else '(未滿 → edge 閘用 ratio 後備)'}"
              for t, n in sorted(iv_counts.items())]

    if card_tracking:
        L += ["", f"### 合約卡追蹤({len(card_tracking)} 張,追到到期前 21 天)", "",
              "上過榜的每張卡,每晚標記市價——校正「造合約規則」用"
              "(標的 T+N 回填校正的是「選股排除規則」,兩者分開量)。", ""]
        for c in card_tracking:
            mark = (f"${c['mid_now']}({c['option_ret_pct']:+.1f}%)"
                    if c.get("mid_now") is not None else "NO_DATA")
            L.append(f"- {c['ticker']} {c['expiry']} ${c['strike']:g}C:"
                     f"掛牌 ${c['premium_then']} → 最新 {mark} · "
                     f"標記 {c['n_marks']} 筆 · 剩 {c['dte_left']} 天")

    if tracer_report:
        tr = tracer_report
        L += ["", "### shadow tracer(collect_only)", "",
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
