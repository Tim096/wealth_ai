# Eval 升級 TODO(基於兩個研究 agent 的網路調查)

## Trigger

使用者:現況約 75 分,大部分功能正常,但 edge case 驗證方法不完整。要求以第一性原理設計測試,並派 agent 上網查證是否有更強做法。派出兩個平行研究 agent(browser agent eval / SEC 10-K 抽取驗證,各含 WebSearch 調查 2023-2026 文獻與工具)後整合。

## Scoring Criteria

- 評估紀律:eval design has depth(A 級標準)
- 正確性驗證:無 public ground truth 下的自我驗證
- silent-failure prevention(Task 1 明列評分項)
- 格式變異穩健性(Task 2 明列評分項)

## Prompt

> 我現在自己使用測試中心測了我能想到的大概情況,但 edge case 要如何測試設計?有沒有簡單粗暴、第一性原理的方法寫測試案例?第一題我想到的是 agent 能不能執行人類每一種動作;第二題是用原文比對,但我不覺得方法完美。
> (後續)派 agent 上網看看有沒有更強的地方。
> (後續)寫成 TODO 寫進去 prompts。ultracode go all, u r PM。

## AI Output Summary

核心診斷:兩題原方向都在測「執行器」沒測「裁判」——沒有 ground truth 的系統,可信度上限等於驗證機制的可信度。第一性原理:**不造更多測試案例,造「任何輸入都必須成立的檢查」(invariant)+ 校準裁判本身**。

調查確認既有 5 項設計(mutation site、fault injection、impossible-task、verifier 校準、pass@k)全部有 2024-2026 論文背書;Task 2 的 partition/coverage invariant 領先(連 ExtractBench 都未 formalize round-trip 質量守恆檢查)。

---

## 研究依據總表(兩個研究 agent 的完整產出)

### Task 1: Browser agent eval 文獻

| 來源 | 關鍵發現 | 對我們的意義 |
|---|---|---|
| **AgentRewardBench** (arxiv 2504.08942) | 第一個「評測自動評測器」的 benchmark(1302 trajectory × 5 benchmark × 4 LLM,專家標註)。rule-based evaluator 系統性 under-report(false negative);LLM judge 彈性但無單一 LLM 全面勝出。標註三維度:success / side effects / repetitiveness | 驗證 T1-1 verifier 校準方向;三維度直接催生 T1-4 |
| **Catching One in Five** (arxiv 2606.10315) | 生產級 agent 上 5 judges × 5 prompt 策略,**無任何組合 AUROC > 0.65**(AppWorld 僅 0.54)。judge 靠「confident closing 語氣」「動作序列長度」等表面 proxy,與真值 anti-correlated。附 Rogan-Gladen estimator 用 judge FP/FN 反推真實 prevalence | LLM-judge 不可獨任裁判的量化證據;校正後成功率(T1-1 步驟 3)的方法來源 |
| **From Confident Closing to Silent Failure** (arxiv 2606.09863) | false success(口頭宣稱完成 vs 環境 state 不符)佔失敗案例:tau2-bench 45-48%、AppWorld 自評 agent 75.8%。**reasoning 模型更糟**(79%,合理化完成而非驗證)。輕量 detector(TF-IDF+XGBoost)AUROC 0.83/0.95 遠勝 judge、快 3300 倍、同 flag rate 多抓 4-8 倍;dual-control 環境驗證壓 false success 94% | T1-3 impossible-task 的量化依據;T1-6 輕量 detector 的方法與數字來源 |
| **WebJudge / Online-Mind2Web** (arxiv 2504.01382) | 目前最強 LLM-judge:human agreement 83.6%(GPT-4o)~87%(WebJudge-7B)。三步法:key point 抽取 → key screenshot 篩選 → binary 判定,**刻意不吃 agent 自述**(舊法 WebVoyager 73.9% agreement,主因 agent final response hallucination → false positive) | 我們 verifier「不吃 agent 自述」的設計獲證實;三步法可作 verifier 演進參考 |
| **One Token to Fool LLM-as-a-Judge** (arxiv 2507.08794) | 單一 token 即可騙過 judge | 直接對應本 repo commit「stop mining a URL token as success needle」——已踩過、已修,論文證實方向 |
| **StressWeb** (arxiv 2604.16385) | 診斷式 robustness benchmark:perception / action selection / execution 三軸擾動 × 強度分檔,clean reference 環境 + deterministic multi-checkpoint evaluator,量 mid-task recovery 與 **degradation curve**、robustness ranking | T1-2 三軸擾動設計的直接藍本(我們 mutation site 想法的學術成熟版) |
| **WebArena / WebArena Verified** (arxiv 2407.01502; openreview CSIo4D7xBG) | functional correctness 對最終環境 state 跑 execution-based 斷言。已知缺陷:環境「太乾淨」(無 popup/延遲/drift)→ 系統性高估 robustness。Verified 版重寫 evaluator 後 false-negative 降 11.3pp | 能程式驗 state 的就別交給 judge(dual-control);乾淨環境高估 robustness = 我們必須做擾動軸的理由 |
| **GUI-Robust** (arxiv 2506.14477) | 7 類真實世界 anomaly 的 robustness 資料集 | fault-injection taxonomy 參考 |
| **AgentProcessBench** (arxiv 2603.14465) / **Web-Shepherd PRM** (arxiv 2505.15277) / **TRACE** (arxiv 2510.02837) | step-level 過程品質診斷、per-step reward model、trajectory 效率指標(最短路徑偏離、多餘證據量) | trajectory-level 評測的現成指標庫(T1-4 之後的演進方向) |
| **Metamorphic testing for agents** (arxiv 2603.13173; 2605.23965) | 語意等價的任務描述應產生相同**最終 state**(非相同輸出文字)構成 metamorphic pair;八種語意保持變換。抗資料污染、解 oracle problem、零標註成本 | 第二波候選(B-1):mock site 上低成本擴增測例 |
| **ST-WebAgentBench** (arxiv 2410.06703) | Completion-under-Policy(CuP):完成且不違反 policy 才計分。實測 agent CuP 不到名目完成率 2/3 | 第二波候選(B-2):我們已有 capability guard(REFUSED),CuP 是現成的合規計分框架 |
| **TimeWarp** (arxiv 2603.04949) / **WebForge** (arxiv 2604.10988) | 重訪網站歷史版本評測 drift / 自架可重現 benchmark 打破 realism-reproducibility-scalability 三難 | 記錄為 prior art;我們的本地 mock site + 擾動矩陣走 WebForge 同路線 |

### Task 2: SEC 10-K 抽取驗證文獻與資源

| 來源 | 關鍵發現 | 對我們的意義 |
|---|---|---|
| **GPT4ItemSeg / BERT4ItemSeg** (arxiv 2502.08875) | item 切分當 line-level sequence labeling,3737 份標註 10-K(僅 item 1/1A/3/7)。macro-F1:BERT 0.9825、CRF 0.9818、GPT4 line-ID prompting 0.9567、**rule-based 僅 0.9048** | 純 regex 在難 item 留 ~10% 誤差 = 多引擎必要性的量化證據;line/char-level F1 比 coverage% 更能定位錯在哪(T2-2 依據) |
| **ExtractBench** (arxiv 2602.12247) | 7 份 SEC 10-K/Q 上 6 個 frontier model **全 0% valid output**(369-field schema、~24,400 token JSON 超出穩定輸出上限)。方法可抄:present/null/MISSING 三態分離 omission 與 hallucination;LLM semantic matching 回傳 matched/FN/FP 對應。反直覺:constrained decoding 反而降準確率(validity 37% vs 51%);失敗主因是 output volume 而非 input 長度 | T2-2 三態記分與 structured judge(回 FN/FP mapping 而非 pass/fail)的方法來源;也證實我們「offset 定址、LLM 不吐內文」的架構優勢——我們根本不受 output volume 限制 |
| **EDGAR-CORPUS / edgar-crawler** (huggingface eloukas/edgar-corpus; github nlpaueb/edgar-crawler) | 25 年全上市公司、已切 item_1..item_16 的 JSON。**警訊:無人工標註,切分是 regex/anchor heuristic 產的 silver label**,與我方 regex 引擎共享偏誤 → 歧異訊號會被低估 | 可當比對素材但不可當 gold;不能取代獨立引擎 |
| **edgartools** (github dgunning/edgartools, MIT, 活躍維護) | form-aware/part-aware parsing,`TenK.items` 回 canonical order。**issue tracker 是真實 landmine 清單**(如 #454:Part I/II Item 編號碰撞,`Item 1` 回傳 Legal Proceedings 而非正確 item) | T2-1 第三引擎首選(獨立 codebase);issues 掃一遍進 landmine(T2-5) |
| **sec-parser** (github alphanome-ai/sec-parser) | semantic/visual tree 轉換。已停止維護,官方明說不保證正確性、無量化 accuracy | 只參考 semantic element 分類思路,不當引擎 |
| **KPI-EDGAR** (arxiv 2210.09163) | 81 份人工標註 10-K(relation extraction 層級) | 少數真人 gold;可抽對應 item 做小型 gold 錨點(第二波 B-4) |
| **SEC iXBRL 官方** (sec.gov structured data; Toppan Merrill blog) | iXBRL 財報標的是「數值 → US-GAAP taxonomy」,**不標 item 文字邊界 → 不能當 item-span ground truth(此路不通)**。例外:(a) cover page DEI tags(2019+);(b) **cybersecurity Item 1C 的 CYD taxonomy block-tag,fiscal year ending ≥ 2024-12-15 強制 → 唯一有官方機器可讀 span 的 item** | T2-3 的全部依據;省掉在 XBRL 上找 item 邊界的死路 |
| **EDGAR Full-Text Search API** (efts.sec.gov; tldrfiling.com blog) | 免費、免 key、10 req/s、需 User-Agent。**`formTypes` 是 exact-match:查 `10-K` 不含 `10-K/A`** | T2-4 分層抽樣工具;formTypes 陷阱進 landmine(查自家 fetcher 有無同 bug) |
| Form 10-K 官方 (sec.gov/files/form10-k.pdf) | Item 6 於 2021-02-10 廢除;Part III 可 incorporate by reference 至 DEF 14A(逾 120 天須 10-K/A 補) | T2-5 landmine 的官方出處 |

---

## TODO

### Task 1: Browser Agent

- [x] **T1-1 Verifier 校準 + 校正後成功率**(最高 ROI)
  - 餵 verifier ≥20 已知成功 + ≥20 程式化損毀的 run(≥4 種損毀 class:換截圖、改結果頁、截斷 trajectory、注入自信但錯誤的自述)→ confusion matrix(FP/FN rate)
  - Rogan-Gladen estimator 反推「校正後真實成功率」寫進 analysis report
  - 依據:judge AUROC 僅 0.54-0.65、靠語氣 proxy(2606.10315);verifier FP rate = 整個 eval 可信度天花板
- [x] **T1-2 Mutation site:三軸擾動 + degradation curve**(最大項)
  - perception(改 id/class、換字、搬位、overlay、div+onclick、藏元件)/ action(a11y tree 缺漏、過期 snapshot)/ execution(XHR 延遲、隨機 500、mid-task 移除元素),每軸輕/中/重
  - 任務中段 checkpoint 量 mid-task recovery rate;產出擾動強度 × 成功率/恢復率的 degradation curve
  - 依據:StressWeb(2604.16385);WebArena「乾淨環境高估 robustness」缺陷(2407.01502)
- [x] **T1-3 Impossible-task set**(silent-failure 偵測)
  - ≥8 個不可能成功的任務;正確答案 = 誠實 FAIL + 原因;回報成功 = silent failure(最嚴重失敗)。REFUSED(guard 擋)與 FAIL(試後誠實敗)分開計
  - 依據:false success 佔失敗 45-75%,reasoning 模型更糟 79%(2606.09863)
- [x] **T1-4 Trajectory 兩維度**:side effects(任務前後 state diff)+ repetitiveness(動作循環偵測)。觀測層,不改 agent 行為(AgentRewardBench 三維度, 2504.08942)
- [x] **T1-5 pass@k 與 flakiness**:--repeat N,報 pass@1 vs pass@3 與結果不一致 case 比例;live LLM 跑小子集控成本
- [x] **T1-6(選配)輕量 false-success detector**:樣本 ≥60 才 train TF-IDF+XGBoost,否則 heuristic 版前哨 + roadmap 記錄(依據:detector AUROC 0.83/0.95 勝 judge、快 3300 倍,2606.09863)——**實作走 heuristic 路線**:盤點後 labeled full trajectory <10,遠低於 ~60 train 門檻;committed-corpus triage precision 1.0 / recall 0.5,TF-IDF+XGBoost 版寫進 artifact roadmap(前置條件:≥60 labeled trajectory + log 補存 agent 自述)

### Task 2: SEC 10-K

- [x] **T2-1 三引擎三角驗證**:接 edgartools 當第三獨立引擎,三取二;歧異 → low confidence + needs_review;11 家 sweep 實跑,歧異案例進 failure_gallery。EDGAR-CORPUS 是 silver label 不可當 gold
- [x] **T2-2 記分升級**:
  - char-offset F1(rule-based 難 item F1 僅 0.90 → 量化多引擎必要,2502.08875)
  - present / null / MISSING 三態:分離漏抽(omission)與幻覺(hallucination)(ExtractBench, 2602.12247)
  - LLM-judge 回 matched/FN/FP span mapping,不是只回 pass/fail
- [x] **T2-3 Item 1C 官方 ground truth**:fiscal year ≥ 2024-12-15 的 10-K,Item 1C 有強制 CYD taxonomy iXBRL block-tag = 唯一官方 item-span 標註;解析後與自家切分比對出 agreement。其餘 XBRL 不標 item 邊界,不走
- [x] **T2-4 分層抽樣按格式來源**:年代(pre-2001 text / 2001+ HTML / iXBRL 世代)× filing agent(Workiva/Donnelley/Toppan);efts.sec.gov API 抽樣;缺口層各跑 1-2 份;不支援就誠實 unsupported
- [x] **T2-5 Landmine 清單擴充**(逐條做成 eval case + test)
  - Item 6:2021-02-10 廢除,post-2021 三種寫法(`[Reserved]` / 整項省略 / 說明段),按年代分開
  - Item 9C(HFCAA 新 item)、Item 16 optional(省略非 bug)
  - "Items 7 and 7A" 合併(同既有 "Items 1 and 2")
  - Cross-reference 型 10-K、Glossy ARS wrap(10-K 包在年報 exhibit 內)
  - EDGAR API `formTypes` exact-match:查 `10-K` 不含 `10-K/A`(查自家 fetcher)
  - TOC 需**先排除**再匹配 item anchor,非僅事後比對
  - Part III incorporated by reference → efts 抓對應 DEF 14A 比對;proxy 逾 120 天未申報須 10-K/A
  - 掃 edgartools GitHub issues 當真實 landmine 來源(Part I/II Item 編號碰撞:#454)
  - >50MB filing chunk 處理,offset 跨 chunk 一致(edgartools 50MB 門檻經驗)

### 執行順序

T1-1 → T2-1 → T2-2 → T1-2 → T2-3 → T1-3,其餘穿插。(實際執行:ultracode workflow,兩 track 平行、track 內串行。)

---

## 第二波候選(本波未派工,查到且值得,記錄避免遺失)

- **B-1 Metamorphic task pairs**(arxiv 2603.13173):語意等價任務描述 → 相同最終 state 的不變性測試。零標註成本,適合 mock site 擴增測例。
- **B-2 Completion-under-Policy(CuP)**(arxiv 2410.06703):已有 capability guard,套 CuP 計分即可量化「完成且合規」;另有 Risk Ratio。
- **B-3 Step-level PRM / TRACE 效率指標**(2505.15277, 2510.02837):per-step 打分與最短路徑偏離,T1-4 之後的演進。
- **B-4 KPI-EDGAR gold 錨點**(2210.09163):81 份人工標註 10-K,抽對應 item 做小型 gold set。
- **B-5 EX-21 子公司 exhibit 一致性**:半結構化免費資源,驗 Item 1 子公司清單。
- **B-6 Cover page DEI tags**(2019+):機器可讀封面欄位,驗文件起點切分。

## 明確不採納(附理由)

- **XBRL 當 item 邊界 ground truth**:iXBRL 標數值→US-GAAP taxonomy,不標 item 文字邊界。死路,唯一例外是 Item 1C(見 T2-3)。
- **EDGAR-CORPUS 當 gold**:silver label(regex heuristic 產),與自家 regex 引擎共享偏誤。
- **sec-parser 當引擎**:已停止維護、官方不保證正確性、無量化 accuracy。
- **constrained decoding 強化輸出**:ExtractBench 實測反而降 validity(37% vs 51%);我們 offset 定址架構本來就不吐大 JSON,不受此限。

## Human / PM Decision

使用者確認整合方案後指示寫成 TODO;隨後以 ultracode 授權 AI 任 PM 派工全部執行(workflow:Map → 兩 track 平行實作 → 對抗式驗證 → 文件整合),easy task 用 opus 4.8 控 token 成本。

## Reason

- 第一性原理:不造更多測試案例,造「任何輸入都必須成立的檢查」(invariant)+ 校準裁判本身
- 每個升級項都有論文級量化依據與來源 URL(見研究依據總表),面試可引用
- 「明確不採納」與「第二波候選」記錄決策邊界,避免重查與 scope creep

## Resulting Change

11 項全數完成(兩 track 平行實作 + 各自對抗式驗證,verify ok;minor issues 記錄於下)。數字與解讀收錄於 `docs/eval_report.md`「Eval 升級(2026-07-10)」段;新 failure 收錄於 `docs/failure_gallery.md` FG-SEC-006~009 / FG-BROWSER-002~005。

### Commit 清單

| 項目 | Commit |
|---|---|
| T1-1 | `67eb56f` feat(eval): calibrate the judge itself — verifier confusion matrix + Rogan-Gladen corrected success rate |
| T1-3 | `a79f3c7` feat(eval): T1-3 impossible-task set + silent-failure rate artifact |
| T2-1 | `ea9f782` feat(sec): edgartools third-engine triangulation (T2-1) |
| T1-4 | `6db9696` feat(agent): T1-4 trajectory metrics — repetitiveness + side-effect diff |
| T1-5 | `9191558` feat(eval): pass@k + flakiness via browser_eval --repeat N (T1-5) |
| T2-2 | `8beb0fc` feat(sec): T2-2 scoring upgrade — char-offset F1 + present/null/MISSING tri-state |
| T2-3 | `f55c650` feat(sec): CYD iXBRL block-tags as the official Item 1C span oracle |
| T1-2 | `a51361e` feat(eval): mutation-site matrix (3 axes x 3 intensities) + degradation curve (T1-2) |
| T2-4 | `a55d773` feat(sec): T2-4 stratified sampling by format source (era x filing agent) |
| T1-6 | `1aa06cf` feat(agent): T1-6 lightweight heuristic false-success detector (opt-in triage) |
| T2-5 | `bcf185f` test(sec): T2-5 landmine catalogue as executable eval cases |

### Artifacts(全部 committed,可重跑指令見 docs/cost_latency_report.md)

- T1-1:`data/browser_eval/calibration/calibration_cases.json`、`calibration_results.json`
- T1-2:`data/browser_eval/artifacts/degradation_curve.json`、`data/mock_sites/mutations/`、`data/mock_sites/PERTURBATIONS.md`
- T1-3:`data/browser_eval/impossible/impossible_results.json`
- T1-4:`data/browser_eval/trajectory/trajectory_results.json`
- T1-5:`data/browser_eval/passk/passk_results.json`
- T1-6:`data/browser_eval/false_success/detector_results.json`
- T2-1:`data/sec_eval/triangulation/triangulation.json`
- T2-2:`data/sec_eval/scoring/offset_f1.json`、`data/golden_labels/offsets/*.json`、`data/sec_eval/records/sweep3/`
- T2-3:`data/sec_eval/cyd_groundtruth/cyd_agreement.json`
- T2-4:`data/sec_eval/stratification/stratification.json`
- T2-5:`data/sec_eval/landmines/landmines.json`

### 驗證員 minor issues(如實記錄,非 blocker)

- T1-6:`tools/false_success_detector.py` 只能 `-m tools.false_success_detector` 執行(缺 sys.path bootstrap)。→ 已修 `470b8b9`,兩種形式皆可。
- T1-2:`degradation_curve.json` 內嵌 per-probe latency_ms,重跑非 byte-stable(metric 欄位確定)。
- T1-5:`tools/browser_eval.py` 會 append committed `data/browser_eval/evidence/*.jsonl`(既有副作用)。
- T2-5:`landmines.json` header total_tests=16 為 off-by-one(實 15;body test 名單正確)。→ 已修 `470b8b9`。
- T2-2:`tools/score_offsets.py` 輸出路徑寫死,對非正式目錄評分會覆寫 committed `offset_f1.json`。→ `--out` 於 `8beb0fc` 已存在(驗證員看到 in-progress 版);`470b8b9` 另補 records_dir 相對路徑正規化。

測試總數 89 → 285(本波完成當下);dashboard render 測試 +6、敏感度注入鎖定測試 +1 後現為 292(`.venv/Scripts/python -m pytest tests -q` → 292 passed,零紅燈,2026-07-10 最終驗收複核)。
