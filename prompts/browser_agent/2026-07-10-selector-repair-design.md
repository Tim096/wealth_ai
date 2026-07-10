# Browser Agent — selector repair 與 capability guard 設計

## Trigger

AI 自主判斷 + 使用者「ultracode do 兩題」。題目一從零開始,需決定:selector 修復怎麼做才穩健、如何避免 silent failure、責任邊界如何強制。

## Scoring Criteria

- 系統性思考:分層(executor/observer/verifier/repair/memory)+ failure taxonomy
- 失敗處理:diagnosis-driven repair,不是 try/catch 重跑
- 正確性驗證:task contract verifier 三態,verifier false-positive rate 可量測
- 誠實邊界:capability boundary 要 code-enforced

## Prompt(AI 自我指令摘要)

「設計一個 capability-aware browser agent:(1) LLM 只輸出受控 action JSON,不跑 code;(2) selector 壞掉時,用 accessibility tree 的候選元素依 purpose 評分修復,避開 decoy;(3) 每個任務轉成 verifier contract,空結果/錯頁不得偽裝成 pass;(4) 責任邊界(login/purchase/submit)用程式擋,不是文件寫寫。用本地 mock site v1→v2 製造 UI 漂移來證明自我修復。」

## AI Output Summary

- `packages/browser_agent/`:executor(Playwright,結構化 outcome)、observer(a11y 候選枚舉)、verifier(三態)、repair(purpose 評分 + decoy 過濾)、memory_store(selector 版本 + repair history)、agent(script→repair 編排)、capability(guard)。
- diagnosis-driven:click_no_effect→press Enter;empty_result→不修成 pass;selector 問題→a11y 搜尋。
- killer demo:v1 pass(0 repair)→ v2 2 repairs still pass;v2-gizmo 0 repair(memory 命中)。
- verifier false-positive rate 0.0(空結果 task 正確 fail)。

## Human / PM Decision

AI 自主(PM 授權)。事後對抗式驗證(16-agent)指出:repair 一開始只記 diagnosis 沒 dispatch、boundary 只在 docs——已於同輪修正(dispatch by failure_type + code-enforced guard)。

## Reason

selector-healing 是既有領域(Healenium),但綁進「三態驗證迴圈 + a11y 定位 + persistent memory」是差異化(見 `docs/prior_art.md`)。responsibility boundary 必須 code-enforced 才能上 production。

## Resulting Change

- packages/browser_agent/*、data/mock_sites/v1|v2、tools/browser_killer_demo.py、tools/browser_eval.py、data/browser_eval/tasks.json
- commits:feat(browser): implement capability-aware agent...;fix(browser): code-enforce capability boundary...
