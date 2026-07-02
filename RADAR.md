# AI Radar 掃描報告

> 2026-07-02T07:15+00:00 · 這是**排除法濾網**:只負責剔掉「不能買/不要買」,留下的交給人判斷。**不是投資建議;要不要出手、出多少,永遠由人決定。**

## 今晚結論

掃描 **18 檔** AI 相關股 → 通過濾網 **0 檔**、排除 **1 檔**、資料缺失 **17 檔**。(宇宙來源:ETF 持股(AIQ、DRAM、SMH、SOXX;18 檔))

**今晚沒有任何標的通過濾網——「不動作」也是一種結論。**

## 排除了誰(一句話)

被剔掉的 1 檔:1 檔「沒有夠便宜的樂透型合約」。明細見下方 Details。

另有 17 檔今晚**拿不到完整資料**(不是被淘汰),明日自動重試。

---

## Details(開發者)

- 資料時戳 2026-07-02T07:15+00:00 · 無風險利率 短 3.663% / 長 4.130%(缺→4.50%)
- G0 曝險護欄未啟用(bypass)—— 曝險/地緣左尾自行判斷。

### 存活者技術表(0)

(無)

### 排除清單(1)

| 標的 | 桶 | 透鏡 | 代碼 | 說明 | 指標 |
|---|---|---|---|---|---|
| KLAC | 設備 | convexity | `CVX_NO_STRIKE` | 無便宜合格價外(權利金上限/OTM 上限/到期窗內全滅) | — |

### NO_DATA(17)—— 資料缺失,非判斷

- **AAPL**(route=convexity):`LIQ_NO_OI_DATA` —— Yahoo 時段性缺 OI —— 資料缺失非判斷,盤中重跑
- **AMAT**(route=convexity):`LIQ_NO_OI_DATA` —— Yahoo 時段性缺 OI —— 資料缺失非判斷,盤中重跑
- **AMD**(route=convexity):`LIQ_NO_OI_DATA` —— Yahoo 時段性缺 OI —— 資料缺失非判斷,盤中重跑
- **AVGO**(route=convexity):`LIQ_NO_OI_DATA` —— Yahoo 時段性缺 OI —— 資料缺失非判斷,盤中重跑
- **CSCO**(route=convexity):`LIQ_NO_OI_DATA` —— Yahoo 時段性缺 OI —— 資料缺失非判斷,盤中重跑
- **INTC**(route=convexity):`LIQ_NO_OI_DATA` —— Yahoo 時段性缺 OI —— 資料缺失非判斷,盤中重跑
- **LRCX**(route=convexity):`LIQ_NO_OI_DATA` —— Yahoo 時段性缺 OI —— 資料缺失非判斷,盤中重跑
- **MRVL**(route=convexity):`LIQ_NO_OI_DATA` —— Yahoo 時段性缺 OI —— 資料缺失非判斷,盤中重跑
- **MU**(route=convexity):`LIQ_NO_OI_DATA` —— Yahoo 時段性缺 OI —— 資料缺失非判斷,盤中重跑
- **NVDA**(route=convexity):`LIQ_NO_OI_DATA` —— Yahoo 時段性缺 OI —— 資料缺失非判斷,盤中重跑
- **NXPI**(route=convexity):`LIQ_NO_OI_DATA` —— Yahoo 時段性缺 OI —— 資料缺失非判斷,盤中重跑
- **ORCL**(route=convexity):`LIQ_NO_OI_DATA` —— Yahoo 時段性缺 OI —— 資料缺失非判斷,盤中重跑
- **QCOM**(route=convexity):`LIQ_NO_OI_DATA` —— Yahoo 時段性缺 OI —— 資料缺失非判斷,盤中重跑
- **SNDK**(route=convexity):`LIQ_NO_OI_DATA` —— Yahoo 時段性缺 OI —— 資料缺失非判斷,盤中重跑
- **STX**(route=convexity):`LIQ_NO_OI_DATA` —— Yahoo 時段性缺 OI —— 資料缺失非判斷,盤中重跑
- **TSM**(route=convexity):`LIQ_NO_OI_DATA` —— Yahoo 時段性缺 OI —— 資料缺失非判斷,盤中重跑
- **TXN**(route=convexity):`LIQ_NO_OI_DATA` —— Yahoo 時段性缺 OI —— 資料缺失非判斷,盤中重跑

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

- 掃描累計 27 筆、outcome 回填 0 筆
- 調參解鎖:否(需 outcome ≥30,解鎖後仍人工週審拍板)

---
*由 nightly-live Action 自動生成(`src/ai_radar/report.py`);歷史紀錄見 `state/tracer.jsonl`。*
