# AI Radar

通用 AI 一籃子選擇權過濾器 — **via negativa**:不告訴你買什麼,只 filter 掉不能買/不要買的,存活者留給人判斷。對存活者算「若動手該買哪張 call」的條件式合約卡。

> 家族:`optscnr` / `space_radar` / `delta_radar` / `tw_scanner` / `rainwalker`。
> 完整設計見 [`SPEC.md`](./SPEC.md)。**接手開發先讀 [`HANDOFF.md`](./HANDOFF.md)。**

## 核心原則
- **scanner 中性**:對所有標的同規則,個人判斷只住 `Gate 0`(曝險護欄,目前延後)。
- **只 call、單腿**(價差 v0.5+)。
- **選股/造合約切開**:選股=人;造合約=規則(可自動)。
- **append-only state**:`bucket_map`、`iv_history`、tracer 全部只追加,供回測。
- **缺資料 `NO_DATA` 降級,不崩潰**。

## 進度
- [x] **Block 1 宇宙管線** — ETF 成分聯集 → 濾可 option → GICS 歸桶 + refine(append-only)。純邏輯已測。
- [ ] Block 1.5 — 接真 ETF 持股 CSV(取代 seed 清單)。
- [x] **Block 2 — 雙透鏡** — BSM 自算 Greeks + IV 反解 + 實現波動 + percentile 自舉。純數學已測(對照教科書值)。
- [x] **Block 2.5 — 真 T-bill 利率 + edge 閘基準改良** — `rates.py` 按天期挑 ^IRX/^FVX;edge 閘改「IV 自身歷史 percentile 優先、ratio 後備」;IV 自舉開始收樣本(append-only)。純邏輯已測,Colab 驗證待跑。
- [x] **Block 3 — 路由器 + 造合約** — 論點時鐘路由(帶日期催化劑→凸性、無→槓桿)+ 條件式單腿 call 合約卡(`router.py`)。純邏輯已測,Colab 驗證待跑;T1 軟催化劑與 tier_map 待補。
- [x] **Block 4 — 催化劑 helper** — `catalysts.py` 標時鐘(最近未來事件 → T-N),只呈現不裁決;遠期事件標注不砍。
- [x] **Block 5 — shadow tracer** — `tracer.py` collect_only:收掃描紀錄 → T+5/10/20 到期回填 → 雙向報表(存活者放對沒/被排除者砍錯沒)。閾值凍結,min_samples 30 前不解鎖,解鎖後也人工拍板。

## 沙盒 vs Colab 分工
純邏輯(聯集、歸桶、append-only)在任何環境可跑並有測試。
**live 抓取(yfinance option chain、ETF 持股)需要能連 Yahoo/發行商的環境** → 用 Colab 或本地。

## 跑法
```bash
pip install -r requirements.txt

# 純邏輯測試(離線可跑)
python -m pytest tests/ -v

# Block 1 live 驗證(需 Colab / 本地,能連 Yahoo)
python notebooks/colab_verify_block1.py

# Block 2–5 live 驗證(同上;或由 nightly-live Action 自動跑)
python notebooks/colab_verify_block2.py
```

## 看結果
**每晚掃描的人讀報告在 [`RADAR.md`](./RADAR.md)**(存活者合約卡、排除理由人話版、
NO_DATA、自舉/tracer 進度),由 nightly Action 自動生成並 commit,不用去翻 Actions log。

## 自動化
- `tests`(push/PR/手動):純邏輯 + 合成資料端到端回歸,不碰網路。
- `nightly-live`(台灣平日 22:00,美股夏令盤中;可手動觸發):跑
  `notebooks/nightly_scan.py` **全宇宙掃描**(seed 20 檔,Block 1.5 後換真 ETF 持股)
  → 每檔:催化劑時鐘 → 路由 → 雙透鏡 → 出卡/排除 → tracer;跑完把
  `RADAR.md` + `state/`(IV 自舉、tracer、bucket_map)自動 commit 回 main。
  冬令要把 cron 改 15:00 UTC。單檔抓取失敗降級 `FETCH_ERROR`,不殺整晚。

`colab_verify_block1.py` 會:
1. dump 每檔 yfinance `industry` 字串 → 校準 `config/gics_map.json`
2. 跑宇宙管線,印出各檔歸桶結果、被濾(無 option)、歸桶失敗清單
3. 再跑一次驗 append-only 沒覆寫

## 目錄
```
config/     config.json + gics_map.json(粗桶)+ refine.json(半導體細桶)
src/ai_radar/  universe.py(Block 1)、state.py(append-only)
notebooks/  colab_verify_block1.py
tests/      純邏輯單元測試
state/      append-only 資料(預設 .gitignore)
```
