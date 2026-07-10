# SPEC 導入與平台基礎建設決策

## Trigger

使用者(PM)交付完整 SPEC(docs/SPEC.md),並授權 AI 自主產生 prompt、commit、push。AI 需決定第一階段建什麼、用什麼 stack。

## Scoring Criteria

- 系統性思考:先建共用 reliability 層,再建兩個 app
- AI 協作品質:本檔案即第一筆 decision log
- 正確性驗證:所有不變量以 code + test 落地,不是文件宣示

## Prompt

(使用者原始 prompt = docs/SPEC.md 全文,加上兩則補充指示)

1. AI 獲授權自主產生 prompt 紀錄,並自主執行 git commit / push(依 SPEC 11–12 判斷時機)。
2. 環境一律使用 repo-local `.venv`,所需套件由 AI 自行安裝。

## AI Output Summary

第一階段(本次)交付:

- Python 3.12 monorepo(repo-local `.venv`),pydantic schemas 對應 SPEC 全部 TS 型別,欄位名一致
- `observability_core`:EvidenceRecord + JSONL EvidenceStore(corrupt record 直接 raise)
- `eval_core`:三態 verdict combinator——缺 evidence 永遠是 unknown,不可能升級成 pass
- `browser_core`:受控 action space(discriminated union,拒絕任意 code)、task contract(強制 ≥1 success condition)、failure taxonomy、selector memory
- `sec_core`:ItemSegment(offset + sha256,LLM 不產生 filing text)、可解釋 confidence、adjudicator guard(高信心無 quote → ValidationError)
- 16 個 tests 全過

## Human / PM Decision

- 採納:AI 自主 commit / push 授權(使用者明示)
- 修改:原本 AI 先建了 TypeScript monorepo(npm workspaces);PM 於開發初期確立「環境統一用 .venv」方針,AI 改為 Python-first,TS 根配置移除(未進 commit history,因為尚未 commit)
- 拒絕紀錄:見 `prompts/rejected_prompts/2026-07-10-typescript-first-stack.md`

## Reason

- Python 生態對兩題核心都更強:Playwright for Python、lxml/bs4 for SEC HTML
- pydantic 讓 SPEC 的 schema 不變量(如 adjudicator quote guard)在 validation 層強制,而不是靠約定
- 前端延後決定——現在沒有可視化的資料,先建 UI 是本末倒置

## Resulting Change

- pyproject.toml、packages/*(5 packages)、tests/*(16 tests)
- docs/SPEC.md、docs/architecture.md、prompts/ 結構
- 對應 commits:見本次 push 的 commit history(chore/docs/feat/eval 分次提交)
