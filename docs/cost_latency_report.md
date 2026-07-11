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

來源:`runs/browser_eval/results.json`(5 tasks,mock sites,offline)。重生:`tools\browser_eval.py`。

**穩定不變量(不隨 run 漂移,以下為硬數字):**

| 指標 | 值 |
|---|---|
| task success rate | 1.0 |
| **verifier false-positive rate** | **0.0**(空結果 task 正確判 fail,不偽裝成功)|
| trace completeness | 1.0 |
| verdict accuracy | 1.0 |

**會隨 selector memory 狀態漂移的量測(不在此硬寫,以 artifact 為準):** 平均延遲(~600 ms/task)、repair success rate——因為 memory 在 tasks 間累積(第二個同類漂移 task 可能 0 repair),這些值 run-to-run 會變。**正確做法是讀 `runs/browser_eval/results.json`,不是把快照凍進文件**——這也是我們對「可重跑」的一致態度:會變的量測不硬寫。

### Browser 成本結構

- **LLM 成本 $0——與 SEC 同樣的誠實說明:** Script Mode(memory 命中)與 a11y-tree repair 都是確定性,不呼叫 LLM;且 escalation 到 LLM 的路徑**尚未 wired**(mock 場景未觸發)。所以 $0 同樣是「不需要」+「未接上」兩者兼有,不宣稱為已量測的成本成果。
- **Runtime 成本**:Playwright headless Chromium,含 launch 攤提;真實網站會受網路延遲主導。
- **Repair 延遲**:UI 漂移時多 1–2 次 observe + a11y 搜尋,單步 <100 ms;selector memory 命中後第二次同類 task **0 repair**(見 eval:v2-gizmo),攤平漂移成本——這是 selector memory 的核心價值。

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
