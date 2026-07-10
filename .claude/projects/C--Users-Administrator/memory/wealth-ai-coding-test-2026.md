---
name: wealth-ai-coding-test-2026
description: E:\Side_Project\wealth = AI Coding Test 2026 reliability platform; Python .venv; AI has standing commit/push authorization
metadata: 
  node_type: memory
  type: project
  originSessionId: 656ed1cc-12d6-49aa-be35-911e5234b494
---

`E:\Side_Project\wealth`(GitHub: Tim096/wealth, private)是「AI Coding Test 2026」專案:一套 AI reliability platform,含兩題——Browser Agent 與 SEC 10-K Item extractor。完整 SPEC 在 `docs/SPEC.md`,是所有開發決策的最高依據(評分標準優先)。

**Why:** 使用者 2026-07-10 交付 SPEC 並明示授權 AI 自主產生 prompt、git commit、push(SPEC 第 11–12 節定義時機)。這覆蓋了全域 CLAUDE.md 的「never commit/push without confirmation」——僅限此 repo。

**How to apply:**
- Commit 粒度(使用者 2026-07-10 指示):每個階段、每次錯誤、每次嘗試、每個自我指令都獨立 commit + push;bug 修復用獨立 fix commit,不 squash。
- 環境:全部用 repo-local `.venv`(使用者指示「All env use .venv 自建自己需要的一切不夠就自己裝」),Python 3.12,pydantic schemas 對應 SPEC TS 型別、欄位名一致。缺什麼套件自己裝進 .venv。
- 每次有影響設計的決策要寫 `prompts/` log(含 rejected);commit 分邏輯單位,message 用 SPEC 11.3 格式;push 前跑 pytest。
- 已完成:packages/*(5 個)+ **SEC pipeline 完整**(normalize/headings/toc/boundary/fetcher/resolver/main_doc/refine)+ 42 tests。跑過 11 家真實 10-K(sweep2,data/sec_eval/records/)。
- **對抗式稽核 harness**(56-agent workflow)是本專案驗證核心:證偽自報 pass rate,抓到 15 個 silent failure(FG-SEC-002/003/004:reference-stub 誤標、trailing furniture 洩漏、terminal runaway = wrapper 10-K,即主管點名的 Intel/Citi corner case)已修復。
- 主管評分重點(2026-07-10 使用者轉述):(1)不是能做出來就好,要看思路與連主管都沒想到的優化方向;(2)重視前沿作法如 harness engineering;(3)**驗證能力是最看重的**——LLM-as-judge 判財報是壞主意,OCR/XBRL/結構化資料才對;(4)向主管要 API key = 直接淘汰(資安);(5)Intel/Citi wrapper 10-K 是常見不完整案例。策略思路寫在 docs/insights_and_directions.md。
- 已完成(2026-07-10 續):cross-reference-index filing 偵測(`cross_ref.py`,Intel/Citi/GE 類,含 Citi 無「Item」前綴的 bare index)——INTC FY2019/2020/2025 + Citi 全正確歸類,Item 14 = needs_review 指標(直接修掉主管點名的「Item 14 標 ok」錯誤)。XBRL 獨立 oracle(`xbrl.py` + `tools/certify.py`)cross-check Item 8 對 SEC companyfacts:11 家 7 certified / 3 contradicted,與 pipeline 分類零分歧。ItemSegment 加 provenance/needs_review/xbrl_check。52 tests。docs/supported_and_unsupported.md 建立。
- **兩題皆已實作可執行**(2026-07-10 ultracode round):
  - Browser Agent:`packages/browser_agent/`(executor/observer/verifier/repair/agent/memory_store/capability)。killer demo(`tools/browser_killer_demo.py`)v1→v2 selector 自修復真跑;eval set(4 layer 含 held-out v3)+ runner。capability guard code-enforced(拒 login/purchase)。借 Agent-E mmid(data-aid)技術(MIT,見 docs/ATTRIBUTION.md)。
  - Eval Dashboard:`apps/web/eval-dashboard/`(自包含 HTML,真實數據)+ Artifact URL。
  - XBRL oracle gate 進 status(certify_item8),evidence 走共用 EvidenceStore(兩題),PDF unsupported code-enforced。
- **驗證循環(user 要 full marks)**:自建 16-agent 對抗式評分 workflow(8 rubric 維度 grade + adversarial verify)。三輪:6.5 → 7.5 → (第三輪 pending)。每輪 findings 都逐一修並 commit。
- **授權立場**:copyleft(edgar-crawler GPL、Skyvern AGPL)只借想法;permissive(Agent-E/edgartools MIT)可抄 code。見 docs/ATTRIBUTION.md、docs/prior_art.md。
- **2026-07-10 續(第二輪深化)**:
  - Task 1 Agent Mode 實接:LLM 驅動瀏覽器(`browser_agent/planner.py`),**預設走 Codex OAuth via 本地 gateway**(`tools/codex_gateway.py` + `config/agent.toml`,base http://127.0.0.1:8791/v1,model gpt-5.3-codex)。user 只需 `codex login`。gateway 有 mock/codex/openai 三後端,e2e 已驗證(mock 驅動 agent → PASS)。手動測試指南 docs/setup_codex_gateway.md、manual_test_browser.md。key 從不進 repo。
  - Task 2 **page-anchor resolution 完成 Intel 核心任務**(`sec_core/page_map.py`,LIS 重建頁碼→offset):Intel 7 item 抽回真實正文,Item 1A=96K、Item 8=202K 且 **XBRL 認證通過**(兩獨立方法互證)。provenance=resolved_from_page_anchor/partial/needs_review。
  - Task 2 **topic-consistency oracle**(`sec_core/topic_check.py`):每個 item 都有獨立 lexical 主題一致性檢查(不只 Item 8 XBRL),回答「全 item status 可信」。11 家零誤報。
  - 89 tests。授權:Agent-E mmid(MIT)已借;copyleft 只借想法。
- 驗證分數軌跡:6.5→7.5→7.88(三輪 16-agent 對抗式評分)。
- 所有 commit push 到 Tim096/wealth(~40 commits)。
- 有一組要問主管的問題(見對話),使用者會代為轉問。
