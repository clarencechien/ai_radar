# AI Radar — Claude Code 交接文件 (HANDOFF)

> 這份文件讓沒參與前面設計對話的 session 能無縫接手。讀完這份 + `SPEC.md` 就夠。
> 回覆一律用**台灣正體中文**(用詞/語法/語感),避免中國大陸用語與翻譯腔。

---

## 0. 一句話定位

**via negativa 中性選擇權過濾器**:不告訴你買什麼,只 filter 掉不能買/不要買的;存活者(未被排除)留給人看,對存活者算「**若**動手該買哪張 call」的條件式合約卡。**扣不扣板機永遠是人。**

## 1. 為什麼存在(設計哲學,別回頭推翻)

- 使用者另有一套「湯姆熊」玩法(repo `optscnr`):買便宜價外 call + 等敘事重定價 + free ride。那是**單軸獵殺器**,適合冷門、會被市場突然重定價的小股。
- AI 權值股(NVDA/台積/大型雲廠)是**大象**:定價太滿、被盯太緊、IV 結構不同 → 湯姆熊玩法相剋(掃出來永遠是「機構場/高價單/低 IV」)。
- 所以 AI Radar 走**雙透鏡分類器**:同一檔用「槓桿」和「凸性」兩個透鏡各看一次,輸出**排除清單**而非買進排名。
- **收費員 vs 賽馬**框架:製造/記憶體是「收費員」(不管誰贏都收過路費)、應用層是「賽馬」(賭哪匹贏)。權重與規則按這個分。

## 2. 七個核心設計決策(釘死,別漂移)

1. **via negativa**:輸出排除理由,不是買進評分。
2. **scanner 中性**:透鏡**不含任何標的別名單**。台積能不能買,純由 `Gate 0`(曝險護欄)決定,不在透鏡裡特判。個人判斷只住 G0 一處。
3. **選股/造合約切開**:選股(哪檔·要不要動手)= 人(第三層);造合約(哪張 strike/expiry)= 規則(可自動)。合約卡永遠印「若買該買哪張,不是該買」。
4. **只 call、單腿**。價差(call spread 便宜化凸性)延後 v0.5+。
5. **append-only state**:`bucket_map` / `iv_history` / tracer 全部只追加不覆寫,供回測與審計。
6. **NO_DATA 降級**:缺資料/無法反解 → 降級不崩潰。但**「數值超出先驗」不建 sanity gate**(慘痛教訓見 §6)。
7. **三層框架**(承 optscnr):純規則自動 → 外部事實查核半自動 → 催化劑持續性 / 扣板機 = 永久人工。

## 3. 已完成(都有離線測試,20 passed)

- **Block 1 宇宙管線** (`src/ai_radar/universe.py`, `state.py`):
  ETF 成分聯集 → 濾可 option → 自動歸桶。歸桶兩層:GICS 粗桶(`config/gics_map.json`,key 對準 yfinance `industry` 字串)+ `refine` 細桶(`config/refine.json`,處理 GICS 分不出的 加速器/記憶體/製造)。全 append-only。
- **Block 2 雙透鏡** (`src/ai_radar/bsm.py`, `volatility.py`, `lenses.py`):
  - `bsm.py`:BSM 封閉解 call 定價 + delta/gamma/vega/theta + IV 反解(bisection)。純 stdlib,對照教科書值驗過。
  - `volatility.py`:實現波動(歷史股價自算)、IV percentile 自舉(樣本 <60 天回 None → 用代理)、event_iv_ratio。
  - `lenses.py`:`leverage_lens`(低IV·高delta·長天期,選每單位 delta 時間價值最低)、`convexity_lens`(帶催化劑·便宜價外·過 IV÷實現波動 edge 閘,選 gamma/權利金最高)。

## 4. 檔案地圖

```
ai_radar/
  SPEC.md                       完整設計(v0.4 + 附錄 v0.4.1 修正)
  README.md                     進度 + 跑法
  HANDOFF.md                    本檔
  config/
    config.json                 所有閾值(見 §7)
    gics_map.json               GICS industry → 粗桶(key 對準 yfinance)
    refine.json                 細桶 override(半導體內分 + ETF + GEV)
  src/ai_radar/
    state.py                    append-only JSONL helpers
    universe.py                 Block 1 宇宙管線(live fetch 用 DI 注入)
    bsm.py                      Block 2 BSM Greeks + IV 反解
    volatility.py               Block 2 實現波動 + IV percentile 自舉
    lenses.py                   Block 2 雙透鏡
    rates.py                    Block 2.5 T-bill 利率(按天期挑,NO_DATA 降級)
    router.py                   Block 3 路由器(論點時鐘)+ 條件式合約卡
    report.py                   人看的 RADAR.md 報告渲染(nightly 自動生成於 root)
    scan.py                     正式進入點純邏輯:掃整個宇宙(fetcher 注入,單檔炸降級)
    etf_holdings.py             Block 1.5 發行商 CSV 解析 + 快照時效(純邏輯)
    live_yf.py                  yfinance live 轉接層(延遲載入,離線 import 不炸)
    catalysts.py                Block 4 催化劑 helper(標時鐘,只呈現不裁決)
    tracer.py                   Block 5 shadow tracer(collect_only + T+N 回填 + 雙向報表)
  notebooks/
    colab_verify_block1.py      Block 1 live 驗證(需 Colab)
    colab_verify_block2.py      Block 2 live 驗證(需 Colab,含診斷;開發除錯用)
    nightly_scan.py             ★ 正式 nightly 進入點:全宇宙掃描 → tracer → RADAR.md
  config/universe_seed.json     過渡期宇宙 seed(Block 1.5 真 ETF 持股後淘汰)
  tests/
    test_universe.py            Block 1 純邏輯
    test_universe_real.py       用真實 industry 字串鎖住 23 檔歸桶
    test_bsm_lenses.py          Block 2 數學 + 透鏡
    test_rates.py               Block 2.5 利率 + IV 序列
    test_router.py              Block 3 路由 + 合約卡 + chain 層級 NO_DATA
    test_catalysts_tracer.py    Block 4 時鐘 + Block 5 收集/回填/報表
  .github/workflows/test.yml    CI 純邏輯+合成 e2e 回歸(push/PR/手動)
  .github/workflows/nightly-live.yml  台灣 22:00 平日夜跑 live 掃描,state 樣本自動 commit 回 main(冬令要改 cron,見檔內註解)
```

## 5. 沙盒 vs Colab 分工(關鍵約束)

- **純邏輯/數學**:任何環境可跑,有 pytest。CI 只跑這些。
- **live 抓取**(yfinance option chain / 股價 / 財報日、ETF 持股 CSV):**需能連 Yahoo / 發行商網域**。開發沙盒連不到這些網域 → 這部分只能在 **Colab 或本地**驗。
- 因此所有 live 相依都用**依賴注入**(fetcher 當參數傳入 `build_universe`),純邏輯才能離線測。

## 6. Block 2 真資料驗證的發現與修正(重要,含教訓)

1. **權利金上限 usd → pct**:原 `cvx_prem_max_usd: 1.5`(絕對美元)在高價股失效——MU 現價 **$1,154**(真的,AI 記憶體超級循環,一年漲約 8 倍),沒有任何 $1.5 的 call,整個記憶體桶(spec 說是「唯一天生凸」的桶)被誤殺。改為 `cvx_prem_max_pct: 1.5`(% of spot,隨股價縮放)。
2. **慘痛教訓——不對「看起來太大/太波動」建 sanity gate**:曾一度想把 $1,154、實現波動 128% 當髒資料擋掉,查證後發現都是真的。**降級只在「資料缺失/無法反解」時觸發,不在「數值超出我的先驗」時觸發。** 對知識截止後的價格尤其別用先驗猜。
3. **lastPrice 後備**:收盤後 bid/ask 常為空 → `build_contracts` 退回 lastPrice。
4. **流動性閘 OI 優先**:LEAPS 日成交量本就低、收盤後 volume=0。改為 **OI 硬門檻、volume 只在 >0 時才生效**(否則靠 OI)。
5. **NaN→int 崩潰**:`int(x or 0)` 對 pandas 的 NaN 無效(NaN 是 truthy)→ 用 `_safe_int()`。
6. **利率 r**:~~固定 0.045~~ → Block 2.5 已接真 T-bill(`rates.py`:^IRX 短率/^FVX 長率按天期挑,抓不到降級回 `risk_free_rate_default`)。
7. **tier 預設值修正**:`convexity_lens` 原預設 `tier="T1"`,讓非賽馬桶(如記憶體 MU)誤吃賽馬 T1 的嚴閘(1.1)。SPEC 明定 T1/T2 閘是賽馬子層專屬 → 預設改 `None`(走基準閘 1.3),只有賽馬桶才傳 tier。
8. **價差閘補實作**:`max_spread_pct` 原本設在 config 但沒人執行。現於 `_passes_liquidity` 實作:**僅在 bid/ask 雙邊報價都存在時才生效**(收盤後報價空 → 跳過,靠 OI),與 OI 優先原則一致。notebook 的 `build_contracts` 已把 bid/ask 傳進合約 dict。
9. **髒合約降級**:iv/mid/dte 缺失或非正的合約直接跳過(`_valid_contract`),不讓 BSM 拋 ValueError 崩潰整個透鏡(承 §2.6 NO_DATA 原則)。

## 7. config 現值與含意 (`config/config.json`)

- `liquidity`: min_oi 500 / min_vol 100(volume 軟門檻)/ max_spread_pct 10
- `leverage`: IV percentile 上限 40、delta 區間 0.70–0.85、DTE 下限 365、挑 min_extrinsic_per_delta
- `convexity`: **cvx_prem_max_pct 1.5(% of spot)**、OTM 上限 25%、edge 閘雙基準(自舉完成→ **cvx_iv_pct_max 60**;不足→ IV÷實現波動閘 1.3)、挑 max_gamma_per_premium;賽馬子層 T1 閘 1.1 / T2 閘 1.5(子層也可各設 cvx_iv_pct_max)
- `exposure`: **enabled false(G0 延後)**、tsm 相關留欄位
- `data`: yfinance、IV percentile 自舉需 60 天、實現波動窗 20 天、**risk_free_rate_default 0.045、rate_tenor_cutoff_days 365**(Block 2.5)
- `tracer`: **mode collect_only**、min_samples 30(先收集不調參)
- `buckets`: 製造 0(TSM 由 G0 管)/ 加速器 .30 / 記憶體 .25 / 設備 .15 / 電力 .10 / 賽馬 .20

## 8. 待驗收:Block 2 收尾(下一步先做這個)

在 Colab 跑 `python notebooks/colab_verify_block2.py`(**挑美股盤中時段**,台灣時間約 21:30 後,bid/ask 才有值),確認三件事:
1. **NVDA** 盤中吐合理 LEAPS:診斷區會印「過 OI 幾張 / delta 落區間幾張 / delta 範圍」。期望挑到 delta 0.70–0.85、eff_leverage ~1.8–2.2x 的一張。
2. **MU** 過凸性透鏡挑了哪張、`iv_realized_ratio` 多少。
3. **edge 閘的已知弱點**:MU 實現波動現在 128%(拋物線灌出來的)。edge 閘 = event_iv ÷ realized_vol,分母太大 → ratio 永遠很低 → 永遠「過閘說便宜」。**這是用趨勢實現波動當基準的先天弱點。** 待改良方向:改用更長窗口實現波動,或改用「IV vs 自己 IV 歷史 percentile」(自舉機制正好給這個),而非 IV vs 近期實現波動。

## 9. Roadmap(建議順序)

- ~~**Block 2.5**:接真 T-bill 利率;edge 閘基準改良(見 §8.3)~~ **已完成(純邏輯已測,Colab 驗證待跑)**:
  - `rates.py`:^IRX(13週)/^FVX(5年)按合約天期挑,NO_DATA 降級回預設。
  - edge 閘改雙基準:IV 自身歷史 percentile 優先(`cvx_iv_pct_max`,不受實現波動失真影響)、歷史不足退用原 ratio 閘。verdict metrics 印 `edge_basis` 標明用了哪個基準。
  - 自舉開始收樣本:notebook 每跑一次(每 ticker 每天一筆)append ATM IV 到 `state/iv_history.jsonl`(`series_by_key` 讀回)。**注意 Colab 環境是暫時的,`state/` 要 commit 回 repo 或存 Drive,樣本才會累積。**
- ~~**Block 1.5**:接真 ETF 持股 CSV~~ **已完成(純邏輯已測,發行商 URL 待首跑驗證)**:
  - `etf_holdings.py`:CSV 解析(容忍 iShares 式前導雜訊、各家欄名)、ticker 正規化(BRK.B→BRK-B、剔現金列)、快照週更時效。
  - 抓取鏈:issuer CSV(可選)→ **yfinance top10(正式主來源)** → 前次快照(`state/universe.jsonl`,進版控)→ `universe_seed.json`。
  - **設計決策(2026-07-05,使用者拍板)**:top10 聯集就是正式宇宙,不是降級——本工具獵大象(SMH 前十大=72.5% 資產),ETF 長尾小部位是湯姆熊(optscnr)的獵場。issuer CSV URL 留在 `etf_sources.json` 當可選擴充,四檔 ETF 的 Yahoo top10 已用真資料驗證全通。
  - 新面孔才做 option 濾網(bucket_map 沒見過的),避免每晚重驗整個宇宙。
  - 「半導體粗桶 limbo」/NO_DATA 歸桶 → RADAR.md Details「需人工處理」段輸出補 refine 提醒。
- **賽馬 T1/T2 tier_map**:yfinance 分不出 PLTR(T2)vs MSFT/ORCL(T1,都是 "Software - Infrastructure")→ 需手動 tier_map(像 refine)。破壞線**按名不按桶**(賽馬賭哪匹馬贏,是個股特有的事)。
- ~~**Block 3**:造合約 + **路由器**~~ **已完成(純邏輯已測,Colab 驗證待跑)**:`router.py`——`route()` 論點時鐘(帶日期催化劑→凸性、無/已過→槓桿)、`build_card()` 組 SPEC §6 合約卡(含損益兩平%、G0 bypass 誠實標記、條件式聲明)、`scan_one()` 單標的走完路由→透鏡→出卡,回傳格式即 tracer 要收的紀錄。**待補**:賽馬 T1 軟催化劑(`CVX_SOFT_CATALYST`,需破壞線基建)與 tier_map(見下)。
- **chain 層級 NO_DATA(修正)**:Colab 真實觀察到 Yahoo 時段性整批缺 OI(同日同 spot,前跑過 OI 250 張、後跑 0 張)→ 空 chain 或全 chain OI=0 時透鏡回 `NO_DATA`(`NO_CONTRACTS` / `LIQ_NO_OI_DATA`)而非 EXCLUDE——資料缺失要降級,不是製造假淘汰(承 §6.2 教訓)。
- ~~**Block 4**:催化劑 helper~~ **已完成(純邏輯已測)**:`catalysts.py`——`next_catalyst()` 挑最近的未來事件(含今天;已過/日期壞 → 無時鐘),`format_clock()` 出 T-N 標記。**lookahead 只標注不裁決**:超過 `catalyst.lookahead_days` 的事件照樣回傳(標 `within_lookahead: false`、印「遠期」),要不要砍遠期時鐘是人的事。live 抓取(yfinance calendar)在 notebook 的 `fetch_earnings_events`。
- ~~**Block 5**:shadow tracer~~ **已完成(純邏輯已測,收集已開始)**:`tracer.py`——`record_scan()` 收 scan_one 紀錄(存活者含假設卡/排除者含理由/NO_DATA 含原因)、`due_backfills()` 算哪些 (scan, T+N) 到期未回填(冪等)、`record_outcome()` 回填標的(+可選選擇權)報酬、`report()` 雙向報表(PASS 組=放對沒、EXCLUDE:code 組=砍錯沒)。**凍結閾值:未達 min_samples 30 前 `tuning_unlocked: false`;達標後也只產報表,人工週審拍板,tracer 永不自動改 config。** state 檔 `state/tracer.jsonl` 已進版控例外,跑完要 commit 才累積。
- **G0 曝險護欄**(客製化,最後做):台積個人總曝險(工作+新台幣資產+部位)超上限就擋;一旦開就常開。put/對沖左尾另議,不在只-call 範圍。

## 10. 開放問題(落地時順手定)

1. `gics_map` / `refine` 的完整 seed(目前夠用,擴宇宙時補)。
2. 賽馬 T1/T2 各自的按名破壞線清單(指標、資料來源)。
3. G0 曝險值怎麼估、UI 怎麼填、何時啟用。
4. tracer 解鎖調參後的調整幅度上限/步長,避免人工過度反應。

## 11. 給接手 session 的第一個動作

```bash
pip install -r requirements.txt
python -m pytest tests/ -v      # 應 20 passed
```
確認綠燈後,依 §8 的 Colab 結果收尾 Block 2,再進 §9 的 Block 3。
使用者會在 Colab 跑 live 驗證並把輸出貼回;純邏輯/數學你可直接在本地寫+測。
