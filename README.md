# AI Coding Test 2026 — Reliability Platform

> 這不是兩個 AI demo。這是一套 AI reliability platform,並用 Browser Agent 與 SEC 10-K Extractor 兩個高難度任務證明它。

**核心命題:AI coding 之後,稀缺的不是「寫得出來」,是「知道自己何時對、何時錯、何時證據不足」。** 本專案把這件事制度化。

## 系統總覽

| 題目 | 內容 | 狀態 |
|---|---|---|
| 題目一 Browser Agent | capability-aware 瀏覽器自動化:受控 action space、task-contract verifier、accessibility-tree selector 自我修復、selector memory | **可執行**:Playwright executor + v1→v2 selector-repair killer demo(`tools/browser_killer_demo.py`) |
| 題目二 SEC Extractor | 10-K Item 1–16 結構化抽取:source-exact span、TOC 防禦、confidence、cross-reference-index(Intel/Citi)、**XBRL 獨立認證** | **可執行**:跑過 11 家真實 10-K + Intel/Citi(`tools/eval_one.py`, `tools/certify.py`) |
| 共用層 | evidence store、三態 verdict、eval case、LLM 成本紀錄 | 已實作 |
| Eval Dashboard | 兩題 eval 結果、XBRL 認證、browser repair trace(真實數據) | `apps/web/eval-dashboard/`,自包含 HTML |

**62 tests 通過**(含真實瀏覽器 integration test)。完整規格:[docs/SPEC.md](docs/SPEC.md)。

## 核心原則(已在 code 層強制,不是文件宣示)

1. **三態判定**:結果只能 `pass` / `fail` / `unknown`。缺 evidence 永遠 `unknown`,結構上不可能升級成 pass(`eval_core/verdict.py`)。
2. **受控 action space**:LLM 只輸出 schema 驗證過的 action JSON,不輸出任意 browser code(`browser_core/actions.py`)。
3. **LLM 不產生 filing text**:抽取結果只以 offset + sha256 定址 source-exact span(`sec_core/items.py`)。
4. **status 可信度四層防禦**:三態 verdict → 對抗式稽核 → **XBRL 獨立 oracle** → provenance/needs_review。見 [docs/supported_and_unsupported.md](docs/supported_and_unsupported.md)。

## Killer demos

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev,sec,browser]"
.venv\Scripts\python -m playwright install chromium
$env:SEC_EDGAR_USER_AGENT = "your-name your@email"

.venv\Scripts\python -m pytest                          # 62 passed
.venv\Scripts\python tools\browser_killer_demo.py       # 題目一:v1→v2 selector 自修復
.venv\Scripts\python tools\eval_one.py AAPL             # 題目二:抽取一份 10-K
.venv\Scripts\python tools\certify.py AAPL XOM JPM      # XBRL 認證 Item 8(certified vs contradicted)
.venv\Scripts\python tools\build_dashboard_data.py      # 重建 dashboard 數據
```

## 支援範圍(Browser Agent,SPEC 6.4)

| 類型 | 支援狀態 |
|---|---|
| 公開網站搜尋、多頁導航、資料擷取、公開文件下載 | 支援 |
| 表單填寫 | 部分支援:僅公開、可逆、無登入、無金流 |
| 登入、CAPTCHA、購買/下單、發文/正式表單、付費資料 | **不支援**(責任邊界) |

## SEC filing class(誠實邊界)

| Class | 行為 |
|---|---|
| standard | offset-exact span 抽取;Item 8 另經 XBRL 認證 |
| cross_reference_index(Intel/Citi/GE) | 自動偵測;items 標 `incorporated_by_reference` + `needs_review`,**不偽裝成內容** |
| non_10k | 誠實標 unsupported |

輸入:ticker+year / CIK+year / accession / SEC URL / HTML upload / TXT upload。掃描 PDF:`unsupported`(正確作法是 OCR,見 insights)。

## 專案結構

```
packages/   observability_core, eval_core, browser_core, sec_core, llm_core,
            sec_core/{normalize,headings,toc,boundary,refine,cross_ref,xbrl,fetcher,resolver,main_doc},
            browser_agent/{executor,observer,verifier,repair,agent,memory_store}
tools/      browser_killer_demo, eval_one, certify, sweep_metrics, build_dashboard_data, gen_fixtures
apps/web/   eval-dashboard(自包含 HTML,真實數據)
data/       sec_eval(fixtures + records), golden_labels, mock_sites(v1/v2), raw_filings(cache)
docs/       SPEC, architecture, eval_report, cost_latency_report, failure_gallery,
            supported_and_unsupported, insights_and_directions, prior_art, ai_collaboration_report
prompts/    所有影響開發的 prompt + 決策(含 rejected)
tests/      62 tests
```

## 已知邊界(誠實揭露)

- **Wrapper/index 正文還原未做**:Intel/Citi/JPM/XOM 的 Item 7/8 誠實標為指標 + needs_review,但未把真 MD&A/財報接回。刻意不出貨脆弱猜測(見 `docs/insights_and_directions.md` §2)。
- **Browser Agent 目前對本地 mock sites 完整驗證**;真實網站廣度 + WebArena/WebVoyager 對標列為 roadmap(`docs/prior_art.md`)。
- **token-level boundary IoU 未量化**(用 status-level golden labels + 對抗式稽核 + XBRL oracle 替代)。

## AI 協作方式

所有影響設計的 prompt 與決策(含被拒絕方案)記錄於 [prompts/](prompts/README.md)。AI 在 PM 授權下自主判斷 commit / push;commit history 反映真實開發順序,含失敗嘗試。見 [docs/ai_collaboration_report.md](docs/ai_collaboration_report.md)。
