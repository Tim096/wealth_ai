# Cost / Latency Report

> **數據為 2026-07-10 快照,可重跑驗證。** 重生指令:
> `.venv\Scripts\python tools\sweep_metrics.py runs\sweep2`(SEC parse)、
> `.venv\Scripts\python tools\browser_eval.py`(browser)、fetch 統計見下方指令。
> 因為 cache 會隨使用增長,本報告的 fetch 數字是特定時點快照;若與現況不符,重跑上述指令即為最新值(這正是「可重跑」的意義)。

## SEC Extractor

### Fetch 成本(EDGAR)

以下由 `data/raw_filings/fetch_log.jsonl` 計算:

| 指標 | 值(2026-07-10 快照)|
|---|---|
| 總存取 | 1,014 |
| 實際 live 請求 | 51 |
| Cache 命中率 | **95.0%** |
| Live fetch 延遲 | mean 551 ms,max 1,430 ms |
| Raw cache | 51 blobs,155 MB |

Content-addressed cache,讀取驗 sha256,corruption raise。同一 filing 重跑=零網路、位元組級可重現。

### Parse 延遲

| 指標 | 值 |
|---|---|
| Parse(11 家 sweep2)| mean 1,146 ms,max 2,544 ms(JPM,12.9M chars)|
| 對文件大小 | 近線性(~0.2 ms/KB)|

單執行緒純 Python,瓶頸是 normalizer 的逐字元 offset mapping。這是**刻意的權衡:offset 精確性 > 速度**——它讓每個 span 可 sha256 驗證。可擴充性:pipeline 是 per-filing 可平行(process pool)。

### XBRL 認證成本

Item 8 對 companyfacts 交叉驗證:每家多 1 次 `companyfacts` fetch(cache 後 0),純字串比對 <1 ms。11 家認證總 live fetch ≤ 11 次。**成本可忽略,價值是獨立 oracle**(見 `data/sec_eval/certification/item8_certification.json`)。

### LLM 成本(實測,2026-07-10)

**主路徑仍是 0 個 LLM call — 確定性 pipeline 覆蓋 253/253 items,ambiguous 觸發率 0%。** adjudicator tier 已 wired(`pipeline.adjudicate_ambiguous()`,opt-in:`SEC_LLM_ADJUDICATE=1` 或顯式呼叫),並以真實 LLM 實測過單筆 $/裁決。真實 sweep 無 ambiguous 樣本,量測用合成 ambiguous fixture(兩個非 TOC 的 Item 1 heading 對決,同 `tests/test_adjudicator_wiring.py`),經完整 wired 路徑:`extract_from_html` → `adjudicate_ambiguous` → `OpenAIClient` → codex exec(ChatGPT OAuth,帳號預設模型)→ `codex --json` 回報的**真實 token usage**。

| 指標(3 次重複,實測)| 值 |
|---|---|
| input tokens / 裁決 | 17,910(固定;其中 adjudicator prompt 本體僅 ~2.6K chars ≈ ~650 tokens,其餘 ~17K 是 codex CLI harness 的固定 system prompt 開銷)|
| output tokens / 裁決 | mean 686(230–1,103,含 reasoning tokens)|
| **$/裁決(codex 通道牌價換算)** | **mean $0.0058**($0.0049–$0.0067;tokens 實測 × `OPENAI_PRICE_IN/OUT` 預設 $0.25/$2.0 per 1M)|
| $/裁決(直連 API 等效,無 harness 開銷)| ~$0.0015(~650 in + 686 out tokens 換算)|
| 延遲 / 裁決 | mean 12,887 ms(7.1–16.6 s;codex exec 啟動 + reasoning 主導)|
| 邊際現金成本(ChatGPT OAuth 訂閱)| $0 |
| schema gate | 3/3 通過(decision=candidate_b 正確、evidence_quote 皆 verbatim)|

舊估計「<$0.005/裁決」對照:codex 通道實測 $0.0058(harness 開銷墊高),直連 API 等效 ~$0.0015(低於估計)。**per-filing 成本欄已入帳**:`ExtractionResult` 帶 `llm_calls / llm_input_tokens / llm_output_tokens / llm_cost_usd / llm_call_records`(deterministic 路徑恆為 0,by construction);`tools/sweep_metrics.py` 聚合並輸出 per-filing `llm calls / llm usd` 欄(舊 records 無此欄=純確定性 run,計 0 是精確值非估計)。

### 擴充性

- 每 filing 均攤:~3 live requests × 0.5s rate limit + ~1.1s parse ≈ 3–5 秒(冷 cache);熱 cache <1.2s。
- S&P 500 單機:冷 <45 分,熱 <10 分。
- **Rate limit 是硬上限**(SEC ~10 req/s),多機平行抓取無意義;平行化只用在 parse 層。

## Browser Agent

來源:`runs/browser_eval/results.json`(5 tasks,mock sites,offline)。重生:`tools\browser_eval.py`。每次 run 併寫 `runs/browser_eval/manifest.json`(P1-2 repro manifest:git commit/dirty、model id、task-set sha256、套件版本;`--strict-repro` 對 dirty tree 直接拒跑,數字永遠可釘回產生它的 code)。

**穩定不變量(不隨 run 漂移,以下為硬數字):**

| 指標 | 值 |
|---|---|
| task success rate | 1.0 |
| **verifier false-positive rate** | **0.0**(空結果 task 正確判 fail,不偽裝成功)|
| trace completeness | 1.0 |
| verdict accuracy | 1.0 |

**會隨 selector memory 狀態漂移的量測(不在此硬寫,以 artifact 為準):** 平均延遲(2026-07-10 passk-restore 重跑後快照 ~946 ms/task)、repair success rate——因為 memory 在 tasks 間累積(第二個同類漂移 task 可能 0 repair),這些值 run-to-run 會變。**正確做法是讀 `runs/browser_eval/results.json`,不是把快照凍進文件**——這也是我們對「可重跑」的一致態度:會變的量測不硬寫。

### Browser 成本結構

- **離線 eval 的 LLM 成本 $0(實測,by construction):** Script Mode(memory 命中)與 a11y-tree repair 都是確定性,不呼叫 LLM;offline eval 的 Agent Mode subset 用 MockPlanner,也不呼叫 LLM——artifact 的 `llm_cost_usd_total: 0.0` 是精確值。舊版此處寫「escalation 到 LLM 尚未 wired」已過時:LLM 路徑**已接上**(`LLMPlanner` via codex gateway + 卡住時視覺升級),且 P0-6 起每個 run/row 帶 `llm_calls / llm_tokens / llm_cost_usd` 入帳(live run 記在 `runs/agent_live/run.json`)。offline set 的 $0 是「不需要」,不是「量不到」。
- **Live 外部量測成本(Online-Mind2Web 20-task subset,實測 2026-07-10):** 平均 **$0.0058/task**、18 可評分題共 ~$0.10;平均 wall ~77s/task(baseline 跑,artifact `runs/browser_eval/m2w_rerun/`(gitignored)+ tracked 快照 `data/browser_eval/external_runs/m2w_rerun/`)。abstain-fix 定向重跑 6 題:per-task llm_cost $0.0002–0.0092、second judge 每題 $0.0002–0.0004、wall 44–257s(artifact `runs/browser_eval/m2w_abstain_fix2_20260710/results.json` + tracked `data/browser_eval/external_runs/m2w_abstain_fix2_20260710/results.json`)。逐題 p50/p95 與 cost-per-success 見下方「Latency 分佈與 cost-per-success」節。
- **Runtime 成本**:Playwright headless Chromium,含 launch 攤提;真實網站會受網路延遲主導(live 外部量測 wall ~44–257s/task,遠高於 mock 的 <1s,主因網路 + LLM planner latency)。
- **Repair 延遲**:UI 漂移時多 1–2 次 observe + a11y 搜尋,單步 <100 ms;selector memory 命中後第二次同類 task **0 repair**(見 eval:v2-gizmo),攤平漂移成本——這是 selector memory 的核心價值。

### Latency 分佈與 cost-per-success(2026-07-11 實算,逐題資料)

各 run 的 tracked 快照 `results.json` 帶逐題 `wall_s` / `latency_ms` / `llm_cost_usd`,可實算分佈(排除 `env_error` 題;percentile 用排序後線性內插):

| Run(artifact,均在 `data/browser_eval/external_runs/`)| n 可評分 | pass | wall p50 | wall p95 | LLM 成本合計 | **cost / successful task** |
|---|---|---|---|---|---|---|
| `m2w_rerun/results.json`(baseline)| 18 | 6 | 45.6 s | 210.5 s | $0.0946 | **$0.0158** |
| `m2w_rerun_20260710/results.json`(bucket-fix rerun)| 18 | 8 | 26.6 s | 226.1 s | $0.0526 | **$0.0066** |
| `m2w_abstain_fix2_20260710/results.json`(6 題定向重跑)| 6 | 3 | 133.5 s | 236.6 s | $0.0253 | **$0.0084** |

SEC parse latency(`data/sec_eval/records/sweep3/*.json` 逐 filing `latency_ms`,n=11):**p50 1,073 ms / p95 2,526 ms / max 2,805 ms**(與上方 sweep2 快照 mean 1,146 ms 同量級;sweep3 為現行 records)。

計算方式:`.venv\Scripts\python` 讀上述 JSON → 過濾 `env_error` → 對 `wall_s` / `latency_ms` 排序取 p50/p95(線性內插);cost-per-success = Σ`llm_cost_usd`(可評分題)÷ pass 數。誠實註記:(1) m2w 是 live 網站單跑,wall 受網路與站點狀態主導,p95 是方向指標非 SLA;(2) abstain-fix 批次是定向重跑先前的 6 個 unknown(選樣偏難),其 p50 不可與全集 run 直接比;(3) SEC records 無 per-filing `llm_cost_usd` 欄的即為純確定性 run(成本恆 0,by construction,見上方 LLM 成本節)。

### Replay cache(P0-10,跨 run 攤平 LLM 成本)

Agent Mode 由 verifier 判 pass 的 run 會把成功動作序列(durable selector + P0-7 結構 hash)入庫 `replay_cache.json`(key = site × task_type × task);同一 task 下次先逐步 replay 再問 planner——**乾淨 replay = 0 LLM call**,第一個失效步驟即 invalidate 並把同一回合交還 planner。verifier 仍是唯一裁判(replay 走完不等於 task pass)。

| 指標 | 值 | 性質 |
|---|---|---|
| banked trajectories(eval 通道,`runs/browser_eval/replay_cache.json`)| 2 條;gizmo `success_count=2` = 兩次 verifier-passed run(第二次走 cache replay),widget = 1 | 實測(artifact,2026-07-10)|
| 乾淨 replay 的 planner 成本 | 0 LLM call(replay 先於 planner)| 實測(`tests/test_p0_10_replay_cache_shadow.py` deterministic 釘死)|
| live 通道(`runs/agent_live/replay_cache.json`)| 2 條,各 `success_count=1` | 實測(artifact)|

Script Mode 另有 **shadow-mode cache 驗證**:remembered-selector 命中每 N 次抽驗一次(`CACHE_SHADOW_EVERY` 覆寫),從頭重推導並以**結構 hash**比對元素(非 selector 字面);`dom_fingerprint` 漂移會強制跳過抽樣直接驗。計數器落在 `TaskRun.cache_stats`(`as_dict()['cache']` 含 fp_rate)。**誠實標註:** mock eval set 無真實漂移場景,fp_rate 尚無非平凡實測值(divergence=0 是預期而非成果);divergence/agreement 行為由 10 個 deterministic tests 釘死,真實網站的 cache fp_rate 待累積,目前不宣稱數字。

### 平行 worker pool(P0-11,多 session 成本模型)

`--workers N`:subprocess pool,每 worker 一條持久 browser session(冷啟攤提)+ 每 task 新 context;parent 端 wall-clock watchdog 終結 hung worker。實測(2026-07-10 重跑 `tools\browser_eval.py --workers 2`,5 tasks,當時 artifact `runs/browser_eval/results.json` `scalability` block;**註**:該檔其後被 passk-restore 的單 pass serial 重跑刷新,現行檔無 `scalability` block——重跑 `--workers 2` 即重生,下表為當時快照):

| 指標 | 值 |
|---|---|
| wall clock | 4.13 s(serial 估計 5.49 s → speedup **1.33x**;2 workers × 5 tasks 天花板本來就低,價值在成本模型非加速本身)|
| throughput | 72.6 tasks/min |
| session 冷啟 | mean 424 ms/session;攤提後 169.6 ms/task |
| per-session utilization | worker0 0.72 / worker1 0.51 |
| watchdog kills | 0 |

wall/throughput/冷啟/utilization 是實測;speedup 的分母 `serial_estimate`(= busy 時間總和)是估計對照,如實標註。P1-15 起 pool watchdog 隨 set 內最大 step budget 線性放大(8 步→90 s、15→168.75 s、25→281.25 s,`watchdog_timeout_s` 實算),hard task 不會被 easy task 的檔期殺掉。

### 成本控制決策

1. Serial prefetch → parallel analysis(避免多 process fetcher 超過 SEC rate limit)。
2. LLM 不在主路徑(hallucination 與成本同時歸零,只留 ambiguous fallback)。
3. Selector memory:漂移修復一次記住,第二次同類 task 免 repair。
4. Raw cache 永久保存:eval 重跑免費。

## 2026-07-10 eval 升級波:成本註記

本波 11 項 eval(T1-1~T1-6、T2-1~T2-5)**全部離線 deterministic、零 LLM 成本**:browser 側(verifier 校準、擾動矩陣、impossible set、trajectory、pass@k、false-success detector)走 headless chromium + 純函式,無 LLM call;SEC 側(三角驗證、offset F1、CYD oracle、分層抽樣、landmines)全走 cache-first EDGAR,重跑零網路(triangulate 對「同一份 cached raw HTML」離線解析;CYD tag 就在同檔內,無新抓取)。數字與解讀見 `eval_report.md`「Eval 升級」段;artifacts 全部 committed。

新工具重跑指令清單:

| 工具 | 指令 |
|---|---|
| Verifier 校準 + Rogan-Gladen | `.venv/Scripts/python tools/calibrate_verifier.py` |
| Impossible set / silent-failure | `.venv/Scripts/python tools/impossible_tasks.py` |
| Trajectory metrics | `.venv/Scripts/python tools/trajectory_metrics.py` |
| pass@k / flakiness | `.venv/Scripts/python tools/browser_eval.py --repeat 3 --agentic` |
| Degradation curve | `.venv/Scripts/python tools/degradation_curve.py` |
| False-success detector | `.venv/Scripts/python -m tools.false_success_detector`(script 形式亦可,`2fc9f06`)|
| 三引擎 triangulation | `SEC_EDGAR_USER_AGENT=<contact> .venv/Scripts/python tools/triangulate.py` |
| char-offset F1 | `.venv/Scripts/python tools/score_offsets.py data/sec_eval/records/sweep3` |
| CYD Item 1C oracle | `SEC_EDGAR_USER_AGENT=<contact> .venv/Scripts/python tools/certify_cyd.py` |
| 分層抽樣 | `SEC_EDGAR_USER_AGENT=<contact> .venv/Scripts/python tools/stratified_sample.py` |
| Landmines | `.venv/Scripts/python -m pytest tests/test_landmines.py -q` |

已知重跑副作用(對抗式驗證員發現,如實揭露):`degradation_curve.json` 內嵌 per-probe latency_ms → 重跑非 byte-stable(metric 欄位完全確定);`tools/browser_eval.py` 會 append `data/browser_eval/evidence/*.jsonl`(既有設計);`tools/score_offsets.py` 預設覆寫 committed `offset_f1.json`(對非正式目錄評分請加 `--out`);`stratification.json` 內嵌 `generated_at` → 重跑非 byte-stable(其餘欄位確定)。重跑後如非刻意更新 artifact,`git restore` 之。其餘 artifact(calibration/impossible/trajectory/passk/false_success/triangulation/cyd)重跑皆 byte-identical(2026-07-10 最終驗收全數實跑複核)。
