# Eval Report

> 數據可重跑:`tools/eval_one.py`(每份 filing 的 JSON record)、`tools/sweep_metrics.py`(彙整)。原始 records 在 `data/sec_eval/records/`。

## 方法論:為什麼這份 eval 特別

一般作業的 eval 會止步於「pass rate 高不高」。本專案的核心主張是:**pass rate 不是正確性,silent failure rate 才是。** 一個 C 級系統會把「抓到一句 cross-reference 指標」報成 pass;A+ 系統會標成 incorporated_by_reference 並說清楚內容在哪裡。

所以本 eval 用**對抗式稽核**驗證 pass 的真偽,而不是相信 pipeline 自報的 pass。

## SEC Extractor

### Eval set(分層,SPEC 7.14)

| Layer | Tickers | 目的 |
|---|---|---|
| 大型科技 | AAPL\*, MSFT, NVDA | baseline |
| 金融 | JPM\*, GS | 長 Item 7/8、wrapper 10-K |
| 零售/製造 | WMT, CAT | 一般格式 |
| 能源/礦業 | XOM\*, NEM | Item 4 特殊、appended financial section |
| 生技 | MRNA | 格式變異 |
| 消費 | KO | 一般格式 |

`*` = dev set(開發期見過);其餘 **8 家為 held-out**,pipeline 首次接觸。合成 fixtures(alpha/beta)另有 manual golden labels(`data/golden_labels/`),ground truth by construction。

### 對抗式稽核(這是本專案的驗證核心)

用一個 multi-agent workflow(56 個 agent)稽核 sweep1 的 253 個 item:每個 ticker 一個 audit agent 檢查可疑 span(短 pass、低信心 pass、Item 7/8 內容真偽、TOC 洩漏),每個回報的 anomaly 再交給獨立的**對抗式驗證 agent**(prompt 設定為「盡力反駁這個 anomaly」),多數決才算成立。**誠實標註**:這是一次性的內部審計過程——workflow 設計與結果摘要留存於 `prompts/eval_design/2026-07-10-adversarial-audit-workflow.md`,但 per-agent 逐一輸出未完整留存為 artifact;下方 31/12 等數字引自該紀錄,非可逐 agent 重放的 committed 資料。

結果:**31 個 anomaly 確認、12 個被反駁**(反駁的多是「這其實是誠實的 incorporated_by_reference / None. 行為,不是 bug」——驗證層自己擋掉了誤報)。

這直接命中評審在意的痛點:**很多作業 SEC 跑出來不完整,但 AI 自報完成度很高。** 我的 sweep1 metrics 自報 75.9% pass,對抗式稽核卻證明其中 15 個是 silent failure。稽核抓到了我自己的 pipeline 在說謊。

### 三大 silent-failure class(稽核發現 → 已修復)

| Class | 範例 | 根因 | 修復 |
|---|---|---|---|
| Reference-stub 誤標 pass | JPM/GS/XOM Item 7/8/1C、MSFT/NVDA/CAT Item 3 | 舊 regex 只認「refer to Item N」,漏掉「refer to Note 14」「reference is made to the Financial Section」「appear on pages 162-314」「incorporated in this Form 10-K by reference」 | `classify_reference_stub` 廣義偵測短指標 body → incorporated_by_reference + 標明指向 |
| Trailing furniture 洩漏 | 幾乎每家 Item 4/9C/16 | span end = 下一個 item start,中間夾著「PART II」「頁碼」「running header」 | `trim_trailing_furniture` 可解釋地裁掉 |
| Terminal runaway | **XOM Item 16 = 311,785 字**、**JPM Item 15 = 985,564 字** | wrapper 10-K 把整本財報接在最後一個 item heading 後;末項 span 吃到 end-of-doc | `detect_appended_section_cut` 在 section break 切斷 + 警告排除了多少字 |

### Metrics:修復前 → 修復後(11 家、253 items)

| Metric | sweep1(修復前) | sweep2(修復後) | 解讀 |
|---|---|---|---|
| pass | 75.9% (192) | **70.0% (177)** | 下降是進步:15 個 silent failure 被誠實重分類 |
| incorporated_by_reference | 19.0% (48) | **24.9% (63)** | stub 現在誠實標示指向何處 |
| reserved | 4.3% (11) | 4.3% (11) | Item 6 |
| missing | 0.8% (2) | 0.8% (2) | GS/JPM Item 16 誠實省略 |
| 稽核確認 silent failure | **31** | 目標 0(見殘留) | — |
| 最大 terminal span | 985,564 字 | **15,529 字** | runaway 已封鎖 |
| confidence 鑑別度 | 全部 ~0.958 | **substantive 0.962 / stub 0.666** | confidence 現在能分辨 stub |

### Confidence calibration

修復前 confidence 對 stub 與實質內容都給 ~0.958,毫無鑑別力(稽核明確點名)。新增 `content_substantiveness` 分量、並對 stub 不計 verifier 分數後:

- 實質 pass:mean **0.962**(min 0.799)
- reference stub:mean **0.666**(0.566–0.700)

兩群完全分離,confidence 首次能作為「這是不是真內容」的信號。

### Intel / Citi(主管點名的 corner case)

實測 4 份 wrapper/index filing,全部正確歸類為 `cross_reference_index`,Item 14 從「碎片/ambiguous」變成誠實的 `needs_review` 指標:

| Filing | 修復前 | 修復後 |
|---|---|---|
| INTC FY2019 | 全 item ambiguous 碎片(33–330 字)| `cross_reference_index`;Item 14 = incorporated_by_reference / needs_review / cross_reference_pointer |
| INTC FY2020 | 同上 | 同上 |
| INTC FY2025 | 同上 | 同上 |
| Citi FY2025 | 0 candidates → 全 missing | `cross_reference_index`(bare index 偵測);1A/8 指標,needs_review |

**沒有任何 item 被偽裝成 extracted/ok**——這正是主管點名別的作業犯的錯。

### Status 可信度:XBRL 獨立 oracle(回答「如何確保 status 可信」)

Item 8 對照 SEC companyfacts 的營收/淨利/總資產(非 LLM,免費、可重現)。11 家 sweep,P0-10 wrapper 重組(`cross_ref.reassemble_wrapper_bodies`,commit 64de3ef)前→後對照:

| 判定 | P0-10 前(歷史 baseline) | P0-10 後(現行,artifact 2026-07-11 重生) |
|---|---|---|
| certified(2–3/3 數字命中)| 8(AAPL/MSFT/GS/WMT/CAT/NEM/MRNA/KO)| **10**(AAPL/MSFT/JPM/GS/WMT/CAT/XOM/NEM/MRNA/KO)|
| contradicted(0/3)| 3(NVDA/JPM/XOM 的 Item 8 stub)| **1**(NVDA,item8_status=incorporated_by_reference,三項 headline 皆不在 span——誠實指標 stub,非內容)|

**JPM/XOM 從 contradicted 轉 certified 是 P0-10 機制改進的直接證據**:兩家 Item 8 原是 wrapper IBR stub(財報數字不在 span → oracle 正確判 contradicted);wrapper 重組把附綁年報正文接回 item(status=`partial` + needs_review)後,重組 span 各含 3/3 XBRL headline → certified。NVDA 維持 contradicted 是正確行為:其 Item 8 仍是未重組的指標 stub。

> 數字為 `tools/certify.py` 實際輸出(重跑:`.venv\Scripts\python tools\certify.py AAPL MSFT NVDA JPM GS WMT CAT XOM NEM MRNA KO`),artifact `data/sec_eval/certification/item8_certification.json`。certify 會把 verdict 寫回 `ItemSegment.xbrl_check`,並在 pipeline 標 pass 但 XBRL contradicted 時翻成 needs_review——oracle 真正 gate 輸出,不只 print。已知快照時差:`data/sec_eval/records/sweep3` 的 JPM/XOM 記錄檔是 P0-10 前存檔,其 `item8_status`(incorporated_by_reference)與 `xbrl_check` 欄位仍為舊值;權威判定以本 artifact 為準,dashboard 的 per-ticker `item8_xbrl` 與 `xbrl_summary` 為即時重算、已一致。

**誠實揭露(disagreements 欄位)**:現行 artifact 的 `disagreements = ["JPM","XOM"]` 非空——不是 verdict 錯,而是 `agrees_with_pipeline` 欄位定義過窄(`tools/certify.py:49` 只把 status=="pass" 視為與 certified 一致,重組後的 `partial` 被記為不一致)。本報告舊版寫「零分歧」的前提(所有 certified 都是 status=pass)在 P0-10 之後不再成立,如實更正。縱深防禦的主張不變:若某結構 heuristic 未來誤標 Item 8 pass,XBRL 會抓到並降級。

### Eval 升級(2026-07-10):三引擎三角驗證 + offset F1 + 官方 span oracle

> 現況 records 以 `data/sec_eval/records/sweep3` 為準(當前 HEAD 重跑,含 char-offset 新 schema);sweep2 降為歷史 baseline。已知漂移(sweep2→sweep3):pass 177→178、incorporated_by_reference 63→62(CAT pass 16→17)、confidence mean 0.962→0.975——sweep2 是舊版 pipeline 產物,非 regression。

#### 三引擎 triangulation(T2-1)

edgartools 5.42.0 作第三獨立引擎,對「同一份 raw HTML」離線解析,與我方 span 以 alphanumeric 正規化 + 8-word shingle containment 比對。11 家 253 items:

| verdict | 數量 | 說明 |
|---|---|---|
| agree | 240 | **94.9%** |
| disagree | 12 | 4.7%;全數逐條人工驗證為真歧異,扣 confidence + needs_review(例 JPM item 7 → 0.515)|
| engine_unavailable | 1 | JPM 1C(引擎缺項不算我方失敗)|

12 個 disagree 的兩大 class:edgartools 端 section misattribution(NEM/NVDA/WMT item 16 → FG-SEC-006)與 wrapper 10-K 邊界定義歧異(JPM/XOM items 7/8 → FG-SEC-007)。三角驗證無仲裁者:即使證據指向錯在對方,也一律 needs_review,不單方判自己贏。

- 重跑:`SEC_EDGAR_USER_AGENT=<contact> .venv/Scripts/python tools/triangulate.py`(cache-first,重跑離線)
- Artifact:`data/sec_eval/triangulation/triangulation.json`

#### char-offset F1 + present/null/MISSING 三態(T2-2)

record 現在 emit `start_offset`/`end_offset`/`text_sha256`/`toc_listed`。5 家(80 個 offset-gold items)macro-F1 over items = **1.0**、over filings = **1.0**;confusion:matched 82 / correct_null 33 / omission 0 / hallucination 0 / false_missing_alarm 0。

**誠實標明:F1=1.0 是建構性結果**——gold 由 pipeline 當前 offsets 半自動凍結(條件:pass/partial + needs_review=false + triangulation agree,協定寫死在 `tools/freeze_offset_gold.py`,凍結後人工 spot-check 7 個 span 頭尾),價值是 **regression baseline** 而非絕對正確率宣稱。敏感度已鎖成可重跑測試(`tests/test_scoring.py::test_sensitivity_injection_on_real_sweep3_aapl`):對真實 AAPL sweep3 record 注入 3 類 regression(1A 邊界截短 2 萬字、Item 3 pass→missing、Item 6 幻覺 pass)後 AAPL 單票 P/R/F1 = **0.9375/0.9191/0.9267**,omission/hallucination 各 1 全被抓到、boundary_moved 被 sha 區分。絕對正確率的獨立訊號是 triangulation(240/12)與 XBRL/CYD oracle。

11 家 sweep3 tri-state:**present 178(70.4%)/ null 75(29.6%)/ MISSING 0**(GS/JPM 缺 Item 16 皆 optional 且 TOC 未列 → 正確映 null,分離 omission 與 hallucination)。

- 重跑:`.venv/Scripts/python tools/score_offsets.py data/sec_eval/records/sweep3`;tri-state:`.venv/Scripts/python tools/sweep_metrics.py data/sec_eval/records/sweep3`
- Artifacts:`data/sec_eval/scoring/offset_f1.json`、`data/golden_labels/offsets/*.json`、`data/sec_eval/records/sweep3/`

#### CYD 官方 ground truth:Item 1C span oracle(T2-3)

SEC 對 FY ≥ 2024-12-15 強制 Item 1C 的 CYD taxonomy iXBRL block-tag——**唯一有官方機器可讀 span 的 item**。掃描同一份 raw HTML 的 `cyd:*TextBlock`(跟 ix:continuation 鏈、排除 ix:hidden),與我方 1C segment 比對。11/11 家全數適用:

| verdict | 家數 | 說明 |
|---|---|---|
| agree | 9 | 9 個 pass segment 的 coverage(我方 span 覆蓋官方 tagged span)全部 **100.0%** |
| disagree | 2 | JPM/GS wrapper 10-K 的 IBR stub,coverage 0%(→ FG-SEC-008)|

這是 offset gold(建構性 F1)之外**第一個真正外部的 span 正確性錨點**。containment 94.6–99.6%,唯 CAT **73.1%** 是真訊號:我方 1C span 尾部吞了 CAT 非標準「Item 1D. Information about our Executive Officers」(1D 不在 VALID_CODES)——oracle 抓到我方 span 跑長。

- 重跑:`SEC_EDGAR_USER_AGENT=<contact> .venv/Scripts/python tools/certify_cyd.py`(cache-first,無新網路)
- Artifact:`data/sec_eval/cyd_groundtruth/cyd_agreement.json`

#### 分層抽樣:format-era × filing agent(T2-4)

baseline 11 家全是 iXBRL(10 Workiva + 1 DFIN)——覆蓋缺口用分層抽樣補:era 軸 × filing-agent 軸。結果:html_2001_2008 cov 0.9824、xbrl_2009_2018 cov 0.9592、Toppan Merrill cov 0.9107 皆 Supported;**pre-2001 純文字 SGML 誠實標 Unsupported**(cov 0.0,heading detector 0 candidate;partition invariant 仍成立,整份退化為單一 unclassified block → FG-SEC-009)。agent survey(efts 2025-02,n=40):Workiva 31 / unknown 8 / Toppan 1——生態系 Workiva 壟斷,baseline 抽樣合理。完整支援表見 `supported_and_unsupported.md`。

- 重跑:`SEC_EDGAR_USER_AGENT=<contact> .venv/Scripts/python tools/stratified_sample.py`
- Artifact:`data/sec_eval/stratification/stratification.json`

#### Landmine 清單 → 可執行 eval cases(T2-5)

10 條官方/社群 landmine(Item 6 廢除後三態、Item 9C/16 optional、"Items 7 and 7A" 合併、wrapper/Glossy ARS、EDGAR formTypes exact-match、TOC 先排除、edgartools #454 Part I/II 編號碰撞、>50MB offset 一致性…)逐條先探針驗證 pipeline 實際行為、再寫成 **15 個 pytest case,全過**、零 source 修改——價值是 regression baseline:任何改動重新引入 landmine 立即被抓。測試 bar 是「絕不 fake pass」:正確結果是誠實 status(reserved/missing/IBR/partial+needs_review)。

- 重跑:`.venv/Scripts/python -m pytest tests/test_landmines.py -q`
- Artifact:`data/sec_eval/landmines/landmines.json`(header 曾有 total_tests=16 off-by-one,已修正為 15,commit `2fc9f06`;10 條 landmine 全數覆蓋)

#### 外部 human-labeled benchmark:NTU itemseg 30-slice head-to-head(2026-07-10,誠實揭露輸)

與三個 vendored 開源引擎在同一份 NTU 人工標註 gold(30-filing slice)上對跑:

| 系統 | macro-F1(NTU 30-slice) | scored / failures |
|---|---|---|
| edgar_crawler | **0.6332** | 30 / 0 |
| **ours**(合法 TOC-strip 落地後;TOC-strip 前 raw 0.5964 為歷史過程值,該次 run 的 artifact 未保存——現行可複核值即 0.6245) | **0.6245** | 28 / 2 |
| datamule | 0.6244 | 28 / 2 |
| edgartools 5.42.0 | 0.4386 | 26 / 4 |

**單軸 F1 我們沒有贏**:輸 edgar_crawler 0.0087、追平 datamule(0.6245 ≈ 0.6244,非「贏」)——如實記錄,F1 tuning 已 CLOSED。差異化在驗證軸:全場唯一有多 oracle 驗證(XBRL/CYD/topic/2-of-N)、誠實 needs_review/棄權(false-pass 是自己量出來自己公布的:TOC-strip 落地前 **100/397**,artifact `data/sec_eval/calibration/calibration.json` 的 `strata.ntu_human_labeled.verifier_false_pass`;落地後 **79**,artifact `data/sec_eval/scoring/head_to_head.json` 的 `summary.ours.verifier_false_pass_items`——交付層移除的 TOC-bleed fp 不再計)、capture-first 覆蓋保證與 mutation harness 的系統——edgar_crawler 的 0.6332 是無法自我審計的數字。

**軸差異聲明(NTU ItemSeg 論文 vs 本表)**:NTU 論文(arXiv 2502.08875)報的 BERT4ItemSeg macro-F1 **0.9825** 是 **per-line BIO 邊界分段分類 F1**、在 3,737 份標註 filing 上**監督式訓練**;本表的 0.62x 是 **item 全文抽取 F1**(30-filing slice、**zero-training**,未在該 gold 上調參)。兩者量的不是同一件事,不可直接比較——0.9825 不是本表的同軸天花板。NTU gold 在本 repo 的角色是**外部弱老師(一票),不是 gold 真值**(引用原則見 `docs/research/giants_task2.md` §4、`docs/research/external_benchmark_spike.md`)。

- confidence 校準:AUROC(NTU human-labeled,n=512)= **0.6307**(gate ≥0.75 未達,MISS 如實記帳,不得引用 0.63 為「可接受」);ECE 0.1762。
- risk-coverage 操作點(從 `data/sec_eval/calibration/calibration.json` `strata.ntu_human_labeled.risk_coverage` 實算;risk = P(錯誤 | confidence ≥ 閾值),不含 needs_review gate):

| confidence 閾值 | coverage | risk(該 gate 下 false-pass rate)|
|---|---|---|
| ≥ 1.0 | 0.2988 | 0.2157 |
| ≥ 0.9 | 0.7207 | 0.2249 |
| ≥ 0.8 | 0.7559 | 0.2274 |
| ≥ 0.7 | 0.8379 | 0.2424 |
| ≥ 0.6 | 0.9531 | 0.2643 |
| 全收(≥ 0.0)| 1.0000 | 0.2754 |

  營運 gate(needs_review==False ∧ conf≥0.6,同 artifact `verifier_false_pass` 欄)另計:coverage **0.7754**、false-pass **0.2519**(gate 含 needs_review,故不落在純閾值曲線上)。誠實解讀:曲線幾乎平坦——閾值從 0 拉到 1.0 只把 risk 從 0.275 壓到 0.216,confidence 對 NTU 錯誤主體(boundary bleed)鑑別力弱,與 AUROC 0.6307 的 MISS 判定一致;這張表是「confidence gate 目前換不到精度」的量化證據,不是可用性宣稱。計算指令:`.venv\Scripts\python -c "import json; rc=json.load(open('data/sec_eval/calibration/calibration.json'))['strata']['ntu_human_labeled']['risk_coverage']; [print(r) for r in rc if r['threshold'] in (1.0,0.9,0.8,0.7,0.6,0.0)]"`
- mutation harness:detection recall **全六類 1.0**(truncate/misalign/toc_anchor/wrapper_swallow/jitter/cross_swap),clean false-alarm 0.0056(門檻 recall ≥0.95 / false-alarm ≤0.05)。
- Artifacts:`data/sec_eval/scoring/head_to_head.json`(4-engine、30 filings)、`data/sec_eval/calibration/calibration.json`;mutation harness:`tests/test_verifier_mutations.py`。裁決鏈(含 TOC-strip 對抗裁決與錯誤更正)見 `docs/research/giants_task2.md`。

## Browser Agent(題目一)

Eval set(`data/browser_eval/tasks.json`,5 tasks:4 solvable + 1 expected-fail,分層,offline mock sites)+ runner(`tools/browser_eval.py`)。實測 metrics(`runs/browser_eval/results.json`):

**穩定不變量(硬數字):**

| Metric | 值 | 意義 |
|---|---|---|
| task success rate | 1.0 | 支援任務完成率 |
| **verifier false-positive rate** | **0.0** | 空結果 task 正確判 fail,**不偽裝成功** |
| trace completeness | 1.0 | 每個 run 都有完整 trace + screenshots + EvidenceRecord |
| verdict accuracy | 1.0 | 判定與 ground truth 一致 |

會漂移的量測(latency、repair success rate)以 `runs/browser_eval/results.json` 為準,不硬寫進文件(selector memory 在 tasks 間累積會改變 repair 次數)。

- **Killer demo(SPEC 15)**:v1 script mode pass(0 repair)→ v2 UI 漂移(id 移除、button→icon、cookie modal、decoy button、lazy render)→ 偵測 selector_not_found + modal_blocking → a11y-tree 修復(避開 decoy)→ verifier pass → memory 更新。trace 在 `runs/browser_demo/trace.json`。
- **自我維護證據**:v2-gizmo task **0 repair**——selector memory 從前一個 v2 task 學到新 selector,漂移成本攤平。
- **誠實邊界(code-enforced)**:capability guard 拒絕 login/purchase/checkout/submit(`packages/browser_agent/capability.py`),task 回 `refused`;非 docs-only。
- repair success rate 定義說明:以「含 repair 的 task 最終 pass」計,偏保守——v1-nonexistent 的 repair 其實成功找到元素,但任務因空結果**正確判 fail**,不計入分子。故此 metric 低估了 repair 機制本身的成功率。
- **Evidence 持久化**:browser run 現在也走共用 `EvidenceStore`,每步 + verdict 產生 `EvidenceRecord`,committed 於 `data/browser_eval/evidence/`——與 SEC 同一 evidence 契約(兩題共用,不是各寫各的)。

### Eval 升級(2026-07-10):校準裁判本身 + 擾動矩陣 + silent-failure 量測

第一性原理:沒有 public ground truth 的系統,可信度上限 = 驗證機制的可信度。本波六項全部離線 deterministic、零 LLM 成本(見 `cost_latency_report.md`)。

#### Verifier 校準 + Rogan-Gladen 校正(T1-1)

50 個 by-construction triple(24 success + 26 corrupted,5 種損毀 class:needle_removed / wrong_url / download_wrong_content / confident_false_claim / **answer_wrong**)餵 verifier(answer_wrong + answer_matches 條件型別為 2026-07-10 answer channel P2 新增,見「修復迭代 2」):

| Metric | 值(2026-07-10 修復後)|
|---|---|
| sensitivity | **1.000** |
| specificity | **1.0**（修復前 0.9583）|
| FP rate | **0.0**（修復前 0.0417；唯一 FP filename-needle bypass 已於 c4ac7cd 修掉,FG-BROWSER-002）|
| FN rate | 0.000 |
| corrupted unknown rate | 0.115385(unknown 單獨列,不併入 fail)|

Rogan-Gladen 校正後成功率 = **0.8**(apparent 0.8,分母 1.0,status=ok;修復前 0.7913／分母 0.9583)。**校準範圍聲明**:僅涵蓋 url_contains / text_visible / download_exists + 4 種 forbidden;table_extracted / screenshot_region_changed / field_value_equals 為結構性 unknown,排除且寫進 artifact 的 `scope.excluded_condition_types`。confident_false_claim class 0 pass、answer_wrong class 0 pass——證實 verifier 不吃 agent 自述、也不吃錯抓的答案。corrupted 三態現為 {pass 0 / fail 23 / unknown 3},confusion FP=0。

- 重跑:`.venv/Scripts/python tools/calibrate_verifier.py`(零瀏覽器)
- Artifacts:`data/browser_eval/calibration/calibration_results.json`(cases 自包含可跨機器重播:`calibration_cases.json`)

#### Impossible-task set:silent-failure rate(T1-3)

12 cases(10 impossible + 2 refused;product_absent / feature_absent / false_premise / unobservable / refused),真 headless chromium end-to-end。**2026-07-10 修復後**:**silent_failure_rate = 0.0**(修復前 0.1／1-of-10)、honest_outcome_rate = **1.0**(8 fail + 2 unknown;修復前 0.9)、expect_status_accuracy = **1.0**(修復前 0.9167)、refused 2/2 正確擋下(0 leaked to action)。原本那個真實 silent failure(query-echo teleporter → FG-BROWSER-003)在 c4ac7cd 由 text_visible 空結果回顯遮罩修掉,teleporter 從 pass 翻成正確的 fail——measure(0.1)→ fix → remeasure(0.0)的完整閉環,不是一開始就 cook 出的 0.0。

- 重跑:`.venv/Scripts/python tools/impossible_tasks.py`
- Artifact:`data/browser_eval/impossible/impossible_results.json`

#### Trajectory 兩維度:repetitiveness + side effects(T1-4)

RUN 級觀測(不改 agent 行為,AgentRewardBench 三維度):5 tasks mean_repetition_score = **0.0**、n_loops_detected = 0——誠實反映 Script Mode 確定性(非零訊號需 live LLM planner);side effects **5/5** 命中(皆 form residue:搜尋後 query 殘留 search box),benign 但真實。三態誠實:真實網站 / 缺 pre-post snapshot 一律 unknown,不偽造 clean。

- 重跑:`.venv/Scripts/python tools/trajectory_metrics.py`
- Artifact:`data/browser_eval/trajectory/trajectory_results.json`

#### pass@k 與 flakiness(T1-5)

`tools/browser_eval.py --repeat N`,每 pass 開頭清 selector memory 使樣本獨立可重現。Script Mode k=3(n_tasks=5、n_solvable=4):pass@1 = pass@k = **1.0**、flaky_rate = **0.0**、**deterministic = true**(v1-nonexistent expected-fail,statuses fail×3 一致,依 aggregate_passk 排除於 pass@k 分母);Agent Mode(MockPlanner,3 solvable tasks)同。確定性是量測證明的性質,不是斷言;非平凡 flakiness 需 live LLM planner(artifact note 已標,聚合機制已備好)。2026-07-10 以 Script Mode 重跑還原 artifact(deterministic、file:// mock sites、LLM 成本 $0),regenerated 與 HEAD **byte-identical**(git diff 空);單 pass artifact 同步刷新於 `runs/browser_eval/results.json`。

- 重跑:`.venv/Scripts/python tools/browser_eval.py --repeat 3 --agentic`
- Artifact:`data/browser_eval/passk/passk_results.json`

#### 三軸擾動 + degradation curve(T1-2)

mutation-site 矩陣(StressWeb 路線):clean + 3 軸(perception / action / execution)× 3 強度 = 10 cells × 3 queries = 30 probes,全部 deterministic(無 Math.random,test 鎖;generator 與 committed HTML 有 drift-lock test)。三軸 curve 皆 **monotone non-increasing**。avg_repairs 呈現「成功但有成本」中間態(light/medium 2.0/1.0 vs clean 0.0)。矩陣原本抓出 2 個真實 repair 弱點(FG-BROWSER-004/005),measure-first 先量測、**2026-07-10 由 commit 3f0b1e9 修復並重跑**:

- **perception 軸(FG-BROWSER-005,bait-field tie-break)**:form-context tie-break 讓真搜尋框勝出誘餌 Promo 欄位。perception curve 1.0→1.0→1.0→**0.0** 變 1.0→1.0→1.0→**1.0**;perception-heavy success 0.0→**1.0**、checkpoint 0.0→**1.0**、recovery 0.0→**1.0**。
- **action 軸(FG-BROWSER-004,repair fallback 到不可行元素)**:可行性 gate 讓 repair 對 `<span onclick>` submit(不進 a11y 枚舉)回「no viable candidate」而非 silent wrong click。action-heavy success **仍 0.0**(submit 真的不存在),但 fail 得**更誠實**:3/3 run honest_refusals=1;curve 1.0→1.0→1.0→0.0 不變、checkpoint 1.0 不變。artifact 新增 `honest_refusals` 欄位把「誠實 fail vs silent wrong click」寫進 committed 數字。

checkpoint 解離訊號仍定位失敗位置:action/execution-heavy ckpt=1.0(失敗在下游)。mid-task recovery:light/medium = 1.0、無 fault 的 cell 誠實回 null。其餘 8 cells 判定與 repairs 完全不變。

- 重跑:`.venv/Scripts/python tools/degradation_curve.py`(注意:artifact 內嵌 per-probe latency_ms,重跑非 byte-stable;全部 metric 欄位確定性重現)
- Artifact:`data/browser_eval/artifacts/degradation_curve.json`

#### 輕量 false-success detector(T1-6,heuristic 路線)

labeled full trajectory <60(論文 2606.09863 的 train 門檻)→ 誠實走 heuristic 前哨,不硬 train。**2026-07-10 修復後**:兩個 ground-truth false success(teleporter query-echo、filename-bypass)在 verifier 上游(c4ac7cd)被消滅,detector 已無假 pass 可抓——applicable claimed-pass 24→**22**、confusion {tp1/fp0/fn1/tn22}→**{tp0/fp0/fn0/tn22}**、flag_rate 0.0417→**0.0**、precision 1.0→**null**、recall 0.5→**null**(P2 answer-channel 擴充 corpus 後重跑:corpus 62、applicable **24**、{tp0/fp0/fn0/tn**24**},結論不變)(分母歸零,已在 artifact `known_limitations` 寫明:代價是此 corpus 上 recall 暫不可量測——上游把 false success 修光是好事,但也讓下游 detector 在此 corpus 失去可量測樣本)。表面 proxy(closing 語氣、序列長度)刻意單獨不足以 flag——直接對應論文警告「judge 過度倚賴表面訊號」。TF-IDF+XGBoost 版寫進 artifact 的 roadmap(前置條件:≥60 labeled trajectory + trajectory log 補存 agent 自述)。detector 是 opt-in triage hint,**絕不改判定**(verdict_unchanged invariant 有 test 鎖)。

- 重跑:`.venv/Scripts/python -m tools.false_success_detector`(script 形式亦可,sys.path bootstrap 已補,commit `2fc9f06`)
- Artifact:`data/browser_eval/false_success/detector_results.json`

#### 開放式(不可驗證)任務:誠實 unknown 而非 crash / vacuous pass(2026-07-10,FIX-1)

無可機讀驗證條件的任務(如「隨便逛逛看有什麼有趣的」)過去會讓 run crash(contract `success_conditions` min_length=1 → ValidationError → status=ERROR),或在繞過後 vacuous pass(什麼都沒證明卻回 pass)。修復(commit 2fec949)讓這類任務:contract 允許空條件、verifier 空 success 時先跑 forbidden、否則短路回 **unknown** + 明講需人工審 trace、agent 照常執行並錄 trace。3 個開放式 case 實測:status 全 unknown、**crashes 0 / vacuous_passes 0 / honest_unknown_rate 1.0**、traces_recorded 3(每 case trace steps 2/3/2 > 0)。這是三態鐵律在「開放式任務」上的落地:缺可驗證證據 → unknown,絕不 vacuous pass、絕不 crash 掉誠實輸入。

- 重跑:`.venv/Scripts/python tools/open_ended_tasks.py`
- Artifact:`data/browser_eval/open_ended/open_ended_results.json`

### 修復迭代(2026-07-10):measure → fix → remeasure 前→後對照

上面 6 項 eval 升級刻意先 measure-first 呈現系統現狀(4 個 browser 弱點 + 1 個開放式 crash),本波把它們全數修掉並重跑 artifact。舊數字保留在上文為歷史 baseline——measure-fix-remeasure 是本專案的方法論賣點,不抹掉「修復前」。

| 指標 / case | 修復前 | 修復後 | commit | artifact |
|---|---|---|---|---|
| 校準 specificity | 0.9583 | **1.0** | c4ac7cd | `calibration/calibration_results.json` |
| 校準 FP rate | 0.0417 | **0.0** | c4ac7cd | 同上 |
| 校準 Rogan-Gladen corrected | 0.7913 | **0.8** | c4ac7cd | 同上 |
| corrupted 三態 | pass1/fail20/unknown3 | **pass0/fail21/unknown3** | c4ac7cd | 同上 |
| impossible silent_failure_rate | 0.1 | **0.0** | c4ac7cd | `impossible/impossible_results.json` |
| impossible honest_outcome_rate | 0.9 | **1.0** | c4ac7cd | 同上 |
| degradation perception curve | 1.0→1.0→1.0→0.0 | **1.0→1.0→1.0→1.0** | 3f0b1e9 | `artifacts/degradation_curve.json` |
| degradation action-heavy | fail(silent wrong click)| **fail(honest_refusals=1)** | 3f0b1e9 | 同上 |
| detector confusion | tp1/fp0/fn1/tn22 | **tp0/fp0/fn0/tn24**(recall 0.5→null;P2 corpus 擴充後 tn22→24)| c4ac7cd | `false_success/detector_results.json` |
| 開放式任務 | crash / vacuous-pass 風險 | **honest_unknown_rate 1.0,crashes 0** | 2fec949 | `open_ended/open_ended_results.json` |

FG-BROWSER-002~006 的逐條 Repair 說明見 `docs/failure_gallery.md`。

### 修復迭代 2(2026-07-10):INTC 營收 false pass 的三重根因,逐一結構性修復

上一波修的是「量測抓到的 verifier/repair 弱點」。這一波修的是**一個真實使用者親測的 false pass** —— 任務「找到 intc 10-k 的財報 找到裡面的最新的營收數字給我」被判 PASS conf 高,但答案從沒交到使用者手上。事後拆出三個獨立根因(見 FG-BROWSER-007),各以結構性防禦修復(非個案打補丁),前後行為對照如下。

#### 根因 1:premature landmark —— 條件是任務句自帶 token(P1,commit f59c65d)

preflight 產出的 success 條件 `text_visible:intc` 是任務句本身的字串,任何開著 EDGAR 搜尋頁的狀態都為真 → 尚未開始做事就 PASS。**結構性修復是 baseline-subtraction**:verifier 在 t0(agent 動作前)先用空 extracted 跑一次 `_check_success`,任何在 t0 就成立的條件是「landmark 而非 deliverable」,從有效 contract 中剔除;全剔除後空條件流進既有 open-ended gate → 誠實 **unknown**(絕不 vacuous pass)。`download_exists` 在 t0 是 unknown 不會被誤剔。planner 端另加 `_task_echo` guard:text_visible value 正規化後若是任務句子字串且 ≤3 詞則不採用。

| 指標 | 修復前 | 修復後 |
|---|---|---|
| INTC 任務 repro | **PASS**(landmark 命中,conf 高)| **unknown**(條件被 baseline 剔除 → open-ended gate)|
| 測試 | — | `tests/test_premature_landmark.py` **9 passed** |

- 重跑:`.venv/Scripts/python -m pytest tests/test_premature_landmark.py -q`

#### 根因 2:答案型任務無交付通道(P2,commit 711f336)

`extract_text` 的結果被丟棄(`run_agentic` 的 `extracted` 只放 `__download__`),即使 agent 抓到營收數字也不進 verifier、不回 UI —— 「做到了但沒交到人手上」在 pass rate 上完美、使用者價值為零。**修復是把答案接成第一級 deliverable**:extract_text 成功結果 append 進 `extracted['answer']`(存 `TaskRun.answer`、UI「📋 擷取內容」區塊),verifier 新增條件型別 **answer_matches**(有 answer 且 regex match → pass;不 match → fail;**沒 answer → fail**,不吃自述;regex 不可編譯 → unknown)。baseline-subtraction 不會誤剔 answer_matches(t0 無 answer 是 fail 非 pass)。

離線 fixture eval(`tools/answer_channel_eval.py`,ScriptedPlanner 無 LLM):

| 指標 | 值 |
|---|---|
| n_answer_tasks / matches_expected | 3 / **3** |
| silent_failures | **0** |
| answers_delivered | 2(pass_with_answer 1 + 錯抓元素 fail 1)|
| fail_without_delivery | 1(沒 extract → 誠實 fail,不偽 pass)|

answer channel 也擴充了 verifier 校準集:新 corruption class **answer_wrong**(抓錯段落當答案,2 case 全 fail)、calibrated_condition_types 加 **answer_matches**,校準集 46→**50**(24 success + 26 corrupted),三態 corrupted {pass0/fail23/unknown3}、sensitivity/specificity 維持 **1.0/1.0**、FP rate **0.0**、Rogan-Gladen corrected **0.8**。

- 重跑:`.venv/Scripts/python tools/answer_channel_eval.py`、`.venv/Scripts/python tools/calibrate_verifier.py`
- Artifacts:`data/browser_eval/answer_channel/answer_channel_results.json`、`data/browser_eval/calibration/calibration_results.json`

#### 根因 3:卡住時無視覺升級 + 首屏盲區 + 新分頁追丟(P3,commit 06eb46b)

原本 agent 卡住只能重試到 give_up、目標在視窗外或內容開在新分頁時會失敗且自述與事實不符。三項自主性升級:

- **Auto vision escalation**:純函式 `vision_escalation_reason(history, page_hashes)` —— 最近 3 步全無進展,或頁面 hash 連 4 觀察不變 → sticky 切入 Set-of-Marks 截圖 + gpt-5.5 視覺路徑。`AGENT_VISION` 語義改為 `1`=每步 / `0`=全關 / **未設=auto(新預設)**;舊行為(=1)完全保留。只掛在 LLMPlanner,離線 eval(Mock/Scripted 無 supports_vision)行為不變。
- **Scroll(off-screen targets)**:planner PLAYBOOK 教 `keyboard keys="PageDown"/"End"` 捲動後重讀 —— 首屏沒找到是捲動理由不是 give_up 理由(純 prompt,keyboard 本就過 capability guard)。
- **新分頁跟隨**:executor 在 click/mouse 後偵測 `context.pages` 成長 → 切到最新頁,agent 同步 `observer.page` 並記「↪ 跟隨新分頁」。修掉「內容在別分頁、agent 自述『點了沒效果』」的自述/事實背離。

鐵律零破壞:vision 是純感知通道(image 只進 planner prompt),action 全走原 schema,**verifier 仍是唯一裁判**(escalation 測試明確斷言 `run.status != pass`)。

- 重跑:`.venv/Scripts/python -m pytest tests/test_auto_vision_and_tabs.py -q`

#### 迭代 2 前→後總表

| 指標 / case | 修復前 | 修復後 | commit | artifact / test |
|---|---|---|---|---|
| INTC 營收任務 verdict | PASS(landmark false pass)| **unknown**(誠實,無交付則不偽 pass)| f59c65d | `tests/test_premature_landmark.py`(9 passed)|
| 答案交付通道 | extract_text 結果被丟棄 | **answer → extracted['answer'] + UI + answer_matches verdict** | 711f336 | `answer_channel/answer_channel_results.json`(3/3、silent 0)|
| answer 型任務 silent failure | 結構性盲區(pass 但零價值)| **0**(沒抓到 → 誠實 fail)| 711f336 | 同上 |
| verifier 校準集 | 46(4 class)| **50(5 class,+answer_wrong)** | 711f336 | `calibration/calibration_results.json`(sens/spec 1.0)|
| 卡住恢復 | 重試到 give_up | **auto 視覺升級(未設 AGENT_VISION=auto)** | 06eb46b | `tests/test_auto_vision_and_tabs.py` |
| off-screen 目標 | 只看首屏 | **PageDown/End 捲動後重讀** | 06eb46b | 同上(prompt)|
| 新分頁內容 | 追丟 + 自述背離 | **executor 跟隨最新分頁 + observer 同步** | 06eb46b | 同上 |

逐條事故報告見 `docs/failure_gallery.md` FG-BROWSER-007。

### Browser held-out / 真實網站(外部量測,2026-07-10)

mock sites 仍是主軸(可控 UI 漂移,offline 可重現、零 flakiness)。真實網站泛化已有初步外部量測:**Online-Mind2Web 20-task live subset**(OSU-NLP-Group,CC-BY-4.0,COLM 2025,arXiv:2504.01382)自跑三波:

| 波次 | success(pass / 可評分 18,排除 2 環境失效) | artifact(原始 run dir 為 gitignored;tracked 快照在 `data/browser_eval/external_runs/`)|
|---|---|---|
| baseline | 6/18 = **33.3%** | `runs/browser_eval/m2w_rerun/` + tracked 快照 `data/browser_eval/external_runs/m2w_rerun/`(其 `results.json` 由 `tools/aggregate_run.py` 從 20 份 per-task `summary.json` 事後聚合,`aggregated_post_hoc=true`;pass 6 / done 18 = 0.333 與本行一致)|
| post bucket-fix rerun | 8/18 = **44.4%** | `runs/browser_eval/m2w_rerun_20260710/` + tracked 快照 `data/browser_eval/external_runs/m2w_rerun_20260710/` |
| abstain-fix 定向重跑 6 unknown(任務集:`data/browser_eval/external/m2w_unknowns6.json`,sha256 `1acfc7a3a20a3bc20d5bb07cdaed243642272dcfeccb232028ff62d8d4226c9b`)| 6 unknown → **3 pass + 2 fail + 1 honest-abstain unknown** | fix 前對照(6 題全 unknown、judge 全 abstain):`runs/browser_eval/m2w_abstain_fix_20260710/` + tracked `data/browser_eval/external_runs/m2w_abstain_fix_20260710/`;最終:`runs/browser_eval/m2w_abstain_fix2_20260710/results.json` + tracked `data/browser_eval/external_runs/m2w_abstain_fix2_20260710/results.json` |
| **合成 topline(明標合成估計,跨兩次 launch,非單跑實測)** | **11/18 ≈ 61.1%** | 上兩列合成 |

- naive baseline 對照(同子集):4/20 = **20%**(`tools/naive_baseline.py`;tracked 快照 `data/browser_eval/external_runs/naive_baseline/results.json`)——機制有加值,但**不宣稱超越 SOTA**(bu-max live 97.0%)。
- **與官方 benchmark 的可比性(明確聲明)**:這是**自建 20 題 live 子集**、成功條件多為單一 landmark、61.1% 是**跨兩次 launch 的合成估計**——**不可與官方 Online-Mind2Web leaderboard(300 題、WebJudge 評審、Browser Use ~97%)直接比較**。我們量的軸是 verifier 誠實性(abstain / unknown 行為與 false-pass 防禦),不是 leaderboard 分數。
- second judge(advisory)abstain rate:**6/6 → 1/6**(殘餘 1 題 ign 為證據不足的誠實棄權,非缺陷);根因修復 commit `49bcc6e`(unwrap codex-gateway action-schema wrapper)+ `3258b73`(open-ended scorer verdict-time 武裝 + groundable final-page evidence),量測基建 `b561e37`。judge 與 verifier 2/6 分歧(nfl、gov.uk),advisory-only 不改判——**verifier 仍唯一裁判**。
- 誠實 caveat:n 小、live variance 未控制,61.1% 是方向指標非穩定增益;這批題的 success condition 多為單一 landmark,verifier 對其是弱 proxy。逐題明細與 caveat a–d 見 `docs/research/giants_task1.md`「外部量測 abstain-fix 2026-07-10」節。

### 已知殘留(誠實邊界)

1. **同檔附綁 wrapper 已還原;跨檔 cross-reference-index 尚未。** JPM/XOM 指向本檔附綁年報區塊的 stub 已由 `cross_ref.reassemble_wrapper_bodies`(commit 64de3ef)以 page-anchor / section-anchor 還原(JPM Item 1C CYD coverage 0%→100%;兩家 Item 8 重組 span 均獲 XBRL 3/3 認證,見 `failure_gallery.md` FG-SEC-007/008)。Intel/Citi 指向**另外裝訂年報 exhibit** 的 cross-reference-index 正文仍未還原——刻意不出貨脆弱的 title-based 猜測(Intel 正文無 emphasis 標記、標題重複當頁首,會出錯),**錯的正文比誠實的指標更糟**,見 `insights_and_directions.md` §2。
2. **boundary 精度已量化(2026-07-10)**:char-offset F1(建構性 gold,regression baseline,敏感度注入鎖在 `tests/test_scoring.py`:AAPL F1 1.0→0.9267)+ CYD 官方 iXBRL oracle(9/9 pass segment coverage 100%,首個外部 span 錨點)。人工 token-level 標註(絕對正確率)仍列 backlog。
3. **`data/sec_eval/records/sweep1` 是刻意保留的修復前 baseline**,其 Item 8 仍顯示舊的(錯誤)pass——用於 before/after 對照(見上方 metrics 表)。當前正確結果在 `sweep3`(sweep2 降為歷史 baseline,漂移見「Eval 升級」段)。
