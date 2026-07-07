# AI Radar — 通用 AI 一籃子選擇權過濾器 · Spec v0.4

> 家族定位:延續 `optscnr` / `space_radar` / `delta_radar` / `tw_scanner` / `rainwalker` 的工程慣例。

### Changelog v0.3 → v0.4
- **§1 自動歸桶**:GICS 自動分桶 + append-only,含 GICS 分不出的半導體子桶 refine 層。
- ETF 成分**每週**更新。
- **G0 曝險護欄延後**(算客製化,下一版);v0.4 維持 bypass。
- 造合約**只單腿 call**,價差確定延後。
- **§賽馬分層**:賽馬桶拆子群/子層,規則可各異。
- **§8 tracer 先收集不調參**:啟動即凍結閾值,純收數據對準,不過早調。

---

## 0. 定位:via negativa 中性過濾器

scanner 中性、笨。照掃整個宇宙,只輸出「哪些被 filter 掉、為什麼」;存活者留給人看,對存活者算「若動手該買哪張 call」的條件式合約卡。扣板機永遠是人(第三層)。**個人判斷只住 G0,不進 scanner 邏輯。**

---

## 1. 標的宇宙:抓 ETF 成分 + 自動歸桶(v0.4)

### 1.1 來源(免費,每週更新)
- 發行商每日公布持股 CSV:`AIQ`(Global X)、`SMH`(VanEck)、`SOXX`(iShares)、`DRAM`(Roundhill)。
- **抓取頻率:每週**(rebalance 慢,每日多餘)。
- 聯集 → 濾掉無流動美股 option 的(自動剔除三星等)。
- MSFT/ORCL/PLTR 等自然從 AIQ 流入,不手加。

### 1.2 自動歸桶(GICS + append-only)
新 ticker 出現 → 查 GICS sub-industry → 依 `gics_to_bucket` 映射 → **append 進 `bucket_map` state**。

- **append-only**:已歸桶的不覆寫(穩定、可審計);只把新 ticker 追加。手動修正 = 追加一筆 refine,不改舊的。
- **GICS 的先天限制(要誠實面對)**:GICS 能分「半導體 / 半導體設備 / 軟體 / 公用事業」,但**分不出加速器 vs 記憶體 vs 製造**(全是 Semiconductors)。所以:
  - GICS 給**粗桶**:半導體、設備、軟體(賽馬)、公用事業(電力)。
  - 一層薄 `refine_override`(也 append-only)處理半導體內的細分:`MU→記憶體`、`TSM→製造`、`NVDA/AMD/AVGO→加速器`。這層小、穩定、少數幾檔,人工追加一次就長期有效。
- 桶只影響再平衡權重與路由傾向,**不影響 filter 中性**。

| 粗桶(GICS 自動) | refine 細桶 | 典型成分 |
|---|---|---|
| 半導體 | 製造 / 加速器 / 記憶體 | TSM·INTC / NVDA·AMD·AVGO·MRVL / MU |
| 半導體設備 | 設備 | ASML·AMAT·LRCX·KLAC |
| 公用事業·電力 | 電力/基建 | VST·CEG·GEV |
| 軟體·網路 | 賽馬(見 §賽馬分層) | GOOGL·MSFT·META·AMZN·ORCL·PLTR |
| — | ETF 代理 | SMH·SOXX·DRAM |

---

## 2. 架構:三閘門 → 雙透鏡 → 造合約(只單腿 call)

```
ETF 成分聯集(週更) → 濾可 option → 自動歸桶 → 宇宙
   │
   ├─ Gate 0  個人曝險護欄（唯一個人判斷；v0.4 bypass，延後實作）
   ├─ Gate 1  流動性（硬）
   ├─ Gate 2  論點破壞線（軟）
   │
   ├─ 雙透鏡（中性）
   │    ├─【槓桿透鏡】低IV·高delta·長天期 call
   │    └─【凸性透鏡】帶日期催化劑·事件IV便宜·價外 call
   │
   ├─ 催化劑 helper（標時鐘）
   └─ 造合約模組 → 條件式單腿 call 合約卡
```

---

## 3. 排除規則

### 3.1 硬性(自動)
`G0_EXPOSURE`(bypass·延後) / `G1_LIQUIDITY` / `LEV_IV_HIGH`(§5 自舉) / `LEV_NO_DELTA` / `CVX_IV_PRICED` / `CVX_NO_STRIKE`

### 3.2 軟性(需外部查核)
`G2_THESIS_BROKEN` / `CVX_SOFT_CATALYST` / `CVX_EARNINGS_NEAR` / `BUCKET_FULL`

### 3.3 永久人工
催化劑持續性、扣不扣板機。

> 透鏡不含任何標的別名單;台積能不能出卡純由 G0 決定,G0 延後 = v0.4 台積被中性掃出、可能出卡,你的眼睛是那道閘。

---

## 賽馬分層(v0.4 新增)

賽馬桶不是鐵板一塊——裡面是很不同的動物,規則要分層。

### 子層定義
| 子層 | 成分 | 性質 | 預設工具 |
|---|---|---|---|
| **T1 超大型雲廠** | MSFT, AMZN, GOOGL, META, ORCL | 半收費員半賽馬(它們**既是** AI capex 買家**也是**應用層玩家);盯太緊、重定價慢而軟 | 偏槓桿;凸性 edge 薄,只在真有帶日期催化劑時 |
| **T2 高 beta 敘事股** | PLTR(及日後進宇宙的同類) | 純賽馬;高本益比、敘事驅動;重定價波動大 | 凸性潛力較厚,但爆掉風險高;需更緊部位紀律 |

### 規則差異(掛在子層上,不掛整桶)
- **凸性 edge 閘 `cvx_iv_ratio_max` 子層可各設**:T1 幾乎給不出 edge(定價太滿)→ 閘更嚴;T2 較常出現錯價 → 閘可較鬆。
- **論點破壞線一律「按名」不按桶**:賽馬賭的是「哪匹馬贏」,是**個股特有**的事,每檔各寫一條(例:ORCL 雲端 backlog 成長率、PLTR 商業客戶數/估值倍數)。
- **軟催化劑規則**:T1 的重定價多是漸進(GOOGL 型)→ 套 `CVX_SOFT_CATALYST`(只長天期微價外 + 強制破壞線);T2 常有較硬的催化劑 → 未必套。
- 具體閾值**留 tracer 收集後校準**,v0.4 先給結構,不寫死數字。

---

## 4. TSM 的處理(v0.4:延後,維持中性)

G0 曝險護欄**算客製化,延後到下一版**。v0.4 維持 bypass:

- TSM 跟所有標的一樣被中性掃,可能出槓桿卡,輸出誠實標記「G0 未啟用,地緣左尾需你自己判斷」。
- G0 之後實作時「一旦開就常開」;啟用後 TSM 回排除清單。
- put/對沖左尾:移出範圍(只 call)。

---

## 5. 資料層:免費做得到

### 5.1 免費堆疊
yfinance(chain + OHLC + `earnings_dates`)、ETF 週更 CSV、Greeks 自算 BSM、實現波動自算;備援 Finnhub/Polygon。

### 5.2 IV percentile 自舉
歷史 IV 是唯一付費缺口 → append-only `iv_history` 每次追加當日 ATM IV;< `iv_percentile_min_history_days`(60)前用 `IV÷實現波動` 代理,累積夠自動啟用。

### 5.3 caveats
yfinance 非官方、延遲、可能壞 → `NO_DATA` 降級不崩潰。EOD 氣象站,延遲夠用。

---

## 6. 選股/造合約切開 + 造合約(只單腿 call)

| | 誰決定 | 自動? |
|---|---|---|
| 選股(哪檔·要不要動手) | 人 | ❌ |
| 造合約(哪張 strike/expiry) | 規則 | ✅ |

- **槓桿透鏡**:DTE>門檻 → delta∈區間 → 每單位 delta 時間價值最低 → 出卡。
- **凸性透鏡**:到期剛過催化劑 → 便宜價外 → 過 IV÷實現波動 edge 閘 → gamma/權利金最高 → 出卡。
- **只單腿 call**;價差便宜化凸性**確定延後**(v0.5+ 再議)。
- Google/T1 軟催化劑:只長天期微價外,缺破壞線不出卡。
- 卡欄位:標的·子層·透鏡·催化劑·到期·strike·估權利金·delta·時間價值·倍數·損益兩平%·資料時戳·⚠️條件式非建議。

### 6.5 催化劑 helper
對存活者標時鐘(財報日/事件日/桶特有訊號),**只呈現不裁決**;餵路由器(帶日期→凸性優先)+ 餵人(卡旁標 T-N 天)。免費 yfinance calendar,抓不到 `NO_DATA`。

---

## 7. 輸出格式
排除清單 + 條件式單腿 call 合約卡(含子層、催化劑 T-N 天、資料時戳);TSM 於 bypass 時誠實標記「G0 未啟用」。永印「過濾器非建議;go/no-go 由你」。

---

## 8. Shadow tracer:先收集,不調參(v0.4)

**啟動階段 = 純收數據對準,凍結所有閾值。** 不過早調,避免拿幾週幾個樣本過擬合。

- **收集**(append-only):存活者、排除者+理由、假設合約卡。
- **回填**:T+5/10/20 標的/選擇權表現。
- **雙向檢查(先只觀察,不動作)**:存活者放對沒、被排除者事後噴沒(false exclusion 率)。
- **調參解鎖條件**:累積樣本 ≥ `tracer.min_samples` 且經人工週度審查後,才**建議**閾值調整(仍人工拍板,不自動改)。在那之前 tracer 只產報表、不碰 config。

---

## 9. 工程慣例
閾值外部化 `config.json` + `--dump-schema`;`NO_DATA` 降級;`state` append-only(`bucket_map` + `iv_history` + tracer);GitHub Actions,背景批次獨立 API key;EOD 節奏,ETF 週更、催化劑日曆、週度再平衡。

---

## 10. config 預設(placeholder)
```jsonc
{
  "universe":  { "etf_sources": ["AIQ","SMH","SOXX","DRAM"], "fetch_cadence": "weekly",
                 "require_us_options": true,
                 "gics_to_bucket": "gics_map.json", "refine_override": "refine.json" },
  "liquidity": { "min_oi": 500, "min_vol": 100, "max_spread_pct": 10 },
  "leverage":  { "lev_iv_pct_max": 40, "lev_delta_lo": 0.70, "lev_delta_hi": 0.85,
                 "lev_dte_min": 365, "lev_pick_metric": "min_extrinsic_per_delta" },
  "convexity": { "cvx_iv_ratio_max": 1.3, "cvx_prem_max_usd": 1.5, "cvx_otm_max_pct": 25,
                 "earn_window_days": 10, "cvx_pick_metric": "max_gamma_per_premium",
                 "target_move_pct": 30,
                 "racehorse_tiers": { "T1": { "cvx_iv_ratio_max": 1.1, "soft_catalyst": true },
                                      "T2": { "cvx_iv_ratio_max": 1.5, "soft_catalyst": false } } },
  "exposure":  { "enabled": false, "tsm_exposure_max_pct": 15, "tsm_current_pct": null }, // 延後
  "data":      { "source": "yfinance", "iv_percentile_min_history_days": 60,
                 "realized_vol_window_days": 20 },
  "catalyst":  { "surface_earnings": true, "lookahead_days": 60 },
  "tracer":    { "horizons_days": [5,10,20], "review_cadence": "weekly",
                 "mode": "collect_only", "min_samples": 30 },  // 先收集不調參
  "buckets":   { "製造": 0, "加速器": 0.30, "記憶體": 0.25,
                 "設備": 0.15, "電力": 0.10, "賽馬": 0.20 }
}
```

---

## 11. 開放問題(v0.5)
1. `gics_to_bucket` 與 `refine_override` 的初始 seed 表要一起定。
2. 賽馬 T1/T2 各自的**按名破壞線**清單(哪些指標、哪裡抓)。
3. G0 曝險客製化:值怎麼估、UI 怎麼填、何時啟用。
4. call spread 便宜化凸性(v0.5+)。
5. tracer 解鎖調參後,閾值調整的幅度上限/步長,避免人工過度反應。
```

---

## 附錄:實作修正紀錄

### v0.4.1(Block 2 真資料驗證後)
- **權利金上限改相對股價**:`cvx_prem_max_usd`(絕對美元)→ `cvx_prem_max_pct`(% of spot)。
  真資料揭露絕對上限在高價股失效:MU $1,154 時無任何 $1.5 call,整個記憶體桶(spec 指定的「唯一天生凸」)被誤殺。相對上限隨股價縮放(1.5% → $1154 約 $17、$200 約 $3)。
- **教訓**:不對「看起來太大/太波動」的資料建 sanity gate。MU $1,154、實現波動 128% 都是真的(AI 記憶體超級循環)。降級只在「資料缺失/無法反解」時觸發,不在「數值超出先驗」時觸發。
- **利率 r 仍固定 0.045**:長天期 LEAPS 的 delta/定價受利率影響,待接真實 T-bill(Block 2.5)。

### v0.4.2(上線版,2026-07-06)
系統已串成產線自主運轉(nightly Action 全宇宙掃描 → `RADAR.md` 報告 + state 自動 commit)。實作層修正與決策:

- **宇宙來源定案:ETF top10 聯集為正式來源**(使用者拍板)。本工具獵大象——SMH 前十大即佔 72.5% 總資產;ETF 長尾小部位是湯姆熊(`optscnr`)的獵場。issuer CSV 全量降為可選擴充。
- **路由退化修正**:每家公司永遠有「下一次財報日」,「有帶日期催化劑→凸性」會退化成全宇宙走凸性、槓桿透鏡變死碼 → 時鐘超過 `catalyst.lookahead_days`(60)視為「現在沒在走」,走槓桿(預設姿勢);遠期時鐘照樣呈現給人。
- **edge 閘雙基準**(§8.3 弱點修正):IV 自身歷史 percentile 優先(`cvx_iv_pct_max`,自舉 ≥60 筆啟用)、不足退用 IV÷實現波動 ratio;拋物線行情灌爆分母時 percentile 基準不受污染。
- **真 T-bill**:^IRX(≤1y)/^FVX(LEAPS)按合約天期挑,缺→config 預設。
- **凸性透鏡 tier 預設修正**:T1/T2 閘是賽馬子層專屬,非賽馬桶走基準閘(原預設誤讓所有桶吃 T1 嚴閘)。
- **價差閘補實作**:`max_spread_pct` 僅在雙邊報價存在時生效(收盤後靠 OI)。
- **chain 層級 NO_DATA**:空 chain / 整鏈 OI=0(Yahoo 時段性)→ `NO_DATA` 非 EXCLUDE;NO_DATA 掃描不進 tracer 回填(沒做判斷,回答不了放對/砍錯)。
- **休市守門**:美股假日(SPY 最近交易日 < 美東今天)整晚跳過,不灌舊資料樣本。
- **合約卡補情境倍數**:`target_move_pct` 接進凸性卡(「若 +30% 內含 N×」,保守只算內含價值)。
- **報告兩段式**:上半外行人(結論/白話卡/排除一句話),下半 Details(技術表/代碼/自舉/tracer)。

### v0.4.3(雙透鏡並行,2026-07-07)
- **路由改雙透鏡並行**(使用者拍板,回到 v0.4 §2「同一檔各看一次」的原意):
  槓桿透鏡**每檔永遠跑**(大象的預設姿勢);凸性透鏡只在論點時鐘「現在在走」
  (催化劑 ≤ `lookahead_days`)時**加跑**。同檔可同晚出兩張條件式卡,tracer 以
  「檔×透鏡」為單位去重、統計與追蹤。
- **改的理由(真資料)**:單透鏡二選一之下,每家公司永遠有下一次財報,財報進
  60 天窗即被路由去凸性再被權利金閘排除——NVDA/AMD 的槓桿視角整季全盲
  (07-02~06 實測);AVGO 07-06 進財報窗後槓桿卡消失。
- **附帶效果**:IV 自舉固定收 LEAPS chain 的 ATM IV(序列天期一致);凸性
  percentile 閘因此是跨期限比較,偏保守——已知限制,若要精確需另收短天期序列。
