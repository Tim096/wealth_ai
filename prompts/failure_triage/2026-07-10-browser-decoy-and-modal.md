# Browser failure triage:decoy button + modal 攔截導致修復選錯元素

> **Record type:** Derived decision record

## Trigger

建 mock site v2 後首次跑 killer demo,AI 自主檢查 repair 選了哪個元素——擔心 selector_not_found 的 a11y 修復會選到 decoy button(`#fake-search`,text=「Search」但 onclick 什麼都不做),或被 cookie modal 攔截而誤判。

## Scoring Criteria

- 失敗處理:diagnosis → 正確修復策略
- 正確性驗證:修復後小步驗證,不偽裝成功
- 可觀測性:repair considered candidates 要可檢視

## Prompt summary

「跑 v2 search,dump 每一步的 diagnosis、considered candidates(含分數)、chosen selector。確認:(1) modal 是否先被關掉;(2) submit_button 修復是否選 `#go`(真 submit)而非 `#fake-search`(decoy);(3) verifier 是否看到真實結果。若選到 decoy,調整 `_score_candidate` 的 decoy 過濾。」

## AI Output Summary

檢查 `runs/browser_demo/trace.json`(committed copy:`data/browser_eval/artifacts/killer_demo_trace.json`):

1. modal_blocking 先被偵測並關閉(dismiss_modal step)。
2. submit_button 修復:`#go` score=5.5(tag=button + purpose word + type=submit)勝出;`#fake-search` 因 `_is_decoy`(id 含 "fake")score=−1 被排除。**未選到 decoy。**
3. verifier 看到「results for」+「Widget」→ pass。

結論:decoy 過濾與 diagnosis-driven 修復如預期運作,無需調整;記錄為 FG-BROWSER-001。

## Decision

採用 deterministic fix。現有證據仍偏 mock，real-site generalization 另列 WebArena/WebVoyager roadmap。

## Reason

decoy/modal 是真實網站常見陷阱;若修復盲目選第一個「像按鈕」的元素會靜默點到假按鈕→silent failure。`_is_decoy` + purpose 評分 + 小步驗證三者共同防範。

## Resulting Change

- `packages/browser_agent/repair.py`:`_is_decoy`、`_score_candidate`。
- `docs/failure_gallery.md`:FG-BROWSER-001。
- 證據:`data/browser_eval/artifacts/killer_demo_trace.json`(git-tracked)。
