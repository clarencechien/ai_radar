"""模擬帳本(paper book):把「上過榜的卡」當成真的買了一張,用既有標記算帳。

單一事實來源 = tracer 的 scan / card_track / bench 紀錄(append-only),帳本是**推導**,
不另存第二份狀態,永遠可從 state 重算(MEASURE.md §2.3)。

規則(記錄規則,不是閾值;透鏡與 config 一個不動):
- 進場:每張 (ticker, expiry, strike) 第一次上榜;有 ask 用 ask(真成本),否則 mid。
- 出場:
  - 槓桿卡:剩 ≤ stop 天(預設 21)的第一筆標記,以 bid(缺→mid)出場。
  - 凸性卡:催化劑日**之後**的第一筆標記(事件已發生),以 bid(缺→mid)出場;
    到期前沒有這筆 → 看最後一筆:若已過到期日 = CENSORED(舊追蹤規則在事件前停追,
    帳本不用它下結論),否則 OPEN。
- 未出場:OPEN,以最新標記估值(unrealized;成本基準用 bid = 現在砍掉拿得到多少)。
- 每張:mid→mid 報酬(與舊卡可比)、成本基準報酬(ask→bid,雙邊都有才算)、標的同期報酬、
  delta 應得報酬、substitute gap、SMH 同期報酬(bench 有才算)、delta/vega/theta 貢獻拆解
  (卡有 vega/iv 且標記有 iv_now 才算;舊卡 None)。
- 匯總:依透鏡 n / n_eff(槓桿:標的數;凸性:標的×到期事件數)/ 均值 / 勝率 /
  每張 $ 損益(×100)/ 貢獻合計。
"""
from __future__ import annotations

import statistics as st
from collections import defaultdict
from datetime import date

from .measure import first_listings, split


def _d(ts) -> str:
    return str(ts)[:10]


def _bench_at(benches: list[dict], day: str, symbol: str):
    """day 當天或之前最近一筆基準收盤;沒有 → None。"""
    best = None
    for b in benches:
        bd = _d(b.get("ts", ""))
        if bd <= day and (b.get("quotes") or {}).get(symbol):
            if best is None or bd > best[0]:
                best = (bd, b["quotes"][symbol])
    return best[1] if best else None


def _entry(card: dict, scan: dict) -> dict:
    ask = card.get("ask") or 0
    mid = card.get("premium")
    return {"mid": mid, "cost": ask if ask > 0 else mid,
            "cost_basis": "ask" if ask > 0 else "mid",
            "spot": card.get("spot"), "delta": card.get("delta"),
            "vega": card.get("vega"), "theta_day": card.get("theta_day"),
            "iv": card.get("iv"), "day": _d(scan["ts"]),
            "catalyst_date": (scan.get("catalyst") or {}).get("date")}


def _first_cards(records) -> dict:
    """(ticker, expiry, strike) → 第一次上榜的 (card, scan)。"""
    first = {}
    for s in split(records)["scan"]:
        c = s.get("card") or {}
        if c.get("expiry"):
            first.setdefault((c["ticker"], c["expiry"], c["strike"]), (c, s))
    return first


def _marks_by_key(records) -> dict:
    by = defaultdict(list)
    for m in split(records)["card_track"]:
        by[(m["ticker"], m["expiry"], m["strike"])].append(m)
    for v in by.values():
        v.sort(key=lambda m: str(m.get("ts", "")))
    return by


def _exit_mark(lens: str, marks: list[dict], entry: dict, stop_days: int, today: date):
    """回 (mark, status)。status ∈ OPEN / CLOSED / CENSORED / NO_MARK。

    - 凸性:催化劑日之後第一筆有市價的標記 → CLOSED;沒有 → 已過期 CENSORED、未過期 OPEN。
    - 槓桿:追蹤規則在到期前 stop 天停,所以「今天距到期 ≤ stop 天」= 追蹤已結束 →
      以最後一筆有市價的標記 CLOSED;否則 OPEN(最新 mid 估值)。
    """
    if not marks:
        return None, "NO_MARK"
    valid = [m for m in marks if m.get("mid_now") is not None]
    last = valid[-1] if valid else marks[-1]
    try:
        dte_today = (date.fromisoformat(str(marks[-1].get("expiry"))) - today).days
    except ValueError:
        dte_today = 9999
    if lens == "convexity":
        cat = entry.get("catalyst_date")
        if cat:
            for m in valid:
                if _d(m["ts"]) > cat:
                    return m, "CLOSED"
        return last, ("CENSORED" if dte_today < 0 else "OPEN")
    return last, ("CLOSED" if dte_today <= stop_days else "OPEN")


def paper_book(records, *, today: date | None = None, stop_days: int = 21,
               bench_symbol: str = "SMH") -> dict:
    """推導模擬帳本。records = tracer 全部紀錄。"""
    today = today or date.today()
    parts = split(records)
    benches = parts["bench"]
    marks_by = _marks_by_key(records)
    positions = []
    for key, (card, scan) in _first_cards(records).items():
        lens = card.get("lens") or scan.get("route")
        e = _entry(card, scan)
        m, status = _exit_mark(lens, marks_by.get(key, []), e, stop_days, today)
        pos = {"key": key, "ticker": key[0], "expiry": key[1], "strike": key[2],
               "lens": lens, "status": status, "entry_day": e["day"],
               "entry_mid": e["mid"], "entry_cost": e["cost"], "cost_basis": e["cost_basis"],
               "catalyst_date": e["catalyst_date"], "n_marks": len(marks_by.get(key, []))}
        if m is None or m.get("mid_now") is None or not e["mid"]:
            pos.update({"ret_mid_pct": None, "exit_day": _d(m["ts"]) if m else None})
            positions.append(pos)
            continue
        mid1 = m["mid_now"]
        # 出場/清算價:有 bid 用 bid(OPEN = 「現在砍掉拿得到多少」),缺 → mid
        px_out = (m.get("bid_now") or 0) or mid1
        pos.update({
            "exit_day": _d(m["ts"]), "exit_mid": mid1, "exit_px": px_out,
            "days_held": (date.fromisoformat(_d(m["ts"])) - date.fromisoformat(e["day"])).days,
            "ret_mid_pct": round((mid1 / e["mid"] - 1) * 100, 1),
            "ret_cost_pct": (round((px_out / e["cost"] - 1) * 100, 1)
                             if e["cost_basis"] == "ask" and (m.get("bid_now") or 0) > 0
                             else None),
            "pnl_usd": round((px_out - e["cost"]) * 100, 0),
        })
        s0, s1 = e["spot"], m.get("spot_now")
        if s0 and s1:
            pos["underlying_ret_pct"] = round((s1 / s0 - 1) * 100, 2)
            if e["delta"]:
                pos["delta_implied_ret_pct"] = round(e["delta"] * (s1 - s0) / e["mid"] * 100, 1)
                pos["substitute_gap"] = round(pos["ret_mid_pct"] - pos["delta_implied_ret_pct"], 1)
            # 貢獻拆解(每張 1 口 = ×100):delta·ΔS + vega·Δσ(%) + theta·天 + 殘差
            if e.get("vega") is not None and e.get("iv") and m.get("iv_now"):
                d_pnl = e["delta"] * (s1 - s0)
                v_pnl = e["vega"] * (m["iv_now"] - e["iv"]) * 100
                t_pnl = (e["theta_day"] or 0) * pos["days_held"]
                actual = mid1 - e["mid"]
                pos["attribution"] = {"delta": round(d_pnl, 2), "vega": round(v_pnl, 2),
                                      "theta": round(t_pnl, 2),
                                      "residual": round(actual - d_pnl - v_pnl - t_pnl, 2)}
        b0, b1 = _bench_at(benches, e["day"], bench_symbol), _bench_at(benches, _d(m["ts"]), bench_symbol)
        if b0 and b1:
            pos["bench_ret_pct"] = round((b1 / b0 - 1) * 100, 2)
        positions.append(pos)

    # 匯總
    summary = {}
    for lens in sorted({p["lens"] for p in positions}):
        ps = [p for p in positions if p["lens"] == lens]
        scored = [p for p in ps if p.get("ret_mid_pct") is not None and p["status"] != "CENSORED"]
        by_status = defaultdict(int)
        for p in ps:
            by_status[p["status"]] += 1
        clusters = ({(p["ticker"], p["expiry"]) for p in scored} if lens == "convexity"
                    else {p["ticker"] for p in scored})
        rets = [p["ret_mid_pct"] for p in scored]
        d = {"n": len(ps), "scored": len(scored), "n_eff": len(clusters),
             "by_status": dict(by_status),
             "mean_ret_mid_pct": round(st.mean(rets), 1) if rets else None,
             "median_ret_mid_pct": round(st.median(rets), 1) if rets else None,
             "win_pct": round(100 * sum(r > 0 for r in rets) / len(rets), 1) if rets else None,
             "pnl_usd_sum": round(sum(p["pnl_usd"] for p in scored), 0) if scored else None}
        for f in ("ret_cost_pct", "underlying_ret_pct", "substitute_gap", "bench_ret_pct"):
            vals = [p[f] for p in scored if p.get(f) is not None]
            d[f"{f}_mean"] = round(st.mean(vals), 1) if vals else None
            d[f"{f}_n"] = len(vals)
        attr = [p["attribution"] for p in scored if p.get("attribution")]
        if attr:
            d["attribution_sum"] = {k: round(sum(a[k] for a in attr), 2)
                                    for k in ("delta", "vega", "theta", "residual")}
            d["attribution_n"] = len(attr)
        closed = [p for p in scored if p["status"] == "CLOSED"]
        if lens == "convexity":
            pe = [p["ret_mid_pct"] for p in closed]
            d["post_event_n"] = len(pe)
            d["post_event_mean_ret_pct"] = round(st.mean(pe), 1) if pe else None
            d["post_event_win_pct"] = (round(100 * sum(r > 0 for r in pe) / len(pe), 1)
                                       if pe else None)
        summary[lens] = d
    return {"asof": today.isoformat(), "stop_days": stop_days, "bench_symbol": bench_symbol,
            "positions": positions, "summary": summary,
            "note": "模擬帳本由 state 推導(第一次上榜=進場;槓桿:剩≤stop 天出場;"
                    "凸性:催化劑後第一筆標記出場);非建議、無真實部位。"}


def _f(x, unit="%", digits=1):
    return "—" if x is None else f"{x:+.{digits}f}{unit}"


def render_paper_text(book: dict) -> str:
    L = [f"== 模擬帳本(paper;{book['asof']};對照 {book['bench_symbol']})"]
    for lens, d in book["summary"].items():
        st_txt = "、".join(f"{k} {v}" for k, v in sorted(d["by_status"].items()))
        L.append(f"  {lens:10s} 張數 {d['n']}(計分 {d['scored']}、n_eff {d['n_eff']};{st_txt})"
                 f" mid→mid mean {_f(d['mean_ret_mid_pct'])} median {_f(d['median_ret_mid_pct'])}"
                 f" win {d['win_pct']}% · 每張合計 ${d['pnl_usd_sum'] or 0:,.0f}")
        L.append(f"             成本基準(ask→bid,n={d['ret_cost_pct_n']}) {_f(d['ret_cost_pct_mean'])}"
                 f" · 標的同期 {_f(d['underlying_ret_pct_mean'])}"
                 f" · substitute gap {_f(d['substitute_gap_mean'], ' 點')}"
                 f" · {book['bench_symbol']} 同期 {_f(d['bench_ret_pct_mean'])}"
                 f"(n={d['bench_ret_pct_n']})")
        if d.get("attribution_sum"):
            a = d["attribution_sum"]
            L.append(f"             貢獻拆解(n={d['attribution_n']},每股):delta {a['delta']:+.2f}"
                     f" vega {a['vega']:+.2f} theta {a['theta']:+.2f} 殘差 {a['residual']:+.2f}")
        if lens == "convexity":
            L.append(f"             事件後出場(post-event)n={d['post_event_n']}"
                     f" mean {_f(d['post_event_mean_ret_pct'])} win {d['post_event_win_pct']}%")
    return "\n".join(L)
