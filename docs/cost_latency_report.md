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

### LLM 成本(誠實說明)

**目前主路徑 0 個 LLM call — 因為確定性 pipeline 已覆蓋 253/253 items,ambiguous adjudicator 的觸發率為 0%,尚未接上真實 LLM client。** 所以「$0 LLM」是「不需要」與「escalation path 尚未 wired」兩者兼有,不宜宣稱為已驗證的成本控制成果。

- 已 wired 且量測:確定性抽取($0)、XBRL 認證($0,公開 API)。
- 尚未 wired:`LLMCallRecord` / `AdjudicatorDecision` schema 存在但未實例化。啟用後每次裁決 ~2K input tokens;以 Haiku 級估 <$0.005/裁決——**這是估計值,無量測背書**,標明為 roadmap。

### 擴充性

- 每 filing 均攤:~3 live requests × 0.5s rate limit + ~1.1s parse ≈ 3–5 秒(冷 cache);熱 cache <1.2s。
- S&P 500 單機:冷 <45 分,熱 <10 分。
- **Rate limit 是硬上限**(SEC ~10 req/s),多機平行抓取無意義;平行化只用在 parse 層。

## Browser Agent

由 `runs/browser_eval/results.json`(4 tasks,mock sites,offline):

| 指標 | 值 |
|---|---|
| 平均延遲 / task | 660 ms |
| task success rate | 1.0 |
| **verifier false-positive rate** | **0.0**(空結果 task 正確判 fail,不偽裝成功)|
| trace completeness | 1.0 |
| repair success rate | 0.5(2 個含 repair 的 task,1 個成功 pass;另一個是刻意的空結果 task,repair 找到元素但任務正確判 fail)|

### Browser 成本結構

- **LLM 成本 $0**:Script Mode(記憶命中)與 a11y-tree repair 都是確定性,不呼叫 LLM。這是 SPEC 6.3 的核心權衡——已知任務不丟給 LLM,LLM 只在真正未知時升級(目前 mock 場景不需要)。
- **Runtime 成本**:Playwright headless Chromium,~660 ms/task 含 launch 攤提;真實網站會受網路延遲主導。
- **Repair 延遲**:UI 漂移時多 1–2 次 observe + a11y 搜尋,單步 <100 ms;selector memory 命中後第二次同類 task **0 repair**(見 eval:v2-gizmo 0 repairs),攤平漂移成本。

### 成本控制決策

1. Serial prefetch → parallel analysis(避免多 process fetcher 超過 SEC rate limit)。
2. LLM 不在主路徑(hallucination 與成本同時歸零,只留 ambiguous fallback)。
3. Selector memory:漂移修復一次記住,第二次同類 task 免 repair。
4. Raw cache 永久保存:eval 重跑免費。
