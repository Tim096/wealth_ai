# AI Coding Test 2026 — Reliability Platform

> 這不是兩個 AI demo。這是一套 AI reliability platform,並用 Browser Agent 與 SEC 10-K Extractor 兩個高難度任務證明它。

**Status: foundation phase(2026-07-10)。** 本 README 只宣稱已存在且可驗證的東西;planned 項目明確標示。

## 系統總覽

| 題目 | 內容 | 狀態 |
|---|---|---|
| 題目一 Browser Agent | capability-aware 瀏覽器自動化:受控 action space、verifier-backed 結果、selector 自我修復 | schemas + invariants 已實作,executor planned |
| 題目二 SEC Extractor | 10-K Item 1–16 結構化抽取:source-exact span、可解釋 confidence、TOC 防禦 | schemas + invariants 已實作,pipeline planned |
| 共用層 | evidence store、三態 verdict、eval case、LLM 成本紀錄 | 已實作,16 tests 通過 |

完整規格:[docs/SPEC.md](docs/SPEC.md)。架構與目前邊界:[docs/architecture.md](docs/architecture.md)。

## 核心原則(已在 code 層強制)

1. **三態判定**:所有結果只能是 `pass` / `fail` / `unknown`。缺 evidence 永遠是 `unknown`,結構上不可能升級成 `pass`(`eval_core/verdict.py`)。
2. **受控 action space**:LLM 只能輸出 schema 驗證過的 action JSON,不能輸出任意 browser code(`browser_core/actions.py`)。
3. **LLM 不產生 filing text**:抽取結果只以 offset + sha256 定址 source exact span;adjudicator 高信心裁決必須附 exact quote,否則 ValidationError(`sec_core/adjudicator.py`)。
4. **可解釋 confidence**:confidence 是具名 component 分數加總,每項附理由(`sec_core/confidence.py`)。

## 如何本機執行

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest        # 目前 16 passed
```

選配依賴:`.[browser]`(Playwright)、`.[sec]`(httpx / lxml / bs4)——對應功能實作後啟用。

## 支援範圍(Browser Agent)

| 類型 | 支援狀態 |
|---|---|
| 公開網站搜尋、多頁導航、資料擷取、公開文件下載 | 支援(planned 實作) |
| 表單填寫 | 部分支援:僅公開、可逆、無登入、無金流 |
| 登入、CAPTCHA、購買/下單、發文/正式表單、付費資料 | **不支援**(SPEC 6.4) |

## SEC 支援輸入

ticker+year / CIK+year / accession number / SEC URL / HTML upload / TXT upload(confidence 較低)。掃描 PDF:`unsupported`。

## 專案結構

```
packages/     observability_core, eval_core, browser_core, sec_core, llm_core(已實作)
tests/        16 tests
docs/         SPEC.md, architecture.md
prompts/      所有影響開發的 prompt + 決策紀錄(含 rejected)
services/     planned
apps/web/     planned(Browser Agent UI / SEC Extractor UI / Eval Dashboard)
data/         planned(eval sets, mock sites, golden labels)
```

## 尚未存在的東西(誠實邊界)

- Live demo URLs:無,前端未開始
- Eval 結果 / 成本延遲數據:無,等 eval runner 有真實 run 後產出 `docs/eval_report.md`、`docs/cost_latency_report.md`
- Failure gallery:無 failure 可展示——第一個真實 failure 出現時建立

## AI 協作方式

所有影響設計的 prompt 與決策(含被拒絕的方案)記錄於 [prompts/](prompts/README.md)。AI 依 SPEC 第 11–12 節自主判斷 commit / push 時機;commit history 反映真實開發順序。
