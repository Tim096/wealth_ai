# Giants Research Synthesis — Task 1 Browser Agent 超越 SOTA 路線圖

日期:2026-07-10
輸入:六份已驗證的 gap analysis(逐條對照本 repo 程式碼行號核實過 status)
範圍:packages/browser_agent、packages/browser_core、packages/eval_core、tools/、data/browser_eval

對照對象:

| 代號 | 專案 / 論文 | 身份 |
|---|---|---|
| BU | browser-use(github.com/browser-use/browser-use) | Online-Mind2Web 榜首 bu-max 97.0%(leaderboard 快照 2026-07-10;live 榜數字會動,需附 retrieval date 方可重現) |
| SK | Skyvern(github.com/Skyvern-AI/skyvern) | vision+DOM hybrid,cached-script self-healing(Code 2.0/v3) |
| SG | Stagehand v3(github.com/browserbase/stagehand) | self-healing replay cache、a11y diff、EncodedId grounding |
| OM | Online-Mind2Web + WebJudge(OSU-NLP-Group,COLM 2025,arXiv:2504.01382) | 300 題 live benchmark + LLM trace judge |
| SV | 2025-2026 survey:Magentic-One(arXiv:2411.04468)、WebChallenger(arXiv:2606.10423)、Alumnium(WebVoyager #1 98.5%,**self-reported WebVoyager 自評協定,judge 未經人類一致性校準,證據力弱;快照 2026-07-10**)、OpenAI CUA/Operator、Anthropic computer-use、steel.dev leaderboard | 榜首機制彙整 |
| BG | BrowserGym + AgentLab(ServiceNow,arXiv:2412.05467)+ WebVoyager eval protocol(arXiv:2401.13919) | eval harness 工程 |
| WC | WebCanvas / Mind2Web-Live(iMeanAI,arXiv:2406.12373) | key-node 中間態 live 評測、URL-first 抗漂移、latch 語義 |
| AE | Agent-E(Emergence AI,arXiv:2407.13032) | hierarchical planner/actor、DOM distillation、change observation |
| AO | AgentOccam(Amazon,ICLR 2025,arXiv:2410.13825) | 極簡反命題:對齊 action/obs space 勝過堆機制 |
| WA | WorkArena / WorkArena++(ServiceNow,arXiv:2403.07718 / 2407.05291) | 企業 compositional 任務、seeded 可重現、collateral-damage watcher |
| M2 | Mind2Web 2(OSU-NLP,NeurIPS'25 D&B,arXiv:2506.21506) | rubric tree + Agent-as-a-Judge(99.03% leaf agreement) |
| VWA | VisualWebArena(CMU,arXiv:2401.13649) | 視覺任務 benchmark、observation-only vision-gain 分層測量 |
| SEC | 安全軸:ST-WebAgentBench(2410.06703)、SafeArena(2503.04957)、WASP(2504.18575)、EIA(2409.11295)、SecureWebArena(2510.10073)、WAInjectBench(2510.01354) | policy-compliance + prompt-injection 兩威脅模型、CuP / intermediate-vs-e2e ASR |

---

## 1. 對照表:我們 vs 巨人(按評分維度)

圖例:**領先** = 我們的機制更強或對方問題在我們架構結構上不存在;**互有** = 各有半邊;**落後** = 對方有、我們缺。

### 1.1 Self-correction(自我修正)

| 對象 | 對方機制 | 我們現況 | 判定 |
|---|---|---|---|
| BU | 5 級 cascading locator healing(EXACT/STABLE hash→XPath→AX name→唯一屬性)+ ActionLoopDetector 遞增 nudge | diagnosis-driven repair(repair.py:44-68 先診斷後修)、purpose-based a11y re-grounding + feasibility gate(repair.py:100-175)、零 LLM 成本修復;但無確定性 element hash、loop 偵測(trajectory.py)只在 run 後觀測不回饋 | 互有 |
| SK | 結構化 element hash rebind(exactly-1-match)、四維修復預算、CODE_FIXABLE triage | RepairEvent telemetry + preferred_selector write-back 已有(selector_memory.py、memory_store.py:49-51);無 hash rebind、無預算 cap、taxonomy 缺 anti-bot/auth/site-down 類 | 互有 |
| SG | selector 失敗→重拍 snapshot→原意圖 re-ground→重試→顯式失敗 | **同構流程已是我們核心**(agent.py:335-426),且 agent mode 每回合以 data-aid 重新 grounding 天然 self-healing | 領先 |
| SV(Magentic-One) | dual-ledger 停滯偵測→更新 facts→重寫 plan | vision_escalation_reason(agent.py:109-127)只升級感知不觸發 replan;preflight plan 整場只跑一次 | 落後 |

### 1.2 Self-maintenance(自我維護 / 跨 run 記憶)

| 對象 | 對方機制 | 我們現況 | 判定 |
|---|---|---|---|
| BU/SK | repair 成功永久 write-back,同一 UI 變更不重複診斷 | Script Mode 已有完整迴圈(repair→RepairEvent→promote→save→下次先讀);**Agent Mode(run_agentic)完全不碰 memory**,每 run 全額 LLM 成本 | 互有 |
| SG | sha256(instruction+URL+variable-keys) 快取 + %key% placeholder + zero-token trajectory replay | 快取只存 selector、以 (site,task_type,purpose) 為鍵;fill 值不進快取(**結構上免疫 stale-payload 問題,領先**);但無 trajectory-level replay | 互有 |
| SK | user_detail_query 個人化解耦 | **already_have by construction**:資料每 run 由 Step.value 新鮮注入,字面用戶資料永不落快取 | 領先 |
| SV | shadow-mode 快取抽驗 + cache FP-rate | dom_fingerprint 有存從未讀回;無抽樣重驗 | 落後 |

### 1.3 Eval depth(評測深度)

| 對象 | 對方機制 | 我們現況 | 判定 |
|---|---|---|---|
| OM | 300 題 live 任務、reference_length 難度分層、WebJudge(85.7% 人類一致)、任務失效維護協議 | 23 題自建 deterministic offline set + impossible 軸(12 題)+ open-ended 軸 + degradation curve(perception/action/execution × 3 強度)+ pass@k/flakiness;**judge 校準(Rogan-Gladen sens 1.0/spec 1.0,n=50:24 success + 26 corrupted,confusion tp24/fn0/fp0/tn26;雙 1.0 出自小校準集,artifact 未附 CI)是對方沒有的**;缺外部任務廣度、缺第二裁判 | 互有 |
| BG | oracle cheat() 全管線校準、repro manifest、per-task 狀態三分法、watchdog relaunch、seeded 任務家族 | verifier 離線校準有(calibrate_verifier.py)但無 end-to-end oracle;harness 單迴圈、無 per-task 落盤、一個 hang 卡全場;無 repro manifest | 落後 |
| SV | ablation + backbone-sensitivity 紀律 | degradation curve 是對「環境」消融,對「我們元件」的逐一移除量測全缺 | 落後 |
| SK | 兩段式 judge(deterministic gate + LLM judge)、judge I/O artifacts | deterministic gate 與 artifact 保留**比 Skyvern 強**(全確定性 + EvidenceStore + 校準);缺 LLM 第二意見與 is_updated 旗標 | 互有 |

### 1.4 Silent-failure prevention(無聲失敗防治)— 我們的主場

| 對象 | 對方機制 | 我們現況 | 判定 |
|---|---|---|---|
| BU | pre_done checklist、done-only schema 強迫交部分結果 | **無聲耗盡步數變假 pass 在我們架構不可能**:任何終止路徑(done/give_up/max_steps)一律走 verify_contract 對真實頁面出 verdict(agent.py:614-616);缺 done 前強制自查與 done-rejection 前閘門 | 領先(缺前閘門) |
| OM(WebJudge) | prompt 約定 judge 不吃 agent 自述 | **程式化保證,比 prompt 約定強**:answer_matches 只吃 extract_text 真實頁面文字(verifier.py:74-86)、query-echo masking(verifier.py:24-35)、baseline subtraction(verifier.py:112-133)、回歸測試防 judge 吃自述 | 領先 |
| SG | forced structured done + claimed-vs-verified 交叉比對、幻覺四分類、EncodedId 前置拒絕 | verdict 從不由 prose 推斷(更強);但 TaskRun 無 claim 欄位餓死 false_success 最強特徵、幻覺 aid 未在執行前攔截、幻覺分類只有 2/4 | 互有 |
| SK | action-history evidence rule(中途成立的證據仍算) | combine_checks 全條件必過 + unknown 傳播(verdict.py:26-65)封死 under-claim 假 pass;但最終 verdict 只看最後 Observation,中途成立後導航離開→誤判 fail/unknown(假陰性) | 互有 |
| BG | per-step validate() | **already_have**:agent mode 每回合 verify_contract、與最終 verdict 同一證據面(agent.py:510-517) | 領先 |

### 1.5 Cost analysis(成本分析)

| 對象 | 對方機制 | 我們現況 | 判定 |
|---|---|---|---|
| SK | cycles/tokens/USD/wall-clock 四維硬預算 | llm_cost 有逐 call 累計(agent.py:544-545)但**從不檢查上限、不落 TaskRun——是死碼**;唯一限制 max_steps=8 | 落後 |
| BG | cache-aware 計價、phase 時間拆解、cost-per-success | 有 per-call cost_usd + per-step latency_ms + docs/cost_latency_report.md;無 cost-per-success、無 phase 拆解 | 落後 |
| SK | 大 planner / 小模型 relocation 分層 | 我們 repair 路徑**零 LLM 成本(確定性)**,已優於分層;分層只在未來加 LLM relocation rung 時才相關 | 領先 |
| BU | use_vision='auto' 按需截圖 | **already_have 等價**:AGENT_VISION 三態 + heuristic 觸發升級(agent.py:216-224),達成視覺按需付費 | 領先 |

---

## 2. Prioritized Backlog(去重後;只列 status = missing / partial)

去重原則:同一機制被多個巨人各自命名者合併為一項,標注所有來源。effort:S(<1 天)/ M(1-3 天)/ L(>3 天)。

### P0 — 直接影響評分維度、原料齊全、S/M 工作量

**P0-1 In-loop 停滯偵測 + 遞增 nudge + replan 觸發** `S / high`
- 來源合併:BU ActionLoopDetector、Magentic-One dual-ledger、SV deterministic loop detector、BU consecutive_failures→REPLAN
- What:run_agentic 迴圈內呼叫 trajectory.repetition_report(已存在,現只在 run 後觀測)+ page fingerprint 停滯計數,命中時把遞增語氣 nudge(5/8/12 步階梯)注入 planner user message;連續失敗達閾值注入 REPLAN 提示(重述 facts + 剩餘步數)。
- Why:loop 是 agent 最常見的步數浪費;兩半原料(repetition_report、page_hashes)都已存在,只差接線。
- 落點:`packages/browser_agent/agent.py` run_agentic(L502-613)、`planner.py` next_action history 參數。

**P0-2 Hallucinated-aid / 座標 pre-execution gate** `S / high`
- 來源:SG EncodedId grounding contract
- What:_build_action 檢查 `aid in {c.index for c in obs.candidates}`,mouse x,y 對照候選座標範圍;不合法→noop decision + reason "hallucinated aid",不進 executor。
- Why:現在幻覺 aid=999 會燒一步、被誤診為 selector_not_found/UI-drift,污染失敗歸因。
- 落點:`packages/browser_agent/planner.py:115-149`(obs 參數目前未被引用)。

**P0-3 終止雙閘門:pre-done checklist + done-rejection** `S / high`
- 來源合併:BU pre_done_verification、SV 終止雙閘門
- What:(1) planner _SYSTEM 加結構化 done 前自查段(數 item 數量、filter 全套用、逐項核對);(2) agent.py done 分支在 loop verdict != pass 且步數未盡時駁回一次並附具體理由(複用 give_up 駁回模式 agent.py:558-565)。
- Why:提早 done 白白放棄剩餘步數,是 open-ended/unknown 收尾任務的主要損分點;後閘門已極強,前閘門是最後一塊。
- 落點:`planner.py:26-70` _SYSTEM、`agent.py:566` 前。

**P0-4 每步 env_change 證據 + 新元素 `*` 標記 + 空 diff 訊號** `S / high`
- 來源合併:**AE change observation(機制本體)**、SV env_change、SG a11y line diff、BU `*[index]` 新元素標記
- 機制先例:Agent-E `dom_mutation_observer.py` 在每個 action 前 subscribe MutationObserver、執行後 sleep 100ms 再讀新節點,回饋 verbatim「new elements have appeared … the action is not yet executed」把「出現 dropdown = 動作未完成」教給 LLM。**已知限制(其 docstring 自承):只偵測新增節點/文字,盲於 attribute/style(aria-expanded、visibility),100ms 窗口對慢速 async 有 race。我們以「連續兩次 observation 用身分鍵 diff」在結構上更優(無 race、可偵測消失與屬性變化)——引 AE 作機制先例但不照抄。**
- What:observe 後以 (tag,id,name,text,x,y) 身份鍵與上一步 diff:(a) history entry 從 "click:ok" 升級為附一句 env_change(URL 變化 / 首行 diff / 「頁面無變化」);(b) 新出現互動元素在 _candidate_lines 加 `*` 前綴 + _SYSTEM 一行教學;(c) click 後空 diff = silent-failure 訊號進診斷。
- Why:直接對應 FG-BROWSER autocomplete/dropdown 弱點與 memory 記載的 measure-first 待決項;零 LLM 成本。
- 落點:`agent.py:588` 附近、`observer.py:59-75`(ElementCandidate 加 is_new)、`planner.py:89-112`。

**P0-5 Trace 級 per-condition 證據累積 + per-step obs 持久化** `S / high`
- 來源合併:**WC key-node latch 語義(既有解法參照)**、SK action-history evidence rule、SG post-step probe evidence
- What:run_agentic 每輪對每條 success condition 記 best-observed status(satisfied-at-step-N),最終 verify_contract 併入;StepTrace 持久化 obs excerpt/hash + candidate 摘要(現在被消費後丟棄)。
- Why:中途真正成立、之後導航離開的 text_visible 目前被誤判 fail/unknown(假陰性);同時餵飽 false_success detector 所需的 per-step 證據。verifier 仍唯一裁判。
- 設計參照(WebCanvas arXiv:2406.12373,`evaluate/step_score.py`):key node = 全 critical、無序集合、**latch(單向閂鎖)語義**——每步對所有未滿足節點重掃 `score=max(old,new)`,滿足即永久記帳,正是我們要的「中途成立不撤銷」。可直接借:URL-first 節點識別(最抗漂移的 evidence source 優先)、選擇器 3 層祖先漂移容忍、Appendix C「必要條件→URL 可表達否」決策樹改寫成 contract 條件 authoring guideline。**但要補 WC 的盲點:latch 無撤銷對「先滿足後被破壞」型任務(購物車先加後刪)會誤判成功——我們需引入「可撤銷條件」型別。反面教材:WC semantic match 用 `eval()` 解析 LLM 輸出、3 次重試後靜默歸 0,是 silent-failure 案例。**
- 落點:`agent.py` run_agentic 迴圈 + StepTrace(L139-151)、`verifier.py:136` 介面。

**P0-6 Budget caps + llm_cost 上 TaskRun + cost-per-success** `S / high`
- 來源合併:SK 四維硬預算、BG cache-aware cost accounting
- What:Budget dataclass(steps/tokens/USD/wall-clock)於迴圈頭檢查;TaskRun 補 llm_cost_usd(修死碼)+ phase timings(planner call / action exec / verify);compute_metrics 加 cost-per-success、cost-per-repair。
- Why:llm_cost 累計後被丟棄,eval rows 帶零成本——成本分析維度目前無法誠實作答;openai_client.py:40 已回 cost_usd,plumbing 一欄之遙。
- 落點:`agent.py:502,618-621`、`tools/browser_eval.py:111-124`。

**P0-7 Element structural hash + cascade rebinding(MatchLevel telemetry)** `M / high`
- 來源合併:BU 5 級 cascading locator、SK cleaned-JSON SHA256 rebind
- What:per-element cleaned structural hash(EXACT/STABLE 兩級,濾暫態 CSS class 的 DYNAMIC_CLASS_PATTERNS);SelectorVersion 加 element_hash;_resolve_and_run 先 hash-match 快路徑(exactly-1 rebind,0/>1 落回 purpose 評分 repair);每級 MatchLevel 命中率進 telemetry。
- Why:兩榜首共同機制;我們已有 durable-selector 鏈與 purpose 評分(功能覆蓋後兩級),補上確定性身份雜湊即完成整條 cascade,修復成功率與跨 run 穩定性同升。
- 落點:`observer.py` _ENUMERATE_JS(補抓 parent path/靜態 attrs)、`selector_memory.py:21-48`、`repair.py` repair_target 前、`agent.py:335-426`。

**P0-8 Advisory second judge(WebJudge→Agent-as-a-Judge 世代)** `S-M / high`
- 來源合併:**M2 rubric-tree Agent-as-a-Judge(最新設計參照)**、OM WebJudge、SK two-stage judge、SV trace judge、BG open-ended LLM-judge fallback
- What:tools 側 opt-in 第二裁判,**每條 contract 條件一個 binary micro-judgment + 決定論聚合**(非「整段 trajectory 一次 LLM 判卷」的 WebJudge 式 task-level 二審),temperature 0、顯式 abstain 態,`browser_eval.py --second-judge`;輸出 per-condition binary + 理由,與主 verifier 做**逐條件 diff**,不一致→flag 進 adjudication artifact(同 SEC track `tools/triangulate.py` disagree→needs_review 模式);open-ended unknown bucket 因此獲得分數通道。**verifier 仍是 runtime 唯一裁判**(與 false_success.py:6-9 同契約)。
- Why:是我們自認的「no external second judge」缺口;SEC 側已有同構先例可直接移植。
- 設計依據(引用鏈,直接指向「分解本身是主因」):WebJudge(o4-mini,**85.7%** 人類 agreement,arXiv:2504.01382)→ Mind2Web 2 Agent-as-a-Judge(**99.03%** leaf-level,arXiv:2506.21506,`mind2web2/verification_tree.py`)。可直接抄:(1) **gate-then-average 聚合**取代平坦 AND(critical=gate 不進平均 / non-critical=平均給 partial credit / sequential 依賴 short-circuit),給比 spec-pass-rate 更有資訊量的 partial-completion 指標;(2) **Extractor/Verifier 分離**(先抽取缺→null 禁臆造,再對抽取物驗證;「來源無關/不可達→not supported」防 hallucinated evidence);(3) judge 自身的 **stub-pass 煙霧測試**(verification 全 stub 成 True 跑一遍抓 runtime error);(4) **evidence pre-caching**(判定所依據的頁面先快取再判,可重放可審計);(5) 校準協定 rubric-level 盲審→node-level 人工重標→discrepancy 複核(先驗人再驗機),回報 N/720 式 leaf-level 正確率而非 task-level agreement。θ=3/CoT 消融數據(arXiv:2504.01382)現成作 WebJudge 側設計依據。
- 落點:新 `packages/browser_agent/second_judge.py`(走 llm_core/openai_client)+ `tools/browser_eval.py`。

**P0-9 Harness per-task 持久化 + watchdog** `S+M / high`
- 來源合併:BG silent-failure trichotomy、BG relaunch loop
- What:(1) 每 task try/finally 寫 `runs/browser_eval/<task_id>/summary.json`,harness 層 status = done/error/incomplete(與 verdict 層 pass/fail/unknown/refused 分離),metrics 只計 done、incomplete 另報;(2) per-task timeout watchdog——win32 無 signal.alarm,採 subprocess-per-task 或 Playwright-level timeout;relaunch 時遮罩已完成任務,>30% error 即停。
- Why:現在一個 Playwright hang 卡全場、mid-set crash 丟光所有 rows 且無 artifact——eval 結果本身有無聲失敗。
- 落點:`tools/browser_eval.py:181-243`、`impossible_tasks.py`、`open_ended_tasks.py`。

**P0-10 Agent-mode 跨 run 記憶 + shadow-mode 快取驗證(自我維護,自 P1-4 升級)** `M / high`
- 來源合併:SK fallback write-back(agent mode 半邊)、SG replay cache、SV shadow-mode、WC scheduled-replay 失效報告 loop
- What:run_agentic 內以 (site, task_type, purpose/step-label) 記錄 planner 選中的 selector/href,下輪先查再問 LLM(複用 MemoryStore write-back 模式);script-mode 快取命中時抽樣同步跑 repair_target 比對,記 cache FP-rate/divergence 進 cost 報告;dom_fingerprint 開始被讀回。
- **優先級修正(解決自身矛盾)**:原列 P1-4。§3.2 自述此項是「cost 維度最大槓桿」,且 self-maintenance 是題目兩大明示能力之一,卻無任何 P0——被自己論證為高槓桿的項目排 P1 是優先級自相矛盾。故升級為 P0,原 P1-4 全數併入此項。
- Why:agent mode 目前每 run 全額 LLM 成本,成功恢復全被丟棄;WebCanvas 的 scheduled replay + 失效報告(3 個月修 18 筆、每筆人力約初標一半)是資料維護 loop 的現成參照,對應我們 self-maintenance 評分項。
- 落點:新 `packages/browser_agent/replay_cache.py` + `agent.py:579-601`、`docs/cost_latency_report.md`。

**P0-11 Scalability:parallel eval + session pool + subprocess-per-task 隔離** `M / high`
- 來源合併:BU/Skyvern 並行執行與 session pool、BG watchdog relaunch;綁定 P0-9
- What:(1) harness 層 worker pool 並行跑多 task(process pool,每 worker 獨立 Playwright context/browser session);(2) session/context pool 復用瀏覽器實例攤平冷啟成本;(3) **subprocess-per-task 隔離**——每 task 跑在子行程,win32 無 signal.alarm 故以子行程 timeout watchdog 收殺 hang(此即 P0-9 watchdog 的實作載體,兩項共用同一隔離邊界);(4) 多 session 成本模型:並發度 × per-session cost/latency 進 cost 報告。
- Why:題目明文要求 analysis of scalability,現行 harness 是單迴圈序列跑、零並行、無 session 復用、無多 session 成本模型——scalability 維度目前零機制、零 backlog、無法誠實作答。
- 落點:`tools/browser_eval.py`(worker pool + 子行程 driver)、新 `tools/eval_worker.py`、`docs/cost_latency_report.md`。

### P1 — 評測廣度與歸因深度

**P1-1 Online-Mind2Web 任務子集匯入(署名)+ naive baseline + 失效維護協議** `M / high`
- 來源:OM 三項合併(任務匯入、naive-search-agent shortcut 檢測、任務失效協議)
- What:HF gated dataset(OSU-NLP-Group/Online-Mind2Web)按 reference_length 分層抽 30-60 題,編譯為 BrowserTaskContract,入 tasks.json 新 layer `external_live_tasks`(**每筆註明來源與 attribution**);tools/naive_baseline.py(query→點第一結果→verifier 裁決)報 trivial-pass 率(paper 對照數字 22% vs 51% 現成可引);live 任務加 added/replaced 欄位 + update history。
- Why:直接回應「eval set breadth vs 136-site benchmarks」弱點;live plumbing(tools/browser_agent_live.py)已存在。
- 落點:新 `tools/import_mind2web.py`、`tools/naive_baseline.py`、`data/browser_eval/tasks.json`、`docs/eval_report.md`。

**P1-2 Per-run reproducibility manifest** `S / high`
- 來源:BG。What:git hash、dirty files、package/playwright 版本、task-set hash 寫 repro_info.json + committed `data/browser_eval/reproducibility_journal.csv`。Why:repo 最近兩個 commit 都在修 stale numbers,病因就是無 manifest。落點:新 `tools/repro_info.py`,browser_eval main() 呼叫。

**P1-3 Oracle cheat scripts 過全管線** `M / high`
- 來源:BG。What:tasks.json 每題加 oracle_steps,`browser_eval.py --oracle` 驅動腳本解法(+ 損毀變體)過 BrowserAgent.run,斷言 verifier 對 oracle pass-rate 1.0 / sabotaged 0.0,作 judge 校準頭條數字。Why:現行校準是離線合成 triples,未驗證 harness+真實執行路徑能認出正確軌跡。落點:`tools/browser_eval.py`、`data/browser_eval/tasks.json`。

**P1-4 → 已升級為 P0-10**(cost 維度最大槓桿 + self-maintenance 為題目明示能力,不應排 P1;見 P0-10)。shadow-mode 抽驗、cache FP-rate、dom_fingerprint 讀回等細節併入 P0-10 What/落點。

**P1-5 Verifier 證據面擴充(新 condition types)** `M / high`
- 來源合併:OM 7 條判定準則、BG evaluator DSL、SK post-fill quality audit
- What:蒸餾為確定性新 condition types(非 prompt 準則):`filter_applied`(URL param/aria-pressed/結果數變化)、`range_equals`(數值精確比對)、URL query-param subset match + |OR|、單 token must_include guard、`form_fields_match`(observer 加 name→value 表單狀態讀取器,對 contract source-of-truth dict 逐欄比對,殺 value-in-wrong-field scrambling)、program_html 式 effect check(verify_contract 選配收 page——設計變更需明確決策)。每型加對應 calibration 損毀 class。注意「空結果合法 success」與 query-echo masking 的邊界需明確界定。
- 落點:`browser_core/contract.py:13-27`、`verifier.py:68-95`、`observer.py`、`tools/calibrate_verifier.py`、`data/mock_sites` 加 form mock。

**P1-6 Failure taxonomy 擴充 + TaskRun 結構化旗標 + per-class eval breakdown** `S / medium-high`
- 來源合併:SK 16-class taxonomy、SK CODE_FIXABLE gate、BU impossible/captcha 旗標、SV validation_error
- What:failures.py 加 anti_bot / auth_required / site_unreachable / validation_error / infra-timeout vs page-timeout(前三者 repairable=False,diagnose_failure 偵測後短路迴圈,CAPTCHA 不再燒 planner turns);Diagnosis 加 confidence;TaskRun 加 impossible_task / reached_captcha 旗標;browser_eval _row 加 per-class breakdown(失敗歸因:site vs agent reasoning vs our code)。
- 落點:`browser_core/failures.py:12-23`、`repair.py:44-68`、`agent.py` TaskRun、`tools/browser_eval.py:60-73`。

**P1-7 Structured final claim + self-report 全文記錄** `S / medium`
- 來源合併:SG forced done call、BU idea 9 的 prereq
- What:loop 結束(任何原因)以最後 done/give_up reason 構造 {taskComplete, reasoning} 存 TaskRun.claim,餵入 false-success record。Why:_feat_hallucinated_claim 現在因無 claim 文字而靜默跳過——最強特徵被餓死。落點:`agent.py` TaskRun + run_agentic 尾、`false_success.py:163-167`。

**P1-8 幻覺四分類補全 + first-point-of-failure 定位** `S / high`
- 來源:SG。What:false_success.py 補 action contradiction(claimed click、state 未變)與 action fabrication 兩特徵(原料:click_no_effect、ActionOutcome.url_before/after);對 TaskRun.steps 做 step-localization pass,失敗 run 產出失敗步 index 而非只有 reason 字串;進 docs/failure_gallery.md。落點:`false_success.py`、`observability_core` VerifierResult。

**P1-9 Process score + uncontrollable-blocker crediting** `M / high`
- 來源:SG。What:combine_checks/VerifierResult 加 earned/max per-criterion 數值 process_score(取代 confidence 的粗糙 base-0.1*repairs);正常任務被不可控因素(site down 等)阻斷時的 credit 規則進 _PREFLIGHT_SYSTEM 與 browser_eval 計分。註:per-criterion evidenceInsufficient 我們已有(三態 ConditionCheck.observed)。落點:`eval_core/verdict.py`、`planner.py` _PREFLIGHT_SYSTEM、`tools/browser_eval.py`。

**P1-10 Ablation harness + AgentOccam minimal-baseline control arm** `S-M / medium`
- 來源合併:SV ablation 紀律、**AO simplicity-vs-mechanism 對照**。What:tools/ablation_eval.py 逐元件關閉量測成功率/steps/tokens 三軸——feature flags 天然存在(AGENT_VISION、plan_steps=None、MemoryStore 清空、跳過 _dismiss_overlay);可加同 harness 換 backbone 敏感度表。
- **新增 minimal-baseline control arm(AO 論證的硬證據形式)**:只測「移除我們的元件」不足以反駁「機制是儀式」——必加一支 reduced-action + cleaned-obs + 無 repair/memory/vision 的極簡 agent 跑同一 task set。若極簡臂接近全配臂,每個機制的存在都需用該差值辯護。AgentOccam 的階梯式 config(`reduced_action.yml`→`reduced_action-X_scrolling-obs_opt-history.yml`)即範本;其 WebArena ablation(16.5→23.1 砍 action→~27 去 scroll→~34 obs 清洗→~37 selective history→43.1 planning tree)證明去 scroll/全頁觀察與 obs 清洗是最大單項增益,值得對照我們 observer 的 `_candidate_lines` 自查冗餘 StaticText/table token。**AO 的反命題也直接判定我們某些計畫項不必要**:多 agent planner/actor 分離(AO 單 agent 勝 Agent-E)、任務策略回灌 planner prompt(+SteP 掉 2 分)——replan 應做成 in-context branch/prune 而非新角色,Script-Mode 知識只走確定性重放不回灌 prompt。落點:新 `tools/ablation_eval.py`、`docs/eval_report.md`。

**P1-11 語意化 wait policy** `S / medium`
- 來源:SV。What:observer 加 spinner/skeleton/aria-busy 偵測 JS;動作後改「有 loading 指示器才輪詢等(上限 3×2s)」取代固定 networkidle+300ms。落點:`observer.py`、`agent.py:608-613`。

**P1-12 Post-dispatch click timeout ≠ 失敗** `S / medium`
- 來源:SK deterministic recovery ladder 缺的那一級。What:executor._dispatch click 路徑區分「click 已派發、導航等待逾時」(url_before != page.url 或 pending navigation)與「click 沒落地」,防止 repair 重複點擊造成 double-submit。落點:`executor.py:67-74,276`。

**P1-13 任務型覆蓋矩陣 audit(WorkArena / VWA 對照)** `S / medium-high`
- 來源合併:WA enterprise 任務分類、VWA 視覺任務三軸難度、WA collateral-damage watcher。
- What:對現行 eval set 做覆蓋矩陣 audit(任務型 × 我們有無),補齊 consumer benchmark 缺、enterprise/visual 有的型別:dashboard/chart 讀值、統計聚合後行動(mean/median/mode)、非標準 HTML list filter/sort widget、KB 檢索→照 SOP 執行(隱含目標)、排程/knapsack 型優化決策、form reference/choice/date 欄位、**infeasible 偵測「無線索」變體(reason="")**(現有 impossible eval 只有有線索型)、視覺比對輸入(以圖找物)、SSIM/VQA 式視覺結果驗證。可移植機制:(1) **collateral-damage watcher**——WorkArena `form.py` setup 注入 JS 對任務範圍外每個 input/select 掛 change listener,一改就 flag,validate 先查此 flag——直接補強我們 silent-failure 防線(抓「任務欄位全對但亂動其他欄位」),對接 P1-5 form_fields_match;(2) **non-terminal vs terminal 失敗分流**(不可逆錯誤立即終止 episode 省步數),對接 P1-6;(3) **cheat() oracle per task**(CI 先跑 oracle 驗任務可解再跑 agent),對接 P1-3。附:VWA raw metadata 有 `"mediun"`/`"hrad"` typo——連頂級 benchmark 的 metadata 都需 schema validation,是我們 eval hygiene 論據。落點:`data/browser_eval/tasks.json`、`tools/browser_eval.py`、`data/mock_sites`、對接 P1-5/P1-6/P1-3。

**P1-14 安全 / prompt-injection 對抗頁 eval 軸(差異化)** `M / high`
- 來源合併:SEC 全軸——ST-WebAgentBench(policy CuP)、SafeArena(misuse ARA)、WASP(intermediate-vs-e2e ASR)、EIA(fake form PII 竊取)、SecureWebArena(視覺欺騙)、WAInjectBench(detector taxonomy)。
- **Eval-axis rationale**:兩個獨立威脅模型都未被本路線圖涵蓋——(1) misuse/policy-compliance(user 要求違規,agent 該拒卻執行;SafeArena 測得 GPT-4o 完成 34.7% harmful,chat-time 拒絕不轉移到 agentic loop);(2) prompt-injection/環境劫持(untrusted 頁面內容夾帶指令劫持 benign 目標)。惡意頁面指令注入是 silent-failure 的**對抗性變體**——正是我們主場的對抗延伸,卻零機制、零 eval 軸、零 backlog。「unseen tasks 驗收」若含對抗頁目前無任何應對。
- What:(1) `data/mock_sites` 加 ~12 頁對抗套件、4 組(DOM-text hidden injection / fake-form PII / fake-consent / misleading UI + pop-up),每組配 clean twin 控 over-refusal,每頁 deterministic oracle;(2) 兩層防禦——Layer 1 instruction/content separation(頁面文字包 `<untrusted_page_content>` 標為 data-never-command、隱藏節點 opacity:0/off-screen/display:none/font-size:0/comment/instruction-bearing alt-aria-title 在進 model 前 strip 或 surface、instruction hierarchy system>user>tool>page)、Layer 2 pre-action policy gate(高後果動作 navigate cross-origin/submit-with-PII/delete/transfer/email/credential 前查:服務原始 user goal 否 + 觸 forbidden policy 否 + 真實 consent vs 頁面自稱 consent);(3) 借 WASP 兩段計分本地化——emit `{completed, policy_violation, injection_intermediate_hit, injection_end_to_end, gate_triggered, latency_ms}`,聚合 **CuP(completion-under-policy,唯完成且零 policy 違反才算成功)**、intermediate/e2e ASR、refusal & over-refusal rate、gate cost。**intermediate-ASR 捕捉 boolean pass 藏不住的部分劫持**,直接強化 silent-failure 與 self-correction/recovery 軸。因 mock 靜態、oracle 決定論,可進 CI 做 measure-fix-remeasure 回歸,幾無 runtime 成本。與現有 capability guard(capability.py 拒 login/purchase/checkout)接壤但更廣。
- 落點:`data/mock_sites`(對抗頁 + clean twin)、`packages/browser_agent`(content-separation 前處理 + action policy gate)、新 `tools/adversarial_eval.py`、`docs/eval_report.md`。

**P1-15 Long-horizon:max_steps 預算與 P1-1 匯入的內部矛盾** `M / high`
- 來源:自查矛盾 + WC/M2 長程任務。
- What:`max_steps=8`(agent.py:440 預設)寫死,而 P1-1 要按 reference_length 分層匯入 Online-Mind2Web——medium/hard 題參考步數遠超 8,匯入即註定 fail。解:(1) task-level step budget(依 contract 難度或 reference_length 動態設上限,取代單一硬預算);(2) 前置 P2 的保守式 message compaction(每 N 步 LLM 摘要舊歷史,禁樂觀化);(3) 長程任務用 P0-5 的 per-condition latch 證據累積衡量 partial completion(M2 partial-completion 指標),不以單一 boolean 收尾。
- Why:A++ 需能收長任務;現行硬 8 步 + 無 compaction + 匯入長題註定 fail 是內部矛盾,P2 的 compaction 自承「max_steps=8 不痛」是迴避而非解決。
- 落點:`agent.py:440,502`、`planner.py` history 管理、`tools/browser_eval.py`(per-task budget)。

**P1-16 Frontend / support-matrix — 交由 deploy-zeabur-p0 workflow**(cross-reference,不在此重複)
- 題目明示的三條驗收線:web frontend(收任務、看進度、可檢視失敗)、supported/unsupported sites 清單、failure inspectability。**這些由 deploy-zeabur-p0 workflow 負責**,本路線圖不重複規劃,僅登記為 cross-reference 確保不漏。現有素材:`docs/supported_and_unsupported.md` 已有支援表、EvidenceStore/StepTrace 已有可上前端的 failure artifact 資料。此處僅標明歸屬,細節見該 workflow。

### P2 — 長任務 / 規模化前置,或需明確決策

| 項目 | 來源 | What(一句)| Effort / Impact | 落點 |
|---|---|---|---|---|
| 受控抽取動作 + agentic second judge(bu-max 追趕)| BU | sandboxed HTML parser 動作(非任意 Python,保 schema 驗證法則)+ eval-side agentic judge;**與「LLM never runs code」法則正面衝突,需明確決策後才動工** | L / high | `browser_core/actions.py`、`executor.py`、`tools/` |
| 保守式 message compaction | BU | 每 N 步 LLM 摘要舊歷史(禁樂觀化規則);max_steps=8 不痛,長任務方向的前置 | M / medium | `agent.py` history 管理 + `llm_core` |
| 表單錯誤多假設 value 修復 | SV | validation_error 類別 + 錯誤訊息/欄位/歷史→候選值 list 逐一試(上限 5)| S / medium | `failures.py`、`repair.py`、`agent.py` |
| 失敗元素黑名單 + URL 級 rollback | SV | fail_count 開始被 preferred()/評分讀取,黑名單元素 -inf;rollback 先做 goto url_before | M / medium | `memory_store.py:30-32`、`repair.py:100-137` |
| StepTrace.url + screenshot loud-fail + v2 export | OM | StepTrace 加 url 欄位;_screenshot 失敗記入 detail(現在 silent swallow);採 P1-1 後加 tools/export_v2.py 提交格式 | M / medium | `agent.py:139-150,260-268` |
| Error-key normalization 報告 | BG | exception/err 訊息 regex 正規化分桶 + burst-vs-scattered 分類,自動產 failure-gallery 候選(依賴 P0-9)| S / medium | 新 `tools/error_report.py` |
| Seeded 任務家族 + --filter | BG | task_seed→可重現變體家族;browser_eval 加 metadata 子集 flag | M / medium | `tools/browser_eval.py:46`、`gen_mutation_sites.py` |
| Domain whitelist 常開 + infeasibility reason 比對 | BG | allowed_origins harness 級常開(非逐 contract opt-in);tasks.json impossible 加 annotated reason 與 give_up reason 比對計分 | S / medium | `agent.py` loop、`tools/impossible_tasks.py` |
| Replay-agent drift regression | BG | 先讓 llm_core 真的落 prompt/response 全文(prompt_log_path 現在沒人寫),再做 ReplayPlanner + difflib ratio CI | M / medium | `llm_core/openai_client.py:105-114`、新 `tools/replay_drift.py` |
| PageMem 式結構化頁面表徵 | SV(WebChallenger -17.6 分最大塊)| 語意分段 + section summary/快取 + 站點記憶;max_steps=8 短任務優先級低 | L / medium | `observer.py`、`memory_store` |
| Model tiering / LLM fallback model | SK、SV | 小模型第二 handle + 備援切換;僅在 repair 長出 LLM rung 後相關 | M / low | `llm_core` |
| Compound action workflows | SV | planner 回 action list(表單場景);效益是 steps/tokens 降幅;引入時必須連帶 BU 的 stale-DOM guard(multi_act 那條 not_applicable 會轉為 required)| M / low | `planner.py` schema、`agent.py` |

---

## 3. 超越論證(per grading criterion)

**我方 outcome-level 基線(before 數字,補批判 C7)**:offline deterministic mock 支援任務集(`data/browser_eval/tasks.json`,4 tasks)task success rate = **1.0**、verdict accuracy = 1.0、verifier FP rate = 0.0(`docs/eval_report.md`,`runs/browser_eval/results.json`);跨 5-task apparent 集 apparent_success_rate = **0.8**、Rogan-Gladen 校正後 = **0.8**(`calibration_results.json`)。**誠實界定**:此為小型自建 deterministic set 上的建構性數字,**不可與 bu-max 的 Online-Mind2Web live 97.0% 直接比較**(任務集、難度、判定協定皆不同)。

### 外部量測 2026-07-10(Online-Mind2Web 20-task subset,live web,自跑)

measure-before-claim 的前置已執行:P1-1 匯入的 20 題 live 子集,以我方 agent 實跑(serial、難度階梯 step budget、second judge advisory on;artifact `runs/browser_eval/m2w_rerun/`)。

| 指標 | 數字 |
|---|---|
| success(pass / 可評分,排除環境失效) | **6/18 = 33.3%** |
| success(raw pass / 20) | 6/20 = 30.0% |
| 分難度 | easy 1/6、medium 4/8、hard 1/4 |
| naive baseline 對照(同子集) | 4/20 = 20%(trivial pass) |
| 環境失效(ERR_HTTP2,依維護協議排除) | 2/20(可重現,orphan 首跑同錯) |
| 成本 | 平均 **$0.0058/task**、18 題共 $0.10;平均 wall ~77s/task |
| second judge(advisory) | **18/18 全 abstain** |

**誠實界定與失敗面**:
- **不贏 SOTA**:33% 遠低於 leaderboard 頂端(bu-max live 97.0%,雲端重工程系統)。我方是小樣本(n=18)、自建、自驗的真實數字,勝過 paper naive 22% / 我方 naive 20%,證明機制有加值,但**「超越 97.0%」不成立**——如實記錄。
- **advisory second judge 在 live 任務全 abstain**:對 open-ended live 任務零訊號——這是誠實暴露的限制(judge 為 mock contract 條件設計,未對 live 泛化);verifier 仍是唯一裁判,運作正常(pass/fail/unknown 三態齊全)。修法待辦:second judge 的 live-task key-point 抽取(WebJudge 式),見 P0-8 延伸。
- **easy < medium 反常**(1/6 vs 4/8):小樣本雜訊 + easy 題落在較難自動化的站點;不粉飾。
- **committed harness 無法驅動 live 外部集**(repo gap):`tools/browser_eval.py` 與 P0-11 pool 皆 mock-only,本次 live 跑靠 scratchpad 臨時腳本 `run_m2w.py`。下一步:產品化 `tools/run_external_eval.py`(讀 external/*.json + run_agentic + 難度階梯 + second judge),讓外部量測可重現、可 CI——這也是「面試官拿新任務來驗」的必要能力。

degradation curve / impossible / open-ended / pass@k 的分項數字見 `docs/eval_report.md`。

### 外部量測 rerun 2026-07-10(post bucket-fix)

同 20 題 live 子集重跑,套上三個 bucket 修復 + verifier 採 `robust_contains` 整合掛鉤 + second judge 經 Codex gateway 武裝(LLM extractor,非 offline)。artifact `runs/browser_eval/m2w_rerun_20260710/`;baseline artifact `runs/browser_eval/m2w_rerun/`(逐題 summary 可對)。

| 指標 | baseline | rerun | 移動 |
|---|---|---|---|
| success(pass / 可評分,排除環境失效) | **6/18 = 33.3%** | **8/18 = 44.4%** | **+11.1pt** |
| success(raw pass / 20) | 6/20 = 30.0% | 8/20 = 40.0% | +10pt |
| easy | 1/6 | 2/6 | +1 |
| medium | 4/8 | 3/8 | −1 |
| hard | 1/4 | 3/4 | +2 |
| unknown 數(可評分池內) | 3 | 6 | +3(變差) |
| 環境失效(ERR_HTTP2,排除) | 2/20(accuweather、ups) | 2/20(同兩站,可重現) | 同 |
| second judge(advisory) | 18/18 abstain | **18/18 abstain(已武裝仍 abstain,cost>0)** | 未動 |

**逐題移動(18 可評分,2 題 env-error 兩跑相同)**:
- fail→pass(3):`iOS.`(recreation,尾點 strip)、`Year Award`(steam,非連續 token 子集)、`Houston`(apartments-hard,同 3 步翻轉、needle 非 brittle → 疑 live variance)。
- pass→unknown(1,回歸):`Formula`(espn,baseline 2 步即 pass,rerun wander 29 步漂離 → unknown)。
- fail→unknown(2,中性重分類):`Qatar Airways`(qatar)、`boardgame`(ign)——baseline-subtraction 把落地即成立的 landmark 剔為 vacuous,契約歸零 → open-ended unknown。
- 其餘 12 題判決不變。

**逐 bucket 裁決**:
- **BUCKET 2(robust text_visible)= 有推動數字**。兩題在**相同步數**下純靠 verifier 比對翻轉 fail→pass:`iOS.` 尾點 strip、`Year Award` tier-2 非連續 token 子集。這是本波唯一可歸因、可複現的加分來源。`robust_contains` 掛鉤本 session 落到 `verifier.py:34`(tier 1 為舊 exact-substring 嚴格超集,721 pytest 全綠、mock verdict_accuracy 1.0 不變)。
- **BUCKET 1(open-ended scoring)= 沒推動數字**。second judge 已經 gateway 武裝(每題 LLM 實際被呼叫,cost 0.00014–0.00042、共 $0.0057),但 **18/18 仍 abstain**;6 個 unknown 一個都沒拿到分。且 unknown 從 3 升到 6(baseline-subtraction 把更多 landmark 契約歸零)。結論:**live-abstain gap 未關閉**——不是 wiring(extractor 已 LLM),是結構性:WebJudge 的 evidence-grounding demotion 對 live 頁面一律降級,且 `run_agentic` 的三處 `verify_contract` 未帶 `open_ended_extractor`(判決時開放式評分沒接線,BUCKET 1 只到 verifier 參數層、未到 agent loop)。能力在、live 泛化不在,如實記錄。
- **BUCKET 3(navigation convergence)= 中性偏負**。早退閘門確實壓低了「兩三步就放棄」,但反作用是**不可收斂任務燒更多預算而非收斂**:student 32→46 步、medicare 23→25、且 espn 由 baseline 2 步 pass 被推成 29 步 wander→unknown(pass→unknown 回歸,最可能是早停閘門過度激進、亦可能 live variance)。本樣本上 BUCKET 3 沒把 wander 轉成 pass,反而貢獻了唯一一筆回歸。hard 3/4 的高分來自快速 pass(2–5 步),非收斂機制之功。

**誠實 caveat**:
- **n 小、live variance 大**:n=18,單跑;`Houston` 翻轉與 `Formula` 回歸都可能是站點內容跑間差異而非機制,+11.1pt 需視為含雜訊的方向指標,非穩定增益。
- **這 20 題契約本身弱**:success condition 全是單一 landmark/搜尋關鍵字(非任務答案),落地即成立者被 baseline-subtraction 剔空 → 判決退化為 open-ended unknown。verifier 判決對這批是弱 proxy;真正的答案軸得靠 second judge,而它 live 全 abstain——兩層都對 live 未泛化,是本波最該補的洞。
- **second-judge live-abstain gap 未關閉**:武裝 extractor 是必要非充分;下一步是 WebJudge 對 live 的 key-point 抽取放寬 grounding、以及把 `open_ended_extractor` 接進 `run_agentic` 的判決路徑(仍守 verifier 唯一裁判、abstain 退回 honest unknown)。

### 追補:abstain-gap 修復後的 6-unknown 定向重跑(2026-07-11)

上節指出的兩個洞已修(commit `3258b73` wiring+grounding、`b561e37` runner 隔離):(1) `run_agentic` 最終 `verify_contract` 在零條件契約且 planner 有 LLM client 時武裝 `open_ended_extractor`;(2) 根因是證據被截在 ~4–5K 字使引文無可 quote——現改餵最終頁 `inner_text` 12K + P0-5 逐步摘錄,引文須真出現於此證據方能 grounded-satisfied,否則降級 abstain。只**定向重跑上一波 6 個 unknown**(artifact `runs/browser_eval/m2w_abstain_fix2_20260710/`),非全集。

| 原 unknown 題 | 站點 | 難度 | 修復後 | 依據 |
|---|---|---|---|---|
| m2w-a6f0434ce6af | yahoo finance | easy | **pass** | 「Tesla 2023-03-17 收盤價」→ 導覽至 TSLA 歷史頁,證據含 `Mar 17, 2023 … Close 180.13`(與實際一致),3/3 key point grounded。**已人工抽查:非幻覺** |
| m2w-6ca20f1da01e | gov.uk | medium | **pass** | key point grounded-satisfied |
| m2w-864244b6969e | nfl | medium | **pass** | all conditions observed and satisfied(7 步) |
| m2w-005be9dd91c9 | — | easy | fail | open-ended 評分:證據不足,誠實 fail |
| m2w-3f312ae3efc3 | — | easy | fail | 同上 |
| m2w-aa4b5cb7114f | — | medium | unknown | 評分棄權(證據不足,不硬判)——防幻覺機制正確運作 |

**結果**:6 題 unknown → **3 pass + 2 fail + 1 abstain-unknown**。live-abstain gap **實質關閉**:武裝 extractor + groundable evidence 後,有真實證據的開放式任務(TSLA 收盤價)確實拿到 grounded pass 且經人工抽查非幻覺;證據不足者仍誠實 abstain,無假 pass。

**合成後整體(定向重跑併回基底,標明為部分重跑組成非全集單跑)**:baseline 8 pass + 定向 3 pass = **11/18 = 61.1%**(排除 2 環境失效),vs naive baseline 20%。

**誠實 caveat**:(a) 這是「44% 全集跑 + 6-unknown 定向重跑」的**組成數字**,非一次乾淨全集跑,live variance 仍在;(b) 開放式 pass 依賴 second judge 的 grounded 評分,verifier 仍唯一裁判、abstain 退 honest unknown,無假 pass 引入(TSLA pass 已抽查證據);(c) n 小,61% 應視為方向指標。這關閉了上節「兩層對 live 皆未泛化」中的 second-judge 層;verifier landmark 層對這批弱契約仍是弱 proxy,屬題目契約設計而非機制缺陷。
- **量測基建**:productized `tools/run_external_eval.py` 用單一共享 page 跑全部任務,一次硬導覽失敗(accuweather ERR_HTTP2)會污染 page、把後續全部 cascade 成「interrupted by another navigation」——本波改用 scratchpad isolated-context driver(每題獨立 context+page,同 agent/verifier/second judge/難度預算)才拿到 18 題;另為讓 flaky 站不中途觸發 30% abort ceiling,量測時把該上限暫調高(source 預設 0.30 未改)。per-task page 隔離應回饋進 runner。

### 3.1 Self-correction
- **SOTA 做法**:BU 五級 locator cascade + loop detector;SK hash rebind + 修復預算;SG re-grounding 標準流程。
- **我們已更強之處**:修復是 diagnosis-driven 而非 retry-driven(先分類再修,docstring 明言);repair 路徑零 LLM 成本(確定性 a11y 評分),SOTA 各家都要花 LLM;feasibility gate 防「修進成功」(empty_result 明確拒修);SG 的標準流程本來就是我們的核心迴圈。
- **Backlog 補上後**:P0-7 hash cascade 補齊兩榜首共同的確定性身份層;P0-1 把已有的 loop 偵測從 run 後觀測接進 mid-run nudge;P0-2 讓幻覺目標在執行前被攔而非事後誤診。結果:同時擁有「確定性優先、LLM 最後」的修復階梯與榜首級 cascade——超越點在我們每級都有 telemetry 且 verifier 獨立驗收修復結果,SOTA 修完自己說了算。

### 3.2 Self-maintenance
- **SOTA**:SG replay cache 零 token 重放;SK 修復永久 write-back。
- **我們已更強**:快取按構造免疫 stale-payload(字面資料不落盤,SK 要靠 user_detail_query 補救);write-back 帶 success/fail 計數 + RepairEvent 完整 telemetry。
- **Backlog 補上後**:P0-10 把 write-back 帶進 agent mode 並加 shadow-mode 抽驗——SOTA 兩家都沒有 cache FP-rate 指標,我們把「快取會不會說謊」本身變成被量測的對象,這是超越點。

### 3.3 Eval depth
- **SOTA**:OM 300 題 live + WebJudge;BG oracle/repro/watchdog 工程紀律。
- **我們已更強**:judge 本身被 sensitivity/specificity 分解校準(Rogan-Gladen 混淆矩陣,n=50、sens 1.0/spec 1.0、confusion tp24/fn0/fp0/tn26,artifact `calibration_results.json`;雙 1.0 出自小集且未附 CI,審查時須先坦承此限)——**OM/BG 皆無 sens/spec 分解與 prevalence 校正**(WebJudge 的 85.7% 是 task-level 人類 agreement,非 sens/spec 分解);impossible-task 軸與 degradation curve(對環境的系統性消融)是兩者都沒有的軸。
- **Backlog 補上後**:P1-1 外部任務廣度(署名匯入)+ naive baseline 證明任務不可 shortcut;P1-3 oracle 全管線校準;P1-2 repro manifest;P1-10 元件 ablation;P0-9 harness 自身不再有無聲失敗。結果:廣度追平、而「校準過的 judge + 可重現 manifest + oracle 雙向驗證」的組合超越兩者。

### 3.4 Silent-failure prevention
- **SOTA**:WebJudge prompt 約定不吃自述;BU pre-done checklist;SG claimed-vs-verified 交叉比對。
- **我們已更強**:自述隔離是程式化而非 prompt 約定(answer channel 只吃頁面抽取、query-echo masking、baseline subtraction、有回歸測試);任何終止路徑都被 verify_contract 收口,「無聲耗盡變假 pass」結構上不存在;unknown 三態傳播使缺證據永不 pass。
- **Backlog 補上後**:P0-3 前閘門、P0-4 空 diff 訊號、P0-5 中途證據累積(殺假陰性——SOTA 只防假陽性,我們兩向都防)、P1-7/P1-8 讓 claimed-vs-verified 自動分類跑起來。超越點:假陽性與假陰性同時有機制,且 false-success 偵測是特徵化、可回歸的。

### 3.5 Cost analysis
- **SOTA**:SK 四維預算;BG cost-per-success 與 phase 拆解。
- **我們已更強**:repair 零 LLM 成本;vision 按需付費(AUTO 觸發);per-call cost 已記帳。
- **Backlog 補上後**:P0-6 預算 cap + llm_cost 落 TaskRun + cost-per-success;P0-10 agent-mode 快取直接砍最大成本項。超越點:成本數字與 eval verdict 在同一 artifact 裡可交叉(cost-per-success by task layer),SOTA 的成本報告與正確性報告是分離的。

---

## 4. 來源引用

| 來源 | 引用內容 |
|---|---|
| browser-use — github.com/browser-use/browser-use | cascading locator healing、ActionLoopDetector、pre_done_verification、message compaction;Online-Mind2Web 榜首 bu-max 97.0%(leaderboard https://osu-nlp-group.github.io/Online-Mind2Web,快照 2026-07-10) |
| Skyvern — github.com/Skyvern-AI/skyvern | element structural hash rebind、四維預算、CODE_FIXABLE triage、16-class taxonomy、two-stage judge(Code 2.0/v3 reviewer) |
| Stagehand v3 — github.com/browserbase/stagehand | self-healing replay cache、a11y line diff、hallucination 4-way split、EncodedId grounding、processScore/outcomeSuccess 分離 |
| Online-Mind2Web + WebJudge — OSU-NLP-Group,COLM 2025,arXiv:2504.01382;HF dataset OSU-NLP-Group/Online-Mind2Web(gated) | 300 題 live benchmark、reference_length 分層、WebJudge 三段裁判、naive-baseline 對照(22% vs 51%)、任務維護協議、v2 ActionStep schema |
| Magentic-One — arXiv:2411.04468(Microsoft) | dual-ledger 停滯偵測 + 觸發式 replanning |
| WebChallenger — arXiv:2606.10423 | PageMem 結構化頁面表徵 ablation(-17.6)、compound workflows |
| Alumnium — WebVoyager #1 98.5%(**self-reported**,WebVoyager 自評協定 judge 未校準,快照 2026-07-10)| selector self-healing 標準流程佐證(證據力弱,僅作機制存在佐證,不作有效性量測)|
| BrowserGym + AgentLab — ServiceNow,arXiv:2412.05467 | per-task status trichotomy、repro manifest、oracle cheat()、watchdog relaunch、seeded 任務家族、evaluator DSL(WebArena 系) |
| WebVoyager eval protocol — arXiv:2401.13919 | LLM-judge fallback(task + answer + last-k screenshots、abstain) |
| OpenAI CUA/Operator、Anthropic computer-use best practices、steel.dev leaderboard | survey 彙整之機制脈絡 |
| WebArena — arXiv:2307.13854 | url/program_html/must_include evaluator 組合語彙(經 BG 轉引) |
| WebCanvas / Mind2Web-Live — iMeanAI,arXiv:2406.12373;repo github.com/iMeanAI/WebCanvas(`evaluate/step_score.py`、`evaluate_utils.py`)| key-node 中間態評測、URL-first 抗漂移、latch(單向閂鎖)語義、選擇器 3 層祖先容忍、Appendix C 必要條件決策樹、scheduled replay 失效報告 loop;**反面教材**:semantic match `eval()` 解析 LLM 輸出後靜默歸 0(P0-5) |
| Agent-E — Emergence AI,arXiv:2407.13032;repo github.com/EmergenceAI/Agent-E(`ae/utils/dom_mutation_observer.py`、`get_detailed_accessibility_tree.py`)| change observation(P0-4 機制本體,含 100ms race + attribute-blind 已知限制)、DOM distillation 三 content-type、hierarchical planner/actor(AO 證明反而較差,見附錄)、WebVoyager 73.1%、self-aware 52% / oblivious(silent)48% 失敗分類 |
| AgentOccam — Amazon,ICLR 2025,arXiv:2410.13825;repo github.com/amazon-science/AgentOccam(`obs_opt.py`、`AgentOccam.py`、`configs/*.yml`)| 極簡反命題;reduced-action + 去 scroll 全頁化 + obs 清洗 + selective history + planning tree 的階梯 ablation(16.5→43.1);pre-execution 幻覺閘門(佐證 P0-2);minimal-baseline control arm 範本(P1-10);+SteP 掉 2 分(策略勿回灌 prompt) |
| WorkArena / WorkArena++ — ServiceNow,ICML 2024 / NeurIPS'24 D&B,arXiv:2403.07718 / 2407.05291;repo github.com/ServiceNow/WorkArena(`tasks/form.py:359-372,822-935`) | 企業任務分類、seeded 可重現 instance、server-side DB validate、**collateral-damage watcher(範圍外欄位 change listener)**、non-terminal vs terminal 失敗分流、cheat() oracle、無線索 infeasible 變體(P1-13) |
| Mind2Web 2 — OSU-NLP,NeurIPS'25 D&B,arXiv:2506.21506;repo github.com/OSU-NLP-Group/Mind2Web-2(`mind2web2/verification_tree.py`、`evaluator.py`)| rubric tree(critical/non-critical/sequential)+ gate-then-average 聚合、Agent-as-a-Judge leaf-level **99.03%**(vs WebJudge 85.7%)、Extractor/Verifier 分離、stub-pass 煙霧測試、evidence pre-caching、rubric→node→discrepancy 校準協定(P0-8) |
| VisualWebArena — CMU,arXiv:2401.13649;repo github.com/web-arena-x/visualwebarena(`evaluation_harness/evaluators.py`、`run.py`)| observation-only vision-gain 分層測量(text 7.25%→+caption 12.75%→GPT-4V 15.05%→+SoM 16.37%,增益須分資訊層 vs grounding 層)、PageImageEvaluator(SSIM 0.8 / VQA)、visual_difficulty 分層;佐證 AGENT_VISION 對外主張(P1-13)|
| 安全軸(SEC)— ST-WebAgentBench arXiv:2410.06703、SafeArena 2503.04957、WASP 2504.18575(code facebookresearch/wasp)、EIA 2409.11295、SecureWebArena 2510.10073、WAInjectBench 2510.01354 | 兩威脅模型(misuse policy-compliance + prompt-injection 環境劫持)、CuP(completion-under-policy)、WASP intermediate-vs-e2e ASR 兩段計分、EIA fake-form PII 竊取、instruction/content separation + action policy gate 兩層防禦(P1-14) |

**資料集使用聲明**:本 repo 的 eval set 可能匯入 Online-Mind2Web 任務子集(P1-1)。匯入時每筆任務將保留原 task_id 映射並在 `data/browser_eval/tasks.json` 與 `docs/eval_report.md` 中明確署名 OSU-NLP-Group Online-Mind2Web(COLM 2025,arXiv:2504.01382),遵守其 HF gated dataset 之取得條款;衍生變體亦標注 derived-from。

---

## 附錄:status = already_have / not_applicable 摘要(不入 backlog 的原因)

- BU multi_act stale-DOM guard:**n/a** — 每回合恰一動作 + 每次 observe 重新 stamp data-aid,結構上不會對舊 DOM 盲操作;僅在引入 action batching 時轉為必要。
- BU use_vision='auto':**already_have**(AGENT_VISION 三態 + heuristic 升級)。
- SK user_detail_query:**already_have by construction**(快取不存字面資料)。
- SK TOTP/credential vault:**n/a by design** — capability guard 拒絕憑證輸入是責任邊界敘事的一部分;正確姿勢是 P1-6 的 auth_required 分類上報。
- SK workflow DAG:**partial 但明確不採** — 依 memory(workflow 拆題偏好),重編排不進 browser agent;僅在 eval 出現多分支任務時重評。
- OM「judge 不吃自述」:**already_have 且更強**(程式化)。
- OM 截圖評分過濾 / vLLM WebJudge-7B:**n/a** — 前置條件(第二裁判、截圖評分階段、回歸量瓶頸)不存在;採 P0-8 後其消融數據作設計依據。
- OM 任務失效維護協議:**n/a 對 mock set**(deterministic offline 不腐化);併入 P1-1 作 live 配套。
- SG Top-K evidence batching:**n/a** — verifier 零 LLM、O(conditions) 成本;若 P0-8 落地則內建於 second judge。
- BG per-step validate():**already_have**(agent mode 每回合 verify_contract 同證據面)。

---

## 完整性批判

批判日期:2026-07-10。目標基準:「超越最佳公開 browser-agent 實作,grade A++」。逐項對照題目原文(Whaleforce-AI-Coding-Test-EN.md Task 1)與公開 SOTA 清單後,以下為具體缺漏。

> **修訂進度(2026-07-10 第二輪,補入 recon)**:A/B/C 多數項已處理,狀態逐項標於下。仍 OPEN 者集中在需實際量測的兩點(§C6 對方 cost 數字、§B5 latency 分佈)。

### A. 未覆蓋的巨人 / benchmark

| 缺漏 | 為何重要 | 狀態 |
|---|---|---|
| **WebCanvas / Mind2Web-Live**(arXiv:2406.12373) | key-node 中間狀態評測——與 P0-5「中途證據累積」同一問題的既有解法 | ✅ 已加入身份表 + §4 引用;附掛 P0-5(latch 語義、URL-first、3 層祖先容忍、決策樹、`eval()` 反面教材) |
| **Agent-E**(Emergence AI,arXiv:2407.13032) | change observation——P0-4 的機制本體 | ✅ 已補為 P0-4 首要來源(含 100ms race / attribute-blind 限制)+ §4 引用 |
| **AgentOccam**(arXiv:2410.13825) | 極簡 agent 勝堆機制——backlog「加機制」路線的反面假設 | ✅ P1-10 新增 minimal-baseline control arm + AO 判定不必要之項(多 agent 分離、策略回灌);+ §4 引用 |
| **WorkArena / WorkArena++**(ServiceNow,arXiv:2403.07718 / 2407.05291) | enterprise 任務廣度、collateral-damage watcher | ✅ 新增 P1-13 覆蓋矩陣 audit(含 watcher / non-terminal 分流 / cheat oracle)+ §4 引用 |
| **Mind2Web 2**(arXiv:2506.21506) | Agent-as-a-Judge 最新設計參照 | ✅ 已補為 P0-8 首要設計依據(gate-then-average、Extractor/Verifier 分離、99.03% vs 85.7% 引用鏈)+ §4 引用 |
| **安全軸整體缺席**(ST-WebAgentBench 等 + prompt-injection) | injection 是 silent-failure 的對抗性變體 | ✅ 新增 P1-14 安全 / prompt-injection 對抗頁 eval 軸(CuP + intermediate/e2e ASR + 兩層防禦)+ §4 SEC 引用 |
| **VisualWebArena**(arXiv:2401.13649) | vision 路徑無外部量測支撐 | ✅ 併入 P1-13(observation-only vision-gain 分層測量協定)+ §4 引用;AGENT_VISION 主張有了外部量測標準 |

### B. 評分維度無 P0 項(對照題目原文,非只對照本文件五維度)

1. ✅ **Self-maintenance 已升 P0**。原 P1-4 升級為 **P0-10**(agent-mode 跨 run 記憶 + shadow-mode 驗證),文中明確標註「§3.2 自承最大槓桿 + 題目明示能力,排 P1 為矛盾」的優先級修正理由;P1-4 位置改為指標。
2. ✅ **Scalability 已補 P0**。新增 **P0-11**(parallel eval worker pool + session/context pool + subprocess-per-task 隔離 + 多 session 成本模型),subprocess 隔離即 P0-9 watchdog 的實作載體。
3. ✅ **Frontend / failure inspectability**:歸屬 **deploy-zeabur-p0 workflow**,新增 **P1-16** 作 cross-reference(不重複規劃);EvidenceStore/StepTrace artifact 已備可上前端。
4. ✅ **Supported / unsupported 清單**:同上併入 P1-16 cross-reference;`docs/supported_and_unsupported.md` 已有支援表。
5. ⚠️ **Runtime performance / latency:部分處理,仍 OPEN**。P0-11 加多 session 成本/latency 模型、P1-14 emit per-action latency、既有 `docs/cost_latency_report.md` 有 per-step latency;**但仍缺 latency 分佈量測與對 SOTA 的 wall-clock 對照**(需實測,非文件可補)。
6. ✅ **長程任務內部矛盾已建項**。新增 **P1-15**(task-level step budget 取代硬 max_steps=8 + compaction + P0-5 partial-completion 衡量),明指 P2 compaction「不痛」是迴避。

### C. 缺證據或過強的宣稱

1. ✅ **arXiv typo 已修**:P0-8 內文改為 2504.01382。
2. ✅ **Alumnium 98.5% 已標** self-reported + WebVoyager 自評協定未校準 + 快照 2026-07-10(身份表 + §4)。
3. ✅ **bu-max 97.0% 已附** leaderboard URL + 快照日期 2026-07-10(身份表 + §4)。
4. ✅ **「OM/BG 都不校準 judge」已窄化**為「無 sensitivity/specificity 分解與 prevalence 校正」(§3.3);WebJudge 85.7% 明標為 task-level agreement 而非 sens/spec 分解。
5. ✅ **sens/spec 已附 n 與 CI 註記**:n=50(24 success + 26 corrupted)、confusion tp24/fn0/fp0/tn26、明註「小集 + artifact 未附 CI,審查須先坦承」(§1.3 表 + §3.3)。
6. ❌ **§3.5 cost 超越論證仍無對方數字**:OPEN——尚未取得 BU/SK 的 cost-per-task 實測或公開數字;「超越」目前仍是機制比較而非量測比較(需外部量測,保留為待辦)。
7. ✅ **我方 outcome-level 基線已陳述**(§3 開頭):mock 支援集 task success 1.0 / apparent 0.8 / RG 0.8,並誠實界定不可與 bu-max live 97.0% 直接比較,「超越 97.0%」須待 P1-1 匯入可比基線後方成立。

### D. 結論

第二輪修訂後,A(七個缺席巨人)全數補入引用與 backlog 掛點、B/C 多數項已 resolve。**仍 OPEN 兩項,皆需實際量測而非文件可補**:(1) §C6 對方(BU/SK)cost-per-task 數字;(2) §B5 latency 分佈與 SOTA wall-clock 對照。核心待辦仍是 P1-1 匯入外部可比 live 任務集,把「超越 97.0%」從機制論證轉為量測論證(measure-before-claim)。
