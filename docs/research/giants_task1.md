# Giants Research — Task 1 Browser Agent 對照研究與 backlog

> 2026-07-13 自工作筆記濃縮;完整跑分紀錄與逐段敘事見 git history(`git log --follow docs/research/giants_task1.md`),canonical 數字以 `docs/eval_report.md` 為準。

**一句話**:這份是「站在巨人的肩膀上」的量尺 —— 我把公開最強的那幾套 browser agent 攤在同一張桌上,逐條問「他有什麼、我有沒有」,再把差距翻成待辦、把跑分照實記(包含我輸的那幾筆)。

**這份分五段**(先給地圖,免得中途迷路):

1. **巨人名單** —— 我拿誰當尺,每把尺量的是什麼。
2. **§1 對照表** —— 五個評分維度,逐條列「對方機制 / 我方現況 / 判定」。判定只有四種:領先、互有、落後、已補。
3. **§2 Backlog** —— 差距翻成可執行的待辦,標優先級、工作量、以及「到底落地了沒」。
4. **§3 定位與外部實測** —— 我方基線,加上五波真實跑分:33.3% → 44.4% → 合成 61.1% → held-out 66.7% → 300 題官方全量 33.57%。每一波都帶 caveat。
5. **§4 來源引用 / 附錄 / 完整性批判** —— 每個機制都引得到人;還沒補的洞掛在最後,不藏。

日期:2026-07-10;輸入:六份逐條對照 repo 程式碼行號核實過 status 的 gap analysis;範圍:packages/browser_agent、packages/browser_core、packages/eval_core、tools/、data/browser_eval。

**對照對象**(白話:這是我的巨人名單 —— 榜首、論文、工程 harness 各取所長,不是挑軟柿子來贏):

| 代號 | 專案 / 論文 | 身份 |
|---|---|---|
| BU | browser-use(github.com/browser-use/browser-use) | Online-Mind2Web 榜首 bu-max 97.0%(leaderboard 快照 2026-07-10;live 榜會動,需附 retrieval date) |
| SK | Skyvern(github.com/Skyvern-AI/skyvern) | vision+DOM hybrid、cached-script self-healing(Code 2.0/v3) |
| SG | Stagehand v3(github.com/browserbase/stagehand) | self-healing replay cache、a11y diff、EncodedId grounding |
| OM | Online-Mind2Web + WebJudge(OSU-NLP-Group,COLM 2025,arXiv:2504.01382) | 300 題 live benchmark + LLM trace judge |
| SV | survey:Magentic-One(arXiv:2411.04468)、WebChallenger(arXiv:2606.10423)、Alumnium(WebVoyager #1 98.5%,self-reported、judge 未校準,快照 2026-07-10)、OpenAI CUA/Operator、Anthropic computer-use、steel.dev | 榜首機制彙整 |
| BG | BrowserGym + AgentLab(ServiceNow,arXiv:2412.05467)+ WebVoyager eval protocol(arXiv:2401.13919) | eval harness 工程 |
| WC | WebCanvas / Mind2Web-Live(iMeanAI,arXiv:2406.12373) | key-node 中間態 live 評測、latch 語義 |
| AE | Agent-E(Emergence AI,arXiv:2407.13032) | hierarchical planner/actor、change observation |
| AO | AgentOccam(Amazon,ICLR 2025,arXiv:2410.13825) | 極簡反命題:對齊 action/obs space 勝過堆機制 |
| WA | WorkArena / WorkArena++(ServiceNow,arXiv:2403.07718 / 2407.05291) | 企業 compositional 任務、collateral-damage watcher |
| M2 | Mind2Web 2(OSU-NLP,NeurIPS'25 D&B,arXiv:2506.21506) | rubric tree + Agent-as-a-Judge(99.03% leaf agreement) |
| VWA | VisualWebArena(CMU,arXiv:2401.13649) | 視覺任務 benchmark、vision-gain 分層測量 |
| SEC | ST-WebAgentBench(2410.06703)、SafeArena(2503.04957)、WASP(2504.18575)、EIA(2409.11295)、SecureWebArena(2510.10073)、WAInjectBench(2510.01354) | policy-compliance + prompt-injection 兩威脅模型 |

## 1. 對照表(按評分維度):同一題,巨人怎麼解、我怎麼解?

一句話:五個維度硬碰硬。**判定不是自評分數,是相對位置三選一** —— 領先 / 互有 / 落後;另有「已補」用來記錄「原本落後、後來做掉了」,不美化成一開始就領先。

### 1.1 Self-correction(自我修正):做錯了,自己救得回來嗎?

白話:agent 找不到按鈕、點錯地方的時候,它會不會自己重找、重試、換條路 —— 而不是閉著眼睛硬走下去。

| 對象 | 對方機制 | 我們現況 | 判定 |
|---|---|---|---|
| BU | 5 級 cascading locator healing + ActionLoopDetector 遞增 nudge | diagnosis-driven 零 LLM 修復 + feasibility gate(repair.py:44-68,100-175);無 element hash,loop 偵測只在 run 後觀測 | 互有 |
| SK | element hash rebind、四維修復預算、CODE_FIXABLE triage | RepairEvent telemetry + selector write-back(selector_memory.py);無 hash rebind、無預算 cap | 互有 |
| SG | selector 失敗→re-ground→重試→顯式失敗 | 同構流程即核心迴圈(agent.py:335-426),agent mode 每回合 re-grounding | 領先 |
| SV(Magentic-One) | dual-ledger 停滯偵測→replan | vision 升級不觸發 replan,preflight plan 整場一次(agent.py:109-127) | 落後 |

> 不是「有沒有自我修復」的問題,是「修復要不要花 LLM 錢、修完誰驗收」——我的修復是零 LLM 的診斷驅動,驗收交給獨立 verifier;但卡住了不會重新規劃,這格我落後。

### 1.2 Self-maintenance(自我維護 / 跨 run 記憶):今天學到的,明天還記得嗎?

白話:同一個網站、同一個任務再跑一次,系統記不記得上次的教訓 —— 記得就省錢省時間,記錯就會拿舊答案去撞新頁面。

| 對象 | 對方機制 | 我們現況 | 判定 |
|---|---|---|---|
| BU/SK | repair 成功永久 write-back | Script Mode 完整迴圈已有;Agent Mode 不碰 memory,每 run 全額 LLM 成本 | 互有 |
| SG | 指令+URL 雜湊快取 + zero-token replay | 快取只存 selector;fill 值不進快取(結構上免疫 stale-payload);無 trajectory replay | 互有 |
| SK | user_detail_query 個人化解耦 | already_have by construction:字面用戶資料永不落快取 | 領先 |
| SV | shadow-mode 快取抽驗 + cache FP-rate | dom_fingerprint 有存從未讀回;無抽樣重驗 | 落後 |

> 不是我特別小心才沒把用戶資料寫進快取,是**結構上根本沒有那條路**(by construction)。反過來說,快取存了 dom_fingerprint 卻從來沒讀回去 —— 存而不用,等於沒有。

### 1.3 Eval depth(評測深度):我的成績單,自己出題自己改嗎?

白話:考卷是誰出的、誰改的、改得準不準 —— 這一格量的是「我憑什麼相信自己的分數」。

| 對象 | 對方機制 | 我們現況 | 判定 |
|---|---|---|---|
| OM | 300 題 live、reference_length 分層、WebJudge(85.7% 人類一致) | 23 題 deterministic offline set + impossible/open-ended 軸 + degradation curve + judge 校準(Rogan-Gladen sens 1.0/spec 1.0,n=50 小校準集、未附 CI);缺外部廣度與第二裁判 | 互有 |
| BG | oracle cheat()、repro manifest、per-task 狀態三分法、watchdog | verifier 離線校準有(calibrate_verifier.py);無 end-to-end oracle、無 per-task 落盤 | 落後 |
| SV | ablation + backbone-sensitivity 紀律 | 元件 ablation 已於 2026-07-11 落地(`tools/ablation_bench.py`,見 P1-10) | 已補(原落後) |
| SK | two-stage judge、judge I/O artifacts | deterministic gate + EvidenceStore + 校準;缺 LLM 第二意見 | 互有 |

> **sens 1.0 / spec 1.0 看起來滿分,但 n=50、沒附 CI** —— 這是小校準集的建構性數字,不是「我的裁判完美」。審查時我先講這句,再講數字。

### 1.4 Silent-failure prevention(無聲失敗防治):它說「做完了」,真的做完了嗎?

白話:agent 回報成功、實際上什麼也沒做成 —— 這叫安靜地失敗,是最貴的一種錯,因為沒人會發現。

| 對象 | 對方機制 | 我們現況 | 判定 |
|---|---|---|---|
| BU | pre_done checklist、done-only schema | 任何終止路徑一律 verify_contract 對真實頁面出 verdict(agent.py:614-616);缺 done 前自查閘門 | 領先(缺前閘門) |
| OM(WebJudge) | prompt 約定 judge 不吃 agent 自述 | 程式化保證:answer_matches 只吃頁面抽取 + query-echo masking + baseline subtraction(verifier.py:24-133),有回歸測試 | 領先 |
| SG | forced structured done、幻覺四分類 | verdict 不由 prose 推斷;但 TaskRun 無 claim 欄位、幻覺 aid 未前置攔截 | 互有 |
| SK | action-history evidence rule | combine_checks 全條件必過 + unknown 傳播(verdict.py:26-65);中途成立後導航離開會誤判(假陰性) | 互有 |
| BG | per-step validate() | already_have:agent mode 每回合 verify_contract 同證據面(agent.py:510-517) | 領先 |

> 不是「用 prompt 拜託裁判不要聽 agent 自述」,是**程式上讓 agent 的自述根本進不了裁判的輸入**。差別在於:prompt 會被說服,型別不會。

### 1.5 Cost analysis(成本分析):一次任務花多少錢,有人在管嗎?

白話:每跑一題燒多少 token、多少美金、多少秒 —— 有沒有人記帳,記了有沒有人設上限。

| 對象 | 對方機制 | 我們現況 | 判定 |
|---|---|---|---|
| SK | cycles/tokens/USD/wall-clock 四維硬預算 | llm_cost 逐 call 累計但不檢查上限、不落 TaskRun(死碼);唯一限制 max_steps | 落後 |
| BG | cache-aware 計價、cost-per-success | per-call cost_usd + docs/cost_latency_report.md;無 cost-per-success、無 phase 拆解 | 落後 |
| SK | 大 planner / 小模型分層 | repair 路徑零 LLM 成本(確定性) | 領先 |
| BU | use_vision='auto' 按需截圖 | already_have 等價:AGENT_VISION 三態 + heuristic 升級(agent.py:216-224) | 領先 |

> **llm_cost 是死碼** —— 我算了錢,但沒人看、沒進 TaskRun、沒設上限。「有記帳」和「有預算」是兩件事,我只有前者。

## 2. Prioritized Backlog(去重後;effort S <1 天 / M 1-3 天 / L >3 天;詳細 What/Why/落點見 git history)

白話讀法:`S/high` 前面是工作量(S <1 天 / M 1-3 天 / L >3 天),後面是影響力。P0 = 對照下最痛的洞;P1 = 該做但可排隊;P2 = 需要明確決策或等前置條件。每項尾巴一律標「已落地 / 部分落地 / 未落地」—— **沒做的就寫沒做,不寫「規劃中」**。

### P0

- **P0-1 In-loop 停滯偵測 + 遞增 nudge + replan 觸發** `S/high` — repetition_report + page fingerprint 接進 run_agentic,命中注入 nudge/REPLAN。未落地。
- **P0-2 Hallucinated-aid / 座標 pre-execution gate** `S/high` — _build_action 驗 aid/座標合法性,不合法→noop 不進 executor。未落地。
- **P0-3 終止雙閘門:pre-done checklist + done-rejection** `S/high` — done 前結構化自查 + loop verdict != pass 時駁回一次。未落地。
- **P0-4 每步 env_change 證據 + 新元素標記 + 空 diff 訊號** `S/high` — 連續兩次 observation 身分鍵 diff 進 history 與診斷(機制先例:AE change observation)。未落地。
- **P0-5 Trace 級 per-condition 證據累積 + per-step obs 持久化** `S/high` — 每條 success condition 記 best-observed(WC latch 語義,需補「可撤銷條件」型別),verify_contract 併入。部分落地(逐步摘錄已用於 judge-fix 證據,見 abstain-fix 節)。
- **P0-6 Budget caps + llm_cost 上 TaskRun + cost-per-success** `S/high` — Budget dataclass + phase timings + cost-per-success。未落地。
- **P0-7 Element structural hash + cascade rebinding(MatchLevel telemetry)** `M/high` — cleaned structural hash 快路徑 rebind,0/>1 落回 purpose 評分 repair。未落地。
- **P0-8 Advisory second judge(per-condition micro-judgment + 決定論聚合)** `S-M/high` — M2/WebJudge 引用鏈為設計依據;verifier 仍 runtime 唯一裁判。已落地(用於全部外部量測波次)。
- **P0-9 Harness per-task 持久化 + watchdog** `S+M/high` — per-task summary.json(harness status 與 verdict 分離)+ timeout watchdog。部分落地(外部 runner per-task summary + resume 已用)。
- **P0-10 Agent-mode 跨 run 記憶 + shadow-mode 快取驗證** `M/high` — 原 P1-4 升級(自證最大 cost 槓桿 + self-maintenance 為題目明示能力,排 P1 為優先級矛盾)。未落地。
- **P0-11 Scalability:parallel eval + session pool + subprocess-per-task 隔離** `M/high` — worker pool + session 復用 + 多 session 成本模型;綁定 P0-9。未落地。

### P1

- **P1-1 Online-Mind2Web 任務子集匯入(署名)+ naive baseline + 失效維護協議** `M/high` — HF gated dataset 分層抽題、每筆註明來源;naive baseline 報 trivial-pass 率。已落地(`tools/import_mind2web.py`、`tools/naive_baseline.py`、`tools/run_external_eval.py`;見外部量測各節)。
- **P1-2 Per-run reproducibility manifest** `S/high` — git hash/版本/task-set hash 落 repro_info.json。部分落地(held-out 波次 freeze_manifest/manifest)。
- **P1-3 Oracle cheat scripts 過全管線** `M/high` — oracle pass-rate 1.0 / sabotaged 0.0 作 judge 校準頭條。未落地。
- **P1-4** — 已升級併入 P0-10。
- **P1-5 Verifier 證據面擴充(新 condition types)** `M/high` — filter_applied / range_equals / form_fields_match 等確定性型別 + 對應 calibration 損毀 class。未落地。
- **P1-6 Failure taxonomy 擴充 + TaskRun 結構化旗標** `S/medium-high` — anti_bot / auth_required / site_unreachable 等 + per-class breakdown。部分落地(env-classified site_unreachable 已用於外部量測排除)。
- **P1-7 Structured final claim + self-report 全文記錄** `S/medium` — TaskRun.claim 餵 false-success detector(現最強特徵被餓死)。未落地。
- **P1-8 幻覺四分類補全 + first-point-of-failure 定位** `S/high` — action contradiction/fabrication 特徵 + step-localization。未落地。
- **P1-9 Process score + uncontrollable-blocker crediting** `M/high` — per-criterion earned/max process_score。未落地。
- **P1-10 Ablation harness + AgentOccam minimal-baseline control arm** `S-M/medium` — 逐元件關閉量測 + AO 極簡對照臂。✅ 落地 2026-07-11(`tools/ablation_bench.py`):script 7 配置 × 18 題 + agent 6 配置 × 8 題 = 174 runs,mock 確定性、$0;full 兩相全對;最大單一元件 = selector repair(關掉 −3/18);AO 極簡臂未接近全配臂——minimal_agentoccam(verifier 仍在)12/18,換 self-report 判準剩 4/18 + 10 false success;no_selector_memory 零損失照錄。完整表見 `docs/eval_report.md`「Browser Agent 元件 Ablation」節;artifact `runs/browser_eval/ablation/`。
- **P1-11 語意化 wait policy** `S/medium` — spinner/aria-busy 偵測輪詢取代固定 networkidle。未落地。
- **P1-12 Post-dispatch click timeout ≠ 失敗** `S/medium` — 區分「click 已派發、導航等待逾時」與「click 沒落地」,防 double-submit。未落地。
- **P1-13 任務型覆蓋矩陣 audit(WorkArena / VWA 對照)** `S/medium-high` — 覆蓋矩陣 + collateral-damage watcher + 無線索 infeasible 變體 + 視覺任務型別。未落地。
- **P1-14 安全 / prompt-injection 對抗頁 eval 軸** `M/high` — 對抗頁套件 + clean twin、兩層防禦(instruction/content separation + pre-action policy gate)、CuP 與 intermediate/e2e ASR 計分;injection 是 silent-failure 的對抗性變體,現況零機制、零 eval 軸。未落地。
- **P1-15 Long-horizon:task-level step budget(解 max_steps=8 與 P1-1 匯入的內部矛盾)** `M/high` — 依難度動態步數上限 + compaction 前置 + P0-5 partial completion。部分落地(外部量測已用難度階梯 step budget)。
- **P1-16 Frontend / support-matrix** — cross-reference:歸 deploy-zeabur-p0 workflow,本文件不重複規劃。

> P1-10 的反例值得單獨拎出來講:**AgentOccam 的「極簡也能打」在我這裡沒複現** —— minimal_agentoccam 留著 verifier 是 12/18,一旦把判準換成 agent 自述,只剩 4/18 外加 10 個 false success。同一個 agent、同一批題,換個裁判就從「還行」變成「一半在騙人」。

### P2(長任務 / 規模化前置,或需明確決策;均未落地)

| 項目 | 來源 | What(一句) |
|---|---|---|
| 受控抽取動作 + agentic second judge | BU | sandboxed HTML parser 動作 + eval-side agentic judge;與「LLM never runs code」法則衝突,需明確決策後動工 |
| 保守式 message compaction | BU | 每 N 步 LLM 摘要舊歷史(禁樂觀化);長任務前置 |
| 表單錯誤多假設 value 修復 | SV | validation_error→候選值逐一試(上限 5) |
| 失敗元素黑名單 + URL 級 rollback | SV | fail_count 進評分、rollback 先 goto url_before |
| StepTrace.url + screenshot loud-fail + v2 export | OM | StepTrace 加 url;_screenshot 失敗記入 detail(現 silent swallow) |
| Error-key normalization 報告 | BG | 錯誤訊息 regex 分桶,自動產 failure-gallery 候選 |
| Seeded 任務家族 + --filter | BG | task_seed 可重現變體 + metadata 子集 flag |
| Domain whitelist 常開 + infeasibility reason 比對 | BG | allowed_origins harness 級常開 + give_up reason 計分 |
| Replay-agent drift regression | BG | prompt/response 全文落盤 + ReplayPlanner difflib CI |
| PageMem 式結構化頁面表徵 | SV | 語意分段 + section summary 快取 |
| Model tiering / LLM fallback | SK、SV | 小模型第二 handle;repair 長出 LLM rung 後才相關 |
| Compound action workflows | SV | planner 回 action list;引入須連帶 stale-DOM guard |

## 3. Per-criterion 定位(對照題目評分維度):我到底站在哪一格?

**我方 outcome-level 基線**:offline deterministic mock 支援集(`data/browser_eval/tasks.json`,4 tasks)task success rate 1.0、verdict accuracy 1.0、verifier FP 0.0;5-task apparent 集 apparent 0.8、Rogan-Gladen 校正後 0.8(`docs/eval_report.md`、`calibration_results.json`)。誠實界定:小型自建 deterministic set 的建構性數字,不可與 bu-max live 97.0% 直接比較(任務集、難度、判定協定皆不同)。

> 白話:1.0 是我自己出的考卷、自己的沙盒裡考的滿分 —— **不是「我跟榜首打平」,是「我在自己家裡沒錯」**。所以下面五節全是拿真實網站打的分數,那才是照妖鏡。

### 外部量測 2026-07-10(Online-Mind2Web 20-task subset,live web,自跑):第一次上真實網站,幾分?

P1-1 匯入的 20 題 live 子集,以我方 agent 實跑(serial、難度階梯 step budget、second judge advisory on)。本波 baseline 跑靠 scratchpad 臨時腳本 `run_m2w.py`;`tools/run_external_eval.py` 其後才產品化。

| 指標 | 數字 |
|---|---|
| success(pass / 可評分,排除環境失效) | **6/18 = 33.3%** |
| success(raw pass / 20) | 6/20 = 30.0% |
| 分難度 | easy 1/6、medium 4/8、hard 1/4 |
| naive baseline 對照(同子集) | 4/20 = 20%(trivial pass;tracked 快照 `data/browser_eval/external_runs/naive_baseline/results.json`) |
| 環境失效(ERR_HTTP2,依維護協議排除) | 2/20(可重現) |
| 成本 | 平均 $0.0058/task、18 題共 $0.10;wall ~77s/task |
| second judge(advisory) | 18/18 全 abstain |

結論:高於 paper naive 22% / 我方 naive 20%(機制有加值),但遠低於 leaderboard 頂端(bu-max live 97.0%)——如實記錄。caveat:n=18 單跑;easy < medium 反常屬小樣本雜訊;second judge live 全 abstain 為當時未泛化之限制(後續已修,見 abstain-fix 節)。artifact:tracked 快照 `data/browser_eval/external_runs/m2w_rerun/`(由 20 份 per-task summary.json 事後聚合,`aggregated_post_hoc=true`)。

> **對照錨永遠要有**:33.3% 單看沒意義,它的意義是「比笨基準 20% 高、離榜首 97.0% 很遠」。第二裁判 18/18 全棄權 —— 我養了個裁判,結果它一題都不敢判,這不是保守,是壞掉。

### 外部量測 rerun 2026-07-10(post bucket-fix):修了三個桶,漲的是哪一個?

同 20 題重跑,套三個 bucket 修復(robust text_visible、open-ended scoring 參數層、navigation convergence)+ second judge 經 gateway 武裝。

| 指標 | baseline | rerun | 移動 |
|---|---|---|---|
| success(pass / 可評分) | 6/18(33.3%) | **8/18 = 44.4%** | +11.1pt |
| success(raw pass / 20) | 6/20 | 8/20 | +10pt |
| easy / medium / hard | 1/6、4/8、1/4 | 2/6、3/8、3/4 | +1、−1、+2 |
| unknown(可評分池內) | 3 | 6 | +3(變差) |
| 環境失效(排除) | 2/20 | 2/20(同兩站,可重現) | 同 |
| second judge(advisory) | 18/18 abstain | 18/18 abstain(已武裝仍 abstain) | 未動 |

結論:唯一可歸因、可複現的加分來源是 robust text_visible(`verifier.py:34`,兩題同步數翻 pass);open-ended 層仍 18/18 abstain(結構性根因,後續 judge-fix 關閉);navigation convergence 中性偏負(貢獻唯一回歸 espn pass→unknown)。caveat:n=18 單跑、live variance 大,+11.1pt 是含雜訊方向指標;這批契約多為單一 landmark,verifier 對其是弱 proxy。artifact:`data/browser_eval/external_runs/m2w_rerun_20260710/`。

> 三個修法只有一個真的有用,一個中性偏負(還害我掉一題),一個完全沒動 —— **不是「修了三個東西漲了 11.1pt」,是「一個東西漲了 11.1pt,另外兩個我照實列在旁邊」**。unknown 從 3 變 6,這格是變差,不藏。

### 外部量測 abstain-fix 2026-07-10(post judge-fix):裁判為什麼從「全棄權」變成「敢判」?

live-abstain 根因修復後的最終量測。根因修復 commit:**`6dbe095`**(unwrap codex-gateway action-schema wrapper,judge 解析不到 body 的直接根因)+ **`9a40ae2`**(open-ended scorer 於 verdict 時武裝:零條件契約接上 `open_ended_extractor`,證據=最終頁 `inner_text` 12K + P0-5 逐步摘錄,引文須真出現於證據方能 grounded-satisfied);量測基建修復 `e53c324`(per-task context 隔離)。定向重跑 `m2w_rerun_20260710` 的 6 個 unknown(任務檔 `data/browser_eval/external/m2w_unknowns6.json`,sha256=`1acfc7a3a20a3bc20d5bb07cdaed243642272dcfeccb232028ff62d8d4226c9b`),非全集。

白話:上一節那個「一題都不敢判」的裁判,根因不是它膽小,是**它根本沒收到題目** —— gateway 把回應包了一層殼,judge 解析不到 body。拆殼(`6dbe095`)+ 把開放式評分器真的接上證據(`9a40ae2`)之後再測。

最終 artifact:`runs/browser_eval/m2w_abstain_fix2_20260710/results.json`(gitignored)+ tracked 快照 `data/browser_eval/external_runs/m2w_abstain_fix2_20260710/results.json`;fix 前對照 artifact:tracked `data/browser_eval/external_runs/m2w_abstain_fix_20260710/`——同 6 題全部 unknown、second judge 全 abstain。

| 題 | 站點 | 難度 | fix 前 | fix 後 verdict | second judge(advisory) | 一致性 |
|---|---|---|---|---|---|---|
| m2w-005be9dd91c9 | qatarairways | easy | unknown / abstain | fail | no | 一致 |
| m2w-3f312ae3efc3 | nfl | easy | unknown / abstain | fail | yes | **分歧**(advisory 不改判) |
| m2w-a6f0434ce6af | yahoo finance | easy | unknown / abstain | **pass** | yes | 一致 |
| m2w-6ca20f1da01e | gov.uk | medium | unknown / abstain | **pass** | no | **分歧**(advisory 不改判) |
| m2w-864244b6969e | espn | medium | unknown / abstain | **pass** | yes | 一致——即 baseline 的 `Formula` 回歸題,本輪**收復** |
| m2w-aa4b5cb7114f | ign | medium | unknown / abstain | unknown | abstain | 有抽到答案(「Undaunted: Stalingrad 10/10 review」)但 key-point grounding 不足 → **誠實棄權,非幻覺通過** |

**結果**:6 unknown → **3 pass + 2 fail + 1 honest-abstain unknown**;judge abstain rate **6/6 → 1/6**。有真實證據的開放式任務(TSLA 收盤價,證據含 `Mar 17, 2023 … Close 180.13`,已人工抽查非幻覺)拿到 grounded pass;證據不足者誠實 fail/abstain,無假 pass;殘餘 1 題 honest abstain(ign)屬防幻覺機制正確運作。

**合成 topline(標明為合成估計,非單跑實測)**:rerun 44.4%(8/18)→ 6 unknown 中 3 翻 pass → **11/18 ≈ 61.1%**(排除 2 環境失效;vs naive baseline 20%)。

**誠實 caveat**(白話:下面四條是我主動攻擊自己這個 61.1%):
- (a) 合成數字**跨兩次 launch**(44% 全集跑 + 6-unknown 定向重跑),live variance 未控制,61.1% 是**估計值非單跑實測**;
- (b) aa4(ign)最後一題經 resume 二次執行——第一次誤用 offline judge,刪除該結果後以 LLM judge 重跑(`results.json` judge_source=llm),兩次 verifier 判決同為 unknown;
- (c) second judge 對 **2/6 題與 verifier 分歧**(nfl:verifier fail vs judge yes;gov.uk:verifier pass vs judge no)——advisory-only 設計守住 **verifier 唯一裁判**,分歧只記錄不改判;
- (d) n 小,61% 應視為方向指標。這關閉了上節「兩層對 live 皆未泛化」中的 second-judge 層;verifier landmark 層對這批弱契約仍是弱 proxy,屬題目契約設計而非機制缺陷。
- 量測基建:productized runner 單一共享 page 會被一次硬導覽失敗 cascade 污染,本波以 isolated-context driver(每題獨立 context+page)量測;per-task page 隔離回饋進 runner 為待辦。

> ign 那題最值得講:**系統抽到了答案,卻選擇不通過** —— 因為 grounding 不足。這不是失手,是防幻覺機制在該響的時候響了。**寧可誠實棄權,不要幻覺通過。**

### 外部量測 held-out 2026-07-11(凍結 20 題不相交子集,單跑,反 overfitting):61.1% 是不是調參調出來的?

61.1% 為迭代後合成數字(bucket-fix/abstain-fix 都照原 20 題修),無法排除 overfitting;本波以 pre-registered 凍結協定補證:同一 cached upstream fetch(300 題,hud-evals CC-BY mirror)→ 同 committed 排除濾網 → 移除原 20 題(零重疊 assertion)→ 依官方難度分佈 largest-remainder 抽 20(easy 5 / medium 10 / hard 5,每層 source_task_id 升冪 FIRST-N,per_domain_cap=2)。先凍結後跑、單跑、如實報,修改 agent/verifier 後重跑本集為禁手(`freeze_manifest.json`,task 檔 sha256 `f143d634ab95cd3e3b203592229dc7c46c73a404e63a790c2dfd50c9e522bea0`)。

【自我攻擊】前面三波我都是「照著同 20 題修、再拿同 20 題測」—— 這叫對著考古題調參,分數當然會漲。【假說】若 61.1% 是調參產物,換一批**沒看過的題**應該掉下來。【去測】凍結一組零重疊的新 20 題,先寫死協定再跑,單跑一次,不准回頭改了再跑。

| 指標 | 數字 |
|---|---|
| 分佈 | done 18、harness_error 2(env-classified site_unreachable,依 taxonomy 排除);pass 12 / fail 5 / unknown 1 |
| **gradable success** | **12/18 = 66.7%** |
| 分難度 | easy 3/5、medium 7/10、hard 2/3(hard +2 harness error) |
| second judge(advisory) | yes 5 / no 5 / abstain 8;硬衝突 2(verifier pass vs judge no),judge 未改任何判定 |
| 成本 / 延遲 | LLM $0.0364、104,910 agent tokens;agent loop mean 58.6s / median 45.3s;end-to-end ~21 min,單次前景 launch,exit 0 |

結論:held-out 單跑 66.7% ≥ 迭代後 61.1%,指向 pipeline 泛化而非調參到原 20 題。可比性(強制聲明):61.1% 是 ITERATED composite、66.7% 是 disjoint 任務 SINGLE frozen run——並排是反 overfitting 證據,非同分母比較;n=18 小、live variance 未控,照舊為方向指標。artifacts:`data/browser_eval/external/m2w_heldout_20260711.json`、`runs/browser_eval/m2w_heldout_20260711/{freeze_manifest.json, results.json, manifest.json, console.log}`。

> **不是「66.7% > 61.1% 所以我更強了」,是「換沒看過的題沒有掉下來,所以那 61.1% 不太像調參調出來的」** —— 這兩個數字並排的用途是反 overfitting,不是比大小。

### 外部量測 300 題官方全量 2026-07-11(無排除、雙口徑;**最終 rollup:done 283/300**):官方全量,不挑題,幾分?

敘事鏈三級:20 題(迭代,合成 61.1%)→ 20 題 held-out(凍結單跑 66.7%)→ 300 題官方全量——三組口徑作用各異(迭代開發 / 反 overfitting / 官方全量對標),不可混比。Run 最終狀態:done 283 / harness error 17(全為環境 site_unreachable,含 anti_bot 4)/ not_run 0;wall 134 分鐘。

**口徑 1:runtime verifier(唯一裁判)**——done-283:pass 95 / fail 158 / unknown 26 / refused 4 → SR = **95/283 = 33.57%**(全分母 95/300 = 31.67%);分層 easy 37.33%、medium 25.19%、hard 45.21%。artifact:`webjudge_results.json → final_summary.verifier_axis_final`。

**口徑 2:WebJudge advisory(官方三段協定:key-point 抽取 → 逐截圖評分 → trajectory 判定)**——judged 283/283:success 21 / failure 192 / abstain 70 → SR = **21/283 = 7.42%**(abstain 留分母);abstain_rate 24.73%。誠實揭露:63/70 abstain 是 judge 照抄 envelope 範例字面字串的 prompt 模板 artifact,abstain_rate 為受此膨脹的上界(`final_summary.webjudge_axis_final.abstain_reasons`)。

白話:同一批 283 題,兩個裁判給的分差了 26 個百分點(33.57% vs 7.42%)。下面這張表就是把兩個裁判的每一種組合攤開來 —— **裁判之間吵架的地方,才是資訊量所在**。

| verifier \ WebJudge | success | failure | abstain |
|---|---|---|---|
| pass(95) | 11 | 56 | 28 |
| fail(158) | 8 | 119 | 31 |
| unknown(26) | 2 | 17 | 7 |
| refused(4) | 0 | 0 | 4 |

decided-pair agreement **130/194 = 67.0%**;最大分歧格 = verifier pass 但 WebJudge failure(56 題,WebJudge 遠嚴於 verifier);hard 上兩軸分歧最大(verifier 45.21% vs WebJudge 2.74%、abstain 34.25%)。**verdict 從不覆寫 runtime verifier**(advisory-only)。

不可比性(強制聲明):judge model = codex gateway gpt-5.5-class,**非論文的 o4-mini/WebJudge-7B** → 不可與 leaderboard 比較(Browser Use ~97% 用官方 WebJudge+o4-mini);偏差逐條列於 results JSON `deviations_from_official` 與 `tools/webjudge.py` docstring;judge 名目成本 $0.4714(實際經 gateway $0)。License:Online-Mind2Web repo 程式碼 MIT、dataset CC-BY-4.0(已署名),登記於 `docs/ATTRIBUTION.md`。過程事件:46/300 時 resume/abort-guard 死鎖(3 題持久 site_unreachable 觸發 `should_abort(3,3)`),根因修復 commit **`548bd6d`** 後補完至 300/300(measure-fix-remeasure,如實記錄)。

- Artifacts:`runs/browser_eval/m2w_full300_20260711/`(results.json 最終 rollup、per-task summary.json 權威、webjudge/webjudge_results.json、webjudge/per_task/*.json 283 份、judge_full_run.log;gitignored)→ 關鍵快照 `data/browser_eval/external_runs/m2w_full300_20260711/`。

> **56 題「我判 pass、WebJudge 判 failure」是這份文件最不舒服、也最誠實的一格。** 我沒有改判 —— advisory 就是 advisory,verifier 是唯一裁判;但我把這 56 印在這裡,而不是只報 33.57%。

### 3.1–3.5 分維度差異點與缺口:每一格,我強在哪、破在哪?

- **Self-correction**:差異點——修復 diagnosis-driven 且零 LLM 成本(確定性 a11y 評分),feasibility gate 防「修進成功」,修復結果由 verifier 獨立驗收。缺口:P0-7 hash cascade、P0-1 mid-run loop 回饋、P0-2 前置攔截。
- **Self-maintenance**:差異點——快取按構造免疫 stale-payload(字面資料不落盤)、write-back 帶 success/fail 計數與 RepairEvent telemetry。缺口:P0-10(agent mode 不碰 memory,自證最大 cost 槓桿)、shadow-mode cache FP-rate。
- **Eval depth**:差異點——judge 以 sens/spec 分解 + Rogan-Gladen 校準(n=50 小集、未附 CI,審查須先坦承此限;OM/BG 無 sens/spec 分解與 prevalence 校正,WebJudge 85.7% 是 task-level agreement);impossible 軸與 degradation curve 為兩者所無。缺口:P1-1 廣度與 P1-10 ablation 已補;P1-3 oracle、P1-2 manifest 未落地。
- **Silent-failure prevention**:差異點——自述隔離是程式化而非 prompt 約定;任何終止路徑被 verify_contract 收口;unknown 三態傳播使缺證據永不 pass。已知弱點(如實列):中途成立後導航離開會誤判假陰性(P0-5)、缺 done 前閘門(P0-3)、claimed-vs-verified 特徵餓死(P1-7/P1-8)。
- **Cost analysis**:差異點——repair 零 LLM 成本、vision 按需付費、per-call cost 記帳。缺口:P0-6(llm_cost 現為死碼)、cost-per-success 未落地;且無 BU/SK cost-per-task 對方實測數字——cost 比較目前是機制比較而非量測比較(OPEN,見完整性批判)。

> 五格裡我真正站得住的是 silent-failure prevention:**不是「我的 agent 比較少犯錯」,是「它犯錯的時候比較難假裝沒犯錯」。**

## 4. 來源引用:每個機制,我從誰的肩膀上拿的?

白話:下表每一行都是「我借了什麼、跟誰借的」。借來的想法就寫是借的,對方的數字就標對方的快照日期 —— **站在巨人肩膀上,前提是說清楚那是誰的肩膀。**

| 來源 | 引用內容 |
|---|---|
| browser-use — github.com/browser-use/browser-use | cascading locator healing、ActionLoopDetector、pre_done_verification、message compaction;bu-max 97.0%(leaderboard https://osu-nlp-group.github.io/Online-Mind2Web,快照 2026-07-10) |
| Skyvern — github.com/Skyvern-AI/skyvern | element structural hash rebind、四維預算、CODE_FIXABLE triage、16-class taxonomy、two-stage judge |
| Stagehand v3 — github.com/browserbase/stagehand | self-healing replay cache、a11y line diff、hallucination 4-way split、EncodedId grounding、processScore/outcomeSuccess 分離 |
| Online-Mind2Web + WebJudge — OSU-NLP-Group,COLM 2025,arXiv:2504.01382;HF dataset OSU-NLP-Group/Online-Mind2Web(gated) | 300 題 live benchmark、reference_length 分層、WebJudge 三段裁判、naive-baseline 對照(22% vs 51%)、任務維護協議 |
| Magentic-One — arXiv:2411.04468(Microsoft) | dual-ledger 停滯偵測 + 觸發式 replanning |
| WebChallenger — arXiv:2606.10423 | PageMem 結構化頁面表徵 ablation(-17.6)、compound workflows |
| Alumnium — WebVoyager #1 98.5%(self-reported,judge 未校準,快照 2026-07-10) | selector self-healing 佐證(證據力弱,僅作機制存在佐證) |
| BrowserGym + AgentLab — ServiceNow,arXiv:2412.05467 | per-task status trichotomy、repro manifest、oracle cheat()、watchdog relaunch、seeded 任務家族、evaluator DSL |
| WebVoyager eval protocol — arXiv:2401.13919 | LLM-judge fallback(task + answer + last-k screenshots、abstain) |
| OpenAI CUA/Operator、Anthropic computer-use、steel.dev leaderboard | survey 彙整之機制脈絡 |
| WebArena — arXiv:2307.13854 | url/program_html/must_include evaluator 組合語彙(經 BG 轉引) |
| WebCanvas / Mind2Web-Live — iMeanAI,arXiv:2406.12373;github.com/iMeanAI/WebCanvas(`evaluate/step_score.py`) | key-node latch 語義、URL-first 抗漂移、scheduled replay 失效報告 loop;反面教材:semantic match `eval()` 解析 LLM 輸出後靜默歸 0(P0-5) |
| Agent-E — Emergence AI,arXiv:2407.13032;github.com/EmergenceAI/Agent-E(`ae/utils/dom_mutation_observer.py`) | change observation(P0-4 機制本體,含 100ms race + attribute-blind 已知限制)、DOM distillation、self-aware 52% / oblivious 48% 失敗分類 |
| AgentOccam — Amazon,ICLR 2025,arXiv:2410.13825;github.com/amazon-science/AgentOccam(`obs_opt.py`、`configs/*.yml`) | 極簡反命題、階梯 ablation(16.5→43.1)、pre-execution 幻覺閘門(P0-2)、minimal-baseline control arm 範本(P1-10)、+SteP 掉 2 分 |
| WorkArena / WorkArena++ — ServiceNow,arXiv:2403.07718 / 2407.05291;github.com/ServiceNow/WorkArena(`tasks/form.py`) | 企業任務分類、collateral-damage watcher(範圍外欄位 change listener)、non-terminal vs terminal 分流、cheat() oracle、無線索 infeasible 變體(P1-13) |
| Mind2Web 2 — OSU-NLP,NeurIPS'25 D&B,arXiv:2506.21506;github.com/OSU-NLP-Group/Mind2Web-2(`mind2web2/verification_tree.py`) | rubric tree + gate-then-average 聚合、Agent-as-a-Judge leaf-level 99.03%(vs WebJudge 85.7%)、Extractor/Verifier 分離、stub-pass 煙霧測試、evidence pre-caching(P0-8) |
| VisualWebArena — CMU,arXiv:2401.13649;github.com/web-arena-x/visualwebarena(`evaluation_harness/evaluators.py`) | observation-only vision-gain 分層測量(text 7.25%→+SoM 16.37%)、PageImageEvaluator(SSIM/VQA)、visual_difficulty 分層(P1-13) |
| 安全軸(SEC)— ST-WebAgentBench arXiv:2410.06703、SafeArena 2503.04957、WASP 2504.18575(code facebookresearch/wasp)、EIA 2409.11295、SecureWebArena 2510.10073、WAInjectBench 2510.01354 | 兩威脅模型(misuse policy-compliance + prompt-injection)、CuP、WASP intermediate-vs-e2e ASR 兩段計分、instruction/content separation + action policy gate 兩層防禦(P1-14) |

**資料集使用聲明**:eval set 匯入之 Online-Mind2Web 任務子集(P1-1)每筆保留原 task_id 映射,於 `data/browser_eval/tasks.json` 與 `docs/eval_report.md` 明確署名 OSU-NLP-Group Online-Mind2Web(COLM 2025,arXiv:2504.01382),遵守 HF gated dataset 取得條款;衍生變體標注 derived-from。

## 附錄:already_have / not_applicable 摘要——哪些「缺項」其實不是缺項?

白話:對照時最容易灌水的一招,是把「對方有、我沒有」全算成待辦,讓 backlog 看起來很努力。這節反過來:下面這些我**明確不做**或**構造上已經有**,理由寫在括號裡,接受檢驗。

BU multi_act stale-DOM guard(n/a:每回合恰一動作 + 每次 observe 重 stamp)、BU use_vision='auto'(already_have:AGENT_VISION 三態)、SK user_detail_query(already_have by construction)、SK TOTP/credential vault(n/a by design:capability guard 拒憑證輸入)、SK workflow DAG(明確不採,依 workflow 拆題偏好)、OM「judge 不吃自述」(already_have 且程式化)、OM 截圖評分過濾 / WebJudge-7B(n/a,前置條件不存在)、OM 任務失效維護協議(併入 P1-1 作 live 配套)、SG Top-K evidence batching(n/a:verifier 零 LLM)、BG per-step validate()(already_have)。

## 完整性批判(2026-07-10;已結項紀錄見 git history):這份對照本身,哪裡還不完整?

白話:這節是**驗證這份文件的驗證器** —— 我請人來挑「你的對照表本身漏了誰、宣稱得太滿沒有」。

兩輪修訂後:七個曾缺席的對照專案(WC/AE/AO/WA/M2/VWA/SEC)均已補入引用與 backlog 掛點;評分維度缺 P0 項(self-maintenance→P0-10、scalability→P0-11、long-horizon→P1-15、frontend→P1-16)與過強宣稱(bu-max/Alumnium 快照標注、sens/spec n 與 CI 註記、judge 校準宣稱窄化)均已 resolve,逐項紀錄見 git history。仍 OPEN、皆需實際量測而非文件可補:

1. §C6:BU/SK cost-per-task 對方數字未取得——§3.5 cost 比較仍是機制比較而非量測比較。
2. §B5:latency 分佈量測與對 SOTA 的 wall-clock 對照未做(現有 `docs/cost_latency_report.md` 僅 per-step latency)。

> 這兩條都不是文件能補的 —— **要嘛去量,要嘛承認沒量。我選後者,並把它印在最後一行,而不是刪掉。**
