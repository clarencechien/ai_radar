# AI Radar

**📊 [最新掃描報告 → RADAR.md](./RADAR.md)**(每個台灣平日 22:00 自動更新;上半白話、下半技術細節)

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
- [x] **Block 1.5 — 真 ETF 持股** — **Yahoo top10 聯集為正式來源**(本工具獵大象;SMH 前十大=72.5% 資產,長尾歸 `optscnr`),issuer CSV 可選擴充;週更快照進版控;歸桶未決輸出「需人工補 refine」提醒。四檔 ETF 真資料驗證全通。
- [x] **Block 2 — 雙透鏡** — BSM 自算 Greeks + IV 反解 + 實現波動 + percentile 自舉。純數學已測(對照教科書值)。
- [x] **Block 2.5 — 真 T-bill 利率 + edge 閘基準改良** — `rates.py` 按天期挑 ^IRX/^FVX;edge 閘改「IV 自身歷史 percentile 優先、ratio 後備」;IV 自舉每晚收樣。真資料已驗(短 3.67%/長 4.23%)。
- [x] **Block 3 — 造合約 + 雙透鏡並行** — 槓桿透鏡每檔永遠跑(大象預設姿勢)、凸性透鏡在時鐘 ≤60 天時加跑;同檔可同晚出兩張條件式卡,各自追蹤(`router.py`/`scan.py`)。T1 軟催化劑與 tier_map 待補。
- [x] **Block 4 — 催化劑 helper** — `catalysts.py` 標時鐘(最近未來事件 → T-N),只呈現不裁決;遠期事件標注不砍。
- [x] **Block 5 — shadow tracer** — `tracer.py` collect_only:收掃描紀錄 → T+5/10/20 標的回填(校正選股排除)+ **合約卡逐日市價追蹤到期前 21 天**(校正造合約)→ 雙向報表。閾值凍結,min_samples 30 前不解鎖,解鎖後也人工拍板。歷史回測免費資料做不到 → append-only 自建資料集。

## 🔧 需要人工操作的事(照這裡做就好)

### 1. 補歸桶(RADAR.md「需人工處理」列的那幾檔)

編輯 [`config/refine.json`](./config/refine.json),把 ticker 指到桶,例:

```json
{ "SNDK": "記憶體", "STX": "記憶體", "QCOM": "半導體-非AI" }
```

- 可用的權重桶:`製造`、`加速器`、`記憶體`、`設備`、`電力`、`賽馬`。
- 不想讓某檔佔權重桶,就自訂一個非權重桶名(如 `半導體-非AI`),它仍會被中性掃描。
- 待決清單以 [`RADAR.md`](./RADAR.md) Details「需人工處理」段為準(目前:AAPL、CSCO、NXPI、QCOM、SNDK、STX、TXN)。

### 2. 之後的(不急,實作到了會再提示)

- **賽馬 T1/T2 tier_map + 按名破壞線**:哪檔算 T1 雲廠/T2 敘事股、各自的論點破壞指標(SPEC §賽馬分層)。
- **G0 曝險護欄**:你的台積總曝險數字(工作+資產+部位),`config.json → exposure`。
- **11 月美股改冬令**:把 `.github/workflows/nightly-live.yml` 的 cron 從 `0 14` 改 `0 15`。
- **(可選)ETF 全量持股**:宇宙來源正式採 **Yahoo top10 聯集**——本工具獵大象,
  SMH 前十大即佔 72.5% 資產,ETF 長尾小部位歸湯姆熊(`optscnr`)管。若日後想涵蓋
  長尾,把發行商 CSV 直接下載網址貼進 [`config/etf_sources.json`](./config/etf_sources.json)
  的 `csv_url`(VanEck/iShares/GlobalX 基金頁的「Download Holdings」),
  隔晚宇宙來源行顯示 `csv` 即生效;不填就維持 top10,完全沒問題。

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
  `notebooks/nightly_scan.py` **全宇宙掃描**(ETF top10 聯集,週更快照)
  → 每檔:催化劑時鐘 → 路由 → 雙透鏡 → 出卡/排除 → tracer;跑完把
  `RADAR.md` + `state/` 自動 commit 回 main。美股休市日自動跳過。
  冬令要把 cron 改 15:00 UTC。單檔抓取失敗降級 `FETCH_ERROR`,不殺整晚。

`colab_verify_block1.py` 會:
1. dump 每檔 yfinance `industry` 字串 → 校準 `config/gics_map.json`
2. 跑宇宙管線,印出各檔歸桶結果、被濾(無 option)、歸桶失敗清單
3. 再跑一次驗 append-only 沒覆寫

## 目錄
```
RADAR.md       每晚自動生成的人讀報告(上半白話、下半 Details)
config/        config.json(閾值)+ gics_map/refine(歸桶)+ universe_seed/etf_sources(宇宙)
src/ai_radar/  Block 1–5 模組 + scan.py(產線)+ live_yf.py(Yahoo 轉接)+ report.py(報告)
notebooks/     nightly_scan.py(★正式進入點)+ colab_verify_block1/2.py(開發驗證)
tests/         54 個離線測試(純邏輯 + 合成資料端到端)
state/         append-only;iv_history/tracer/bucket_map/universe 進版控,自舉靠它累積
```
完整檔案地圖與逐檔說明見 [`HANDOFF.md`](./HANDOFF.md) §4。
