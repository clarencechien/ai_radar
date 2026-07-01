# AI Radar

通用 AI 一籃子選擇權過濾器 — **via negativa**:不告訴你買什麼,只 filter 掉不能買/不要買的,存活者留給人判斷。對存活者算「若動手該買哪張 call」的條件式合約卡。

> 家族:`optscnr` / `space_radar` / `delta_radar` / `tw_scanner` / `rainwalker`。
> 完整設計見 [`SPEC.md`](./SPEC.md)(v0.4)。

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
- [ ] Block 3 — 造合約模組(條件式 call 合約卡)。
- [ ] Block 4 — 催化劑 helper。
- [ ] Block 5 — shadow tracer(先 collect_only)。

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
```

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
