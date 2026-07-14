# AI Coding Test 2026 — Reliability Platform

> 這不是兩個 AI demo。這是一套 AI reliability platform,並用 Browser Agent 與 SEC 10-K Extractor 兩個高難度任務證明它。

**核心命題:AI coding 之後,稀缺的不是「寫得出來」,是「知道自己何時對、何時錯、何時證據不足」。** 本專案把這件事制度化。

## Quick start for graders

No installation or account is required for the deployed demos.

| Task | Open this URL | What to do |
|---|---|---|
| Task 1 — Browser Agent | [wealth-agent-ncku.zeabur.app](https://wealth-agent-ncku.zeabur.app) | Click **Self-repair / 自我修復(v2 介面漂移)** for a deterministic, keyless repair demo, or enter a public-web task and press **Run / 派工**. Inspect the live steps, screenshots, verifier verdict, and artifacts. |
| Task 2 — SEC 10-K Extractor | [wealth-sec-ncku.zeabur.app](https://wealth-sec-ncku.zeabur.app) | Enter `AAPL`, click **Extract / 開始抽取**, then open any Item row to inspect the source-exact text, confidence, provenance, and validation signals. `/dashboard` shows the evaluation evidence. |

The Task 1 deployment currently has an LLM configured. The **示範任務** buttons
listed by [`GET /api/demo`](https://wealth-agent-ncku.zeabur.app/api/demo) remain
deterministic and keyless. Login, CAPTCHA, purchases, posting, and other
irreversible tasks are refused by design.

### Latest deployed Task 1 evidence (2026-07-14)

The frozen `live-mixed-interaction-v1` regression suite covers ten reversible,
no-account tasks on six public domains: dynamic controls and waits, form fill +
submit, keyboard input, new-tab following, cross-site navigation, and category,
tag, and hierarchical navigation. Its ten granular task labels map to eight
operation families. One scored run on commit `f384843` recorded mixed-operation
pass **10/10**, 18 LLM calls, median latency **6.160 s**, inclusive p95
**40.237 s**, **79,497** total tokens, and **$0.042266** total model cost; no
task crossed 60 s. This is an externally hosted regression suite, not a
held-out estimate: reachability and feasibility were probed before freeze. See
the frozen [mixed task set](data/browser_eval/live_mixed_interaction/tasks.json)
and [per-task results](data/browser_eval/live_mixed_interaction/results.json).

The frozen `live-information-retrieval-v2` suite runs ten read-only answer tasks
against ten public documentation/reference domains. The deployed agent receives
only a generic answer-shape contract; the runner applies hidden gold offline.
One scored run on direct `x-ai/grok-4.5` passed **10/10** with one LLM call per
task, median latency **4.505 s**, inclusive p95 **7.333 s**, **36,207** total
tokens, and **$0.015917** total model cost. No task crossed the 60 s slow
threshold. See the frozen [task set](data/browser_eval/live_information_retrieval/tasks.json),
[per-task results](data/browser_eval/live_information_retrieval/results.json),
and [runner](tools/live_information_retrieval_eval.py).

Neither suite replaces the historical frozen Online-Mind2Web result: the strict
advisory WebJudge figure remains `21/283`.

Deployment provenance is public and machine-checked: [`/api/health`](https://wealth-agent-ncku.zeabur.app/api/health)
returns the deployed 40-character `build_sha`. The live runner aborts before
submitting any task unless that value exactly equals local `git HEAD`. A separate
two-domain smoke recorded deployment-attested **true** and `2/2` pass; see its
[task set](data/browser_eval/live_attested_smoke/tasks.json) and
[result](data/browser_eval/live_attested_smoke/results.json).

### Public API smoke test

```bash
# Task 2: submit an extraction. The response is either a completed cached result
# or a job containing job_id; poll GET /api/jobs/<job_id> until status is done.
curl -X POST https://wealth-sec-ncku.zeabur.app/api/extract \
  -H "Content-Type: application/json" -d '{"ticker":"AAPL"}'

# Task 1: run the deterministic UI-drift/self-repair demo, then poll the task URL
# returned by the service.
curl -X POST https://wealth-agent-ncku.zeabur.app/api/demo/demo-v2-drift
```

Health and endpoint discovery:

- Task 1: [`/api/health`](https://wealth-agent-ncku.zeabur.app/api/health),
  [`/api/demo`](https://wealth-agent-ncku.zeabur.app/api/demo), and
  [API reference](apps/services/agent/README.md).
- Task 2: [`/api/health`](https://wealth-sec-ncku.zeabur.app/api/health),
  [`/dashboard`](https://wealth-sec-ncku.zeabur.app/dashboard), and
  [API reference](apps/services/sec/README.md).

### Run locally

Windows: double-click `啟動測試中心.bat`; it installs nothing and opens
`http://127.0.0.1:8765` using the existing environment. For a clean setup on any
platform, install the project first:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev,sec,browser]"
.venv\Scripts\python -m playwright install chromium
$env:SEC_EDGAR_USER_AGENT = "your-name your@email"
.venv\Scripts\python tools\test_center.py
```

Linux/macOS use `.venv/bin/python` and `export SEC_EDGAR_USER_AGENT="..."`.
For separate Docker services, environment variables, and deployment commands,
see [docs/deploy.md](docs/deploy.md).

## Strong cases and known weak cases

| Area | Works well — reproducible examples | Does not work well — why |
|---|---|---|
| Task 1: UI drift and recovery | The deployed **自我修復(v2 介面漂移)** demo changes element IDs, adds a blocking cookie dialog, and introduces a decoy search button. Grounded action history also moves a deterministic three-shape recovery probe from `0/3` to `3/3`. | Highly dynamic or anti-bot sites can become unreachable or invalidate observations between steps. Login, CAPTCHA, purchases, posting, and irreversible workflows are deliberately refused instead of being presented as supported. |
| Task 1: silent-failure prevention | The injection demo reaches all five adversarial traps in the undefended control but records defended ASR `0/5`; impossible and open-ended tasks end as `fail`/`unknown`, not a fabricated pass. | Real-web generalization remains the main weakness. On the frozen 300-task Online-Mind2Web run, 17 tasks were environment failures; the strict advisory WebJudge accepted only `21/283` completed trajectories. The planner, verifier, and external judge still disagree materially on ambiguous completion evidence. |
| Task 2: standard modern 10-K | `AAPL`, `MSFT`, `JPM`, `XOM`, and the other tracked modern filings extract source-addressable Items with offsets, hashes, confidence, provenance, partition checks, and independent XBRL/topic signals. Try `AAPL` in the deployed UI. | `Intel`/`Citi`/`GE` cross-reference-index filings scatter substantive sections across printed-page ranges. Page-anchored Item bodies are now reassembled into source-exact `partial` spans (multi-range aware), but page-boundary alignment stays heuristic, XBRL-contradicted years (e.g. INTC FY2019 Item 8) are demoted to `unsupported` rather than shipped as `partial`, and Items pointing to a **separately filed proxy statement** stay `incorporated_by_reference` — never guessed text. |
| Task 2: format variance | Same-file wrappers such as tracked `JPM`/`XOM` cases are reconstructed with page/section anchors and checked against XBRL/CYD evidence. Unsupported binary/PDF input is rejected without inventing Items. | Pre-2001 plain-text SGML examples (`AAPL` FY1996, `KO` FY1997) have headings that the HTML-oriented detector cannot reliably segment, so they return missing/unsupported coverage. Scanned PDFs need a separate OCR pipeline and are not supported. |

Full evidence, metrics, and failure traces: [evaluation report](docs/eval_report.md),
[failure gallery](docs/failure_gallery.md), and
[supported/unsupported matrix](docs/supported_and_unsupported.md).

### Reviewer evidence path

1. Run the two deployed demos using the steps above.
2. Read [docs/eval_report.md](docs/eval_report.md) for canonical metrics and
   [docs/cost_latency_report.md](docs/cost_latency_report.md) for runtime, cost,
   and scalability.
3. Inspect [docs/failure_gallery.md](docs/failure_gallery.md) and
   [docs/supported_and_unsupported.md](docs/supported_and_unsupported.md) for
   concrete failures and honest boundaries.
4. Read [prompts/README.md](prompts/README.md) for the key AI decisions and
   rejected approaches. The full manual Task 1 acceptance script is
   [docs/manual_test_browser.md](docs/manual_test_browser.md).
5. 確認「裁判本身可不可信」:[docs/verifier_trust_card.md](docs/verifier_trust_card.md)(由 `tools/verifier_trust_card.py` 從 artifact 生成的計分卡,含 AUROC MISS 的誠實揭露)。
6. 重跑 Task 1 action-history 泛化機制 probe：`.venv\Scripts\python tools\action_history_cross_site_eval.py`。
7. 重跑 deployed 10-domain information-retrieval suite：`.venv\Scripts\python tools\live_information_retrieval_eval.py`。
8. 重跑 deployed mixed-operation suite：`.venv\Scripts\python tools\live_information_retrieval_eval.py --tasks data/browser_eval/live_mixed_interaction/tasks.json --output data/browser_eval/live_mixed_interaction/results.json`。
9. 驗證 deployed build SHA 並跑 smoke：`.venv\Scripts\python tools\live_information_retrieval_eval.py --tasks data/browser_eval/live_attested_smoke/tasks.json --output data/browser_eval/live_attested_smoke/results.json --require-build-sha`。

Known limitations and planned experiments: [TODO.md](TODO.md).

## 系統總覽

| 題目 | 內容 | 狀態 |
|---|---|---|
| 題目一 Browser Agent | 受控 action space、**preflight task contract 凍結並揭露條件來源**、deterministic verifier、a11y selector 自修復、selector memory、**Agent Mode(LLM 驅動,預設接 Codex OAuth via gateway)**、**卡住時自動視覺升級(SoM 截圖 + gpt-5.5 視覺)**、**答案交付通道(查數字/問答)**、code-enforced capability guard | **可執行**:selector-repair killer demo(`tools/browser_killer_demo.py`)+ live LLM 驅動(`tools/browser_agent_live.py`) |
| 題目二 SEC Extractor | 10-K Item 1–16 source-exact 抽取、TOC 防禦、cross-reference-index 偵測、**same-file wrapper page-anchor 還原**、**多段頁碼 body 重組(`source_ranges[]`)**、**XBRL 認證(Item 8)**、**topic-consistency oracle(全 item)** | **可執行**:11 家真實 10-K + Intel(`tools/eval_one.py INTC`)/Citi(pseudo-ticker,`tools/eval_one.py CITI --cik 831001 --accession <acc>`)、`tools/certify.py` |
| 共用層 | evidence schema / library、三態 verdict、eval case、LLM 成本紀錄 | Browser deployed path 會寫 EvidenceStore；SEC deployed path 目前以 raw bytes + offsets/hash + job payload 稽核，尚未注入 JSONL store |
| Eval Dashboard | 兩題 eval、XBRL 認證、browser repair trace(真實數據) | `apps/web/eval-dashboard/`,自包含 HTML |

[![CI](https://github.com/Tim096/wealth/actions/workflows/ci.yml/badge.svg)](https://github.com/Tim096/wealth/actions/workflows/ci.yml)
測試數量與結果以當前 commit 的 CI collection/output 為準，不在文件複製容易過期的 snapshot。完整規格:[docs/SPEC.md](docs/SPEC.md)。手動測 Task 1:[docs/setup_codex_gateway.md](docs/setup_codex_gateway.md)。

## 核心原則(已在 code 層強制,不是文件宣示)

1. **三態判定**:結果只能 `pass` / `fail` / `unknown`。缺 evidence 永遠 `unknown`,結構上不可能升級成 pass(`eval_core/verdict.py`)。
2. **受控 action space**:LLM 只輸出 schema 驗證過的 action JSON,不輸出任意 browser code(`browser_core/actions.py`)。
3. **LLM 不產生 filing text**:抽取結果只以 offset + sha256 定址 source-exact span(`sec_core/items.py`)。
4. **status 可信度四層防禦**:三態 verdict → 對抗式稽核 → **XBRL 獨立 oracle** → provenance/needs_review。見 [docs/supported_and_unsupported.md](docs/supported_and_unsupported.md)。

## 一鍵測試中心(最快的驗證方式)

雙擊 **`啟動測試中心.bat`** → 自動開 `http://127.0.0.1:8765`,一頁測兩題:

- **題目一**:輸入自然語言任務 → 另開真實瀏覽器視窗全程可看,頁面串流每一步(思考→動作→驗證),最終由 verifier 判 PASS/FAIL/REFUSED;開放式(無可機讀驗證條件)任務照跑並錄 trace,結果誠實判 **UNKNOWN**(交人工審 trace),不 crash 也不 vacuous pass。
- **題目二**:輸入 ticker → 逐 item 檢視 status/confidence/provenance/XBRL/topic,點任一 item 讀 source-exact 原文;可一鍵下載原始 filing(byte-for-byte)。

(Codex gateway 自動啟動;需先 `codex login` 一次。另有獨立視窗版:`啟動Agent.bat`、`驗證SEC.bat`。)

## Killer demos

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev,sec,browser]"
.venv\Scripts\python -m playwright install chromium
$env:SEC_EDGAR_USER_AGENT = "your-name your@email"

.venv\Scripts\python -m pytest -m "not integration"     # 快速 lane；實際數量由 pytest collection 回報
.venv\Scripts\python tools\browser_killer_demo.py       # 題目一:v1→v2 selector 自修復
.venv\Scripts\python tools\browser_agent_live.py --mock # 題目一:Agent Mode 迴圈(免 key)
.venv\Scripts\python tools\eval_one.py AAPL             # 題目二:抽取一份 10-K
.venv\Scripts\python tools\certify.py AAPL XOM JPM      # XBRL 認證 Item 8(11 家實測 certified 10 / contradicted 1,artifact data\sec_eval\certification\item8_certification.json)

# 2026-07-10 eval 升級波(全部離線 deterministic、零 LLM 成本;數字見 docs/eval_report.md)
.venv\Scripts\python tools\calibrate_verifier.py        # 題目一:校準裁判本身(sens 1.0 / spec 1.0 + Rogan-Gladen 0.8,2026-07-10 修復後)
.venv\Scripts\python tools\degradation_curve.py         # 題目一:三軸擾動 degradation curve(monotone 遞減 + checkpoint 失敗定位)
.venv\Scripts\python tools\triangulate.py               # 題目二:外部引擎三角驗證(edgartools/edgar_crawler/datamule,2-of-N 投票;249 agree / 4 disagree)
.venv\Scripts\python tools\certify_cyd.py               # 題目二:Item 1C 官方 CYD iXBRL span oracle(11 agree / 0 disagree,wrapper 1C 還原後)
.venv\Scripts\python tools\score_offsets.py data\sec_eval\records\sweep3   # 題目二:char-offset F1 + tri-state
.venv\Scripts\python tools\stratified_sample.py         # 題目二:format-era × filing-agent 分層抽樣

# 2026-07-10 波:對抗軸 + 外部基準
.venv\Scripts\python -m pytest tests\test_adversarial_suite.py  # 題目一:prompt-injection 對抗 suite(5 攻擊型態,ASR 指標)
.venv\Scripts\python tools\naive_baseline.py            # 題目一:Online-Mind2Web 20-task 外部子集 naive baseline(實測 trivial-pass 20%)
```

Task 1 用你自己的 **Codex OAuth**(預設走 gateway)實測:見 [docs/setup_codex_gateway.md](docs/setup_codex_gateway.md)。

## 支援範圍(Browser Agent,SPEC 6.4)

| 類型 | 支援狀態 |
|---|---|
| 公開網站搜尋、多頁導航、資料擷取、公開文件下載 | 支援 |
| 答案型任務(查數字 / 問答,如「NVDA 現在股價多少」) | 支援:答案顯示於結果(📋 擷取內容);抓不到 → 誠實 **fail / unknown**,絕不無交付卻判 pass |
| 表單填寫 | 部分支援:僅公開、可逆、無登入、無金流 |
| 登入、CAPTCHA、購買/下單、發文/正式表單、付費資料 | **不支援**(責任邊界) |

## SEC filing class(誠實邊界)

| Class | 行為 |
|---|---|
| standard | offset-exact span 抽取;Item 8 另經 XBRL 認證 |
| cross_reference_index(Intel/Citi/GE) | 自動偵測;可解析的 item body 由印刷頁碼錨點還原成 source-exact span(`partial` / `resolved_from_page_anchor`),body 被 index 拆成多段時以 `source_ranges[]` **多段重組**(如 Intel MD&A);頁碼圖被財報數字表污染或 XBRL 矛盾者**誠實降級 `unsupported`**,無錨點者留 `incorporated_by_reference`,一律 `needs_review`,**絕不偽裝成內容** |
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
tests/      quick + Playwright/integration lanes；實際數量由 pytest collection 回報
```

## 部署(Zeabur)— 線上可直接用

| 服務 | URL | 狀態(2026-07-14 實測) |
|---|---|---|
| SEC Extractor + dashboard | **https://wealth-sec-ncku.zeabur.app** | 完整可用、免 auth(AAPL 23 items、warm repeat ~0.6s) |
| Browser Agent | **https://wealth-agent-ncku.zeabur.app** | **真實 LLM(OpenRouter `x-ai/grok-4.5`)**；frozen answer 與 mixed-operation suites 各實跑 **10/10**，另有 `/api/demo` 列出的免 key 示範任務 |

兩個 service 各自容器化(Docker 本地驗證通過,零修正):**wealth-sec**(SEC Extractor API + dashboard,`Dockerfile.wealth-sec`)與 **wealth-agent**(Browser Agent + Playwright Chromium,`Dockerfile.wealth-agent`),同一 repo root 為 build context,根目錄 `.dockerignore` 排除 `.venv` / `data/raw_filings` / `runs`(context 縮小約 830MB)。

拓撲、環境變數(`SEC_EDGAR_USER_AGENT`、`AGENT_LLM_MODE=direct` + `OPENAI_*`、選用 `ACCESS_TOKEN`;值只存 Zeabur,不進 repo)、`npx zeabur@latest` 部署/redeploy 指令與 smoke test 清單:見 [docs/deploy.md](docs/deploy.md)。

## 已知邊界(誠實揭露)

- **同檔正文已還原(wrapper + cross-reference-index 頁碼錨點);僅跨檔 proxy statement 未 join**:JPM/XOM 的本檔附綁正文已由 page/section-anchor 重組(Item 8 獲 XBRL 3/3 認證);2026-07-11 page-top section anchoring 收尾 GS/JPM Item 1C,官方 CYD oracle 現為 **11 agree / 0 disagree**(kill-switch `SEC_WRAPPER_SECTION_ANCHOR=0`;見 `docs/eval_report.md` T2-3)。Intel/Citi 的 cross-reference-index 正文亦已由**同檔印刷頁碼錨點**重組為 source-exact `partial`(多段以 `source_ranges[]` 串接,needs_review;頁邊界對齊為 heuristic,XBRL 矛盾年度如 INTC FY2019 Item 8 誠實降 `unsupported`);僅指向**另外申報 proxy statement** 的 Item 10–14 維持誠實指標,刻意不 join、不出貨脆弱猜測(見 `docs/insights_and_directions.md` §2)。
- **Browser Agent 對本地 mock sites 完整驗證;真實網站對標仍弱(2026-07-10~11)**:外部基準子集 **Online-Mind2Web** 20 tasks(OSU-NLP-Group,**CC-BY-4.0**,COLM 2025,arXiv:2504.01382;`data/browser_eval/external/`)的 20%→33.3%→44.4%→61.1% 與 held-out 66.7% 都使用 task-text landmark contract,只適合觀察 verifier/repair 迭代,**不是 task-success 成績**。300 題 frozen run 完成 283/300(17 個 site_unreachable);歷史 runtime landmark hit **95/283 = 33.57%**,但其中含只驗網站名/普通動詞的弱條件,不得視為成功率。獨立 WebJudge outcome estimate 為 **21/283 = 7.42%**;其中 63/70 abstain 來自 judge prompt literal `success|failure` artifact,且 judge model 非官方 o4-mini,所以也不可與 leaderboard 比較。現在 importer 已停止把 heuristic landmark 當 authoritative `success_conditions`;未來 run 保留完整 trajectory,以修正後 independent WebJudge 或 human review 決定完成。舊 frozen artifacts 不重寫,詳見 `docs/eval_report.md`。Mock/eval 仍有 selector-repair ablation、prompt-injection defended ASR 0/5、step budgets 與完整 evidence artifacts。
- **token-level boundary 已量化(2026-07-10)**:char-offset F1(建構性 gold,regression baseline,敏感度注入驗證 0.9853)+ CYD 官方 iXBRL oracle(9/9 pass segment coverage 100%);人工標註的絕對正確率仍列 backlog。見 `docs/eval_report.md`。
- **pre-2001 純文字 SGML filing:Unsupported**(heading detector 0 candidate,誠實全 missing,partition invariant 仍成立)。見 `docs/supported_and_unsupported.md` format-era 支援表。
- **Browser 4 個 measure-first 弱點已於 2026-07-10 修復**(verifier filename-needle bypass、query-echo silent failure、repair fallback 到不可行元素、bait-field tie-break;commit bcdc9cf / d5481eb):校準 specificity 0.9583→1.0、FP rate 0.0417→0.0、impossible silent_failure_rate 0.1→0.0、perception degradation curve 尾端 0.0→1.0。原 `test_known_*` 已翻寫為 `test_fixed_*` 並重跑 artifact。另修復開放式(零條件)任務 crash → 誠實 unknown(FG-BROWSER-006,commit f535c93)。逐條前→後見 `docs/failure_gallery.md` FG-BROWSER-002~006 與 `docs/eval_report.md`「修復迭代」段。
- **INTC 營收 false pass 三重根因已修復(2026-07-10,FG-BROWSER-007)**:使用者親測「找 intc 10-k 最新營收數字」被判 PASS 卻沒交付答案。三根因分別結構性修復——(1) premature-landmark → verifier baseline-subtraction(t0 即成立的條件視為 landmark 剔除,INTC repro pass→unknown;commit 8437826);(2) 答案無交付通道 → answer channel + verifier `answer_matches`(沒抓到答案 → 誠實 fail,不偽 pass;commit 3431335);(3) 卡住無視覺升級 → auto vision escalation + scroll + 新分頁跟隨(commit 1c8f103)。見 `docs/eval_report.md`「修復迭代 2」段。

## AI 協作方式

AI 協作證據記錄於 [prompts/](prompts/README.md)：verbatim excerpts 保留可核對的原文邊界，derived decision records 則明確標示為摘要而非逐字 prompt。`tools/verify_prompt_provenance.py` 會核對分類、原始 Git blob 與 verbatim body hash；設計取捨與 AI 使用邊界見 [docs/ai_collaboration_report.md](docs/ai_collaboration_report.md)。
