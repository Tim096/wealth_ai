# Prompt Logs

依 SPEC 第 10 節:任何影響設計、程式、eval、文件、修復的 prompt 都必須記錄——不論來自使用者還是 AI 自主產生。

## 目錄

| 目錄 | 內容 |
|---|---|
| `browser_agent/` | browser agent 設計 / repair / capability 決策 |
| `eval_design/` | eval set 設計、對抗式稽核、XBRL 決策 |
| `failure_triage/` | failure 診斷(如 JPM cross-ref stub) |
| `rejected_prompts/` | 被拒絕的設計與理由(TS-first stack、vision-model repair) |
| `project/` | 專案層級決策(SPEC 導入、commit 粒度) |

> `sec_extractor/` 的 boundary/adjudicator 決策目前併在 `eval_design/` 與 `failure_triage/`(SEC 尚未觸發 LLM adjudicator);待 adjudicator 實際啟用再獨立成目錄。

## 格式

每個檔案依 SPEC 10.2:Trigger / Scoring Criteria / Prompt / AI Output Summary / Human-PM Decision / Reason / Resulting Change。

命名:`YYYY-MM-DD-short-slug.md`。
