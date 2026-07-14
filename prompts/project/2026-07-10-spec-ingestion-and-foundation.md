# SPEC 導入與平台基礎建設決策

> **Record type:** Derived decision record

## Trigger

`docs/SPEC.md` is the project brief. The first implementation step was choosing the shared reliability layer, stack, and package boundaries.

## Scoring Criteria

- 系統性思考:先建共用 reliability 層,再建兩個 app
- AI 協作品質:本檔案即第一筆 decision log
- 正確性驗證:所有不變量以 code + test 落地,不是文件宣示

## Prompt summary

需求來源：`docs/SPEC.md`。

以 `docs/SPEC.md` 為需求來源，決策紀錄放在 `prompts/`，Python 工具鏈統一使用 repo-local `.venv`。

## AI Output Summary

第一階段(本次)交付:

- Python 3.12 monorepo(repo-local `.venv`),pydantic schemas 對應 SPEC 全部 TS 型別,欄位名一致
- `observability_core`:EvidenceRecord + JSONL EvidenceStore(corrupt record 直接 raise)
- `eval_core`:三態 verdict combinator——缺 evidence 永遠是 unknown,不可能升級成 pass
- `browser_core`:受控 action space(discriminated union,拒絕任意 code)、task contract(強制 ≥1 success condition)、failure taxonomy、selector memory
- `sec_core`:ItemSegment(offset + sha256,LLM 不產生 filing text)、可解釋 confidence、adjudicator guard(高信心無 quote → ValidationError)
- 16 個 tests 全過

## Decision

- Create prompt records alongside implementation changes.
- Replace the initial uncommitted TypeScript-first attempt with Python-first and a repo-local `.venv`.
- 拒絕紀錄:見 `prompts/rejected_prompts/2026-07-10-typescript-first-stack.md`

## Reason

- Python 生態對兩題核心都更強:Playwright for Python、lxml/bs4 for SEC HTML
- pydantic 讓 SPEC 的 schema 不變量(如 adjudicator quote guard)在 validation 層強制,而不是靠約定
- 前端延後決定——現在沒有可視化的資料,先建 UI 是本末倒置

## Resulting Change

- pyproject.toml、packages/*(5 packages)、tests/*(16 tests)
- docs/SPEC.md、docs/architecture.md、prompts/ 結構
- 對應 commits:見本次 push 的 commit history(chore/docs/feat/eval 分次提交)
