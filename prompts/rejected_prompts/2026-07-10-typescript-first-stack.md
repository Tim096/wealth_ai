# Rejected: TypeScript-first monorepo

## Trigger

AI 初始判斷:SPEC 內所有 schema 以 TypeScript 撰寫,故先建 npm workspaces + tsc + vitest 的 TS monorepo。

## Scoring Criteria

- 工程權衡:stack 選擇影響後續所有開發成本
- AI 協作品質:記錄被推翻的決策與理由

## Prompt

(AI 自主決策,無獨立 prompt;決策內容 = 建立 package.json workspaces + tsconfig.base.json + vitest)

## AI Output Summary

已建立 TS 根配置並準備以 TS 實作 packages/*。

## Human / PM Decision

拒絕。PM 確立「環境統一用 repo-local `.venv`,所需套件自行安裝」方針 → 全面改為 Python-first。

## Reason

- `.venv` 指示明確指向 Python 工具鏈
- Python 對 SEC HTML parsing(lxml)與 Playwright 支援成熟
- 單一後端語言降低維護成本;TS 保留給未來前端

## Resulting Change

- 刪除 package.json / tsconfig.base.json(未曾 commit)
- 建立 pyproject.toml + .venv + pydantic schemas
- SPEC 的 TS 欄位名在 pydantic model 中原樣保留,未來前端可直接吃同樣 JSON
