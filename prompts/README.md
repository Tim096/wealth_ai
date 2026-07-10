# Prompt Logs

依 SPEC 第 10 節:任何影響設計、程式、eval、文件、修復的 prompt 都必須記錄——不論來自使用者還是 AI 自主產生。

## 目錄

| 目錄 | 內容 |
|---|---|
| `browser_agent/` | planner / repair / capability routing prompts |
| `sec_extractor/` | boundary adjudicator prompts |
| `eval_design/` | eval set 設計 prompts |
| `failure_triage/` | failure 診斷 prompts |
| `rejected_prompts/` | 被拒絕的設計與其理由 |
| `project/` | 專案層級決策 prompts(架構、stack、流程) |

## 格式

每個檔案依 SPEC 10.2:Trigger / Scoring Criteria / Prompt / AI Output Summary / Human-PM Decision / Reason / Resulting Change。

命名:`YYYY-MM-DD-short-slug.md`。
