# AI Radar 掃描報告

> 2026-07-02T16:01+00:00 · 這是**排除法濾網**:只負責剔掉「不能買/不要買」,留下的交給人判斷。**不是投資建議;要不要出手、出多少,永遠由人決定。**

## 今晚結論

掃描 **18 檔** AI 相關股 → 通過濾網 **2 檔**、排除 **16 檔**、資料缺失 **0 檔**。(宇宙來源:ETF 持股(AIQ:top10、DRAM:top10、SMH:top10、SOXX:top10;18 檔))

以下每檔附「若要動手,規則會挑哪一張合約」——**是條件式答案,不是買進訊號**:

### AAPL(NO_DATA桶)· 事件凸性
- 規則挑的合約:**2026-08-21 到期、履約價 $360 的買權**,一張約 **$69**(報價 $0.69×100)。
- 白話:財報/事件 T-28 天的小額大賠率——股價需漲過 **+17.7%** 才開始賺;若事件把股價推到 **+30%**,光內含價值就是本金的 **55.4 倍**。輸的上限就是那一張的錢。

### AVGO(加速器桶)· 長期槓桿
- 規則挑的合約:**2028-12-15 到期、履約價 $350 的買權**,一張約 **$13,380**(報價 $133.8×100)。
- 白話:用約 1.96 倍槓桿參與 AVGO 的長期走勢(深價內、時間站在你這邊較久);股價漲過 **+33.1%** 開始賺。無近期事件時鐘。

## 排除了誰(一句話)

被剔掉的 16 檔:14 檔「沒有夠便宜的樂透型合約」、2 檔「找不到條件合適的長期買權」。明細見下方 Details。

---

## Details(開發者)

- 資料時戳 2026-07-02T16:01+00:00 · 無風險利率 短 3.665% / 長 4.200%(缺→4.50%)
- G0 曝險護欄未啟用(bypass)—— 曝險/地緣左尾自行判斷。

### 存活者技術表(2)

| 標的 | 桶 | 透鏡 | 催化劑 | 合約 | 估權利金 | delta | 倍數 | 損益兩平 | 情境 |
|---|---|---|---|---|---|---|---|---|---|
| AAPL | NO_DATA | convexity | T-28 | 2026-08-21 $360C | $0.69 | 0.057 | 25.29x | +17.7% | 若+30% 內含 55.4× |
| AVGO | 加速器 | leverage | — | 2028-12-15 $350C | $133.8 | 0.72 | 1.96x | +33.1% | — |

### 排除清單(16)

| 標的 | 桶 | 透鏡 | 代碼 | 說明 | 指標 |
|---|---|---|---|---|---|
| AMAT | 設備 | convexity | `CVX_NO_STRIKE` | 無便宜合格價外(權利金上限/OTM 上限/到期窗內全滅) | — |
| AMD | 加速器 | convexity | `CVX_NO_STRIKE` | 無便宜合格價外(權利金上限/OTM 上限/到期窗內全滅) | — |
| CSCO | NO_DATA | convexity | `CVX_NO_STRIKE` | 無便宜合格價外(權利金上限/OTM 上限/到期窗內全滅) | — |
| INTC | 製造 | convexity | `CVX_NO_STRIKE` | 無便宜合格價外(權利金上限/OTM 上限/到期窗內全滅) | — |
| KLAC | 設備 | convexity | `CVX_NO_STRIKE` | 無便宜合格價外(權利金上限/OTM 上限/到期窗內全滅) | — |
| LRCX | 設備 | convexity | `CVX_NO_STRIKE` | 無便宜合格價外(權利金上限/OTM 上限/到期窗內全滅) | — |
| MRVL | 加速器 | convexity | `CVX_NO_STRIKE` | 無便宜合格價外(權利金上限/OTM 上限/到期窗內全滅) | — |
| MU | 記憶體 | leverage | `LEV_NO_DELTA` | 無 delta 落區間的合格 LEAPS | — |
| NVDA | 加速器 | convexity | `CVX_NO_STRIKE` | 無便宜合格價外(權利金上限/OTM 上限/到期窗內全滅) | — |
| NXPI | 半導體 | convexity | `CVX_NO_STRIKE` | 無便宜合格價外(權利金上限/OTM 上限/到期窗內全滅) | — |
| ORCL | 賽馬 | leverage | `LEV_NO_DELTA` | 無 delta 落區間的合格 LEAPS | — |
| QCOM | 半導體 | convexity | `CVX_NO_STRIKE` | 無便宜合格價外(權利金上限/OTM 上限/到期窗內全滅) | — |
| SNDK | NO_DATA | convexity | `CVX_NO_STRIKE` | 無便宜合格價外(權利金上限/OTM 上限/到期窗內全滅) | — |
| STX | NO_DATA | convexity | `CVX_NO_STRIKE` | 無便宜合格價外(權利金上限/OTM 上限/到期窗內全滅) | — |
| TSM | 製造 | convexity | `CVX_NO_STRIKE` | 無便宜合格價外(權利金上限/OTM 上限/到期窗內全滅) | — |
| TXN | 半導體 | convexity | `CVX_NO_STRIKE` | 無便宜合格價外(權利金上限/OTM 上限/到期窗內全滅) | — |

### 需人工處理

- 歸桶未決(粗桶/NO_DATA),請補 config/refine.json:AAPL、CSCO、NXPI、QCOM、SNDK、STX、TXN

### IV percentile 自舉進度

- AAPL:1/60 筆(未滿 → edge 閘用 ratio 後備)
- AMAT:1/60 筆(未滿 → edge 閘用 ratio 後備)
- AMD:1/60 筆(未滿 → edge 閘用 ratio 後備)
- AMZN:1/60 筆(未滿 → edge 閘用 ratio 後備)
- ASML:1/60 筆(未滿 → edge 閘用 ratio 後備)
- AVGO:1/60 筆(未滿 → edge 閘用 ratio 後備)
- CEG:1/60 筆(未滿 → edge 閘用 ratio 後備)
- CSCO:1/60 筆(未滿 → edge 閘用 ratio 後備)
- GEV:1/60 筆(未滿 → edge 閘用 ratio 後備)
- GOOGL:1/60 筆(未滿 → edge 閘用 ratio 後備)
- INTC:1/60 筆(未滿 → edge 閘用 ratio 後備)
- KLAC:1/60 筆(未滿 → edge 閘用 ratio 後備)
- LRCX:1/60 筆(未滿 → edge 閘用 ratio 後備)
- META:1/60 筆(未滿 → edge 閘用 ratio 後備)
- MRVL:1/60 筆(未滿 → edge 閘用 ratio 後備)
- MSFT:1/60 筆(未滿 → edge 閘用 ratio 後備)
- MU:1/60 筆(未滿 → edge 閘用 ratio 後備)
- NVDA:1/60 筆(未滿 → edge 閘用 ratio 後備)
- NXPI:1/60 筆(未滿 → edge 閘用 ratio 後備)
- ORCL:1/60 筆(未滿 → edge 閘用 ratio 後備)
- PLTR:1/60 筆(未滿 → edge 閘用 ratio 後備)
- QCOM:1/60 筆(未滿 → edge 閘用 ratio 後備)
- SNDK:1/60 筆(未滿 → edge 閘用 ratio 後備)
- STX:1/60 筆(未滿 → edge 閘用 ratio 後備)
- TSM:1/60 筆(未滿 → edge 閘用 ratio 後備)
- TXN:1/60 筆(未滿 → edge 閘用 ratio 後備)
- VST:1/60 筆(未滿 → edge 閘用 ratio 後備)

### shadow tracer(collect_only)

- 掃描累計 44 筆、outcome 回填 0 筆
- 調參解鎖:否(需 outcome ≥30,解鎖後仍人工週審拍板)

---
*由 nightly-live Action 自動生成(`src/ai_radar/report.py`);歷史紀錄見 `state/tracer.jsonl`。*
