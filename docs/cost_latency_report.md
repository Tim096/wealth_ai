# Cost / Latency Report(成本與延遲的成績單)

一句話:這份文件只回答兩個問題 —— **跑一次要花多少錢、要等多久**;而且每一個數字都能指回產生它的那個檔案。

**先畫地圖 —— 本份分六段:**

| 段 | 回答什麼 |
|---|---|
| 一、這份報告怎麼讀? | 哪些數字釘死不動、哪些是會漂的快照 —— 先講規矩再上數字 |
| 二、SEC Extractor 花多少? | 抓檔、解析、XBRL 認證、LLM 裁決,四筆帳分開算 |
| 三、Browser Agent 花多少? | 離線 eval、live 外部量測、replay cache,三筆帳分開算 |
| 四、加機器有用嗎? | workers 1/2/4/8 掃描、瓶頸判讀、外推到哪就停 |
| 五、我為了省錢做了哪些取捨? | 每個決定都是一筆可計價的交易 |
| 六、eval 升級波的成本註記 | 重跑指令清單 + 已知重跑副作用(如實揭露) |

---

## 一、這份報告怎麼讀?

> **數據為 2026-07-10 快照,可重跑驗證。** 重生指令:
> `.venv\Scripts\python tools\sweep_metrics.py runs\sweep2`(SEC parse)、
> `.venv\Scripts\python tools\browser_eval.py`(browser)、fetch 統計見下方指令。
> 因為 cache 會隨使用增長,本報告的 fetch 數字是特定時點快照;若與現況不符,重跑上述指令即為最新值(這正是「可重跑」的意義)。

白話:cache(把抓過的檔案存起來下次直接用的暫存區)只會愈用愈大,所以「命中率 95.0%」這種數字明天就會變。我沒有把它假裝成永恆真理 —— **不是「這個數字永遠是 95.0%」,是「2026-07-10 這個時點是 95.0%,你重跑就會拿到你的那一版」**。

這帶出我在全篇的規矩:數字分兩類。

- **硬數字**:不隨 run 漂移的(例如 verifier 判錯率 0.0)—— 直接寫進文件。
- **快照 / 會漂的量測**:隨 cache、隨 selector memory 狀態變的 —— 寫明時點,並指向 artifact,**以檔案為準,不以文件為準**。

> **不是「我報了一個好看的數字」,是「我報了一個你能自己重跑出來的數字,並且先告訴你它會不會變」。**

---

## 二、SEC Extractor 花多少?

### 抓一份財報要花多少網路?(Fetch 成本,EDGAR)

以下由 `data/raw_filings/fetch_log.jsonl` 計算 —— 白話:每一次對外抓檔都會留一行日誌,這張表就是把那些日誌加總。

| 指標 | 值(2026-07-10 快照)|
|---|---|
| 總存取 | 1,014 |
| 實際 live 請求 | 51 |
| Cache 命中率 | **95.0%** |
| Live fetch 延遲 | mean 551 ms,max 1,430 ms |
| Raw cache | 51 blobs,155 MB |

**逢數字必問 why —— 95.0% 是怎麼來的?** 1,014 次存取裡只有 51 次真的出門上網,其餘全部在本機吃 cache。**對照錨就在同一張表裡**:1,014(要的)對 51(付錢的)—— 這個比值就是 cache 的價值,不需要外部基準來吹。

Content-addressed cache(白話:檔案用「內容的指紋」當檔名存,不是用網址),讀取驗 sha256(一種內容指紋演算法,內容改一個位元指紋就完全不同),corruption raise(指紋對不上就直接報錯,不會默默給你壞資料)。同一 filing 重跑=零網路、位元組級可重現。

> **不是「我抓得比較快」,是「我第二次根本不用抓」。**

### 解析一份財報要等多久?(Parse 延遲)

| 指標 | 值 |
|---|---|
| Parse(11 家 sweep2)| mean 1,146 ms,max 2,544 ms(JPM,12.9M chars)|
| 對文件大小 | 近線性(~0.2 ms/KB)|

單執行緒純 Python,瓶頸是 normalizer 的逐字元 offset mapping(白話:把清理後文字的每一個字,對回原始 HTML 裡的哪一個位置)。這是**刻意的權衡:offset 精確性 > 速度**——它讓每個 span(從原文切出來的一段引用)可 sha256 驗證。可擴充性:pipeline 是 per-filing 可平行(process pool)。

**這個 1,146 ms 慢嗎?自我攻擊一下:**是不是我寫得爛所以慢?—— 假說:若是實作爛,延遲對文件大小應該是亂的;若是「刻意換精確性」,延遲應該對大小近線性、而且最慢的那家就是最大的那家。**去測 → 判定**:~0.2 ms/KB 近線性,max 2,544 ms 正好落在 JPM(12.9M chars,全 sweep 最大)。**這不是效能 bug,是我拿速度換 offset 精確性的帳單。**

### 用 XBRL 交叉驗證,要加多少成本?

先翻人話:**XBRL** 是上市公司交給 SEC 的一份「機器可讀的財報數字檔」;`companyfacts` 是 SEC 官方提供的那份數字 API。我拿它來對我自己抽出來的 Item 8(財務報表)做交叉驗證 —— 等於**找一個跟我完全無關的裁判來對答案**。

Item 8 對 companyfacts 交叉驗證:每家多 1 次 `companyfacts` fetch(cache 後 0),純字串比對 <1 ms。11 家認證總 live fetch ≤ 11 次。**成本可忽略,價值是獨立 oracle**(oracle = 不靠我的程式、能獨立給出正確答案的來源;見 `data/sec_eval/certification/item8_certification.json`)。

> **不是「我自己檢查自己說沒問題」,是「我花 11 次 fetch 請一個外人來打我臉,他沒打成」。**

### LLM 到底花了我多少?(實測,2026-07-10)

**主路徑仍是 0 個 LLM call — 確定性 pipeline 覆蓋 253/253 items,ambiguous 觸發率 0%。**

白話:**LLM**(大型語言模型,會胡說八道但很聰明的那種 AI)在正常流程裡**一次都沒被叫到**。253 個 item 全部由寫死規則的程式(deterministic pipeline)處理完,沒有一個案子模稜兩可到需要問 AI。

adjudicator tier(白話:當兩個候選答案打平時,才叫 LLM 來當裁判的那一層)已 wired(`pipeline.adjudicate_ambiguous()`,opt-in:`SEC_LLM_ADJUDICATE=1` 或顯式呼叫),並以真實 LLM 實測過單筆 $/裁決。

**自我攻擊:0% 觸發率會不會只是「這條路根本沒接上、所以永遠不會觸發」?** 假說:若真的沒接上,我應該量不到任何真實 token 數字。**去測**:真實 sweep 無 ambiguous 樣本,量測用合成 ambiguous fixture(兩個非 TOC 的 Item 1 heading 對決 —— TOC = table of contents,目錄;白話:故意造一個「兩個都長得像正文 Item 1 標題」的難題,同 `tests/test_adjudicator_wiring.py`),經完整 wired 路徑:`extract_from_html` → `adjudicate_ambiguous` → `OpenAIClient` → codex exec(ChatGPT OAuth,帳號預設模型)→ `codex --json` 回報的**真實 token usage**。**判定:路徑是通的,0% 是「不需要」不是「壞掉」。**

| 指標(3 次重複,實測)| 值 |
|---|---|
| input tokens / 裁決 | 17,910(固定;其中 adjudicator prompt 本體僅 ~2.6K chars ≈ ~650 tokens,其餘 ~17K 是 codex CLI harness 的固定 system prompt 開銷)|
| output tokens / 裁決 | mean 686(230–1,103,含 reasoning tokens)|
| **$/裁決(codex 通道牌價換算)** | **mean $0.0058**($0.0049–$0.0067;tokens 實測 × `OPENAI_PRICE_IN/OUT` 預設 $0.25/$2.0 per 1M)|
| $/裁決(直連 API 等效,無 harness 開銷)| ~$0.0015(~650 in + 686 out tokens 換算)|
| 延遲 / 裁決 | mean 12,887 ms(7.1–16.6 s;codex exec 啟動 + reasoning 主導)|
| 邊際現金成本(ChatGPT OAuth 訂閱)| $0 |
| schema gate | 3/3 通過(decision=candidate_b 正確、evidence_quote 皆 verbatim)|

**每個數字哪來的,一個一個交代:**

- **17,910 input tokens**:實測(codex `--json` 回報),不是估的。**why 這麼大?** 我的 prompt 本體只有 ~2.6K chars ≈ ~650 tokens,其餘 ~17K 是 codex CLI harness 灌進去的固定 system prompt —— **這筆錢不是我的 prompt 花的,是通道花的**,我照實把它算進帳。
- **mean 686 output tokens(230–1,103)**:實測 3 次,含 reasoning tokens(模型「想」的過程也計費)。
- **$0.0058**:不是牌價抄來的,是 **tokens 實測 × `OPENAI_PRICE_IN/OUT` 預設 $0.25/$2.0 per 1M** 換算 —— 工程取捨:用可查的牌價把 token 折成錢,價格參數在 env var 裡可覆寫。
- **$0**:邊際現金成本,因為走 ChatGPT OAuth 訂閱 —— 白話:我已經付了月費,多跑一次不多收我錢。**但我不用這個 $0 來吹**,上面照樣把牌價換算的 $0.0058 寫在標題級。
- **schema gate 3/3**:白話 —— 「LLM 回的 JSON 格式對不對、引用的句子是不是真的一字不差出現在原文」,3 次全過。

**誠實註記(artifact 缺口):** 本量測(3-rep)的逐筆 per-call log 未保留為 tracked artifact,上表數字無法釘回原始 JSON;重生方式:`codex login` 後啟動 `.venv\Scripts\python tools\codex_gateway.py --port 8791`,另一 shell 設 `SEC_LLM_ADJUDICATE=1`、`OPENAI_BASE_URL=http://127.0.0.1:8791/v1`、`OPENAI_API_KEY=x`(任意非空值即可,codex backend 不驗 key),對 `tests/test_adjudicator_wiring.py` 的 `AMBIG_HTML` fixture 跑 `sec_core.pipeline.extract_from_html`(重複 3 次),每筆 tokens / cost_usd / latency_ms / schema_valid 落在 `ExtractionResult.llm_call_records`,dump 該欄即為 per-call log。

翻成一般人能懂的版本:**這張表的數字我跑得出來,但我沒把那次跑的原始逐筆記錄存進 repo。** 所以你現在無法把 $0.0058 釘回一個 committed 的 JSON —— 你只能照上面的指令自己重跑一次。這是缺口,我不藏在附錄,直接放在表格正下方。

**對照錨 —— 我以前是怎麼估的?** 舊估計「<$0.005/裁決」對照:codex 通道實測 $0.0058(harness 開銷墊高),直連 API 等效 ~$0.0015(低於估計)。**per-filing 成本欄已入帳**:`ExtractionResult` 帶 `llm_calls / llm_input_tokens / llm_output_tokens / llm_cost_usd / llm_call_records`(deterministic 路徑恆為 0,by construction);`tools/sweep_metrics.py` 聚合並輸出 per-filing `llm calls / llm usd` 欄(舊 records 無此欄=純確定性 run,計 0 是精確值非估計)。

白話:我以前猜「一次裁決不到 $0.005」。實測打臉了一半 —— **走 codex 通道是 $0.0058,比我猜的貴**(因為 harness 硬塞 ~17K token);**直連 API 是 ~$0.0015,比我猜的便宜**。兩個都寫出來,不挑好看的講。

> **不是「我的系統 0 成本」,是「主路徑不需要 LLM,所以正常跑是 0;真的叫下去,一次 $0.0058,我量過。」**

### 這套東西擴得起來嗎?

- 每 filing 均攤:~3 live requests × 0.5s rate limit + ~1.1s parse ≈ 3–5 秒(冷 cache);熱 cache <1.2s。
- S&P 500 單機:冷 <45 分,熱 <10 分。
- **Rate limit 是硬上限**(SEC ~10 req/s),多機平行抓取無意義;平行化只用在 parse 層。

白話:**rate limit** = SEC 規定你每秒最多敲他家門幾次。這是**風控/工程硬限**,不是我調得動的參數 —— 所以「多買幾台機器一起抓」這個直覺**是錯的**:天花板在對方那邊,不在我這邊。買機器只能加速「解析」,不能加速「抓取」。

> **不是「加機器就更快」,是「加機器只對解析有用,抓取那段你買再多台也一樣塞在 SEC 門口」。**

---

## 三、Browser Agent 花多少?

來源:`runs/browser_eval/results.json`(5 tasks,mock sites,offline)。重生:`tools\browser_eval.py`。每次 run 併寫 `runs/browser_eval/manifest.json`(P1-2 repro manifest:git commit/dirty、model id、task-set sha256、套件版本;`--strict-repro` 對 dirty tree 直接拒跑,數字永遠可釘回產生它的 code)。

白話:**每跑一次就順手記下「這個數字是哪一版 code 跑出來的」**;如果你的工作目錄有未 commit 的改動(dirty tree),`--strict-repro` 會直接不讓你跑 —— 寧可不給數字,也不給一個釘不回去的數字。

**穩定不變量(不隨 run 漂移,以下為硬數字):**

| 指標 | 值 |
|---|---|
| task success rate | 1.0 |
| **verifier false-positive rate** | **0.0**(空結果 task 正確判 fail,不偽裝成功)|
| trace completeness | 1.0 |
| verdict accuracy | 1.0 |

翻成一般人能懂的版本:**verifier** 是我請來給 agent 打分的「閱卷老師」。**false-positive rate 0.0** 的意思是 —— 我故意餵它「什麼都沒做出來」的任務,它一次都沒有睜眼說瞎話判成功。這是全篇最重要的一個 0。

**會隨 selector memory 狀態漂移的量測(不在此硬寫,以 artifact 為準):** 平均延遲(2026-07-10 passk-restore 重跑後快照 ~946 ms/task)、repair success rate——因為 memory 在 tasks 間累積(第二個同類漂移 task 可能 0 repair),這些值 run-to-run 會變。**正確做法是讀 `runs/browser_eval/results.json`,不是把快照凍進文件**——這也是我們對「可重跑」的一致態度:會變的量測不硬寫。

### Browser 的錢花在哪?(成本結構)

- **離線 eval 的 LLM 成本 $0(實測,by construction):** Script Mode(memory 命中)與 a11y-tree repair(a11y-tree = 無障礙樹,瀏覽器提供給輔助工具的頁面結構;白話:不看畫面、直接讀頁面骨架來找元素)都是確定性,不呼叫 LLM;offline eval 的 Agent Mode subset 用 MockPlanner,也不呼叫 LLM——artifact 的 `llm_cost_usd_total: 0.0` 是精確值。舊版此處寫「escalation 到 LLM 尚未 wired」已過時:LLM 路徑**已接上**(`LLMPlanner` via codex gateway + 卡住時視覺升級),且 P0-6 起每個 run/row 帶 `llm_calls / llm_tokens / llm_cost_usd` 入帳(live run 記在 `runs/agent_live/run.json`)。**offline set 的 $0 是「不需要」,不是「量不到」。**
- **Live 外部量測成本(Online-Mind2Web 20-task subset,實測 2026-07-10):** 平均 **$0.0058/task**、18 可評分題共 ~$0.10;平均 wall ~77s/task(baseline 跑,artifact `runs/browser_eval/m2w_rerun/`(gitignored)+ tracked 快照 `data/browser_eval/external_runs/m2w_rerun/`)。abstain-fix 定向重跑 6 題:per-task llm_cost $0.0002–0.0092、second judge 每題 $0.0002–0.0004、wall 44–257s(artifact `runs/browser_eval/m2w_abstain_fix2_20260710/results.json` + tracked `data/browser_eval/external_runs/m2w_abstain_fix2_20260710/results.json`)。逐題 p50/p95 與 cost-per-success 見下方「Latency 分佈與 cost-per-success」節。
- **Runtime 成本**:Playwright headless Chromium(無視窗的瀏覽器),含 launch 攤提;真實網站會受網路延遲主導(live 外部量測 wall ~44–257s/task,遠高於 mock 的 <1s,主因網路 + LLM planner latency)。
- **Repair 延遲**:UI 漂移時多 1–2 次 observe + a11y 搜尋,單步 <100 ms;selector memory 命中後第二次同類 task **0 repair**(見 eval:v2-gizmo),攤平漂移成本——這是 selector memory 的核心價值。

白話一下 **selector memory**:網站改版後,原本記住的「按鈕在哪」會失效(UI 漂移)。第一次遇到要花 1–2 次額外觀察去修;**修好就記起來,第二次同類任務 0 次修復**。這就是「接刀接一次,之後就知道刀從哪來」。

> **不是「我的 agent 不花錢」,是「離線那套 by construction 就沒有 LLM 可花;真的上網,一題 $0.0058,帳在 artifact 裡。」**

### 一題到底等多久、一次成功要花多少?(2026-07-11 實算,逐題資料)

先翻術語:**p50** = 中位數(一半的題比它快);**p95** = 前 95% 的分界(只有最慢的 5% 比它更慢,用來看尾巴多長)。**cost-per-success** = 花掉的總錢 ÷ 真正做對的題數 —— **這比「平均一題多少錢」誠實**,因為做錯的題也是花了錢的。

各 run 的 tracked 快照 `results.json` 帶逐題 `wall_s` / `latency_ms` / `llm_cost_usd`,可實算分佈(排除 `env_error` 題;percentile 用排序後線性內插):

| Run(artifact,均在 `data/browser_eval/external_runs/`)| n 可評分 | pass | wall p50 | wall p95 | LLM 成本合計 | **cost / successful task** |
|---|---|---|---|---|---|---|
| `m2w_rerun/results.json`(baseline)| 18 | 6 | 45.6 s | 210.5 s | $0.0946 | **$0.0158** |
| `m2w_rerun_20260710/results.json`(bucket-fix rerun)| 18 | 8 | 26.6 s | 226.1 s | $0.0526 | **$0.0066** |
| `m2w_abstain_fix2_20260710/results.json`(6 題定向重跑)| 6 | 3 | 133.5 s | 236.6 s | $0.0253 | **$0.0084** |

**對照錨就在第一列**:baseline `$0.0158/成功`,bucket-fix 後 `$0.0066/成功` —— 同一批 18 題、pass 從 6 升到 8、總成本從 $0.0946 降到 $0.0526,兩邊一起動,所以每次成功便宜了。孤立看「$0.0066」沒有意義,對著 baseline 看才有。

SEC parse latency(`data/sec_eval/records/sweep3/*.json` 逐 filing `latency_ms`,n=11):**p50 1,073 ms / p95 2,526 ms / max 2,805 ms**(與上方 sweep2 快照 mean 1,146 ms 同量級;sweep3 為現行 records)。

計算方式:`.venv\Scripts\python` 讀上述 JSON → 過濾 `env_error` → 對 `wall_s` / `latency_ms` 排序取 p50/p95(線性內插);cost-per-success = Σ`llm_cost_usd`(可評分題)÷ pass 數。

**三道誠實註記,主動打自己:**

1. m2w 是 live 網站單跑,wall 受網路與站點狀態主導,**p95 是方向指標非 SLA**(SLA = 對外承諾的服務水準;白話:我不敢拿這個數字跟你保證什麼)。
2. abstain-fix 批次是定向重跑先前的 6 個 unknown(**選樣偏難**),其 p50 不可與全集 run 直接比 —— 所以它的 133.5 s 看起來慢,不是退步,是題目本來就挑硬的。
3. SEC records 無 per-filing `llm_cost_usd` 欄的即為純確定性 run(成本恆 0,by construction,見上方 LLM 成本節)。

### 同一題跑第二次,還要再付錢嗎?(Replay cache,P0-10)

Agent Mode 由 verifier 判 pass 的 run 會把成功動作序列(durable selector + P0-7 結構 hash)入庫 `replay_cache.json`(key = site × task_type × task);同一 task 下次先逐步 replay 再問 planner——**乾淨 replay = 0 LLM call**,第一個失效步驟即 invalidate 並把同一回合交還 planner。verifier 仍是唯一裁判(replay 走完不等於 task pass)。

白話:**做對過的事就錄影存起來,下次先照著錄影做一遍**。錄影只要有一步對不上,立刻作廢、把方向盤交還給 LLM。**但錄影跑完不代表這題就算過 —— 判過不過的永遠只有 verifier 那個閱卷老師。**

| 指標 | 值 | 性質 |
|---|---|---|
| banked trajectories(eval 通道,`runs/browser_eval/replay_cache.json`)| 2 條;gizmo `success_count=2` = 兩次 verifier-passed run(第二次走 cache replay),widget = 1 | 實測(artifact,2026-07-10)|
| 乾淨 replay 的 planner 成本 | 0 LLM call(replay 先於 planner)| 實測(`tests/test_p0_10_replay_cache_shadow.py` deterministic 釘死)|
| live 通道(`runs/agent_live/replay_cache.json`)| 2 條,各 `success_count=1` | 實測(artifact)|

**元層思考:驗證我的 cache 驗證器。** 光說「cache 沒出錯」不夠 —— 我還得證明「如果 cache 出錯,我抓得到」。Script Mode 另有 **shadow-mode cache 驗證**:remembered-selector 命中每 N 次抽驗一次(`CACHE_SHADOW_EVERY` 覆寫),從頭重推導並以**結構 hash**比對元素(非 selector 字面);`dom_fingerprint` 漂移會強制跳過抽樣直接驗。計數器落在 `TaskRun.cache_stats`(`as_dict()['cache']` 含 fp_rate)。

**誠實標註,不軟化:** mock eval set 無真實漂移場景,fp_rate 尚無非平凡實測值(**divergence=0 是預期而非成果**);divergence/agreement 行為由 10 個 deterministic tests 釘死,真實網站的 cache fp_rate 待累積,**目前不宣稱數字**。

翻成一般人能懂的版本:抽驗機制我寫好了、行為有 10 個測試釘死,但我的 mock 網站根本不會漂移 —— 所以「抽驗零分歧」這件事是**廢話,不是成績**。真實網站的誤判率我還沒有,我就不給數字。

> **不是「我的 cache 零誤判」,是「我的 cache 在一個不會出錯的環境裡零誤判 —— 這句話沒有資訊量,我照實說。」**

### 開多個瀏覽器一起跑,成本模型長怎樣?(平行 worker pool,P0-11)

`--workers N`:subprocess pool,每 worker 一條持久 browser session(冷啟攤提)+ 每 task 新 context;parent 端 wall-clock watchdog 終結 hung worker(白話:主控端拿碼表盯著,卡死的工人直接斃掉)。

實測(2026-07-10 重跑 `tools\browser_eval.py --workers 2`,5 tasks,當時 artifact `runs/browser_eval/results.json` `scalability` block;**註**:該檔其後被 passk-restore 的單 pass serial 重跑刷新,現行檔無 `scalability` block——重跑 `--workers 2` 即重生,下表為當時快照):

| 指標 | 值 |
|---|---|
| wall clock | 4.13 s(serial 估計 5.49 s → speedup **1.33x**;2 workers × 5 tasks 天花板本來就低,價值在成本模型非加速本身)|
| throughput | 72.6 tasks/min |
| session 冷啟 | mean 424 ms/session;攤提後 169.6 ms/task |
| per-session utilization | worker0 0.72 / worker1 0.51 |
| watchdog kills | 0 |

**溯源分類,一個都不含糊:** wall/throughput/冷啟/utilization 是**實測**;speedup 的分母 `serial_estimate`(= busy 時間總和)是**估計對照**,如實標註 —— 也就是說 **1.33x 這個數字的分母不是我真的跑了一次 serial 量出來的**,我沒把它偽裝成實測。

P1-15 起 pool watchdog 隨 set 內最大 step budget 線性放大(8 步→90 s、15→168.75 s、25→281.25 s,`watchdog_timeout_s` 實算),hard task 不會被 easy task 的檔期殺掉。

---

## 四、加機器有用嗎?(Scalability 實測,2026-07-11,workers = 1/2/4/8 掃描)

固定任務集:5 題 Script-Mode set 複製展開成 **20 個 task 實例**(unique task_id),file:// mock sites、無 LLM、$0。每個 worker 數跑 2 次;所有 run 20/20 done、20/20 verdict correct、0 harness error、0 watchdog kill。機器:i9-9900K(8C/16T)、64 GB RAM(量測時 available ~36 GB)、Windows 10。artifact:`runs/browser_eval/scalability/results.json`(逐 run 明細在 `runs/browser_eval/scalability/w{N}_rep{r}/bench.json`)。重現:`.venv\Scripts\python tools\scalability_bench.py --workers <N> --rep <r>`,全部跑完後 `--merge`。量測隔離:out_root/mem_dir 均在 scalability/ 下,不觸碰 `runs/browser_eval/results.json`、共享 evidence log 與 `data/browser_eval/passk/passk_results.json`。

白話「量測隔離」:**跑效能測試不可以順手弄髒別人的成績單** —— 所以這批 run 的輸出全關在自己的資料夾裡。

| workers | wall clock(2 reps)| throughput(tasks/min,2 reps)| mean | spread | **speedup vs w1** | avg task latency(ms)| session 冷啟 mean | per-session utilization |
|---|---|---|---|---|---|---|---|---|
| 1 | 22.16 / 22.37 s | 54.2 / 53.6 | **53.9** | 0.9% | 1.00x | 973 / 984 | 446 ms | 0.90 |
| 2 | 12.18 / 12.30 s | 98.5 / 97.6 | **98.0** | 1.0% | **1.82x** | 992 / 1,002 | 498 ms | 0.83 / 0.83 |
| 4 | 8.03 / 8.12 s | 149.5 / 147.8 | **148.6** | 1.1% | **2.76x** | 1,024 / 1,040 | 577 ms | 0.62–0.69 |
| 8 | 7.28 / 7.74 s | 164.9 / 155.1 | **160.0** | 6.2% | **2.97x** | 1,154 / 1,216 | 956 ms | 0.33–0.52 |

(wall clock 含 process spawn + import + browser 冷啟;utilization/冷啟取 rep1 的 cost model,`w{N}_rep1/bench.json`。)

**這裡的對照錨是 w1**,而且是**真的跑出來的 w1**(22.16 / 22.37 s),不是估計 —— 這正是上一節 1.33x 缺的東西,這一節補上了。

**瓶頸判讀(只用量到的數據):**

1. **CPU contention(主因)**:workers 加倍時 per-task busy latency 同步膨脹——w1 973 ms → w8 ~1,185 ms(**+22%**),busy 時間總和 19.8 s → 24.3 s;每個 worker = 1 個 Python 子行程 + 1 個 Chromium(本身多 process),w8 時同時競爭 8 顆實體核,單 task 變慢直接吃掉平行收益。
2. **Playwright instance 冷啟 contention**:session 冷啟 mean 446 ms(w1)→ 956 ms(w8),**+114%**——8 個 Chromium 同時 launch 互相搶 I/O 與 CPU。
3. **固定開銷攤提變差 + 尾端不平衡**:20 tasks / 8 workers 每 worker 只攤 2–3 題,spawn + import + 冷啟的固定成本占比升高;utilization 從 0.90(w1)掉到 0.33–0.52(w8),部分 worker 早早空轉等尾端。

**外推極限(僅由實測外推):** w4→w8 邊際增益僅 +7.6%(148.6 → 160.0 tasks/min),曲線已平;在這台 8C/16T 機器上,吞吐上限約 **~160 tasks/min**,workers > 8 預期無增益(每 worker 已對應 1 實體核,再加只會加深 contention;**未實測 w>8,不給數字**)。效率甜蜜點是 **w4**(每 worker 效率 69%,latency 膨脹僅 ~5%);w8 每 worker 效率掉到 37%。RAM 非瓶頸(64 GB,量測全程無壓力)。此外推僅適用 mock(<1s/task、CPU-bound)場景;live 網站 task 是網路/LLM-latency-bound(wall 44–257 s/task,見上節),同機可支撐的併發 worker 數會遠高於 8,但**需另行實測,不在此宣稱**。

**一句話讀懂這張表:w1→w2 幾乎白賺(1.82x),w2→w4 開始打折(2.76x),w4→w8 只多 7.6% —— 我用 w8 的 37% 每-worker 效率換了 7.6% 吞吐,這筆交易不划算,所以甜蜜點是 w4。**

> **不是「開 8 個最快所以用 8 個」,是「開 8 個確實最快,但每個工人只剩三分之一在做事 —— 我選 w4。」**

---

## 五、我為了省錢做了哪些取捨?(每個決定都是一筆交易)

1. Serial prefetch → parallel analysis(避免多 process fetcher 超過 SEC rate limit)。**用抓取的平行度,換不被 SEC 擋。**
2. LLM 不在主路徑(hallucination 與成本同時歸零,只留 ambiguous fallback)。**用「AI 的聰明」,換「不會胡說八道 + $0」。**
3. Selector memory:漂移修復一次記住,第二次同類 task 免 repair。**用一次接刀的痛,換之後永遠不痛。**
4. Raw cache 永久保存:eval 重跑免費。**用 155 MB 硬碟,換零網路的可重現性。**

---

## 六、eval 升級波的成本註記(2026-07-10)

本波 11 項 eval(T1-1~T1-6、T2-1~T2-5)**全部離線 deterministic、零 LLM 成本**:browser 側(verifier 校準、擾動矩陣、impossible set、trajectory、pass@k、false-success detector)走 headless chromium + 純函式,無 LLM call;SEC 側(三角驗證、offset F1、CYD oracle、分層抽樣、landmines)全走 cache-first EDGAR,重跑零網路(triangulate 對「同一份 cached raw HTML」離線解析;CYD tag 就在同檔內,無新抓取)。數字與解讀見 `eval_report.md`「Eval 升級」段;artifacts 全部 committed。

白話:**這 11 項驗證,一毛錢的 LLM 費用都沒花,而且你重跑不用連網。** 為什麼做得到?因為要用的原始檔早就 cache 在本機了(cache-first),要驗的東西都是純函式或離線解析。

**這一波的重跑指令清單:**

| 工具 | 指令 |
|---|---|
| Verifier 校準 + Rogan-Gladen | `.venv/Scripts/python tools/calibrate_verifier.py` |
| Impossible set / silent-failure | `.venv/Scripts/python tools/impossible_tasks.py` |
| Trajectory metrics | `.venv/Scripts/python tools/trajectory_metrics.py` |
| pass@k / flakiness | `.venv/Scripts/python tools/browser_eval.py --repeat 3 --agentic` |
| Degradation curve | `.venv/Scripts/python tools/degradation_curve.py` |
| False-success detector | `.venv/Scripts/python -m tools.false_success_detector`(script 形式亦可,`470b8b9`)|
| 三引擎 triangulation | `SEC_EDGAR_USER_AGENT=<contact> .venv/Scripts/python tools/triangulate.py` |
| char-offset F1 | `.venv/Scripts/python tools/score_offsets.py data/sec_eval/records/sweep3` |
| CYD Item 1C oracle | `SEC_EDGAR_USER_AGENT=<contact> .venv/Scripts/python tools/certify_cyd.py` |
| 分層抽樣 | `SEC_EDGAR_USER_AGENT=<contact> .venv/Scripts/python tools/stratified_sample.py` |
| Landmines | `.venv/Scripts/python -m pytest tests/test_landmines.py -q` |

### 重跑會不會弄髒東西?(對抗式驗證員發現,如實揭露)

**已知重跑副作用:**

- `degradation_curve.json` 內嵌 per-probe latency_ms → **重跑非 byte-stable**(metric 欄位完全確定)。
- `tools/browser_eval.py` 會 append `data/browser_eval/evidence/*.jsonl`(既有設計)。
- `tools/score_offsets.py` 預設**覆寫** committed `offset_f1.json`(對非正式目錄評分請加 `--out`)。
- `stratification.json` 內嵌 `generated_at` → **重跑非 byte-stable**(其餘欄位確定)。

重跑後如非刻意更新 artifact,`git restore` 之。

白話「byte-stable」:同一份 code 重跑,產出的檔案是不是**一個位元都不差**。上面這幾個做不到 —— 因為裡面塞了時間戳和延遲,那些本來就每次不同。**我沒有把「metric 值確定」偷換成「檔案完全相同」**,兩件事分開講。

其餘 artifact(calibration/impossible/trajectory/passk/false_success/triangulation/cyd)重跑皆 **byte-identical**(2026-07-10 最終驗收全數實跑複核)。

> **不是「我的 artifact 全都可完美重現」,是「七個可以位元級重現,四個因為內嵌時間戳做不到 —— 我把那四個一個一個點名。」**
