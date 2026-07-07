# =====================================================================
# AI Radar — 正式 nightly 進入點:掃整個宇宙 → tracer → RADAR.md
# 需能連 Yahoo(Colab / GitHub Actions / 本地);沙盒跑不了 live。
# 宇宙:config/universe_seed.json(過渡)+ append-only bucket_map 歸桶。
# =====================================================================
import datetime as dt
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ai_radar.universe import load_json, append_new_buckets, union_dedup  # noqa: E402
from ai_radar.etf_holdings import parse_holdings_csv, is_stale  # noqa: E402
from ai_radar.state import (  # noqa: E402
    append_record, latest_by_key, read_records, series_by_key)
from ai_radar.rates import resolve_rate  # noqa: E402
from ai_radar.scan import scan_universe  # noqa: E402
from ai_radar.router import format_card  # noqa: E402
from ai_radar.report import render_report  # noqa: E402
from ai_radar.tracer import (  # noqa: E402
    record_scan, record_outcome, due_backfills, report, scanned_on,
    open_cards, record_card_track, card_report)
from ai_radar import live_yf  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
CFG = load_json(os.path.join(ROOT, "config", "config.json"))
TODAY = dt.date.today()
STATE = os.path.join(ROOT, "state")
IV_HISTORY = os.path.join(STATE, "iv_history.jsonl")
TRACER = os.path.join(STATE, "tracer.jsonl")
BUCKET_MAP = os.path.join(STATE, "bucket_map.jsonl")
UNIVERSE_SNAP = os.path.join(STATE, "universe.jsonl")

R_DEFAULT = CFG["data"].get("risk_free_rate_default", 0.045)
R_CUTOFF = CFG["data"].get("rate_tenor_cutoff_days", 365)


def _load_cfg_json(name):
    d = load_json(os.path.join(ROOT, "config", name))
    return {k: v for k, v in d.items() if not k.startswith("_")}


def fetch_universe_tickers():
    """Block 1.5:真 ETF 持股,週更 + 逐級降級。回傳 (tickers, 來源說明)。

    快照 ≤7 天 → 直接用;過期 → issuer CSV → yfinance 前十大 → 舊快照 → seed。
    新面孔(bucket_map 沒見過)才做 option 濾網,避免每晚重驗整個宇宙。
    """
    seed = _load_cfg_json("universe_seed.json")["tickers"]
    snaps = list(read_records(UNIVERSE_SNAP))
    last = snaps[-1] if snaps else None
    # 設計決策(2026-07-05):Yahoo top10 聯集是「正式」宇宙來源,不是降級——
    # 本工具獵的是大象(SMH 前十大=72.5% 資產),ETF 長尾小部位歸湯姆熊(optscnr)。
    # issuer CSV 全量是可選擴充(config/etf_sources.json 有 URL 才試)。
    if last and not is_stale(last.get("ts", ""), TODAY):
        return last["tickers"], f"快照 {last['ts'][:10]}(週更未到期)"

    srcs = _load_cfg_json("etf_sources.json")
    got, how = {}, {}
    for etf in CFG["universe"]["etf_sources"]:
        tickers, via = None, "fail"
        url = (srcs.get(etf) or {}).get("csv_url")
        if url:
            try:
                tickers = parse_holdings_csv(live_yf.fetch_url_text(url)) or None
                via = "csv" if tickers else via
            except Exception:
                tickers = None
        if tickers is None:
            tickers = live_yf.fetch_etf_top_holdings(etf) or None
            via = "top10" if tickers else via   # 後備只有前十大,宇宙會偏小
        got[etf], how[etf] = tickers, via

    ok = {k: v for k, v in got.items() if v}
    if not ok:
        if last:
            return last["tickers"], f"舊快照 {last['ts'][:10]}(ETF 來源全掛)"
        return seed, "seed 後備(ETF 來源全掛且無快照)"

    tickers = union_dedup(ok)
    known = set(latest_by_key(BUCKET_MAP))
    no_option = sorted(t for t in tickers
                       if t not in known and not live_yf.is_optionable(t))
    tickers = [t for t in tickers if t not in no_option]
    append_record(UNIVERSE_SNAP, {
        "tickers": tickers, "dropped_no_option": no_option, "sources": how})
    detail = "、".join(f"{k}:{how[k]}" for k in sorted(got))
    return tickers, f"ETF 持股({detail};{len(tickers)} 檔)"


def resolve_universe():
    """宇宙 → append-only 歸桶(缺的用 yfinance industry 補)→ [(ticker, bucket)]。"""
    tickers, src_note = fetch_universe_tickers()
    gics_map, refine = _load_cfg_json("gics_map.json"), _load_cfg_json("refine.json")

    def gics_lookup(t):
        try:
            return live_yf._yf().Ticker(t).info.get("industry")
        except Exception:
            return None

    append_new_buckets(tickers, gics_lookup, gics_map, refine, BUCKET_MAP)
    bmap = latest_by_key(BUCKET_MAP)
    uni = [(t, bmap.get(t, {}).get("bucket", "NO_DATA")) for t in tickers]
    return [(t, b) for t, b in uni if b != "ETF代理"], src_note


def record_atm_iv(t, S, chain):
    """IV 自舉:每 ticker 每天一筆 ATM IV(同日重跑不重複灌)。"""
    if not chain:
        return
    atm_iv = min(chain, key=lambda c: abs(c["strike"] - S))["iv"]
    last = latest_by_key(IV_HISTORY).get(t)
    if last and str(last.get("ts", "")).startswith(TODAY.isoformat()):
        return
    append_record(IV_HISTORY, {"ticker": t, "iv": round(atm_iv, 4)})


if __name__ == "__main__":
    # 休市守門:美股今天沒交易(假日)→ 資料全是上一交易日的,掃了只會
    # 灌雜訊樣本進 tracer/IV 自舉 → 跳過本晚(判斷不了就照跑,交給降級)。
    try:
        last_trade = live_yf._yf().Ticker("SPY").history(period="1d").index[-1].date()
        us_today = dt.datetime.now(dt.timezone(dt.timedelta(hours=-4))).date()
        if last_trade < us_today:
            print(f"美股休市(最近交易日 {last_trade},美東今天 {us_today})"
                  f"→ 本晚跳過,不掃描、不 commit")
            sys.exit(0)
    except Exception:
        pass

    asof = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    r_short, r_long = live_yf.fetch_yields()

    def rate_for(dte):
        return resolve_rate(dte or 90, r_short, r_long, R_DEFAULT, R_CUTOFF)

    universe, src_note = resolve_universe()
    fmt = lambda x: f"{x:.3%}" if x is not None else "NO_DATA"  # noqa: E731
    print(f"AI Radar nightly scan · {asof} · 宇宙 {len(universe)} 檔 · 來源:{src_note}")
    print(f"無風險利率:短 {fmt(r_short)} / 長 {fmt(r_long)}(缺→{R_DEFAULT:.2%})")

    iv_hist = series_by_key(IV_HISTORY)
    recs = scan_universe(
        universe, CFG, today=TODAY,
        fetch_spot=live_yf.fetch_spot,
        fetch_chain=live_yf.make_chain_fetcher(rate_for, TODAY),
        fetch_events=live_yf.fetch_events,
        fetch_rv=lambda t: live_yf.fetch_rv(t, CFG["data"]["realized_vol_window_days"]),
        rate_for=rate_for, iv_history=iv_hist, asof=asof,
        on_chain=record_atm_iv, sleep=lambda: time.sleep(0.8))

    # 掃描進度即時可讀
    for rec in recs:
        line = f"  {rec['ticker']:6s} {rec['bucket']:4s} route={rec['route'] or '—':9s} {rec['verdict']}"
        if rec.get("code"):
            line += f" {rec['code']}"
        print(line)

    # tracer:同日去重(檔×透鏡;NO_DATA 可被實判蓋過)→ 收 → 回填到期 → 報表
    seen = scanned_on(TRACER, TODAY)
    saved = 0
    for rec in recs:
        vs = seen.get((rec["ticker"], rec["route"]))
        if vs is None or (rec["verdict"] != "NO_DATA" and vs == {"NO_DATA"}):
            record_scan(TRACER, rec)
            saved += 1
    due = due_backfills(TRACER, TODAY, CFG["tracer"]["horizons_days"])
    filled = 0
    for d in due:
        try:
            now_px = live_yf.fetch_spot(d["ticker"])
        except Exception:
            continue   # 抓不到 → 留著下次回填
        record_outcome(TRACER, d["ticker"], d["scan_ts"], d["horizon_days"],
                       d["spot_then"], now_px, option_mid_then=d["option_mid_then"])
        filled += 1
    rep = report(TRACER, CFG["tracer"]["min_samples"])

    # 合約卡追蹤:曾上榜的每張卡,每晚標記市價,追到「到期前 N 天」為止
    stop_days = CFG["tracer"].get("card_track_stop_before_expiry_days", 21)
    tracked = 0
    for c in open_cards(TRACER, TODAY, stop_days):
        mid_now = live_yf.fetch_option_mid(c["ticker"], c["expiry"], c["strike"])
        try:
            spot_now = live_yf.fetch_spot(c["ticker"])
        except Exception:
            spot_now = None
        record_card_track(TRACER, c, mid_now, spot_now)
        tracked += 1
    cards_now = card_report(TRACER)

    # 人看的報告(上半白話、下半 Details)
    after_iv = series_by_key(IV_HISTORY)
    limbo = sorted(t for t, b in universe if b in ("NO_DATA", "半導體"))
    attention = ([f"歸桶未決(粗桶/NO_DATA),請補 config/refine.json:{'、'.join(limbo)}"]
                 if limbo else None)
    md = render_report(recs, asof=asof, r_short=r_short, r_long=r_long,
                       r_default=R_DEFAULT,
                       iv_counts={t: len(v) for t, v in after_iv.items()},
                       ivp_min=CFG["data"]["iv_percentile_min_history_days"],
                       tracer_report=rep, universe_note=src_note, attention=attention,
                       card_tracking=cards_now)
    with open(os.path.join(ROOT, "RADAR.md"), "w", encoding="utf-8") as f:
        f.write(md)

    survivors = [r for r in recs if r.get("card")]
    n_ex = sum(1 for r in recs if not r.get("card") and r["verdict"] != "NO_DATA")
    n_nd = sum(1 for r in recs if r["verdict"] == "NO_DATA")
    print(f"\n存活者 {len(survivors)} / 排除 {n_ex} / NO_DATA {n_nd};"
          f"tracer 收 {saved} 筆、回填 {filled}/{len(due)}、卡追蹤 {tracked} 張"
          f" → RADAR.md 已更新")
    for r in survivors:
        print(format_card(r["card"]))
