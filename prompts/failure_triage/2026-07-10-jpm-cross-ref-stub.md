# JPM Item 11 cross-reference stub 誤判 triage

## Trigger

AI 自主判斷:首次真實 EDGAR smoke run(AAPL/JPM/XOM)後逐項檢查輸出,發現 JPM Item 11 span 僅 51 字元卻標 pass。

## Scoring Criteria

- 失敗處理:診斷 → 分類 → 修復 → 記錄
- 正確性驗證:不信任 verifier 表面 pass,主動查 span 內容
- 評估紀律:失敗案例進 failure gallery

## Prompt

(AI 自我指令)「JPM Item 11 span 只有 'Refer to Item 10.'。檢查:(1) 這是 filing 本身如此還是 boundary 錯誤?(2) 若 filing 如此,現有 status 分類是否誠實?(3) Item 16 missing 是真 missing 還是 normalizer 丟失?」

## AI Output Summary

1. Boundary 正確——JPM 真的只寫了一行 cross-reference
2. 但標 `pass` 不誠實:內容實際在 Item 10(其本身 incorporated by reference)
3. Item 16:raw HTML 0 hits,JPM 合法省略選填項 → `missing` 正確

修復:`_CROSS_REF_RE` + body < 600 字元 → `incorporated_by_reference` + warning。

## Human / PM Decision

AI 自主修復(在 PM 授權範圍內),PM 未介入。

## Reason

SPEC 4.1:畫面看起來完成 ≠ 成功。這是 silent failure rate metric 的實際案例。

## Resulting Change

- 初版:packages/sec_core/boundary.py 的 `_CROSS_REF_RE`(commit 892ae0b)。
- **後續(commit 0c46e9d)**:此 regex 被 `sec_core/refine.py::classify_reference_stub`(廣義 reference cue,body < 900)取代並自 boundary.py 移除——現行 code 已無 `_CROSS_REF_RE`。此為誠實的歷史紀錄。
- docs/failure_gallery.md:FG-SEC-001 → 一般化為 FG-SEC-002。
- 對應 commit:fix(sec): classify cross-reference stub bodies as incorporated_by_reference;fix(sec): kill three silent-failure classes found by 11-company audit
