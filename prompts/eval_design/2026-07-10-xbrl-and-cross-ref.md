# Cross-reference-index 處理 + XBRL 獨立驗證

## Trigger

使用者轉述主管對**其他人選作業**的回饋(反推評分重點):
- SEC status 不是全 item 可信、需探討「如何確保 status 可信」
- INTC FY2019/FY2020 Item 14 被標 extracted/ok,實際只是短連結/摘要
- 好作業有 char_range/status/confidence/provenance、失敗會標 needs_review、文件列 Intel/GE 為 unsupported class
- 主要缺點:Intel filing 沒完成核心任務,只抓到短 cross-reference/index 片段
- Browser Agent 在非 Wikipedia 網站不穩;10-K 在 Intel/Citi 章節邊界有問題
- **要避免並全面超越**

## Scoring Criteria

正確性驗證、失敗處理、誠實邊界、可觀測性、系統性思考。

## Prompt / 決策

AI 自主判斷,分兩線:

1. **實測 Intel/Citi**(不是讀 code 猜)。發現 Intel = 正文在前段用無 Item 前綴標題、正式 Item 索引在文末指向年報頁碼;Citi = 索引寫成「1A.Risk Factors49-62」完全無「Item」。兩者皆 cross-reference-index filing class。
2. **決定不做脆弱的正文還原**:Intel 正文無 emphasis 標記、標題重複當頁首,title-based 抽取會出錯。**錯的正文比誠實的指標更糟**(違反主管最看重的 trustworthy status)。改為:偵測 filing class + 誠實標 incorporated_by_reference/needs_review。
3. **加獨立 oracle 回答「如何確保 status 可信」**:XBRL companyfacts cross-check Item 8。非 LLM,對照 SEC 自己的結構化數字。

## AI Output Summary

- `cross_ref.py`:偵測 cross-reference-index(群聚 + 頁碼/極小行距 + 群聚外無正文),`scan_bare_index` 處理 Citi 無前綴。INTC FY2019/2020/2025 + Citi 全部正確歸類,Item 14 變 needs_review 指標。
- `xbrl.py` + `certify.py`:11 家 sweep,7 certified / 3 contradicted,與 pipeline 分類零分歧。
- ItemSegment 加 `provenance` / `needs_review` / `xbrl_check`(對齊好作業揭露的欄位)。
- 52 tests。

## Human / PM Decision

AI 自主(PM 授權)。策略對照主管回饋:避免「Item 14 標 ok」的錯、超越「只標 unsupported」到「自動偵測 + XBRL 認證」。

## Reason

主管最看重「驗證能力」與「trustworthy status」。四層防禦(三態 / 對抗式稽核 / XBRL oracle / provenance)直接回應,且明確不出貨脆弱正文以維持可信度。

## Resulting Change

- packages/sec_core/cross_ref.py, xbrl.py, items.py, pipeline.py
- tools/certify.py, tests/test_cross_ref.py, test_xbrl.py
- docs/supported_and_unsupported.md, failure_gallery.md(FG-SEC-005), insights_and_directions.md, eval_report.md
- commits:feat(sec): detect cross-reference-index filings;feat(sec): add XBRL cross-validation oracle
