# AI Coding Test 2026 — Reliability Platform

> 這不是兩個 AI demo。這是一套 AI reliability platform,並用 Browser Agent 與 SEC 10-K Extractor 兩個高難度任務證明它。

**核心命題:AI coding 之後,稀缺的不是「寫得出來」,是「知道自己何時對、何時錯、何時證據不足」。** 本專案把這件事制度化。

**一句話電梯簡報:我交付的不是「會做事的 AI」,是「知道自己有沒有做到的 AI」。** 兩個任務都能線上點開;做不到的時候,它會誠實吐 `fail` 或 `unknown`,而不是編一個 `pass` 給你看。

## 這份 README 怎麼讀?(先攤開地圖)

本份分十一段,每段回答評審心裡的一個問題 —— 順序刻意由淺入深:**先「做了什麼」→ 再「憑什麼信」→ 再「邊界在哪」→ 最後「怎麼複製」。**

1. **現在就能點開什麼?** — 兩個線上服務,零安裝、零帳號。
2. **哪裡強、哪裡弱?** — 強項與弱項並排,各附可重現的例子。
3. **這套系統長什麼樣?** — 兩題 + 共用層 + dashboard 的總覽。
4. **憑什麼相信它不會唬人?** — 四條寫進 code、不是寫進文件的原則。
5. **最快的驗證方式是什麼?** — 一鍵測試中心 + killer demos。
6. **支援範圍(Browser Agent,SPEC 6.4)** — 責任邊界表。
7. **SEC filing 分成哪幾類?** — 誠實邊界表。
8. **專案結構長怎樣?** — 檔案地圖。
9. **線上部署怎麼做的?** — Zeabur 兩容器拓撲。
10. **它哪裡還不行?** — 已知邊界,全部拉到標題級,不藏附錄。
11. **AI 是怎麼參與的?** — prompt provenance,可機器核對。

## 現在就能點開什麼?(Quick start for graders)

No installation or account is required for the deployed demos.

| Task | Open this URL | What to do |
|---|---|---|
| Task 1 — Browser Agent | [wealth-agent-ncku.zeabur.app](https://wealth-agent-ncku.zeabur.app) | Click **Self-repair / 自我修復(v2 介面漂移)** for a deterministic, keyless repair demo, or enter a public-web task and press **Run / 派工**. Inspect the live steps, screenshots, verifier verdict, and artifacts. |
| Task 2 — SEC 10-K Extractor | [wealth-sec-ncku.zeabur.app](https://wealth-sec-ncku.zeabur.app) | Enter `AAPL`, click **Extract / 開始抽取**, then open any Item row to inspect the normalized-source text, offsets/hash, provenance, audit manifest, and servability signals. `/dashboard` shows the evaluation evidence. |

The Task 1 deployment currently has an LLM configured. The **示範任務** buttons
listed by [`GET /api/demo`](https://wealth-agent-ncku.zeabur.app/api/demo) remain
deterministic and keyless. Login, CAPTCHA, purchases, posting, and other
irreversible tasks are refused before planner or browser side effects. The
deterministic guard covers English and Chinese action intents while allowing
read-only mentions such as login documentation or checkout UX articles.

In plain terms: the demo buttons need no API key and always do the same thing —
so a grader can reproduce them. The refused categories are not a capability gap;
they are a line I drew on purpose.

### 最新一次線上實測長怎樣?(Latest deployed Task 1 evidence, 2026-07-16)

第一件事 —— **這是外部託管的迴歸測試,不是 held-out 估計。** 我把這句話放在數字前面,
因為順序反過來就是包裝。

The frozen `live-mixed-interaction-v1` regression suite covers ten reversible,
no-account tasks on six public domains: dynamic controls and waits, form fill +
submit, keyboard input, new-tab following, cross-site navigation, and category,
tag, and hierarchical navigation. Its ten granular task labels map to eight
operation families. One scored run on commit `aa1c039` recorded mixed-operation
pass **10/10**, 16 LLM calls, median latency **5.831 s**, inclusive p95
**28.609 s**, **70,955** total tokens, and **$0.036847** total model cost; no
task crossed 60 s. This is an externally hosted regression suite, not a
held-out estimate: reachability and feasibility were probed before freeze. See
the frozen [mixed task set](data/browser_eval/live_mixed_interaction/tasks.json)
and [per-task results](data/browser_eval/live_mixed_interaction/results.json).

The frozen `live-information-retrieval-v2` suite runs ten read-only answer tasks
against ten public documentation/reference domains. The deployed agent receives
only a generic answer-shape contract; the runner applies hidden gold offline.
One scored run on commit `aa1c039` (direct `x-ai/grok-4.5`) recorded **two
separate numbers, and the gap between them is the point**:
gold-pass **10/10** — every delivered answer is correct against hidden gold —
but self-certified **5/10**. The other five it delivered correctly and then
honestly refused to vouch for. One LLM call per task, median latency
**3.599 s**, inclusive p95 **5.821 s**, **35,822** total tokens, **$0.015147**
total model cost, no task over the 60 s slow threshold.
See the frozen [task set](data/browser_eval/live_information_retrieval/tasks.json),
[per-task results](data/browser_eval/live_information_retrieval/results.json),
and [runner](tools/live_information_retrieval_eval.py).

白話:agent 只拿到「答案該長什麼形狀」的通用契約,正確答案(gold)留在 runner 手上、
離線比對 —— 考生看不到答案卷。

**那個 10/10 vs 5/10 的落差,是這一版最該讀的數字。** 之前這裡寫的是單一個 10/10 ——
而那個數字是假的:runner 當時要求「agent 自己判 pass」才給分,等於把外部 gold 從屬於
考生的自我宣稱。更糟的是,agent 判 pass 的依據是 LLM 自己寫給自己的條件
`answer_matches:(?s).+` —— **對任何非空答案都成立**。答案對不對它根本沒驗,它驗的是
「有沒有東西」。現在條件若對 decoy 語料的命中率過高就不算證據,判決封頂 unknown;
gold 歸 gold、自我認證歸自我認證,兩個數字分開報。**能力沒有變,變的是我不再拿
「有交付」冒充「有驗證」。** 順帶一提,誠實化之後 median latency 從 4.505 s 掉到
3.599 s、成本從 $0.015917 掉到 $0.015147 —— 這件事沒有付出代價。

Neither suite replaces the historical frozen Online-Mind2Web result: the strict
advisory WebJudge figure remains `21/283`.

**不是兩張 10/10 就抵掉那個 21/283,是兩件不同的事並存。** 迴歸測試證明「不會壞掉」,
外部基準才是「真實網站上的成績單」—— 後者仍然難看,我不拿前者去蓋它。

問題是:線上跑的到底是不是我 repo 裡的那份 code?答案是機器去比對,不是我口頭保證。

Deployment provenance is public and machine-checked: [`/api/health`](https://wealth-agent-ncku.zeabur.app/api/health)
returns the deployed 40-character `build_sha`. The live runner aborts before
submitting any task unless that value exactly equals local `git HEAD` — **but
only under `--require-build-sha`; the flag is off by default, so runs 7 and 8 of
the reviewer path below are unattested, and only run 9 asserts the identity.**
A separate
two-domain smoke recorded deployment-attested **true** and `2/2` pass; see its
[task set](data/browser_eval/live_attested_smoke/tasks.json) and
[result](data/browser_eval/live_attested_smoke/results.json).

### 怎麼用 curl 直接打 API?(Public API smoke test)

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

### 怎麼在自己電腦上跑?(Run locally)

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

## 哪裡強、哪裡弱?(Strong cases and known weak cases)

這張表左右等寬 —— **不是先鋪三頁優點再把缺點塞附錄,是同一列並排讓你左右對讀。**

| Area | Works well — reproducible examples | Does not work well — why |
|---|---|---|
| Task 1: UI drift and recovery | The deployed **自我修復(v2 介面漂移)** demo changes element IDs, adds a blocking cookie dialog, and introduces a decoy search button. Grounded action history also moves a deterministic three-shape recovery probe from `0/3` to `3/3`. | Highly dynamic or anti-bot sites can become unreachable or invalidate observations between steps. Login, CAPTCHA, purchases, posting, and irreversible workflows are deliberately refused instead of being presented as supported. |
| Task 1: silent-failure prevention | The injection demo reaches all five adversarial traps in the undefended control but records defended ASR `0/5`; impossible and open-ended tasks end as `fail`/`unknown`, not a fabricated pass. A condition that the decoy corpus also satisfies is no longer evidence: `answer_matches:.+` (22/22 decoys) caps the verdict at `unknown` instead of passing at confidence 1.0. | Real-web generalization remains the main weakness. On the frozen 300-task Online-Mind2Web run, 17 tasks were environment failures; the strict advisory WebJudge accepted only `21/283` completed trajectories. The planner, verifier, and external judge still disagree materially on ambiguous completion evidence. The verdict now abstains where it used to overclaim, but abstaining is not the same as verifying: free-form answers are still checked by shape, never for correctness. |
| Task 2: standard modern 10-K | `AAPL`, `MSFT`, `JPM`, `XOM`, and the other tracked modern filings extract source-addressable Items with offsets, hashes, confidence, provenance, partition checks, and independent XBRL/topic signals. Try `AAPL` in the deployed UI. Held-out REITs stay upright but fray at the edges — see the right-hand column and `data/sec_eval/heldout_probe/`. | `Intel`/`Citi`/`GE` cross-reference-index filings scatter substantive sections across printed-page ranges. Page-anchored Item bodies are now reassembled into source-exact `partial` spans (multi-range aware), but page-boundary alignment stays heuristic, XBRL-contradicted years (e.g. INTC FY2019 Item 8) are demoted to `unsupported` rather than shipped as `partial`, and Items pointing to a **separately filed proxy statement** stay `incorporated_by_reference` — never guessed text. |
| Task 2: format variance | Same-file wrappers such as tracked `JPM`/`XOM` cases are reconstructed with page/section anchors and checked against XBRL/CYD evidence. Pre-2001 plain-text SGML now extracts too (`AAPL` FY1996 7 `pass` + 2 `partial`, `KO` FY1997 6 `pass`). Unsupported binary/PDF input is rejected without inventing Items. | Pre-2001 item codes that did not exist in that filing's year return `missing` — the set is per-year, not one list (`AAPL` FY1996 misses 7A, `KO` FY1997 has it and misses 15 instead). Era headings that combine two items (FY1996 `Item 14. Exhibits… and Reports on Form 8-K`) resolve both codes to one span — flagged `needs_review`, not silently split. Era-aware schema mapping is not implemented, so coverage reads low where that era incorporated core items from the annual report (`KO` FY1997 0.2126). Scanned PDFs need a separate OCR pipeline and are not supported. |

白話三個關鍵詞:**ASR**(attack success rate,攻擊得手率 —— `0/5` = 五種注入攻擊全部沒得手);
**XBRL**(公司自己申報給 SEC 的結構化財報資料,可以拿來當獨立裁判);
**incorporated_by_reference**(這個 Item 的正文根本不在這份檔案裡,它指向另一份文件)。

Full evidence, metrics, and failure traces: [evaluation report](docs/eval_report.md),
[failure gallery](docs/failure_gallery.md), and
[supported/unsupported matrix](docs/supported_and_unsupported.md).

### 評審要怎麼自己查證?(Reviewer evidence path)

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

第 5 條是這份專案的元層動作,值得單獨拎出來講:**先證明系統沒出錯不夠,還要證明「我的裁判抓得到錯」。**
所以裁判自己也有一張成績單,而且那張成績單上寫著 AUROC MISS —— 沒過的就寫沒過。

Known limitations and planned experiments: [TODO.md](TODO.md).

## 這套系統長什麼樣?(系統總覽)

| 題目 | 內容 | 狀態 |
|---|---|---|
| 題目一 Browser Agent | 受控 action space、**preflight task contract 凍結並揭露條件來源**、deterministic verifier、**條件鑑別力檢查(擋 vacuous pass)**、a11y selector 自修復 + selector memory(**2026-07-16 起才真的接進部署路徑**,見下)、**Agent Mode(LLM 驅動,預設接 Codex OAuth via gateway)**、**卡住時自動視覺升級(SoM 截圖 + gpt-5.5 視覺)**、**答案交付通道(查數字/問答)**、code-enforced capability guard(**中英文 intent 皆篩;在 planner／browser 任何 side effect 之前拒絕**) | **可執行**:selector-repair killer demo(`tools/browser_killer_demo.py`)+ live LLM 驅動(`tools/browser_agent_live.py`) |
| 題目二 SEC Extractor | 10-K Item 1–16 normalized-source 抽取、TOC 防禦、cross-reference-index 偵測、**same-file wrapper page-anchor 還原**、**多段頁碼 body 重組(`source_ranges[]`)**、**XBRL value check(Item 8)**、**topic-consistency oracle(全 item)**、audit manifest + servability gate | **可執行**:11 家真實 10-K + Intel(`tools/eval_one.py INTC`)/Citi(pseudo-ticker,`tools/eval_one.py CITI --cik 831001 --accession <acc>`)、`tools/certify.py` |
| 共用層 | evidence schema / library、三態 verdict、eval case、LLM 成本紀錄 | Browser deployed path 會寫 EvidenceStore；SEC deployed path 目前以 raw bytes + offsets/hash + job payload 稽核，尚未注入 JSONL store |
| Eval Dashboard | 兩題 eval、XBRL 認證、browser repair trace(真實數據) | `apps/web/eval-dashboard/`,自包含 HTML |

Current runtime note: Task 1 screens English and Chinese irreversible intents before planner/browser side effects, and deterministic contract lint caps wholly weak contracts at `unknown`.

白話幾個詞:**action space**(agent 只能從一份固定清單裡挑動作,不能自由發揮);
**normalized-source-exact**(offsets 是 normalized text 的 Python code-point indices；raw bytes 另以原檔下載與 SHA-256 重播，不冒充 raw byte offsets);
**TOC 防禦**(目錄裡也寫著「Item 1 Business」,不擋掉就會把目錄當正文抽走)。

注意共用層那一格寫的是「尚未注入 JSONL store」—— **這是還沒做完的事,我寫在總覽表裡,不寫在附錄裡。**

[![CI](https://github.com/Tim096/wealth_ai/actions/workflows/ci.yml/badge.svg)](https://github.com/Tim096/wealth_ai/actions/workflows/ci.yml)
測試數量與結果以當前 commit 的 CI collection/output 為準，不在文件複製容易過期的 snapshot。完整規格:[docs/SPEC.md](docs/SPEC.md)。手動測 Task 1:[docs/setup_codex_gateway.md](docs/setup_codex_gateway.md)。

**不是我懶得寫測試數量,是寫死的數字必然過期成謊話。** 要看數字就去看 CI 那一跑。

## 憑什麼相信它不會唬人?(核心原則:已在 code 層強制,不是文件宣示)

一句話:這四條不是我的承諾,是我把「作弊路徑」從程式裡刪掉了 —— 想唬人也唬不了。

1. **三態判定**:結果只能 `pass` / `fail` / `unknown`。缺 evidence 永遠 `unknown`,結構上不可能升級成 pass(`eval_core/verdict.py`)。
   白話:沒證據就是不知道。**不是「傾向 pass」,是不給你這個選項。**
2. **受控 action space**:LLM 只輸出 schema 驗證過的 action JSON,不輸出任意 browser code(`browser_core/actions.py`)。
   白話:LLM 只能點菜,不能進廚房。
3. **LLM 不產生 filing text**:抽取結果只以 normalized offsets + sha256 定址來源 span(`sec_core/items.py`)；raw bytes 另行保存與雜湊。
   白話:財報文字不由 LLM 生成。程式從固定版本的 normalized document 依 offsets 切片，並保留原始上傳/抓取 bytes 供獨立重播。
4. **status 可信度四層防禦**:三態 verdict → 對抗式稽核 → **XBRL headline value cross-check(尚未驗 period/unit/currency identity)** → provenance/needs_review + servability gate。見 [docs/supported_and_unsupported.md](docs/supported_and_unsupported.md)。
   白話:自己判、被攻擊、被外部資料打臉、最後還留一個「這條要人看」的標記。

> 可信度不是宣稱出來的,是把不誠實的那條路從 code 裡拆掉之後剩下的東西。

## 最快的驗證方式是什麼?(一鍵測試中心)

雙擊 **`啟動測試中心.bat`** → 自動開 `http://127.0.0.1:8765`,一頁測兩題:

- **題目一**:輸入自然語言任務 → 另開真實瀏覽器視窗全程可看,頁面串流每一步(思考→動作→驗證),最終由 verifier 判 PASS/FAIL/REFUSED;開放式(無可機讀驗證條件)任務照跑並錄 trace,結果誠實判 **UNKNOWN**(交人工審 trace),不 crash 也不 vacuous pass。
- **題目二**:輸入 ticker → 逐 item 檢視 status/provenance/XBRL/topic、audit manifest 與 servability reason codes；點任一 item 讀 normalized-source 原文，可下載原始 filing(byte-for-byte)重播 SHA-256。

(Codex gateway 自動啟動;需先 `codex login` 一次。另有獨立視窗版:`啟動Agent.bat`、`驗證SEC.bat`。)

白話「vacuous pass」:條件寫得太鬆,agent 什麼都沒做也算過 —— **這是最危險的失敗,因為它長得像成功。**

### Killer demos:每一行在證明什麼?

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

這些指令裡藏了兩個 house 原則,值得指出來:

- **`certify.py` 的 `certified 10 / contradicted 1` 是重點在那個 1。** 有一家被公司自己申報的 XBRL 打臉了,我留著這個數字 —— 一個從不 contradict 的 oracle 才是壞掉的 oracle。
- **`naive_baseline.py` 是對照錨。** 一個什麼都不做的笨基準在同一份 20-task 子集上實測 trivial-pass 20% —— **孤立的分數沒有意義,旁邊沒有笨基準的分數不該被相信。**

Task 1 用你自己的 **Codex OAuth**(預設走 gateway)實測:見 [docs/setup_codex_gateway.md](docs/setup_codex_gateway.md)。

## 支援範圍(Browser Agent,SPEC 6.4)

白話:這張表的下面兩列**不是做不到,是我不做**。登入、CAPTCHA、下單、發文都是不可逆動作 —— 一個會自作主張幫你按下「確認購買」的 agent,不是能力強,是危險。

| 類型 | 支援狀態 |
|---|---|
| 公開網站搜尋、多頁導航、資料擷取、公開文件下載 | 支援 |
| 答案型任務(查數字 / 問答,如「NVDA 現在股價多少」) | 支援:答案顯示於結果(📋 擷取內容);抓不到 → 誠實 **fail / unknown**,絕不無交付卻判 pass |
| 表單填寫 | 部分支援:僅公開、可逆、無登入、無金流 |
| 登入、CAPTCHA、購買/下單、發文/正式表單、付費資料 | **不支援**(責任邊界) |

**這張表現在中英文都成立,而且是在任何 side effect 之前強制。** 舊版 `_FORBIDDEN_INTENT` 只比對
英文 keyword,`screen_task("登入我的銀行帳戶")` 會回 `allowed=True` —— 那個洞我曾經選擇留著並公開
標註,因為當時唯一的修法(非英文一律拒絕)會砍掉中文任務能力。現在補的是中英文 intent 詞表,
並把 guard 提前到 `submit()`:被拒任務不進 queue、不呼叫 planner、不開 browser、不 `page.goto`。
單純提及(`閱讀 login 說明文件`、`Find an article about checkout UX`)仍放行,明確的副作用
(`Complete the payment flow with the saved card`、`Find checkout UX article, submit the form`)一律拒絕。
行為鎖在 `tests/test_browser_agent.py::test_screen_task_refuses_chinese_side_effects`、
`::test_screen_task_allows_read_only_mentions` 與
`tests/test_agent_service_demo.py::test_refused_task_never_reaches_planner_or_browser_queue`。

## SEC filing 分成哪幾類?(誠實邊界)

| Class | 行為 |
|---|---|
| standard | offset-exact span 抽取;Item 8 另經 XBRL 認證 |
| cross_reference_index(Intel/Citi/GE) | 自動偵測;可解析的 item body 由印刷頁碼錨點還原成 source-exact span(`partial` / `resolved_from_page_anchor`),body 被 index 拆成多段時以 `source_ranges[]` **多段重組**(如 Intel MD&A);頁碼圖被財報數字表污染或 XBRL 矛盾者**誠實降級 `unsupported`**,無錨點者留 `incorporated_by_reference`,一律 `needs_review`,**絕不偽裝成內容** |
| part_level_incorporation(Berkshire 類) | Part III 用**一句散文**打發掉整個 Part:「information required by this Part (Items 10, 11, 12, 13 and 14) is incorporated by reference from the …proxy statement」,沒有逐 item 標題。宣告句被解析成 source-exact span,涵蓋的 item 全標 `incorporated_by_reference` / `cross_reference_pointer` / `needs_review`,**絕不猜正文**。全 corpus 12 份文件只命中 1 次,零誤報 |
| plain_text_sgml(pre-2001) | text-mode normalize 保留行結構後正常抽取(`NORMALIZATION_VERSION` 1.1);該年代不存在的 item code 誠實標 `missing`,合併標題造成兩個 code 共用同一段者一律 `needs_review` |
| non_10k | 誠實標 unsupported |

輸入:ticker+year / CIK+year / accession / SEC URL / HTML upload / TXT upload。掃描 PDF:`unsupported`(正確作法是 OCR,見 insights)。

白話 `part_level_incorporation`:**這一類是評審用 Berkshire 打我打出來的。** 我原本的偵測是逐 item 標題導向,遇到「一句話打發整個 Part III」就全部回 `missing` —— 而且 `needs_review=false`,錯了還不叫人看。現在除了修掉它,還加了一張獨立的網:**任何 confidence 0 的 `missing` 一律強制 `needs_review`**(全 corpus 51 → 0)。第二張網比第一個修復重要 —— 它擋的是我還沒想到的那些。

白話 `cross_reference_index`:有些公司的 10-K 正文長得像一份索引 ——「本項內容請見後面某段印刷頁碼」。我照著那個印刷頁碼把正文撈回來、標成 `partial`;撈不回來的就承認撈不回來。**不是抽不到就寫空字串,是抽不到就說抽不到。**

## 專案結構長怎樣?

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

## 線上部署怎麼做的?(Zeabur — 線上可直接用)

| 服務 | URL | 狀態(2026-07-14 實測) |
|---|---|---|
| SEC Extractor + dashboard | **https://wealth-sec-ncku.zeabur.app** | 完整可用、免 auth(AAPL 23 items、warm repeat ~0.6s) |
| Browser Agent | **https://wealth-agent-ncku.zeabur.app** | **真實 LLM(OpenRouter `x-ai/grok-4.5`)**；frozen answer 與 mixed-operation suites 各實跑 **10/10**，另有 `/api/demo` 列出的免 key 示範任務 |

兩個 service 各自容器化(Docker 本地驗證通過,零修正):**wealth-sec**(SEC Extractor API + dashboard,`Dockerfile.wealth-sec`)與 **wealth-agent**(Browser Agent + Playwright Chromium,`Dockerfile.wealth-agent`),同一 repo root 為 build context,根目錄 `.dockerignore` 排除 `.venv` / `data/raw_filings` / `runs`(context 縮小約 830MB)。

拓撲、環境變數(`SEC_EDGAR_USER_AGENT`、`AGENT_LLM_MODE=direct` + `OPENAI_*`、選用 `ACCESS_TOKEN`;值只存 Zeabur,不進 repo)、`npx zeabur@latest` 部署/redeploy 指令與 smoke test 清單:見 [docs/deploy.md](docs/deploy.md)。

## 它哪裡還不行?(已知邊界,誠實揭露)

這一段是整份 README 我最不想寫、但最該寫的。**負面結果放在這裡,不放附錄;不改判、不軟化、不包裝。**

- **Task 2 的「11 家 held-out」是假的,而真的 held-out 現在有一份 probe(2026-07-16,未修)**:sweep1→3 那 11 家正是 FG-SEC-002/003/004 **被發現並修好的那批** —— 對一份 filing 修過之後它就不是 held-out,誠實的 held-out 數是 0。`tools/heldout_probe.py` 打 7 個從未調校過的 ticker(REIT 為主,因為 Item 16 `None.` 後面接印表索引的形狀,`refine.py` 的切割器只被 XOM/JPM 餵過),結果留在 `data/sec_eval/heldout_probe/`:
  - **`PLD` coverage 0.3725、`supported: true`、`pipeline_warnings: []`** —— 63% 的文件沒被分類,而系統一句話都沒說。coverage 低到這個程度卻不觸發任何警告,是 threshold 沒接線,不是判斷。
  - **`BRK-B` Item 7A 1,527 字 conf 0.97 `needs_review: false`,而它自己的 topic oracle 已經說 `weak`** —— 這是全 probe 唯二漏網的:oracle 叫了,沒有人接。`SPG` Item 9B(477 字、conf 1.0、topic weak)同理。
  - 好消息是 needs_review 那張網大致有效:`SPG` Item 16 吞掉整份 exhibit index(23,883 字)、`PLD` Item 16 吞進財報索引、`O` Item 2 只有 87 字的指路句 —— **三個都 `needs_review: true`**,沒有偽裝成乾淨結果。`TSM` 誠實回 `NotA10KFilerError`(20-F filer)。
  - 根因不用猜,`refine.py:190-200` 的註解自己寫了:`_HARD_BREAK_RE = ^\s*financial\s+section\s*$`「(XOM binds a "FINANCIAL SECTION"...)」、`_SOFT_BREAK_RE` 的 `index to financial statements`「(JPM binds the annual report...)」。`PLD` 的 `INDEX TO **THE CONSOLIDATED** FINANCIAL STATEMENTS` 中間多兩個字就漏掉,`SPG` 的 `EXHIBIT INDEX` 根本不在列舉裡。**這正是 FG-SEC-002 我自己寫下「不是規則寫錯,是用一條窄規則去接一個開放世界這個設計本身錯」、標了 Status: fixed,然後在隔壁函式重新出貨的同一個 bug。** 我把它留在這裡沒修,因為交件前改抽取核心比留著這條誠實的更危險。

- **同檔正文已還原(wrapper + cross-reference-index 頁碼錨點);僅跨檔 proxy statement 未 join**:JPM/XOM 的本檔附綁正文已由 page/section-anchor 重組(Item 8 獲 XBRL 3/3 認證);2026-07-11 page-top section anchoring 收尾 GS/JPM Item 1C,官方 CYD oracle 現為 **11 agree / 0 disagree**(kill-switch `SEC_WRAPPER_SECTION_ANCHOR=0`;見 `docs/eval_report.md` T2-3)。Intel/Citi 的 cross-reference-index 正文亦已由**同檔印刷頁碼錨點**重組為 source-exact `partial`(多段以 `source_ranges[]` 串接,needs_review;頁邊界對齊為 heuristic,XBRL 矛盾年度如 INTC FY2019 Item 8 誠實降 `unsupported`);僅指向**另外申報 proxy statement** 的 Item 10–14 維持誠實指標,刻意不 join、不出貨脆弱猜測(見 `docs/insights_and_directions.md` §2)。
  白話:**不是我 join 不起來那份 proxy statement,是我拒絕出貨一個脆弱的猜測。** 這是一筆交易 —— 用「少幾個 Item 的覆蓋率」換「零編造」。

- **Browser Agent 對本地 mock sites 完整驗證;真實網站對標仍弱(2026-07-10~11)**:外部基準子集 **Online-Mind2Web** 20 tasks(OSU-NLP-Group,**CC-BY-4.0**,COLM 2025,arXiv:2504.01382;`data/browser_eval/external/`)的 20%→33.3%→44.4%→61.1% 與 held-out 66.7% 都使用 task-text landmark contract,只適合觀察 verifier/repair 迭代,**不是 task-success 成績**。300 題 frozen run 完成 283/300(17 個 site_unreachable);歷史 runtime landmark hit **95/283 = 33.57%**,但其中含只驗網站名/普通動詞的弱條件,不得視為成功率。獨立 WebJudge outcome estimate 為 **21/283 = 7.42%**;其中 63/70 abstain 來自 judge prompt literal `success|failure` artifact,且 judge model 非官方 o4-mini,所以也不可與 leaderboard 比較。現在 importer 已停止把 heuristic landmark 當 authoritative `success_conditions`;未來 run 保留完整 trajectory,以修正後 independent WebJudge 或 human review 決定完成。舊 frozen artifacts 不重寫,詳見 `docs/eval_report.md`。Mock/eval 仍有 selector-repair ablation、prompt-injection defended ASR 0/5、step budgets 與完整 evidence artifacts。
  白話:那條 20%→33.3%→44.4%→61.1% 的漂亮上升曲線,**我親手把它降級成「不能當成功率」** —— 因為它的驗證條件鬆到只檢查網站名或普通動詞。同一批 trajectory 交給比較嚴的獨立 WebJudge,只剩 21/283 = 7.42%。而那個 7.42% 我也不准自己拿去跟 leaderboard 比,因為 63/70 的 abstain 是我 prompt 的 artifact、judge model 也不是官方的 o4-mini。**兩個數字我都留著,兩個數字我都不能宣稱。**

- **token-level boundary 已量化(2026-07-10)**:char-offset F1(建構性 gold,regression baseline,敏感度注入驗證 **AAPL F1 1.0→0.9267**,鎖在 `tests/test_scoring.py::test_sensitivity_injection_on_real_sweep3_aapl`)+ CYD 官方 iXBRL oracle(9/9 pass segment coverage 100%);人工標註的絕對正確率仍列 backlog。見 `docs/eval_report.md`。
  白話:**F1**(把「我抽的範圍」和「正確範圍」的重疊程度算成一個分數,愈高愈準);**iXBRL**(SEC 官方把標記直接埋進網頁裡的財報格式,可以當標準答案)。「敏感度注入驗證」是元層動作 —— 我故意把資料弄壞(把 Item 1A 的結尾砍掉 2 萬字、讓 Item 3 憑空消失、讓 Item 6 謊稱有內容),看偵測器會不會叫;它叫了,F1 從 1.0 掉到 **0.9267**,而且三種錯誤各自被歸類。**結論從「沒發現問題」升級成「有能力發現問題、而且沒發現」。** 但注意最後半句:人工標註的絕對正確率仍列 backlog,也就是說這個 gold 是我建構的,不是人標的。

- **pre-2001「不支援」是我自己的 bug,不是時代邊界 —— 而且我把它凍結成規格(2026-07-16 修正)**:舊版說法是「heading detector 0 candidate,誠實全 missing」。**那個 root cause 是假的。** 實測:`normalize_html` 只在 block tag 產生換行,純文字節點裡的 `\n` 被當空白吃掉,AAPL FY1996 的 6,246 個換行塌成 51 個、整份變成 52 行(最長一行 74,186 字元)—— detector 拿到的是一坨,當然 0 candidate。同一個 detector 餵進保留行結構的文字就吐 16 個候選。加了 text-mode 分支後 AAPL FY1996 抽出 **7 pass + 2 partial**、KO FY1997 **6 pass**,HTML 時代輸出逐位不變(`NORMALIZATION_VERSION` 1.0 → 1.1)。見 `docs/supported_and_unsupported.md` format-era 支援表。
  白話:**最丟臉的不是這個 bug,是我用一個測試(FG-SEC-009)把它凍結成「預期不支援」,還讓 CI 保護它,然後在 README 寫成時代邊界。** 一個假的 root cause + 一個守著它的測試 + 一份對外解釋 —— 三層都對上了,所以沒人會發現。這條的教訓不是「pre-2001 很重要」,是**「誠實揭露」本身也需要被驗證,否則它只是一個講得比較好聽的宣稱**。

- **這個 bug 的帳單在 2026-07-16 才結出來,而它翻掉了我對外講最久的一個結論(commit 36d42eb)**:同一個 bug 讓 NTU ItemSeg 30-slice(外部人工標註 gold)裡的兩份純文字檔回 `no items extracted`,我把它們記成「引擎失敗」就沒再追。修完之後那兩份是 HNET **0.9023**(edgar_crawler 0.8346)、Integrated Electric Systems **0.88** —— **都遠高於我自己其他 28 份的平均 0.6245**。30-slice macro-F1 因此 0.6245 → **0.6423**,在 30/30 對 30/30、雙方零失敗下高過 edgar_crawler 的 **0.6332**、datamule **0.6244**、edgartools **0.4386**。這是本 repo 在唯一一組外部人工標註 gold 上第一次贏過全部 vendored baseline。**但這個數字不能單獨引用,否則它就是過度宣稱 —— 三件事必須跟它一起講:**
  1. **我不是靠演算法贏的,是靠修掉自己的 bug 贏的。** F1 這條線我在 2026-07-10 親手判過 CLOSED、認過輸;開它的不是 tuning,是 `dfc3378` 的 normalize 修復。**而且我凍結掉的那一層,正是我表現最好的那一層**(純文字排版的行結構最乾淨、最好切)。
  2. **我先前報的「輸 0.0087」是假的,共同基準下是輸 0.0503。** `tools/head_to_head.py` 舊版只報 `macro_f1_filings`,分母是「引擎自己解析得動的 filing」—— **引擎自己的失敗會從自己的分數裡消失,愈脆弱的引擎排名愈高**。當時我有 2 個失敗,所以那張表在替我美化(0.5829 vs 0.6332 才是共同基準)。現在兩種分母並列。**這個偏誤是我在它對我不利時發現的;現在它對我有利(datamule 0.6244→0.5828),那更沒有理由不修。**
  3. **這個勝利在 artifact 裡躺了整整一天沒被發現。** `head_to_head.json` 最後寫入於 `69af928`,是 `dfc3378` 的祖先 —— **code 早就贏了,數字還在報輸。**

  白話:**這條為什麼留在「哪裡還不行」,而不是搬到前面當賣點?** 因為它證明的不是我的 parser 比較強,是**我的自我審計連續漏掉三件事**:報錯的分母、判錯的 root cause、過期的 artifact。而「能自我審計」正是這個專案的賣點 —— **一個審計不到自己計分方式的系統,那句「能自我審計」就只是一句好聽的話。** 兩欄分母表、逐筆數字與時序見 `docs/eval_report.md` head-to-head 段;重跑 `SEC_EDGAR_USER_AGENT=<contact> .venv\Scripts\python tools\head_to_head.py --slice 30 --engines ours,edgartools,edgar_crawler,datamule`。

- **答案型任務:agent 判 pass 的依據曾經是零證據(2026-07-16 修正)**:LLM 自己寫給自己的驗證條件 `answer_matches:.+` 對任何非空答案都成立,系統據此判 **pass、confidence 1.0**。現在條件要先過鑑別力檢查:對 22 條 decoy 語料命中率 ≥50% 就不算證據(`.+` 命中 22/22、`[0-9]+` 命中 12/22;真實 shape 條件如美元金額 0/22、四位年份 2/22),判決封頂 `unknown`,答案照常交付。frozen IR suite 因此從「10/10 pass」變成誠實的兩個數字:**gold 10/10、自我認證 5/10**。
  白話:**這是使用者以外唯一一個「我自己抓到自己說謊」的案例,而它躲過了前面所有防線** —— 因為 t0 baseline-subtraction 只擋「一開始就成立」的條件,擋不掉「對任何答案都成立」的條件。同一種病的另外一半,我花了很久才看見。修完之後那個漂亮的 10/10 就沒了,剩下 5/10 —— **但那 5 個是真的。**

- **自修復 cascade 曾經只跑在 mock site,沒接到部署路徑(2026-07-16 修正)**:診斷 → hash rebind → a11y purpose scoring 這條梯寫得完整、有 ablation、有 shadow check —— 然後只在 scripted `run()` 裡跑。評審在前端打的每一個任務走的是 `run_agentic()`,那裡 `repairs` **硬寫死 0**、selector memory 完全惰性:全專案的 memory key **100% 是 `mockshop::*`**,真實網站一個都沒學過。題目逐字要求的 "adjust locator strategies dynamically" 因此在部署路徑上不存在。現已接上(重用既有 primitive,非平行實作):repairs 真實計數。**但 selector memory 只接了一半,這是本條現在的誠實版本**:`worker.py:354` 把 `site` 寫死成字面值 `"web"`,而 memory key 是 `{site}::{task_type}::{purpose}`(`memory_store.py:25`)—— 所以部署路徑學到的 key 只可能是 `web::agentic::*`,**整個網際網路共用一個 bucket**,arxiv 學到的 `search_box` 會在別的站被當首選試打。加上 `RUNS` 落在 Zeabur 的 ephemeral disk、容器重啟即歸零、repo 內 committed 的 selector memory 檔是 0 個 —— **「修好一次之後永遠免費」的 cross-run payoff 在 production 沒有證據,而且結構上不成立。** 這行只值一個 registrable-domain 的改動,我沒在交件前動它:`site` 同時是 ablation 的 memory-transfer key(v1 學、v2 重用),改成動態 domain 會讓 v1/v2 落到不同 bucket、打斷既有的 repair ablation 證據鏈。**先誠實揭露,不趕在死線前動抽取以外的核心。**
  白話:**這條是「文件說有、code 說沒有」裡最貴的一種 —— 因為它不是唬爛,是真的寫好了,只是沒接線。** `docs/architecture.md` 當時精確揭露了「它只在 Script Mode 跑」,但 README 仍把它列成 Task 1 能力、還導引評審去點那個 scripted demo。**揭露放在對的地方才叫揭露,放在沒人讀的那一頁叫存檔。**

- **Browser 4 個 measure-first 弱點已於 2026-07-10 修復**(verifier filename-needle bypass、query-echo silent failure、repair fallback 到不可行元素、bait-field tie-break;commit bcdc9cf / d5481eb):校準 specificity 0.9583→1.0、FP rate 0.0417→0.0、impossible silent_failure_rate 0.1→0.0、perception degradation curve 尾端 0.0→1.0。原 `test_known_*` 已翻寫為 `test_fixed_*` 並重跑 artifact。另修復開放式(零條件)任務 crash → 誠實 unknown(FG-BROWSER-006,commit f535c93)。逐條前→後見 `docs/failure_gallery.md` FG-BROWSER-002~006 與 `docs/eval_report.md`「修復迭代」段。
  白話 measure-first:**先寫一個會失敗的測試把弱點釘死,再去修。** 所以每一條都有「前→後」兩個數字,不是修完才回頭補一個好看的數字。

- **INTC 營收 false pass 三重根因已修復(2026-07-10,FG-BROWSER-007)**:使用者親測「找 intc 10-k 最新營收數字」被判 PASS 卻沒交付答案。三根因分別結構性修復——(1) premature-landmark → verifier baseline-subtraction(t0 即成立的條件視為 landmark 剔除,INTC repro pass→unknown;commit 8437826);(2) 答案無交付通道 → answer channel + verifier `answer_matches`(沒抓到答案 → 誠實 fail,不偽 pass;commit 3431335);(3) 卡住無視覺升級 → auto vision escalation + scroll + 新分頁跟隨(commit 1c8f103)。見 `docs/eval_report.md`「修復迭代 2」段。
  白話:這是最丟臉也最有價值的一條 —— **使用者親手抓到我的系統說謊。** 它判 PASS,但沒給出任何數字。三個根因我都用結構性修復處理,其中最關鍵的是 baseline-subtraction:一個在任務還沒開始(t0)就已經成立的「條件」,根本不算完成證據,得剔除。修完之後同一個 INTC 重現案例從 pass 變 unknown —— **變難看了,但變誠實了。**

## AI 是怎麼參與的?(AI 協作方式)

AI 協作證據記錄於 [prompts/](prompts/README.md)：verbatim excerpts 保留可核對的原文邊界，derived decision records 則明確標示為摘要而非逐字 prompt。`tools/verify_prompt_provenance.py` 會核對分類、原始 Git blob 與 verbatim body hash；設計取捨與 AI 使用邊界見 [docs/ai_collaboration_report.md](docs/ai_collaboration_report.md)。

白話:**逐字的 prompt 和事後整理的摘要,我分開標,而且用程式去核對,不是靠我自己說。** `verify_prompt_provenance.py` 會回頭比對 Git blob 與 verbatim body hash —— 我改一個字,它就會抓到。

> 這整個 repo 的價值不在「AI 幫我寫了多少 code」,而在「哪些結論我敢簽名、哪些我當場說我不敢」。
