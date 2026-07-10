# 對抗式稽核 workflow(56 agents)

## Trigger

AI 自主判斷 + 使用者本輪啟用 ultracode。SEC pipeline 通過合成 fixtures 與 3 家 smoke test 後,不能相信自報的 pass rate——需要對真實 filing 做**證偽式**驗證,而非確認式。

## Scoring Criteria

- 正確性驗證:evidence-backed,不是 AI 自述成功
- 評估紀律:held-out + 失敗案例
- 失敗處理:silent failure 的系統性偵測
- AI 協作品質:AI 驗證 AI 的 harness 設計

## Prompt / Harness 設計

Multi-agent workflow(`Workflow` tool),兩階段 pipeline:

1. **Audit 階段**:11 家 ticker,每家一個 audit agent。prompt 明確要求檢查:短 pass span、低信心 pass、Item 7/1A 內容真偽(要求 dump 前 40 行確認是真 MD&A/risk factor 而非 TOC/財報洩漏)、Item 8 是否夠大、missing 是否合理。並明確告知「誠實的 missing/incorporated_by_reference/None. 是正確行為,不是 anomaly」以壓低誤報。
2. **Verify 階段**:每個回報的 anomaly 交獨立 verifier agent,prompt 設定為「**盡力反駁這個 anomaly**,預設 is_real=false,除非能引具體證據證明輸出誤導消費者」。這是對抗式設計——讓確認與證偽由不同 agent 做。

schema 強制結構化輸出(StructuredOutput),避免自由文字解析。

## AI Output Summary

56 agents(54 完成、2 因 StructuredOutput 重試上限失敗)。**31 anomaly 確認、12 反駁。** 反駁層擋掉的多是「這其實是誠實 incorporated_by_reference / None. 行為」的誤報——證明反駁層真的在工作,不是橡皮圖章。

三大確認 class:reference-stub 誤標 pass、trailing furniture 洩漏、terminal runaway(XOM Item 16 = 311K 字、JPM Item 15 = 985K 字)。

## Human / PM Decision

AI 自主執行並依結果修復(PM 授權範圍)。使用者事後給了策略指引(見文末),確認方向正確(Intel/Citi corner case、驗證是最看重的能力、OCR/XBRL 是對的驗證基材)。

## Reason

- demo 不可信(SPEC 17)。確認式驗證會漏掉 silent failure;證偽式(對抗)才會逼出來。
- fan-out 讓 11 家平行稽核,pipeline 讓每個 anomaly 一浮現就驗證,不等 barrier。
- 兩個 StructuredOutput 失敗的 agent 已記錄為已知限制,不影響結論(43 個 anomaly 判定完成)。

## Resulting Change

- packages/sec_core/refine.py + boundary.py + confidence.py 修復三大 class
- docs/eval_report.md、docs/failure_gallery.md(FG-SEC-002/003/004)、docs/insights_and_directions.md
- data/sec_eval/records/sweep2/*.json
- 對應 commit:fix(sec): kill three silent-failure classes found by 11-company audit
