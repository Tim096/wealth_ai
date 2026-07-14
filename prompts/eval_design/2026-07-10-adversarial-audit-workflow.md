# 對抗式稽核設計

> **Record type:** Derived decision record

## Trigger

Synthetic fixtures 與三家公司 smoke test 通過後，下一步是主動證偽 real-filing 輸出，而不是相信自報 pass rate。

## Scoring Criteria

- 正確性驗證:evidence-backed,不是 AI 自述成功
- 評估紀律:held-out + 失敗案例
- 失敗處理:silent failure 的系統性偵測
- AI 協作品質:AI 驗證 AI 的 harness 設計

## Prompt summary

Multi-agent workflow(`Workflow` tool),兩階段 pipeline:

1. **Audit 階段**:11 家 ticker,每家一個 audit agent。prompt 明確要求檢查:短 pass span、低信心 pass、Item 7/1A 內容真偽(要求 dump 前 40 行確認是真 MD&A/risk factor 而非 TOC/財報洩漏)、Item 8 是否夠大、missing 是否合理。並明確告知「誠實的 missing/incorporated_by_reference/None. 是正確行為,不是 anomaly」以壓低誤報。
2. **Verify 階段**:每個回報的 anomaly 交獨立 verifier agent,prompt 設定為「**盡力反駁這個 anomaly**,預設 is_real=false,除非能引具體證據證明輸出誤導消費者」。這是對抗式設計——讓確認與證偽由不同 agent 做。

schema 強制結構化輸出(StructuredOutput),避免自由文字解析。

## AI Output Summary

**Reproducible evidence:** the repository retains 11-company accession-level records under `data/sec_eval/records/sweep2/` and `sweep3/`. The failure classes are locked by tests including `tests/test_refine.py`, `tests/test_cross_ref.py`, `tests/test_wrapper_reassembly.py`, and accession drift checks in `tests/test_golden_drift.py`.

這些可重跑證據覆蓋三類問題：reference-stub misclassification、trailing-furniture leakage、terminal-runaway spans。

## Decision

採納 accession audit 結果，補上 Intel/Citi 處理、XBRL validation 與上述三類 regression tests。

## Reason

- demo 不可信(SPEC 17)。確認式驗證會漏掉 silent failure;證偽式(對抗)才會逼出來。
- Separate the 11 accession audits, then use an independent verifier stage to challenge reported anomalies.

## Resulting Change

- packages/sec_core/refine.py + boundary.py + confidence.py 修復三大 class
- docs/eval_report.md、docs/failure_gallery.md(FG-SEC-002/003/004)、docs/insights_and_directions.md
- data/sec_eval/records/sweep2/*.json
- 對應 commit:fix(sec): kill three silent-failure classes found by 11-company audit
