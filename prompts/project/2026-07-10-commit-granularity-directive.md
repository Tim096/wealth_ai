# PM 指令:每次錯誤、每次嘗試、每個階段、每個自我指令都 commit + push

## Trigger

使用者(PM)於 SEC pipeline 開發中補充流程指令。

## Scoring Criteria

- AI 協作品質:commit history 反映真實開發過程,包含失敗與修復
- 失敗處理:錯誤不藏在 pre-commit 修正裡,而是進 history

## Prompt

「我建議每一次的錯誤,每一次的嘗試最好都可以 commit 和 push it 每一個階段也是 每一個對自我的指令也是」

## AI Output Summary

採納,調整為:

1. 每完成一個 pipeline 階段 → commit + push
2. 發現 bug → 先 commit 失敗狀態或以獨立 fix commit 記錄(不再把修復 squash 進原始 commit)
3. AI 自我指令 / 流程決策 → prompts/ log + commit
4. 已發生但被 squash 的兩個 pre-commit 修復,補記於本檔案:
   - `boundary.py`: combined Items-1-and-2 被 sequence filter 誤砍 + 同 start pair 算出零長度 span(修復:combined bypass + min-over-later ends)
   - `toc.py`: dense_cluster 誤判緊跟 TOC 之後的正文 Item 1(修復:要求 cluster 有 ≥2 個後向鄰居)

## Human / PM Decision

採納全部。

## Reason

評審需要看到真實的 try → fail → diagnose → fix 過程;細粒度 push 也讓遠端隨時反映最新狀態。

## Resulting Change

本檔案 + 後續 commit 粒度改變(見 commit history)。
