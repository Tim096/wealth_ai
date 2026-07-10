# Planner system prompt v2(大改版)

## Trigger

使用者要求:「大幅度更新 prompt,把我們上面大幅度美化後的能力更新進去」。原 v1 prompt 是 Agent Mode 初版寫的,只有 5 條規則,未反映後續實作與實測學到的東西(download、decoy、modal、SPA、YouTube 真實 run 的行為)。

## Scoring Criteria

- AI 協作品質:prompt 演進有紀錄、可對照
- 失敗處理:把實測看到的失敗模式(重複無效 click、SPA 誤判、decoy)寫進 prompt 預防
- 誠實邊界:done/give_up 的誠實準則、能力邊界明示

## Prompt(v2 全文)

見 `packages/browser_agent/planner.py::_SYSTEM`(單一事實來源,不在此複製以免漂移)。

## v1 → v2 的重點差異

| 面向 | v1 | v2 |
|---|---|---|
| 結構 | 5 條混列規則 | 分節:OUTPUT / CHOOSING ELEMENTS / PLAYBOOK / PROGRESS DISCIPLINE / HONESTY |
| download | 一句帶過 | 完整:用 download action、檔案落地會被驗證、控制項不可見先導航 |
| 元素選擇 | 「避開 decoy」 | 明確用 tag/role/type/id/label 全部權衡;偏好 type=submit;列出 decoy/fake/ad/promo/login/cookie 陷阱 |
| modal | 無 | 「consent/cookie 擋住先關掉再繼續」(實測 YouTube 需要) |
| SPA | 無 | 「URL/內容可能已變且無 full reload,先讀當前狀態再行動」(實測 YouTube /watch 判定經驗) |
| 迴圈紀律 | 無 | 「檢查 ACTIONS SO FAR,同樣失敗不得重複,要換策略」;每回合一動作、不加無關探索 |
| done 誠實性 | 「看起來滿足」 | 「當前狀態實際滿足(可見文字/URL/已完成下載),不是預期會變成真」+ 明示 verifier 才是裁判 |
| 邊界 | 無 | 永不輸入憑證/個資/付款、不購買訂閱送出;明講 guard 會拒絕 |
| 語言 | 無 | 任務可中可英,reason 跟隨任務語言,fill 值照原文 |

## AI Output Summary

v2 寫入 planner.py;93 tests 不變全過(prompt 內容不影響結構化測試);gateway 的 output schema 不變(action enum 已含 download)。

## Human / PM Decision

使用者主動要求本次更新;內容由 AI 依實測經驗擬定。

## Reason

prompt 是 Agent Mode 的行為核心;實測(YouTube run、下載功能、decoy mock site)暴露的每個行為模式都應固化進 prompt,而不是留在 AI 的記憶裡。成本考量:v2 約 450 tokens/step,對每步 LLM call 是可接受的固定開銷。

## Resulting Change

- `packages/browser_agent/planner.py::_SYSTEM`(v2)
- 本紀錄;commit: docs(browser): planner system prompt v2
