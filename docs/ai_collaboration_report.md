# AI Collaboration Report

> SPEC 14.3。本專案由 AI coding agent 在 PM 授權下自主開發,以下如實記錄 AI 用在哪、不被允許做什麼、被採納與被拒絕的例子、如何主動 commit/push、如何對照評分標準工作。

## AI 用在哪些地方

| 用途 | 說明 |
|---|---|
| 架構與 schema 設計 | packages/* 全部 pydantic schema、不變量的 code-level 強制 |
| 確定性 pipeline 實作 | SEC normalize/headings/toc/boundary/fetcher/resolver/main_doc(無 LLM) |
| 對抗式稽核 harness | 56-agent workflow 稽核 11 家真實 10-K,證偽自報 pass rate |
| 失敗診斷與修復 | JPM cross-ref stub、三大 silent-failure class |
| Eval 設計 | 分層 eval set、合成 fixtures + golden labels、held-out |
| 文件與 prompt log | 全部 docs/ 與 prompts/ |

## AI 沒有被允許做的事(硬邊界)

- **不向使用者/主管索取 API key**(資安)。SEC 走公開 EDGAR;LLM 主路徑 $0。
- **LLM 不產生 filing text**:所有 item text 是 offset-exact source span;LLM 只在 ambiguous boundary 當裁判,且高信心裁決必須附 exact quote(schema validator 強制)。
- **LLM 不輸出任意 browser code**:只輸出 schema 驗證過的 action JSON。
- **缺證據不得標 success**:三態 verdict 結構上讓 unknown 不能升級成 pass。

## AI 建議被採納的例子

- 對抗式稽核 harness(自主提出並執行)→ 抓到 15 個 silent failure。
- Python-first + repo-local .venv(使用者指示後,AI 主動移除已建的 TS 配置並記錄為 rejected)。
- 細粒度 commit/push(使用者指示後,AI 改變 commit 粒度並補記已 squash 的修復)。

## AI 建議被拒絕 / 修正的例子

- **TypeScript-first stack**(AI 初始判斷)→ 使用者「All env use .venv」推翻 → 改 Python。記錄於 `prompts/rejected_prompts/2026-07-10-typescript-first-stack.md`。
- 對抗式稽核回報的 **12 個 anomaly 被驗證層反駁**(NVDA Item 8「honest pass」等)——AI 的稽核 agent 誤報,被 AI 的驗證 agent 擋下。這是 AI 內部的 reject,不是全盤接受自己的產出。

## AI 如何主動 commit / push

不等使用者說「commit」。依 SPEC 11 與使用者「每次錯誤/嘗試/階段/自我指令都 commit+push」的指示:每個可驗證單位一個 commit,message 用 conventional 格式,push 前跑 pytest。失敗嘗試(如 `exec(open())` prefetch 炸掉、heredoc 在 PowerShell 失效)也進 prompt log,不藏。

## AI 如何對照評分標準工作

每個改動自問:對應哪個評分項?有 evidence 嗎?有 verifier 嗎?有 eval 嗎?有 failure case 嗎?會不會 silent failure?——三大 silent-failure class 的修復,就是「會不會 silent failure」這一問的直接產物:先用對抗式稽核逼出來,再修,再用新 test 鎖住,再誠實更新 metrics(pass rate 下降但正確性上升)。
