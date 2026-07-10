# Rejected: Intel/Citi 正文用 title-based section 抽取還原

## Trigger

實測 Intel/Citi(cross-reference-index filing)後,AI 考慮的一個方案:既然正文其實在同一份文件的前段(以「Risk Factors」「Management's Discussion and Analysis」等**無 Item 前綴**標題),就用 canonical-title 搜尋這些 section heading,把真正 span 接回對應 item——讓 Intel/Citi 也「完成核心任務」。

## Scoring Criteria

- 正確性驗證:抽出的正文是否可信
- 誠實邊界:錯的正文 vs 誠實的指標,何者傷害小
- 失敗處理:不確定時的正確行為

## Prompt(被評估的設計)

「對 cross_reference_index filing,對每個 item 用 canonical title 當關鍵字,在文件正文(index 區塊外)找 emphasis/heading 命中的 section,取到下一個 section 為 span,還原正文。」

## AI Output Summary(為何評估後拒絕)

實測 Intel FY2025 後拒絕當作出貨路徑,證據:

1. **無 emphasis 標記**:Intel 正文的 section 標題 `emph=0.00`(不是 bold/heading tag),DOM heading 偵測完全失效。
2. **標題重複當頁首**:「Risk Factors」在正文出現 15+ 次(每頁頁首),無法用「出現即 section start」定位。
3. **會產生錯的正文**:上述兩點導致 title-based 抽取時對時錯,而**錯的正文比誠實的指標更糟**——直接違反主管最看重的 trustworthy status。

## Human / PM Decision

拒絕出貨。改為:偵測 filing class + 誠實標 `incorporated_by_reference` / `needs_review`,並保留 page-range 指標。正文還原改用 **page-anchor resolution**(跟著頁碼進 annual-report exhibit)當 roadmap,不用脆弱的 title 猜測。

## Reason

SPEC 1.1「正確性驗證」與「誠實邊界」優先於「完成度看起來高」。這正是主管回饋裡「別的作業只抓到片段卻標 ok」的反面教材——寧可誠實不完整,不要自信地錯。

## Resulting Change

- 採用 `sec_core/cross_ref.py`(偵測 + 誠實指標),**不做** title-based 正文抽取。
- 決策紀錄亦見 `prompts/eval_design/2026-07-10-xbrl-and-cross-ref.md`;此檔將其提升為 first-class rejected design。
