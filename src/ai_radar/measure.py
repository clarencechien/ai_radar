"""量測模組:把 append-only 的 tracer / iv_history 樣本算成「有沒有 edge、有效樣本多少」。

純邏輯、只讀 state、不改 config(承 SPEC §8:tracer 只產報表,調參人工拍板)。
每一段回答一個問題:
- verdict_table:濾網留下的(PASS)vs 砍掉的(EXCLUDE)標的事後表現,含全宇宙基準。
- card_returns_by_lens:合約卡(若真的買了)的報酬,槓桿卡另算「delta 應得」缺口。
- convexity_event_coverage:凸性卡的追蹤有沒有跨過催化劑日(沒跨過 = 論點沒被測到)。
- iv_trend:期間籃子 IV 走勢(long premium 的順風/逆風)。
- regime_prototype:短窗價格動能當 regime 標籤的條件式報酬(只觀察,不當閘)。
- effective_n:重疊視窗與高相關標的下的「獨立樣本數」估計,避免拿 n=3000 自欺。
"""
from __future__ import annotations

import math
import statistics as st
from collections import defaultdict
from datetime import date, datetime


def _mean(v):
    return round(st.mean(v), 2) if v else None


def _median(v):
    return round(st.median(v), 2) if v else None


def _win(v):
    return round(100.0 * sum(x > 0 for x in v) / len(v), 1) if v else None


def _day(ts: str) -> str:
    return str(ts)[:10]


def split(records) -> dict:
    """把 tracer 紀錄依 kind 分桶:{scan, outcome, card_track, bench, regime}。"""
    out = defaultdict(list)
    for r in records:
        out[r.get("kind")].append(r)
    return out


def effective_n(distinct_days: int, horizon_days: int, distinct_clusters: int) -> int:
    """獨立樣本數的保守估計:不重疊視窗數 × 群數(標的高相關時群數 ≈ 1–3)。

    49 個掃描日、20 天窗 → 只有 2–3 個不重疊視窗;乘上標的群數才是真 n。
    這裡群數直接用 distinct_clusters 上限,已是偏樂觀;呼叫端可再除以相關性。
    """
    if distinct_days <= 0 or horizon_days <= 0:
        return 0
    windows = max(1, math.ceil(distinct_days / horizon_days))
    return windows * max(1, distinct_clusters)


def verdict_table(records, horizons=(5, 10, 20)) -> dict:
    """PASS vs EXCLUDE × T+N 的標的報酬分布 + 全宇宙(ticker×day 去重)基準。"""
    parts = split(records)
    smap = {(s["ticker"], s["ts"]): s for s in parts["scan"]}
    out = {}
    for h in horizons:
        groups = defaultdict(list)     # verdict -> [(ticker, day, ret)]
        universe = {}                  # (ticker, day) -> ret
        for o in parts["outcome"]:
            if o.get("horizon_days") != h or o.get("underlying_ret_pct") is None:
                continue
            s = smap.get((o["ticker"], o["scan_ts"]))
            if s is None or s.get("verdict") == "NO_DATA":
                continue
            v = "PASS" if s["verdict"] == "PASS" else "EXCLUDE"
            groups[v].append((o["ticker"], _day(o["scan_ts"]), o["underlying_ret_pct"]))
            universe[(o["ticker"], _day(o["scan_ts"]))] = o["underlying_ret_pct"]
        row = {}
        for v in ("PASS", "EXCLUDE"):
            g = groups.get(v, [])
            rets = [x[2] for x in g]
            by_t = defaultdict(list)
            for t, _, r in g:
                by_t[t].append(r)
            days = {x[1] for x in g}
            row[v] = {"n": len(rets), "tickers": len(by_t), "days": len(days),
                      "mean": _mean(rets), "median": _median(rets), "win_pct": _win(rets),
                      "n_eff": effective_n(len(days), h, len(by_t)),
                      "per_ticker_mean": {t: _mean(r) for t, r in
                                          sorted(by_t.items(), key=lambda x: -st.mean(x[1]))}}
        u = list(universe.values())
        row["UNIVERSE"] = {"n": len(u), "mean": _mean(u), "median": _median(u),
                           "win_pct": _win(u)}
        row["pass_minus_universe"] = (round(row["PASS"]["mean"] - row["UNIVERSE"]["mean"], 2)
                                      if row["PASS"]["mean"] is not None and u else None)
        out[f"T+{h}"] = row
    return out


def first_listings(records) -> dict:
    """每張卡(ticker, expiry, strike)第一次上榜的資料(掛牌基準)。"""
    first = {}
    for s in split(records)["scan"]:
        c = s.get("card") or {}
        if not c.get("expiry"):
            continue
        key = (c["ticker"], c["expiry"], c["strike"])
        if key not in first:
            first[key] = {"lens": c.get("lens") or s.get("route"), "listed": _day(s["ts"]),
                          "premium": c.get("premium"), "spot": c.get("spot"),
                          "delta": c.get("delta"),
                          "catalyst_date": (s.get("catalyst") or {}).get("date")}
    return first


def latest_marks(records) -> tuple[dict, dict]:
    """每張卡最新一筆 card_track 與標記次數。"""
    latest, counts = {}, defaultdict(int)
    for c in split(records)["card_track"]:
        key = (c["ticker"], c["expiry"], c["strike"])
        latest[key] = c
        counts[key] += 1
    return latest, counts


def card_returns_by_lens(records) -> dict:
    """合約卡報酬(掛牌 mid → 最新 mid)依透鏡分組;槓桿卡加算 delta 應得缺口。

    n_eff:槓桿卡以「標的」為群(同檔多張卡高度相關);凸性卡以「標的×到期」為事件。
    substitute_gap = 實際報酬 − delta×ΔS/權利金(現貨替代品應得的部分);
    負值 = 被 vega/theta/價差吃掉。
    """
    first = first_listings(records)
    latest, _ = latest_marks(records)
    by = defaultdict(list)
    for key, f in first.items():
        c = latest.get(key)
        if not c or c.get("option_ret_pct") is None:
            continue
        row = {"key": key, "listed": f["listed"], "ret": c["option_ret_pct"],
               "dte_left": c.get("dte_left")}
        s0, s1, dl, p0 = f["spot"], c.get("spot_now"), f["delta"], f["premium"]
        if s0 and s1 and dl and p0:
            row["underlying_ret"] = round((s1 / s0 - 1) * 100, 2)
            row["delta_implied_ret"] = round(dl * (s1 - s0) / p0 * 100, 2)
            row["substitute_gap"] = round(row["ret"] - row["delta_implied_ret"], 2)
        by[f["lens"]].append(row)
    out = {}
    for lens, rows in by.items():
        rets = [r["ret"] for r in rows]
        if lens == "convexity":
            clusters = {(r["key"][0], r["key"][1]) for r in rows}
        else:
            clusters = {r["key"][0] for r in rows}
        d = {"n": len(rows), "n_eff": len(clusters), "mean": _mean(rets),
             "median": _median(rets), "win_pct": _win(rets),
             "min": min(rets), "max": max(rets),
             "rows": sorted(rows, key=lambda r: r["ret"])}
        gaps = [r["substitute_gap"] for r in rows if "substitute_gap" in r]
        und = [r["underlying_ret"] for r in rows if "underlying_ret" in r]
        if gaps:
            d["underlying_mean"] = _mean(und)
            d["substitute_gap_mean"] = _mean(gaps)
            d["substitute_gap_median"] = _median(gaps)
            d["substitute_gap_neg_pct"] = round(100.0 * sum(g < 0 for g in gaps) / len(gaps), 1)
        out[lens] = d
    return out


def convexity_event_coverage(records) -> dict:
    """凸性卡:追蹤最後一筆是否在催化劑日之後(否 → 事件本身沒被量到)。"""
    first = first_listings(records)
    latest, _ = latest_marks(records)
    rows = []
    for key, f in first.items():
        if f["lens"] != "convexity":
            continue
        last = latest.get(key)
        last_day = _day(last["ts"]) if last else None
        cat = f.get("catalyst_date")
        covered = bool(cat and last_day and last_day > cat)
        rows.append({"key": key, "listed": f["listed"], "catalyst": cat,
                     "last_track": last_day, "expiry": key[1], "covered": covered})
    return {"n": len(rows), "covered": sum(r["covered"] for r in rows), "rows": rows}


def iv_trend(iv_records) -> dict:
    """籃子 LEAPS ATM IV 的期間走勢(每日平均)+ 每檔首尾。"""
    by_t = defaultdict(dict)
    for r in iv_records:
        if r.get("iv") is not None:
            by_t[r["ticker"]][_day(r["ts"])] = r["iv"]
    by_day = defaultdict(list)
    for t, dd in by_t.items():
        for d, v in dd.items():
            by_day[d].append(v)
    days = sorted(by_day)
    basket = {d: round(st.mean(by_day[d]), 4) for d in days}
    per_t = {}
    for t, dd in by_t.items():
        ds = sorted(dd)
        if len(ds) >= 2:
            per_t[t] = {"first": dd[ds[0]], "last": dd[ds[-1]],
                        "chg_pct": round((dd[ds[-1]] / dd[ds[0]] - 1) * 100, 1)}
    out = {"days": len(days), "basket_by_day": basket, "per_ticker": per_t}
    if days:
        out["basket_first"], out["basket_last"] = basket[days[0]], basket[days[-1]]
        out["basket_chg_pct"] = round((basket[days[-1]] / basket[days[0]] - 1) * 100, 1)
    return out


def regime_prototype(records, horizons=(10, 20), window=10, min_history=35) -> dict:
    """短窗價格 regime 原型:籃子等權 window 日報酬 > 0 且漲家數 ≥ 50% → TAIL,否則 HEAD。

    只觀察:回答「若照短窗動能只打順風球,事後如何」。基準籃子取歷史 ≥ min_history 的標的。
    """
    parts = split(records)
    panel = defaultdict(dict)
    for s in parts["scan"]:
        if s.get("spot"):
            panel[s["ticker"]][_day(s["ts"])] = s["spot"]
    days = sorted({_day(s["ts"]) for s in parts["scan"]})
    core = [t for t, d in panel.items() if len(d) >= min_history]
    regime = {}
    for i, d in enumerate(days):
        if i < window:
            continue
        d0 = days[i - window]
        rets = [panel[t][d] / panel[t][d0] - 1 for t in core
                if d in panel[t] and d0 in panel[t]]
        if len(rets) < 5:
            continue
        breadth = sum(r > 0 for r in rets) / len(rets)
        ew = st.mean(rets) * 100
        regime[d] = {"ew_ret_pct": round(ew, 1), "breadth": round(breadth, 2),
                     "label": "TAIL" if (ew > 0 and breadth >= 0.5) else "HEAD"}
    smap = {(s["ticker"], s["ts"]): s for s in parts["scan"]}
    cond = {}
    for h in horizons:
        g = defaultdict(list)
        for o in parts["outcome"]:
            if o.get("horizon_days") != h or o.get("underlying_ret_pct") is None:
                continue
            s = smap.get((o["ticker"], o["scan_ts"]))
            d = _day(o["scan_ts"])
            if not s or d not in regime or s.get("verdict") == "NO_DATA":
                continue
            v = "PASS" if s["verdict"] == "PASS" else "EXCLUDE"
            g[(regime[d]["label"], v)].append(o["underlying_ret_pct"])
        cond[f"T+{h}"] = {f"{lab}/{v}": {"n": len(x), "mean": _mean(x), "win_pct": _win(x)}
                          for (lab, v), x in sorted(g.items())}
    n_lab = defaultdict(int)
    for r in regime.values():
        n_lab[r["label"]] += 1
    return {"core_tickers": core, "window": window, "by_day": regime,
            "days_by_label": dict(n_lab), "conditional": cond}


def measure_all(records, iv_records, horizons=(5, 10, 20)) -> dict:
    return {"verdict": verdict_table(records, horizons),
            "cards": card_returns_by_lens(records),
            "cvx_coverage": convexity_event_coverage(records),
            "iv": iv_trend(iv_records),
            "regime": regime_prototype(records)}


def _fmt_stats(s: dict) -> str:
    return (f"n={s['n']} mean={s['mean']:+.2f}% median={s['median']:+.2f}% "
            f"win={s['win_pct']}%") if s.get("n") else "n=0"


def render_text(m: dict) -> str:
    """CLI 用的人讀文字。"""
    L = ["== 濾網:PASS vs EXCLUDE vs 全宇宙(標的報酬)"]
    for h, row in m["verdict"].items():
        L.append(f"[{h}]")
        for v in ("PASS", "EXCLUDE"):
            s = row[v]
            L.append(f"  {v:8s} {_fmt_stats(s)} | tickers={s['tickers']} days={s['days']} "
                     f"n_eff≈{s['n_eff']}")
        u = row["UNIVERSE"]
        L.append(f"  UNIVERSE {_fmt_stats(u)} | PASS−UNIVERSE = "
                 f"{row['pass_minus_universe']:+.2f} 點" if u.get("n") else "  UNIVERSE n=0")
    L.append("")
    L.append("== 合約卡(掛牌 mid → 最新 mid)")
    for lens, d in m["cards"].items():
        L.append(f"  {lens:10s} n={d['n']} n_eff={d['n_eff']} mean={d['mean']:+.1f}% "
                 f"median={d['median']:+.1f}% win={d['win_pct']}% "
                 f"range {d['min']:+.1f}%~{d['max']:+.1f}%")
        if "substitute_gap_mean" in d:
            L.append(f"             標的均漲 {d['underlying_mean']:+.2f}% → 卡應得(delta)− 實際:"
                     f"缺口 mean {d['substitute_gap_mean']:+.1f} 點 / median "
                     f"{d['substitute_gap_median']:+.1f} 點 / {d['substitute_gap_neg_pct']}% 為負")
    cv = m["cvx_coverage"]
    L += ["", f"== 凸性卡追蹤跨過催化劑日:{cv['covered']}/{cv['n']} 張"]
    for r in cv["rows"]:
        L.append(f"  {r['key'][0]} {r['expiry']} ${r['key'][2]:g}C 掛牌 {r['listed']} "
                 f"催化劑 {r['catalyst']} 最後追蹤 {r['last_track']} "
                 f"{'✓' if r['covered'] else '✗ 事件前停追'}")
    iv = m["iv"]
    if iv.get("days"):
        L += ["", f"== 籃子 LEAPS ATM IV:{iv['basket_first']:.3f} → {iv['basket_last']:.3f} "
              f"({iv['basket_chg_pct']:+.1f}%,{iv['days']} 天)"]
        for t, x in sorted(iv["per_ticker"].items(), key=lambda kv: kv[1]["chg_pct"]):
            L.append(f"  {t:6s} {x['first']:.3f} → {x['last']:.3f} ({x['chg_pct']:+.1f}%)")
    rg = m["regime"]
    L += ["", f"== regime 原型(籃子 {rg['window']} 日動能;只觀察不當閘)"
          f" 天數 {rg['days_by_label']}"]
    for h, d in rg["conditional"].items():
        for k, s in d.items():
            L.append(f"  {h} {k:14s} n={s['n']} mean={s['mean']:+.2f}% win={s['win_pct']}%")
    return "\n".join(L)
