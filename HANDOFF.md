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
  notebooks/
    colab_verify_block1.py      Block 1 live 驗證(需 Colab)
    colab_verify_block2.py      Block 2 live 驗證(需 Colab,含診斷)
  tests/
    test_universe.py            Block 1 純邏輯
    test_universe_real.py       用真實 industry 字串鎖住 23 檔歸桶
    test_bsm_lenses.py          Block 2 數學 + 透鏡
  .github/workflows/test.yml    CI 只跑純邏輯測試(不碰 live)
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
- **Block 1.5**:接真 ETF 持股 CSV(發行商每日公布,免費;各家 URL 格式不一、會改版,是髒活)。同時處理「半導體粗桶 limbo」——不在 refine 的半導體個股會卡在粗桶「半導體」(非權重桶),要輸出「需人工補 refine」提醒清單。
- **賽馬 T1/T2 tier_map**:yfinance 分不出 PLTR(T2)vs MSFT/ORCL(T1,都是 "Software - Infrastructure")→ 需手動 tier_map(像 refine)。破壞線**按名不按桶**(賽馬賭哪匹馬贏,是個股特有的事)。
- **Block 3**:造合約 + **路由器**。路由靠**論點時鐘**:某檔現在有沒有帶日期的催化劑(財報/合約報價/發表)→ 有進凸性透鏡、沒有進槓桿透鏡。把兩透鏡輸出組裝成 spec §7 那張條件式合約卡。
- **Block 4**:催化劑 helper(財報/事件日,只呈現不裁決;餵路由器 + 餵人看 T-N 天)。
- **Block 5**:shadow tracer(先 collect_only,回填 T+5/10/20,雙向檢查存活者放對沒/被排除者砍錯沒;min_samples 30 且人工週審後才**建議**調參,不自動改 config)。
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
