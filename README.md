# AI Coding Test 2026 — Reliability Platform

> 這不是兩個 AI demo。這是一套 AI reliability platform,並用 Browser Agent 與 SEC 10-K Extractor 兩個高難度任務證明它。

**核心命題:AI coding 之後,稀缺的不是「寫得出來」,是「知道自己何時對、何時錯、何時證據不足」。** 本專案把這件事制度化。

## 系統總覽

| 題目 | 內容 | 狀態 |
|---|---|---|
| 題目一 Browser Agent | 受控 action space、task-contract verifier、a11y selector 自修復、selector memory、**Agent Mode(LLM 驅動,預設接 Codex OAuth via gateway)**、code-enforced capability guard | **可執行**:selector-repair killer demo(`tools/browser_killer_demo.py`)+ live LLM 驅動(`tools/browser_agent_live.py`) |
| 題目二 SEC Extractor | 10-K Item 1–16 source-exact 抽取、TOC 防禦、cross-reference-index、**page-anchor 還原(Intel 正文抽回)**、**XBRL 認證(Item 8)**、**topic-consistency oracle(全 item)** | **可執行**:11 家真實 10-K + Intel/Citi(`tools/eval_one.py`, `tools/certify.py`) |
| 共用層 | evidence store(兩題共用)、三態 verdict、eval case、LLM 成本紀錄 | 已實作 |
| Eval Dashboard | 兩題 eval、XBRL 認證、browser repair trace(真實數據) | `apps/web/eval-dashboard/`,自包含 HTML |

**291 tests 通過**(含真實瀏覽器 integration test + gateway e2e)。完整規格:[docs/SPEC.md](docs/SPEC.md)。手動測 Task 1:[docs/setup_codex_gateway.md](docs/setup_codex_gateway.md)。

## 核心原則(已在 code 層強制,不是文件宣示)

1. **三態判定**:結果只能 `pass` / `fail` / `unknown`。缺 evidence 永遠 `unknown`,結構上不可能升級成 pass(`eval_core/verdict.py`)。
2. **受控 action space**:LLM 只輸出 schema 驗證過的 action JSON,不輸出任意 browser code(`browser_core/actions.py`)。
3. **LLM 不產生 filing text**:抽取結果只以 offset + sha256 定址 source-exact span(`sec_core/items.py`)。
4. **status 可信度四層防禦**:三態 verdict → 對抗式稽核 → **XBRL 獨立 oracle** → provenance/needs_review。見 [docs/supported_and_unsupported.md](docs/supported_and_unsupported.md)。

## 一鍵測試中心(最快的驗證方式)

雙擊 **`啟動測試中心.bat`** → 自動開 `http://127.0.0.1:8765`,一頁測兩題:

- **題目一**:輸入自然語言任務 → 另開真實瀏覽器視窗全程可看,頁面串流每一步(思考→動作→驗證),最終由 verifier 判 PASS/FAIL/REFUSED。
- **題目二**:輸入 ticker → 逐 item 檢視 status/confidence/provenance/XBRL/topic,點任一 item 讀 source-exact 原文;可一鍵下載原始 filing(byte-for-byte)。

(Codex gateway 自動啟動;需先 `codex login` 一次。另有獨立視窗版:`啟動Agent.bat`、`驗證SEC.bat`。)

## Killer demos

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev,sec,browser]"
.venv\Scripts\python -m playwright install chromium
$env:SEC_EDGAR_USER_AGENT = "your-name your@email"

.venv\Scripts\python -m pytest                          # 291 passed
.venv\Scripts\python tools\browser_killer_demo.py       # 題目一:v1→v2 selector 自修復
.venv\Scripts\python tools\browser_agent_live.py --mock # 題目一:Agent Mode 迴圈(免 key)
.venv\Scripts\python tools\eval_one.py AAPL             # 題目二:抽取一份 10-K
.venv\Scripts\python tools\certify.py AAPL XOM JPM      # XBRL 認證 Item 8(certified vs contradicted)

# 2026-07-10 eval 升級波(全部離線 deterministic、零 LLM 成本;數字見 docs/eval_report.md)
.venv\Scripts\python tools\calibrate_verifier.py        # 題目一:校準裁判本身(sens 1.0 / spec 0.958 + Rogan-Gladen 0.7913)
.venv\Scripts\python tools\degradation_curve.py         # 題目一:三軸擾動 degradation curve(monotone 遞減 + checkpoint 失敗定位)
.venv\Scripts\python tools\triangulate.py               # 題目二:edgartools 第三引擎三角驗證(240 agree / 12 disagree)
.venv\Scripts\python tools\certify_cyd.py               # 題目二:Item 1C 官方 CYD iXBRL span oracle(9/9 coverage 100%)
.venv\Scripts\python tools\score_offsets.py data\sec_eval\records\sweep3   # 題目二:char-offset F1 + tri-state
.venv\Scripts\python tools\stratified_sample.py         # 題目二:format-era × filing-agent 分層抽樣
```

Task 1 用你自己的 **Codex OAuth**(預設走 gateway)實測:見 [docs/setup_codex_gateway.md](docs/setup_codex_gateway.md)。

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
tests/      291 tests
```

## 已知邊界(誠實揭露)

- **Wrapper/index 正文還原未做**:Intel/Citi/JPM/XOM 的 Item 7/8 誠實標為指標 + needs_review,但未把真 MD&A/財報接回。刻意不出貨脆弱猜測(見 `docs/insights_and_directions.md` §2)。
- **Browser Agent 目前對本地 mock sites 完整驗證**;真實網站廣度 + WebArena/WebVoyager 對標列為 roadmap(`docs/prior_art.md`)。
- **token-level boundary 已量化(2026-07-10)**:char-offset F1(建構性 gold,regression baseline,敏感度注入驗證 0.9853)+ CYD 官方 iXBRL oracle(9/9 pass segment coverage 100%);人工標註的絕對正確率仍列 backlog。見 `docs/eval_report.md`。
- **pre-2001 純文字 SGML filing:Unsupported**(heading detector 0 candidate,誠實全 missing,partition invariant 仍成立)。見 `docs/supported_and_unsupported.md` format-era 支援表。
- **Browser 4 個 measure-first 保留的已知弱點**(verifier filename-needle bypass、query-echo silent failure、repair fallback 到不可行元素、bait-field tie-break),刻意不修、各有 test 鎖住,見 `docs/failure_gallery.md` FG-BROWSER-002~005。

## AI 協作方式

所有影響設計的 prompt 與決策(含被拒絕方案)記錄於 [prompts/](prompts/README.md)。AI 在 PM 授權下自主判斷 commit / push;commit history 反映真實開發順序,含失敗嘗試。見 [docs/ai_collaboration_report.md](docs/ai_collaboration_report.md)。
