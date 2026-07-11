# 站在巨人肩膀上:SEC 10-K Item Extraction 超越 SOTA 研究總結(Task 2)

> 本文件是六份「巨人 vs 本 repo(packages/sec_core)」逐項驗證後的合併總結。
> 所有 status 皆經實際 grep / 執行 regex / 讀碼驗證,非僅文獻比對。
> 巨人:edgar-crawler (nlpaueb)、edgartools、sec-parser (alphanome-ai)、sec-api.io(商業)、EDGAR-CORPUS(資料集)、NTU itemseg(arXiv 2502.08875,外部 benchmark)。
> **第二波(2026-07-10,回應 §5 完整性批判)**:新增 SRAF/Loughran-McDonald 10-X Parse、OpenEDGAR (LexPredict)、doc2dict、datamule 四個調研對象(皆實際 clone 讀碼或實測 EDGAR index),以及 10-K405/10-KSB form-variant 普查。判定見 §1.5,引用見 §4,批判處理狀態見 §5。

---

## 1. 對照表:我們 vs 各巨人(依評分維度)

評等:**優**(我們已超越)/ **平**(等價)/ **劣**(對方有我們沒有)。

### 1.1 Format-variance robustness(格式變異穩健性)

| 巨人 | 對方做法 | 我們現況 | 評等 |
|---|---|---|---|
| edgar-crawler | flat regex + 字距修復('I T E M 1')、case-priority、'Item No. 1' 仍是 open issue #37 | streaming char-flag normalizer(normalize.py)+ 4 detector(strict/loose regex、dom_heading、visual_layout);mid-word `<span>` 拆字 by construction 免疫;但 'Item No. 1'、roman numeral 同樣不匹配 | 平(backlog 後轉優) |
| edgartools | anchor/TOC 主路徑 + body-scan fallback、'<8 items → 換策略' 閘 | 主路徑即 body-scan;pipeline.py:74-77 已有 <8 → scan_bare_index 升級閘;cross_ref.py 處理 Intel/Citi/GE index 類 | 優 |
| sec-parser | inline-CSS style-fingerprint(font-weight/centered)辨識 heading | 只有 tag-level flags(b/strong/h1-h6);`<span style="font-weight:700">` 全盲(靠其他 detector 補位);CSS margin-top 當換行也缺 | 劣(P1) |
| sec-api.io | 自承 Citi Item 7、GE Item 1、Intel 為其 failure;pre-2002 不支援 | 同名 filer 已修復並有 fixture(FG-SEC-005);pre-2001 誠實標 unsupported(與其同樣讓步) | 優 |
| EDGAR-CORPUS | remove_tables=True 的 regex 切分,1993+ 全覆蓋 | 保留 table 內文、offset+sha256 source-exact;但 pre-2001 SGML 不支援 | 平 |

### 1.2 Self-verification without ground truth(無標註自我驗證)

| 巨人 | 對方做法 | 我們現況 | 評等 |
|---|---|---|---|
| edgartools | 54-filing fixture corpus CI 重測;但 flag 後照常回傳、caller 不看 warning | partition invariants(coverage.py 全文鋪磚)、7 值 typed ItemStatus、needs_review 一級欄位、3-engine triangulation(240 agree / 12 disagree)、8 組 named confidence components | 優 |
| sec-parser | per-element ProcessingLog 審計鏈 | BoundaryEvidence + ConfidenceComponent + toc_reasons 機器可讀;缺:純分數落選候選無 disposition 記錄(P1) | 平偏優 |
| sec-api.io | 'processing' 空字串反模式(issue #34:partial text + HTTP 200) | typed absent/failed 區分是我們的 design center(scoring.py tri-state、IBR typed status) | 優 |
| NTU itemseg | 3,737 份人工標註 benchmark + leaderboard | 未跑該 benchmark;自家 gold 僅 5 份 self-frozen(F1 1.0 無誤差訊號可校準) | 劣(P0) |

### 1.3 Edge cases(地雷覆蓋)

| 巨人 | 對方做法 | 我們現況 | 評等 |
|---|---|---|---|
| edgar-crawler | issue #35 combined items 兩邊皆空、#37 'Item No. 1' 未修 | 'Items 1 and 2' 顯式 combined 端到端建模(detection→boundary→triangulation→tests),勝過 #35;缺:singular header 隱含合併的推斷(Item 2 靜默 missing)、'Item No. 1'、roman | 優(2 缺口在 backlog) |
| edgartools | items 10-16 rescue path bug(_ITEM_TITLE_PATTERNS 止於 9C;**pinned @ 5.42.0**,即 triangulation 所用版本,升版需重驗)、terminal EOF-runoff | SIGNATURES body-scan 終界 + detect_appended_section_cut(XOM 311,785→33 字);但 triangulation 未對 edgartools 盲區 down-weight,12 個 disagree 中 8 個是 item 16 白白扣分 | 優(down-weight 在 P0) |
| sec-api.io | 自承 STRATS/CorTS trust(MD&A 合法缺席)為難例 | 語彙上支援 9C/16/1C(對方沒有),但 corpus 無 trust 10-K、無 legitimately-absent 期望測試 | 平(P0 fixture) |
| NTU 論文 | 錯標 heading(9A 標成 14)、<100 行 stub、7A 巢狀於 7 | landmine L1-L10 + 15 tests 覆蓋廣;上述三類無 fixture;topic_check 可 flag 但無測試證明 | 平(P0 fixture) |

### 1.4 Cost discipline(成本紀律)

| 巨人 | 對方做法 | 我們現況 | 評等 |
|---|---|---|---|
| doc2dict/datamule 路線 | deterministic style-aware parser first、LLM 僅 invariant failure | 同構且已文件化:deterministic $0 主管線,LLM adjudicator schema-gated(evidence-quote validator);缺:LLM tier 從未 wired/量測($/filing 是估計) | 平(**P0-12** 補量測) |
| sec-api.io | $49-599/mo 商業 API | 全免費;其 free tier(100 lifetime calls)可反過來當我們的外部仲裁票(P0) | 優 |
| EDGAR-CORPUS | 一次性離線 corpus,零邊際成本 | 可 join 當 weak-label 額外一票,批次成本近零(P0) | 平 |

### 1.5 第二波巨人(2026-07-10 調研,誠實判定)

| 巨人 | 有無 item segmentation | 維護狀態(pinned) | 判定 |
|---|---|---|---|
| **SRAF / Loughran-McDonald 10-X Parse**(Notre Dame) | **無**。Stage One parse 是整份文件清洗;"Item 7/8" 只出現在刪表格的保護規則。所有衍生資料集(LM_10X_Summaries、Document Dictionaries)皆 whole-filing 粒度。清洗程式碼未公開;公開的 `Generic_Parser.py`(ND-SRAF/McDonald 2016/06,本機鏡像實讀)是純 LM 字典計數,無 item 邏輯 | 資料持續更新(Summaries 至 2025);與 edgar-crawler/edgartools **血統完全獨立** | **不是 boundary teacher,不能當 P0-7 票**。實際價值:(a) LM_10X_Summaries 當清洗對帳 oracle(per-accession net size/word count/HTML·XBRL 佔比);(b) sum-of-items ≲ whole-doc word count 不變式(餵 P0-11);(c) 10-X Header Data(140 萬筆,1993–2025)當 crawler 召回普查的 master index;(d) 清洗規範參考(10% numeric table 規則等學界事實標準)。**注意**:>10% numeric 表格被刪 → 其 Item 8 密集段落文字殘缺,不可當內容 gold |
| **OpenEDGAR**(LexPredict) | **無**。`parsers/edgar.py`(398 行全讀):SGML `<DOCUMENT>` 切分 + SEC-header 欄位 + 整份丟 Apache Tika 全文抽取;grep item/section 零命中。paper(arXiv 1806.04973)自述亦僅 database + full-text pipeline | dead:最後實質 commit `1d1b8bc` 2019-05-15 | **not applicable**——不能當 vote,也不構成「最佳公開實作」挑戰。僅在 pre-2001 SGML/uuencoded PDF 進 scope 時回頭抄其 decode fallback 鏈(edgar.py:55-88, 328-383) |
| **doc2dict**(john-friedman) | 引擎層:regex 主裁判 + bold/font-size 樣式 fallback 分層(`convert_instructions_to_dict.py:229-271`) | 活躍:commit `01e6d0c` 2026-02-02;README 自承 early stage | **borrow techniques**:樣式屬性佐證 header(≈我方 P1-3 的現成參照)、repetitive-text 頁首尾去除(重複 ≥20 次移除)、TOC 免疫(table pipeline 分流 + href 版 TOC 移除)。弱點:regex 命中即給 level、不要求樣式佐證 |
| **datamule**(john-friedman;解析後端=doc2dict) | **有,一級公民**:per-form mapping dict(10-K/10-Q/8-K/20-F/S-1 等 ~40 form),`document.py:291` `parse()` → `:539` `get_section('item1a')`;.htm 與 .txt 同 mapping(pre-2001 純文字有路徑) | 非常活躍:commit `122fc54` 2026-06-25 | **usable as triangulation vote**(P0-7c):pip 可裝、樣式驅動路線與我方 regex 驅動獨立。**無公開 accuracy benchmark**——當票不當 gold |

---

## 2. Prioritized backlog(已去重;僅列 status = missing / partial)

指定必須處理的四個 known gaps 對應:verifier calibration curve → **P0-3**;runtime verifier mutation harness → **P0-4**;golden-set expansion via multi-teacher pseudo-gold → **P0-1**;wrapper reassembly → **P0-10**。

### P0

| # | What | Why | Effort | Impact | Where it lands |
|---|---|---|---|---|---|
| P0-1 | **Multi-teacher pseudo-gold 擴充 golden set**:EDGAR-CORPUS join + era-stratified 抽樣 + 3-way vote(我方/edgartools/corpus)+ lineage discount(corpus 血統=edgar-crawler,corpus+crawler 同意只算一票)+ table-strip 比對視圖(corpus 是 remove_tables=True,不 strip 會系統性誤判 Item 8 disagree)+ hard-case queue + **form-type→item-schema 對映(§2.1 規格,必經,否則 pre-2003 層系統性錯位)** | 解 known gap「golden set 只有 5 份 self-frozen」;是 P0-3 校準的前置。pre-2001 層退化為 2-way,誠實記錄。**校準去相關**:pseudo-gold 供 P0-3 時,edgartools 有雙重身分(teacher + triangulation 第三引擎)→ 投票時排除 edgartools 或分層報告(見 P0-3) | M | high | 新 tools/mine_pseudo_gold.py + third_engine.py source-aware compare mode(cell-flag masking 便宜,normalize.py CELL_TAGS 已標);freeze 進 data/golden_labels/offsets/ |
| P0-2 | **NTU itemseg 外部 benchmark**(3,737 份標註 10-K,arXiv 2502.08875):**第一步 = fetch 可行性 spike**(leaderboard 存在性與 dataset 可取得性未驗證);dataset fetch + ItemSegment offset → line-level per-item F1 adapter,對照公開 leaderboard。**姊妹交付物 A(head-to-head 同場競技表)**:edgar-crawler、edgartools(5.42.0)、datamule 跑在同一份 gold set(NTU + 擴充 gold),輸出 per-item F1 對照表——「超越最佳公開實作」的最短證據鏈;P0-7 vendor 進來的 engine 順手就能跑。**姊妹交付物 B**:verifier false-pass rate on external benchmark(我方抽錯的 filing 上 needs_review/低 confidence 是否有亮)——A++ 的單一決定性數字 | 把 eval 從自我參照(自家 gold F1 1.0)升級為可引用的外部對標——超越 SOTA 主張的直接證據 | M | high | tools/(比照 tools/score_offsets.py)+ fetch script + 新 tools/head_to_head.py |
| P0-3 | **Verifier calibration curve**:per-item confidence vs 正確性的 AUROC / ECE / risk-coverage;**分層報告**:human-labeled subset(NTU + κ-gated 人工)為主曲線,pseudo-gold 曲線僅輔助(或 pseudo-gold 投票排除 edgartools),否則 edgartools 雙重身分(teacher + confidence 訊號源)的相關誤差會抬高 AUROC;**交付物含 verifier false-pass rate**(risk-coverage 曲線上顯式標出) | known gap「無 P(correct\|pass) 校準曲線」;confidence 已有 8 named components 與判別力證據(sweep2:substantive 0.962 vs stub 0.666;sweep3 pass mean 已漂移至 **0.975**,見 eval_report.md:91,校準應以 sweep3 為準),缺的只是橋。**Gated on P0-1/P0-2**(5 份 F1 1.0 的 gold 沒有誤差訊號可校準) | M | high | 新 tools/calibrate_sec_confidence.py,吃 data/sec_eval/records/sweep3 + 擴充後 gold |
| P0-4 | **Runtime verifier mutation harness**:對 pipeline 輸出注入已知腐蝕(截斷 span、item 錯位、TOC-anchored 短 span、吞入財報 wrapper)+ **開放類 mutation**(隨機 ±N% 邊界抖動、跨 item 換文),斷言驗證層(confidence/needs_review/triangulation/topic_check/size band)必須抓到。**量化門檻:per-mutation-class detection recall ≥ 0.95(被 needs_review 或 confidence 顯著下降抓到);specificity:對未注入的乾淨 sweep3 輸出 false-alarm rate ≤ 0.05**——低於門檻 = harness fail,不是報數字就算過 | 現有 mutation test 只覆蓋 scorer(tests/test_mutation_sites.py:截 20k chars 必被抓);runtime 驗證訊號本身未被 mutation 測試——這是「驗證器自己被驗證」的缺口;無數字門檻則只是存在性證明,不可引用 | S | high | 擴充 tests/test_mutation_sites.py 或新 tests/test_verifier_mutations.py |
| P0-5 | **Triangulation engine-blind-class down-weighting**:item 10-16 + engine text 疑似 TOC junk 時,disagree 輸出 engine_suspect 而非扣我方分 | 12 個 disagree 中 8 個是 item 16,正好命中 edgartools(**pinned 5.42.0**)_ITEM_TITLE_PATTERNS 止於 9C 的 rescue bug(FG-SEC-006 已歸因,程式未消費);上游若修復,down-weight 依據隨版本重驗 | S | high | third_engine.py:98-158 compare_item + :181-193 apply_triangulation |
| P0-6 | **Adversarial fixture suite L11+**:STRATS/CorTS trust 10-K(MD&A 合法缺席期望)、'Item No. 1'(edgar-crawler #37)、錯標 heading(9A 標 14,斷言至少 needs_review)、<100 行 stub、7A-in-7 巢狀 | sec-api 自承難例 + NTU 論文錯誤分類法,直接變成「對手已踩的坑我們有 regression」的可引用證據;fixture pattern 已存在,便宜 | S | high | tests/test_landmines.py L11+、data/sec_eval/fixtures/、tools/stratified_sample.py SEEDS 加 trust filer |
| P0-7 | **第四/第五仲裁票**:(a) vendor edgar-crawler regex core 為第四 engine + apply_triangulation 擴為 2-of-N 投票;(b) sec-api.io free-tier(100 lifetime calls)仲裁協定,先打 12 個既有 disagree,回應立即 disk cache;(c) **datamule**(pip,commit `122fc54` 2026-06-25,後端 doc2dict)`get_section('item1a')` 為第五票——樣式驅動路線,與我方 regex 驅動及 (a)(b) 皆實作獨立,且對 pre-2001 .txt 有路徑。**明確排除 SRAF**:調查確認其不產生 item 邊界(見 §1.5),不是票源;其 cleaned text 至多當「獨立清洗管道同輸入變體」的弱 ablation(offset 不對齊、Item 8 表格殘缺,不可當內容 gold) | 多票血統獨立(sec-api 閉源,agree 權重最高;datamule 無公開 benchmark,當票不當 gold);比對機制可直接重用(third_engine.py:73-129 shingle containment 即所需度量形狀) | M | high | (a) 新 sec_core engine module + tools/triangulate.py:47-48 call site + ConfidenceComponent 擴充;(b) 新 tools/arbitrate_secapi.py + data/sec_eval/arbitration/;(c) requirements-dev + engine adapter |
| P0-8 | **CI golden-drift harness + typed known-bad manifest**:raw HTML 快取進 fixtures、failure gallery 的 FG-SEC-001..009 轉 machine-readable manifest 欄位、pytest 內跑 live pipeline 對凍結 gold 重測 | 對標 edgartools 54-fixture corpus;目前 score_offsets 手動跑且依賴網路 fetch,drift 無 CI 防線 | M | high | fixtures dir + manifest.json typed marker 欄位 + pytest |
| P0-9 | **Combined-item 推斷 fallback**:singular header 'Item 1. Business and Properties' 且 Item 2 無 anchor 時,檢查前項 title_text 是否含缺項 canonical title,標 combined 而非靜默 missing | 內容未丟失(span 正確跑到下個 anchor)但 Item 2 recall 靜默為零;consumer 端(third_engine.py:132 combined containment)已 ready | M | high | boundary.py resolve_items 的 r.chosen is None 分支 + items.py CANONICAL_ITEM_TITLES |
| P0-10 | **Wrapper body reassembly(JPM/XOM class)**:IBR stub 之後把 deferred Financial Section 正文重組回 item;順手修 cross_ref.py:13-16 stale docstring(寫 'not shipped' 但 L237-252 已實作 page-anchor resolution) | MEMORY 既定下一步;Intel class 已有 resolved_from_page_anchor,JPM/XOM 是最後一塊。stale docstring 會讓評審誤判已有能力 | M | high | cross_ref.py + page_map.py 延伸;docstring 一行修 |
| P0-11 | **Per-(form,item) 經驗 size band 硬性 guardrail**:從 agree-且-pass 的 sweep 條目算 p50,band p50/5..p50*8,出帶 → hard needs_review / 再抽取;**外加 whole-filing 不變式(SRAF)**:sum-of-items 字數 ≲ LM_10X_Summaries 該 accession 的 whole-doc word count,離群即 flag(注意 SRAF 是 whole-filing 粒度,只能供全檔上界,不能供 per-item band) | 現在只有全域 50..3,000,000 chars 一條帶(boundary.py:163-170),不分 item;素材(our_words/engine_words)已在 data/sec_eval 內,免新標註;SRAF Summaries 是血統獨立的免費對帳源 | M | high | 新 sec_core/size_bands.py + boundary.py 或 pipeline.py 掛檢查;SRAF CSV join 進 tools/ |
| P0-12 | **Cost discipline 落地量測**:(a) LLM adjudicator wire 一次真實 client + 量測單筆 $/裁決(現值 <$0.005 是估計,cost_latency_report.md:42 自承「無量測背書」);(b) eval record + tools/sweep_metrics.py 加 per-filing 成本欄(llm_calls、tokens、usd;現在只聚合 latency_ms,零成本欄位);(c) cost_latency_report.md 換上實測數字 | §5.2 批判成立:cost discipline 四維度之一的核心數字是估計值,A++ 不可接受;S effort 即可終結 | S | high | pipeline.py LLM tier wiring + tools/sweep_metrics.py 成本欄 + docs/cost_latency_report.md |

### 2.1 P0-1 附屬規格:form-type→item-schema 對映(2026-07-10 實測 EDGAR full-index 1993–2009 + 真實樣本 filings 驗證)

**EDGAR-CORPUS 實際組成(決定性證據)**:建置 config(edgar-crawler commit [`058a121a41`](https://raw.githubusercontent.com/nlpaueb/edgar-crawler/058a121a41/config.json))`filing_types = ["10-K","10-K405","10-KT"]`,下載端精確匹配(`edgar_crawler.py` @`5823367ae1` L45/L295)→ corpus = 10-K ∪ 10-K405 ∪ 10-KT,**永遠不含 KSB 家族與任何 /A**(1997 算術驗證吻合:corpus 10,106 ≈ 6,698+3,201+18)。

**規格(join 與直抽兩側都必須套)**:

1. **Normalize**:`10-K/10-K405→10K`;`10-KT/10KT405→10K(transition)`;`10KSB/10KSB40/10-KSB→10KSB`;`/A` 尾碼單獨立 flag。**Type 字串陷阱**:index 中是 `10KSB`(無連字號)、`10KSB40`、`10KT405`——`startswith("10-K")` 漏整個 KSB 家族,精確 `=="10-K"` 漏一切變體;匹配用完整枚舉。
2. **Era schema**(以 period-of-report 選,邊界年用 Item 14 標題雙驗證:含 "Exhibit"→PRE2003、含 "Accountant Fees"→MODERN):pre-2003 10-K/10-K405 為 Items 1–14 且 **14=Exhibits**(無 15/1A/1B/9A/9B);Release 33-8183(FYE≥2003-12-15)後 14=Fees、Exhibits→15。10-K405 與同年代 10-K item 結構完全相同(僅封面 checkbox),可安全歸併;10-K405 實測 1995–2002 佔標準家族約 1/3,2003 起為 0(Release 33-8230)。
3. **Canonical 對映**:PRE2003 10-K:1..13 恆等、14→canonical 15、canonical 14=NOT_APPLICABLE。10-KSB(1995–2008,巔峰年 ≈ 標準 10-K 的 40%):**6=MD&A、7=FinStmt、8=AuditorChg 起全面位移一格以上**,對映 6→7、7→8、8→9、8A→9A、8B→9B、9→10…13→15;canonical 6/7A=NOT_APPLICABLE(非 missing)。用 10-K schema 直抽 KSB = 系統性錯位;但 KSB 不威脅 corpus join(corpus 沒收),處理是分流+對映而非丟棄(丟棄 = 1995–2008 小市值母體的倖存者偏差)。
4. **Join guardrails**:g1 join key 撞多份先排除 /A 與 KSB;g2 pre-2004 層 corpus `section_14` 語義=canonical 15(Exhibits)、`section_15` 空=no-signal 非 disagreement,禁止當 accountant-fees 教師票;g3 2016–2020 層 corpus `section_15` 尾部含 Item 16 污染(其 extractor 最後一個 item 直吃到 EOF),比對先切除 "Item 16" 後文字;g4 KSB 層 3-way 退化 2-way,lineage 如實記錄;g5 `/A` 不入 pseudo-gold(Rule 12b-15 允許部分重述,樣本 Paramount 1999 `0000950120-99-000136` 僅含 Items 10–13),導入 hard-case queue;g6 1993 層不從 full-index 重建 join key(現行 index 該年僅 4 份 10-K,corpus 的 1,060 份無法重現),以 corpus filename/CIK 反查 accession;g7 `10-K/A` 每年約為 10-K 的 17–25%,量大,不可假設罕見。
5. **P1-8 era-emptiness prior 素材**(同批普查產出):7A≥FY1997、9A≥2002H2、9B≥2004、1A/1B≥FYE 2005-12、16≥2016、9C≥2021、1C≥FYE 2023-12;Item 4 語義 Vote→Removed(2010)→Mine Safety(2011)。

樣本 filings 與 SEC release 引註見 §4。

### P1

| # | What | Why | Effort | Impact | Where it lands |
|---|---|---|---|---|---|
| P1-1 | Heading 變體:'Item No. 1'(edgar-crawler open issue #37)+ roman numeral 'ITEM XIV' regex alternates | 4 變體中淨新增 2 個(9A(T)、Items-plural 已 work);#37 是「巨人未解我們解了」的直接引用點 | S | medium | headings.py _LOOSE_RE/_STRICT_RE + _make_code(:71-73)+ fixtures |
| P1-2 | CSS margin-as-line-break:`<span style="margin-top:...">` / display:block 補 newline | heading 黏上前行 prose → 所有 line-anchored regex 靜默失敗 | S | medium | normalize.py _Normalizer.handle_starttag 解析 style attr |
| P1-3 | Inline-CSS style fingerprint:font-weight/italic/centered/underline 新 FLAG + 已確認標題 style consensus 裁決模糊候選 | 現代 iXBRL 用 `<span style="font-weight:700">` 標 heading,dom_heading 全盲 | M | medium | normalize.py 新 FLAG + boundary.py _score/ambiguity tie-break |
| P1-4 | Gold 保護:freeze_offset_gold.py 加 exists/overwrite guard + per-item manually_verified flag;人工標註時採 kappa-gated protocol(double-annotate 10%,Cohen's κ≥0.8,label by content) | 重跑 freeze 會無聲清掉人工修正;κ protocol 讓擴充後的 gold 可辯護(與 P0-1 配套) | S | medium | tools/freeze_offset_gold.py + gold JSON schema + docs/eval_report.md 方法論段 |
| P1-5 | Runtime era/reliability tier:classify_format 移入 sec_core,ExtractionResult 帶 era 欄位 +(可選)confidence component | eval 資料已有 per-era 度量,轉成每筆輸出的校準 metadata(pre-2001 → low tier 對齊 coverage 0.0) | S | medium | pipeline.py(Result 目前只有 filing_class)+ confidence.py |
| P1-6 | Near-miss bucket:outcome_counts 加「off by ≤N chars」分箱(F1 0.98 與 0.55 目前同進 matched 箱);可選 Pk/WindowDiff 補充欄 | 報表層小改,讓 boundary 品質可分級引用 | S | medium | scoring.py score_filing + tools/score_offsets.py 輸出欄 |
| P1-7 | 落選候選 disposition evidence:_select_candidates 對每個純分數輸家追加一條 evidence(rejected_toc 已留,分數輸家沒有) | 補齊 sec-parser 式完整審計鏈,直接餵 self-verification 敘事 | S | medium | boundary.py:78-79 |
| P1-8 | Era-conditional item-emptiness prior:per-era expected-items 表,1998 filing 不再把 1C/9C/16 報 missing | 消除 false-alarm 面;**gated on P0-1** 的 corpus join(per-year empty-rate 表由其產出);規則面初稿已在 §2.1 第 5 點(SEC release 依據)。注:SRAF 是 whole-filing 粒度,**不能**供 per-item emptiness(§5.1 原建議修正) | M | medium | items.py 或新 module + boundary.py resolve_items + coverage verdicts |
| P1-9 | Early-HTML era(2001-2010)真實 filing 凍結 gold 進 pytest | 現有 5 份 offset-gold 全是 2025-26 iXBRL,era-specific regression 無防線 | S | medium | tools/freeze_offset_gold.py 產出 + pytest |
| P1-10 | 免疫證據 fixtures:no-Part-heading 10-K、accented title 兩個 synthetic fixture | 架構上免疫(無 part 狀態機、regex 只看 'item \d')但無測試佐證;把「對手踩坑我們免疫」變可引用 | S | medium | tests/ synthetic fixtures |
| P1-11 | 文件宣稱:prior_art.md/README 明寫 sec-api($49-599/mo)缺 9C/16、我們 1C 另有 CYD iXBRL oracle;Citi/GE(sec-api 自承 failure)我們有 typed 修復 + fixture;issue #34 對比一句 | 能力已在,缺的只是 citable claim;純文件 | S | medium | docs/prior_art.md + README |
| P1-12 | Longest-span-after-previous-end 第二選擇函數,與 score-rule 不一致時 flag hard case | 比既有 AMBIGUITY_MARGIN(score-ratio)正交的 span-length 訊號;邊際但近零成本 | S | medium | boundary.py 第二 selection fn + warning component |

### P2

| # | What | Why | Effort | Impact | Where it lands |
|---|---|---|---|---|---|
| P2-1 | Case-sensitive-first 兩段式 heading match + 「僅 case-insensitive 命中」扣分 | 意圖已被 line-anchoring + is_uppercase(+0.25)弱機制覆蓋 | S | low | headings.py detect_candidates + boundary.py _score |
| P2-2 | Letter-spaced 修復('I T E M 1' collapse) | 病灶集中 pre-2001 SGML,現行宣告 unsupported;僅在 pre-2001 進 scope 時升級 | S | low | normalize.py 或 headings pre-pass |
| P2-3 | PART divider 狀態機 + part-context 不符候選扣分 | 我們以 item code 唯一鍵,edgartools 該 bug class 主後果結構性不成立;殘餘風險小 | S | low | headings.py + boundary.py _score |
| P2-4 | ##TABLE_START/END sentinel — 僅放 export/比對層,**絕不進 normalize.py**(會破壞 offset+sha256 source-exact 不變量) | 只有搭配 P0-7(b) sec-api diff 才有價值 | S | low | arbitration diff layer / export formatter |
| P2-5 | detect_agent(Workiva/DFIN/Toppan)移入 sec_core 當 metadata 欄位(不做 agent-dispatch) | 擴大 sweep 時分層抽樣可直接引用;runtime prior 價值低 | S | low | tools/stratified_sample.py → sec_core |
| P2-6 | ~~LLM adjudication tier 實際 wire + 量測 $/裁決,更新 cost 表~~ **已升級為 P0-12**(§5.2 批判) | — | — | — | 見 P0-12 |
| P2-7 | Content-based item 重新指派(錯標 heading 全自動改派) | 論文顯示所有自動方法在此類全滅;P0-6 的 flag-needs_review fixture 已是務實上限 | M | low | (研究性,不建議近期做) |

---

## 3. 超越論證(per grading criterion)

### 3.1 Format-variance robustness

- **最佳公開實作**:sec-parser 的 style-fingerprint heading 偵測 + edgartools 的 multi-strategy fallback。
- **我們已經更好**:streaming HTMLParser 把整份 DOM 壓成帶 flags 的 char stream——wrapper 巢狀、mid-word `<span>` 拆字(sec-parser 的 top-level-tag 病灶、edgar-crawler 需要修復的 'B</span><span>USINESS')在我們架構 **by construction 不存在**(架構論證;直接測試佐證尚缺,與 P1-10 fixture 同綁,fixture 落地前此句不得單獨外引);4-detector 候選(strict/loose/dom/visual)本來就是 body-scan 主路徑,大銀行 link-less TOC 不構成災難;Intel/Citi/GE cross-reference-index 有 typed 修復 + 真實 accession fixture——其中 Citi Item 7 / GE Item 1 是 **sec-api 官方文件自承的 failure**。
- **Backlog 補上**:inline-CSS style flags(P1-3)、margin-as-newline(P1-2)、'Item No. 1'/roman(P1-1,含 edgar-crawler 未解的 #37)、JPM/XOM wrapper 正文重組(P0-10)。

### 3.2 Self-verification without ground truth

- **最佳公開實作**:edgartools 的 54-fixture CI 重測——但它 flag 後照常回傳,caller 不看 warning。
- **我們已經更好**:**multi-oracle triangulation**(regex/dom/visual detectors + edgartools 獨立引擎 + topic lexical oracle + XBRL/CYD certified oracles,240 agree / 12 disagree 全路由 needs_review);**capture-first coverage**(coverage.py 全文鋪磚,每 char 屬於恰一 block,gap 顯式浮出——「先全抓再分類」);offset+sha256 source-exact span,LLM 永不生成 filing 文字,AdjudicatorDecision 無 evidence quote 即拒絕;7 值 typed status 讓 absent≠failed(直接輾壓 sec-api issue #34 的 partial-text-HTTP-200);**honest failure gallery**(FG-SEC-001..009 記真實 accession、修復前後數字)。
- **Backlog 補上**:把「驗證器可信」變成可量測——calibration curve(P0-3)、runtime verifier mutation harness(P0-4)、per-item size bands(P0-11)、engine-blind-class 加權(P0-5)、血統獨立的第四/五票(P0-7)。這組合起來的主張是:*我們不只驗證抽取結果,還校準並 mutation-test 驗證器本身*——在我們逐項驗證過的十個公開實作/資料源(六巨人 + SRAF/OpenEDGAR/doc2dict/datamule)中,無一做到這層。

### 3.3 Edge cases

- **最佳公開實作**:sec-api 的自承難例清單 + NTU 論文的錯誤分類法(它們知道坑在哪,但多數沒修)。
- **我們已經更好**:landmine suite L1-L10 + 15 tests;combined 'Items 1 and 2' 端到端建模(勝 edgar-crawler #35);IBR typed status + Item 8 stub 指路(勝 edgartools);SIGNATURES body-scan + appended-section cut(XOM Item 16 從 311,785 字修到 33 字);TOC 5-signal 加權拒絕。
- **Backlog 補上**:trust/STRATS 合法缺席 MD&A(P0-6)、combined 推斷 fallback(P0-9)、錯標 heading 至少 flag(P0-6)、no-Part/accented 免疫證據(P1-10)。

### 3.4 Cost discipline

- **最佳公開實作**:doc2dict 路線的 deterministic-first 分層。
- **我們已經更好**:主管線 deterministic $0,LLM adjudicator schema-gated 且從未需要啟動(誠實記於 cost_latency_report.md);eval 用 era×agent 分層抽樣而非亂槍掃 corpus。
- **Backlog 補上**:sec-api 100-lifetime-call 配額的 cache-immediately 仲裁協定(P0-7b,把商業對手變成免費驗證票)、EDGAR-CORPUS 批次 join 近零邊際成本(P0-1)、LLM tier 實測 $/裁決 + per-filing 成本欄(**P0-12**,自 P2-6 升級;tools/sweep_metrics.py 現只聚合 latency_ms)。

---

## 4. 引用來源與使用限制

| 來源 | 用途 | 限制 / attribution |
|---|---|---|
| nlpaueb/edgar-crawler(GitHub)| heading 變體、字距修復、issues #35/#37 作為對照與 fixture 來源;P0-7a 擬 vendor 其 regex core | **Vendoring 前必查 LICENSE 並保留原始授權與版權聲明**;若授權不相容(GPL 系)改為 subprocess 隔離或依其行為重實作。其 README 要求學術引用 Loukas et al. 2021 |
| EDGAR-CORPUS(HF: eloukas/edgar-corpus;Loukas et al., *EDGAR-CORPUS: Billions of Tokens Make The World Go Round*, ECONLP 2021)| P0-1 pseudo-gold 的 corpus join | **標籤是 edgar-crawler 機器產生的 weak labels——只能當額外 engine vote,絕不可當 gold**;且與 edgar-crawler 同血統,兩者同意只折算一票(lineage discount);remove_tables=True,比對必須用 table-strip 視圖。組成 = 10-K ∪ 10-K405 ∪ 10-KT、無 /A 無 KSB(建置 config pinned @ crawler commit `058a121a41`,下載邏輯 @`5823367ae1` L45/L295)。引用其論文 |
| dgunning/edgartools(GitHub, MIT)| 既有第三引擎(**5.42.0**,triangulation 所用版本);其 items 10-16 rescue bug / EOF-runoff 為 P0-5 down-weight 依據(bug 宣稱 pinned @ 5.42.0,升版重驗) | 保留 MIT 聲明(已列 docs/ATTRIBUTION.md 者免重複) |
| **SRAF / Loughran-McDonald**(sraf.nd.edu:Cleaned 10-X Files、LM_10X_Summaries 1993–2025、10-X Header Data、Stage One Parsing Documentation,updated 1/2019)| **cleaning norms + 血統獨立 master index**——非 boundary teacher(無 item segmentation,§1.5):P0-11 sum-of-items 不變式、crawler 召回普查、清洗規範參照 | **"as is … for non-commercial purposes"**,學術免費、商用需洽作者;無正式 license 文本 → 資料不入 repo,fetch-on-demand + 引用 Loughran & McDonald (2011, JF) / (2016, JAR)。其 >10% numeric 表格刪除規則 → Item 8 文字殘缺,不可當內容 gold |
| **LexPredict/openedgar**(GitHub;arXiv 1806.04973)| gap-scan 完成:無 item 邏輯(`parsers/edgar.py` 全讀,SGML 切分 + Tika 全文),dead(最後實質 commit `1d1b8bc` 2019-05)→ **not applicable**;僅 pre-2001 SGML/uudecode fallback 鏈可回頭參考 | MIT(clone 內 LICENSE 實讀,LexPredict 2018);目前僅想法層,無 vendor 計畫 |
| **john-friedman/doc2dict**(GitHub,pinned @ `01e6d0c` 2026-02-02)| P1-2/P1-3 技術參照:樣式 fallback header 分層、repetitive-text 頁首尾去除、TOC 免疫(僅借想法,未 vendor) | MIT;想法層引用註明出處。README 自承 early stage |
| **john-friedman/datamule-python**(GitHub,pinned @ `122fc54` 2026-06-25)| P0-7c 第五仲裁票(`get_section('item1a')`,~40 form mapping dicts);P0-2 head-to-head 參賽 engine | MIT;**無公開 accuracy benchmark——當票不當 gold**;解析品質 = doc2dict 品質 |
| **SEC full-index form.idx 實測(1993–2009)+ 樣本 filings**(SanDisk 10-K405 `0001000180-99-000003`、Nicholas Financial 10KSB `0001000045-97-000004`、Broadway Financial 10KSB `0001193125-05-065205`、Paramount 10-K/A `0000950120-99-000136`)+ SEC Releases 33-8230/33-8183/33-8876/33-8591 | §2.1 form-type→schema 規格的一手證據 | 公開資料;計數腳本存 scratchpad(count_forms.py),入 repo 前移 tools/ |
| alphanome-ai/sec-parser(GitHub)| style-fingerprint、ProcessingLog、eval harness 設計參照(僅取想法,未 vendor 程式碼) | 想法層引用,註明出處即可 |
| sec-api.io Extractor API + janlukasschroeder/sec-api-python | P0-7b 外部仲裁票;其文件自承難例(Citi/GE/Intel/STRATS/pre-2002)與 issue #34 為對照證據 | 商業 ToS:cached responses 僅供內部 eval,**不可再散布原文 payload**;free tier 100 lifetime calls,回應必須立即 cache |
| NTU itemseg dataset(arXiv 2502.08875)| P0-2 外部 benchmark | 引用論文;確認 dataset 授權後才納入 repo(必要時 fetch-on-demand 不入庫) |
| 本 repo 既有文件 | docs/prior_art.md(競品表)、docs/failure_gallery.md(FG-SEC-001..009)、docs/eval_report.md、docs/cost_latency_report.md、docs/ATTRIBUTION.md | 新增引用一律同步 ATTRIBUTION.md |

**SEC EDGAR 本身**:原始 filings 為公開資料;快取 raw HTML 進 fixtures(P0-8)無授權問題,但需遵守 SEC fair-access rate limit(既有 fetch 工具已處理)。

---

## 5. 完整性批判

> Completeness critic pass(2026-07-10):針對「超越最佳公開實作、A++」目標的具體缺漏。
> **處理狀態更新(2026-07-10 第二波調研後)**:✅ = 已在本文件落地;⏳ = 仍開放。

### 5.1 漏掉的巨人 / 資料集

| 缺漏 | 為何重要 | 處理狀態 |
|---|---|---|
| **Loughran-McDonald / Notre Dame SRAF 10-X Parse** | 會計金融學界引用量最大的清洗版 10-K corpus(1993+ 全量),血統與 edgar-crawler 完全獨立 | ✅ 調查完成(§1.5)。**原建議修正**:SRAF 無 item segmentation,不能當 P0-7 票或 teacher;whole-filing 粒度也不能餵 per-item size band / emptiness prior。實際落地:P0-11 sum-of-items 不變式 + master index 召回普查 + 清洗規範參照;入 §4(non-commercial 授權註記) |
| **OpenEDGAR(LexPredict)** | 「最佳公開實作」完整性主張需對照 | ✅ gap-scan 完成(§1.5):無 item 邏輯(Tika 全文)、dead(2019-05)→ not applicable;入 §4。⏳ 尚未同步 prior_art.md |
| **doc2dict/datamule** | 引用了未驗證的對象 | ✅ 逐項驗證完成(clone 讀碼,§1.5):datamule 有真 item-level 抽取 → P0-7c 第五票 + P0-2 head-to-head 參賽;doc2dict 三項技術借鑑(P1-2/P1-3 參照);皆入 §4 並 pin commit |
| **10-K405 / 10-KSB form variants** | pre-2003 層系統性 join 失敗或誤配 | ✅ 完整規格落地(§2.1,實測 form.idx 1993–2009 + 4 份真實樣本):corpus 組成證實為 10-K∪10-K405∪10-KT;pre-2003 item 14/15 重對映、KSB 分流、/A 排除、g1–g7 guardrails 折入 P0-1 |

### 5.2 評分維度缺 P0

- **Cost discipline 無真 P0**:✅ 已落地為 **P0-12**(LLM tier wire 一次 + 實測 $/裁決 + sweep_metrics.py per-filing 成本欄;現況已驗證:sweep_metrics.py 只聚合 latency_ms、cost_latency_report.md:42 自承估計無量測);P2-6 註銷併入。
- 其餘三維度皆有 ≥2 個 P0,無缺口。

### 5.3 Who-judges-the-judge:未完全終結

1. **校準循環未斷**:✅ 修法已寫進 P0-1(pseudo-gold 投票排除 edgartools 或分層)與 P0-3(human-labeled subset 為主曲線、pseudo-gold 僅輔助)。regress 真正的終點是人工標籤——此原則已入 P0-3 條文。⏳ 實作未動工。
2. **P0-4 mutation harness 無量化門檻**:✅ P0-4 已加硬門檻:per-class detection recall ≥ 0.95、乾淨 sweep3 輸出 false-alarm ≤ 0.05,低於門檻 = harness fail。
3. **Mutation 類別封閉**:✅ P0-4 已加開放類 mutation(隨機 ±N% 邊界抖動、跨 item 換文)。
4. **未閉環**:✅ 「verifier false-pass rate on external benchmark」已明寫為 P0-2 姊妹交付物 B,並要求 P0-3 risk-coverage 曲線顯式標出。

### 5.4 缺證據的宣稱

| 宣稱 | 問題 | 處理狀態 |
|---|---|---|
| §3.2「沒有任何公開實作做到這層」 | 不可證的全稱否定 | ✅ 改為「逐項驗證過的十個公開實作/資料源中無一做到」 |
| P0-3「0.962 vs 0.666」 | eval_report.md:91 註明 sweep3 已漂移至 0.975 | ✅ P0-3 改註:sweep2 substantive 0.962 / stub 0.666;sweep3 pass mean 0.975,校準以 sweep3 為準 |
| P0-2「公開 leaderboard」 | leaderboard 存在性與 dataset 可取得性未驗證 | ✅ P0-2 已加「fetch 可行性 spike」為第一步(spike 本身 ⏳ 未跑) |
| §3.1「mid-word 拆字 by construction 免疫」以事實陳述 | P1-10 自承無測試佐證 | ✅ §3.1 已帶 caveat 並與 P1-10 同綁(fixture 落地前不得單獨外引) |
| edgartools「_ITEM_TITLE_PATTERNS 止於 9C」等競品 bug | 未 pin 對方版本/commit | ✅ 部分:edgartools pinned @ 5.42.0(§1.3/P0-5/§4);新巨人皆 pin commit(doc2dict `01e6d0c`、datamule `122fc54`、OpenEDGAR `1d1b8bc`、crawler config `058a121a41`/`5823367ae1`)。⏳ edgar-crawler issues #35/#37 與 sec-parser 缺陷宣稱仍未 pin 對方 commit |
| sec-api「自承 failure」 | 引註應與使用同時 | ⏳ 仍開放:URL/原文引註排在 P1-11,未提前 |

### 5.5 缺席的直接對決

✅ 已落地為 P0-2 姊妹交付物 A:edgar-crawler、edgartools(5.42.0)、datamule 跑在同一份 gold set(NTU + 擴充 gold),輸出 per-item F1 對照表(新 tools/head_to_head.py)。sec-parser 因無 end-to-end item extractor(heading 偵測層)不參賽,如實註記。⏳ 實作未動工。

---

## 外部量測 rerun 2026-07-10(post wave-2)

> (歷史紀錄,16:50 盤點;17:23 rerun 已補齊 after 欄,見下表。)
> Adversarial interpreter pass(16:50 當下盤點)。**結論先講:post-wave-2 的外部數字尚不存在。**
> 磁碟上的 `data/sec_eval/scoring/head_to_head.json`(mtime 15:16)是 pre-wave 產物:schema 只有
> `ours`/`edgartools` 兩 engine(wave-2 的 edgar_crawler/datamule 參賽 engine 不在內),summary 與
> 16:46 備份的 h2h_prev.json 逐位元相同。16:31 重跑的 `calibration.json` 直接讀該 stale artifact,
> 因此 AUROC/ECE 到小數第 4 位「不變」——這不是穩定,是輸入沒換。16:45 的 4-engine smoke(slice=2)
> 證明新 pipeline 可跑,但 n=2 的數字是雜訊。完整 30-slice rerun 截至 16:51 尚未啟動(無對應 process)。

### 數字表(before = pre-wave 實測;after = post overshoot-guard rerun 實測)

Rerun 於 2026-07-10 17:22–17:23 完成(overshoot guard `7940dbe` 之後),artifacts committed
`8589577`:head_to_head.json 為 4-engine schema、30 filings;calibration.json generated_at
17:23,讀的是同分鐘的新 h2h。Adversarial 重算(獨立腳本,非引用 tool 輸出):macro-F1 由
30 筆 per-filing 逐筆平均重算全數吻合;ECE 由 10-bin reliability bins 重算 = 0.1762(exact);
conf≥0.9 錯誤 = 369×(1−0.7751) = 83.0;攔截拆帳 141−100(false pass)−12(conf<0.6 bins
實算)= 29 needs_review,閉合。

| 指標 | 來源 | before(pre-wave) | after(post-fix) | 手工重算驗證 |
|---|---|---|---|---|
| macro-F1(ours, n=28) | head_to_head.json, NTU 30-slice | 0.5961 | **0.5964** | 0.5964 ✓(filings 逐筆平均) |
| macro-F1(edgartools, n=26) | 同上 | 0.4386 | 0.4386 | 0.4386 ✓ |
| macro-F1(edgar_crawler, n=30) | 同上(wave-2 新參賽) | — | 0.6332 | 0.6332 ✓ |
| macro-F1(datamule, n=28) | 同上(wave-2 新參賽) | — | 0.6244 | 0.6244 ✓ |
| AUROC(ntu_human_labeled, n=512) | calibration.json | 0.6277 | **0.6307** | binned 下界 0.5984 一致 ✓ |
| ECE(ntu_human_labeled) | 同上 | 0.1753 | 0.1762 | 0.1762 ✓(10-bin 重算, exact) |
| verifier false-pass rate | 同上(gate: conf≥0.6 ∧ ¬needs_review) | 0.2410(107/444) | **0.2519(100/397)** | 100/397=0.2519 ✓;coverage 397/512=0.7754 ✓ |
| AUROC(pseudo_gold_corpus_only, n=275) | calibration.json | 0.4288(比丟銅板差) | 0.4139 | —(aux,維持煙霧偵測定位) |

### 驗收門檻判定(§下一步修法設的 gate,誠實記帳)

| Gate | 目標 | after 實測 | 判定 |
|---|---|---|---|
| needs_review 錯誤攔截率 | 19/141 → **≥50%** | 29/141 = **20.6%** | **MISS**(+10 items,遠不及) |
| conf≥0.9 桶內錯誤 | 87 → **減半(≤44)** | **83** | **MISS**(−4) |
| AUROC(NTU) | 0.6277 → **≥0.75** | **0.6307** | **MISS**(+0.003) |
| macro-F1(副產品) | 上漲 | 0.5961 → 0.5964 | PASS(邊際,+0.0003) |

三個主 gate 全 MISS。Guard 確實上線(38 筆樣本落在 0.70–0.75 封頂區、sweep3 clean corpus
零新增誤報),但對 NTU 錯誤主體幾乎無感。

### 修後殘餘主導桶(為何 guard 打不到)

修前診斷的 123/141 boundary-bleed 桶,修後仍有 46 個錯誤停在 conf=1.0、83 個在 conf≥0.9。
原因是 containment check 的前提——「吞進去的下一個 item heading 能被 headings.py detector
以 strict_regex + DOM/visual 佐證找到」——在 NTU 主導桶大多不成立:bleed 多為 cascade
選擇錯誤或 heading 形態偵測不到(bare/變體 heading、表格內 heading),containment 無訊號;
size-ratio 單獨在 NTU 上鑑別力不足(band 是 corpus p95-proxy,對 IBR stub 與長 item 同時
失準)。下一個訊號需要不依賴「heading 可偵測」:候選有 next-item-anchor 時量 span 終點與
anchor 的距離,或 per-item gold-free 長度先驗(相對於 filing 總長的占比分布)。在該訊號
落地前,AUROC ≥0.75 與 ≥50% 攔截這兩個 gate 維持未達成狀態,不得引用 0.63 為「可接受」。

### 診斷:AUROC 為何卡在 0.63(從 512 筆 raw data 算,非臆測)

512 個 gold item 中 141 個錯(27.5%)。錯誤分桶:

1. **主導桶:boundary bleed(precision 稀釋)——123/141(87%)**。F1∈(0,0.5) 且其中 121 筆
   fp 行數 > gold 行數:recall≈1、起點抓對,尾巴掃過下一個 item 把 precision 打死。
   典型:item 6 錯 16 筆(平均 gold 33 行 vs fp 159 行)、item 9A 錯 15 筆(gold 17 vs fp 76)。
   徹底 miss(F1=0)只有 18 筆——這不是「找不到」的問題,是「不知道停」的問題。
2. **信心飽和讓 verifier 對主導桶全盲**:237/512(46%)conf=1.0、377/512(74%)conf≥0.9
   (bin 平均 conf 0.9793、accuracy 卻只 0.7692);141 個錯裡 87 個(62%)落在 conf≥0.9,
   needs_review 只攔到 19/141(13%)。verifier 目前量的是「item 有沒有找到、內容像不像」,
   完全看不到 overshoot——分數軸對主導失敗模式零訊號,AUROC 自然沒有 headroom。
3. **items 10–13(Part III IBR)是次要桶,且非 metric 冤枉**:40/141(28%),其中 28 筆
   gold≤3 行(IBR stub 極小,幾行 fp 就把 F1 砸穿 0.5);平均 conf 0.762,落在非飽和區,
   是 AUROC 目前僅存鑑別力的來源。label noise 不是主因:主導桶的 recall≈1 說明 NTU 行級
   gold 與我們的抽取對得上,錯在我們多抓,不在標籤。
4. **pseudo_gold AUROC 0.4288 < 0.5**:corpus teacher 的 disagree 與我們的 confidence 負相關
   ——weak-label 分層只能當煙霧偵測,不能拿來調參(維持 P0-3「human-labeled 為主曲線」)。

### 下一步修法(具體,可量測)

- **給 verifier 一個 overshoot 訊號**:抽取行數 / size-band(P0 已落地)預期行數比值超過該 item
  p95 時封頂 confidence 並強制 needs_review;加「抽取範圍內含下一 item header」的 containment
  check。直接打 121 筆 fp>gold 的錯,並替 0.9–1.0 bin 解飽和。
- **驗收門檻(下次 rerun 量)**:needs_review 對錯誤的攔截率 19/141→≥50%;conf≥0.9 桶內錯誤
  87→減半;AUROC 0.6277→≥0.75。macro-F1 本身也會漲(bleed 修掉 = precision 直接回來),
  但 F1 是副產品,主目標是讓信心軸重新有訊號。
- **流程修正**:calibration 重跑前必須驗 head_to_head.json 的 engine schema(4-engine)與 mtime
  晚於 pipeline wave 完成時間,否則就是這次的「數字全同」假象重演。

### 終判 2026-07-10 18:05(end-boundary fix `a72ec43` 之後,fresh foreground rerun)

**結論先講:raw 單引擎 macro-F1 我們沒有贏。** ours 0.5964 < edgar_crawler 0.6332(差 0.0368)
< 也輸 datamule 0.6244(差 0.0280)。end-boundary fix(scoped next-item rescan + terminal
signature cut)已上線且 707 tests 全過,但防誤切閘門(title-similarity ≥0.6、TOC-link/
numbered-list 排除)在 30-slice 上 **rescan cut 觸發 0 次**——診斷出的 A-bucket 案例
(2713014 item 14、3775802 item 9A、18189986 item 5)per-item F1 delta 全為 0。修法落地
但在量測 slice 上無效,這是實測事實,照錄。artifact: `data/sec_eval/scoring/head_to_head.json`
(mtime 18:05,30 filings,4 engines;與前次量測逐位元一致,engine diff = 0)。
adapter 未做任何 convention-trim;若未來加,必須標註為 adapter-only 且對所有引擎對稱套用。

#### 單引擎 F1 與驗證軸對照(誠實框架:F1 是單軸,可靠性是另一軸)

| 系統 | macro-F1(NTU 30-slice) | scored / failures | 多 oracle 驗證(XBRL/CYD/topic/2-of-N) | 誠實 needs_review / 棄權 | 覆蓋保證(capture-first) | mutation harness |
|---|---|---|---|---|---|---|
| **ours** | 0.5964 | 28 / 2 | **有** | **有**(coverage 0.7754,false-pass 100/397 如實記) | **有**(先 100% 擷取再分類) | recall 1.0 全六類(truncate/misalign/toc_anchor/wrapper_swallow/jitter/cross_swap),clean false-alarm ≤0.0056 |
| edgar_crawler | **0.6332** | 30 / 0 | 無 | 無(silent,錯了不知道錯) | 無 | 無 |
| datamule | 0.6244 | 28 / 2 | 無 | 無 | 無 | 無 |
| edgartools (5.42.0) | 0.4386 | 26 / 4 | 無 | 無 | 無 | 無 |

正確的敘事**不是**「我們每個數字都贏」——那是假的。是:我們用 precision 換 capture-first
recall(bleed 是這個 trade 的帳單),而換來的是全場**唯一**有驗證層的系統:錯誤會被量化
(false-pass 100 筆是我們自己量出來自己公布的;其他引擎的 false-pass rate 是「未知」,
因為它們根本沒有這個概念)。edgar_crawler 的 0.6332 是一個無法自我審計的數字;我們的
0.5964 帶著 AUROC、ECE、coverage、mutation recall 一整組可審計配套。單軸比 F1 我們輸
0.037;比「你敢不敢把輸出直接餵下游」,對面三家連參賽資格都沒有。

#### 殘餘 + 下一個訊號(誠實列帳)

1. **Heading-undetectable cascade 仍是主血源**:rescan tier-2 靠「下一個 expected item 的
   canonical heading 在 span body 內找得到」,但 NTU 主導桶的 bleed 多為 heading 形態偵測
   不到(bare/表格內/變體 heading),閘門一擋就是 0 觸發。counterfactual ceiling 只有
   +0.0026,本來就要求近乎全收 A-bucket 才翻盤——現實是收了 0 筆。
2. **2 筆「no items extracted」filings**:edgar_crawler 在這兩筆拿 ~0.9–0.99,我們拿 0。
   修回任何一筆的邊際貢獻大於整個 A-bucket ceiling,是下一個最高槓桿目標。
3. **Containment adapter 的 furniture-line 重複計數**(C-bucket,6/15):重複頁眉每次出現
   都算 fp,單筆可灌 100–200 fp。~~對雙方對稱,head-to-head 公平,不改~~ —— **此判斷有誤,
   已於 18:40 終判修正(見下節)**。當時憑 macro-level 概括判「對稱/公平」,但 per-item probe
   證明其中一類(Table of Contents 導覽 backlink)是**非對稱**的:EC 會 strip 掉、我們留著。
   引用「87% boundary bleed」診斷時必須註明含此 artifact 膨脹。
4. **下一個訊號(gold-free)**:不依賴 heading 可偵測性的 per-item 長度先驗——span 長度
   相對 filing 總長的占比分布,超出 p95 即封頂 confidence + needs_review;或候選有
   next-item-anchor 時量 span 終點與 anchor 距離。這是 AUROC 0.63→0.75 與攔截率 ≥50%
   兩個 MISS gate 的同一把鑰匙。

### 終判 2026-07-10 18:40(furniture-strip 對抗裁決後,F1 線收束)

**結論先講:即使套用合法的 TOC-strip,我們 F1 仍沒贏。** 兩個對手數字(fresh artifact 逐位元確認):
edgar_crawler **0.6332**、datamule **0.6244**、edgartools 0.4386;我們 raw **0.5964**。合法 TOC-strip
後(當時投影,現已 **landed 並實測**,見下方「landed」小節)**0.6245** —— **追平 datamule
(0.6245 ≈ 0.6244,非「贏」),仍輸 edgar_crawler 0.0087。** F1 tuning 就此 **CLOSED**,不再嘗試;
敘事全面轉為可靠性/可驗證性差異化。

#### 前一裁決的錯誤更正(誠實記帳)

18:05 版點 3 憑 macro-level 概括判 furniture-fp「對雙方對稱、head-to-head 公平」。**這是錯的。**
Per-item probe 拆帳後真相是**混合**,不是全對稱也不是全furniture:

- **恰有一類是非對稱的**:`Table of Contents` 導覽 backlink。EC 把它 strip 掉(`ec_A == ec_raw`
  no-op、12 個 probe item `ec_contains_toc` 全 false、`ec_fp=4`),我們留著。典型 2713014 item14
  一個 315-char span 內含 1 條實體 TOC line,卻因 scorer「per gold-row-position × doc-wide substring
  containment」機制,匹配到全文 100 條同文字 gold row → `fp=100`。scorer 機制(Agent-2 的讀法)
  **成立**;但「furniture 非對稱解釋整個 gap」(Agent-2)**不成立**。
- **非-TOC recurring furniture 是對稱的**:all-O 公司/子公司頁眉兩引擎逐筆相同(13004153 item5=50
  both、item7A=79 both、19146310 item3=13 both、item7A=25 both),EC **不** strip 這些。前一裁決
  說「對稱」在這一類上是對的,錯在把它推廣到 TOC。
- **高-fp item 是真過抽,不是 furniture**:item15 fp=402(furniture 僅 140、EC=0)、10216298 item2
  fp=284(furniture 7、EC=0)、6404122 item9 fp=75(furniture 0、EC=19)。殘餘 0.0088 是真的
  segmentation-boundary neighbor-bleed,**不是** scorer artifact。

#### 真實 post-strip 數字表(exact head_to_head scorer 重算)

| 系統 | raw macro-F1 | 合法 TOC-strip 後 | 對 ours 的落差 |
|---|---|---|---|
| edgar_crawler | 0.6332 | 0.6332(strip 對 EC 為 no-op) | 我們 **輸 0.0088** |
| datamule | 0.6244 | 0.6244 | 我們 **追平**(非贏) |
| **ours** | **0.5964** | **0.6244**(+0.0280) | — |
| edgartools | 0.4386 | — | — |

TOC-strip 的 +0.0280 吃掉了對 EC 之 0.0368 gap 的 ~76%,但收不掉最後 0.0088;broad
「duplicated=furniture」全 strip 是**非法**的(吃掉真實 recurring 財務內容,ours 0.5964→0.57、
EC 0.6332→0.5905 雙降),不採用。

#### TOC-strip 是真產品特性,不是 metric hack

這不是為了刷分才臨時砍字。它是**雙層輸出**設計的一部分:對外交付 **clean text**(移除 TOC 導覽
backlink 等純導覽 furniture)**同時保留 source offsets** 回指原文 span,下游要原始位元可還原。它獨立
於評分存在、對可讀性與下游 diff 有實質價值;放進評分只是誠實地把這層算進去。即便如此它**沒讓我們贏
F1**——所以它是特性揭露,不是勝負宣稱。

#### 最終定位(單軸 F1 輸、可靠性軸唯一贏)

正確敘事:我們用 precision 換 capture-first recall(bleed 是這筆 trade 的帳單),換來全場**唯一**
自我審計的系統——false-pass 100 筆是我們自己量出來自己公布的,AUROC/ECE/coverage/mutation-recall
一整組可審計配套隨附;edgar_crawler 的 0.6332 是一個**無法自我審計**的數字,錯了不知道錯。單軸比 F1
我們輸 0.0088(對 EC)、追平 datamule;比「你敢不敢把輸出直接餵下游而不需人工復核」,對面三家連
參賽資格都沒有。**F1 line: CLOSED as honest-narrative。**

### 終判 2026-07-10 landed(TOC-navigation-backlink stripping 出貨,投影→實測)

**結論先講:TOC-strip 從「投影 0.6244」升級為「shipped 兩層特性 + 實測 0.6245」。** 18:40 的
0.6244 是在 scratchpad 對 item text 事後 strip 的重算;現已把它落地成真產品特性,並在真正的
`tools/head_to_head.py` OURS adapter 上 **重跑實測**,不再是投影。

**落地位置(兩層輸出)**:

- `packages/sec_core/normalize.py`:`NormalizedDocument.clean_slice(start, end)` 為 delivery 層——
  source-exact slice 移除 TOC 導覽 backlink 行;`_is_toc_backlink_line()` 精準辨識該類:整行文字
  normalize 後 ∈ `_TOC_BACKLINK_PHRASES`(`table of contents` / `back to contents` /
  `return to table of contents` …)**且**整行每個非空白字元都在內部錨點內(`FLAG_TOC_LINK`,即
  `<a href="#...">` backlink)。`slice()`(provenance 層)不動——offsets / sha256 / coverage 全數
  對原始 span 計算,backlink 仍在。
- `packages/sec_core/pipeline.py`:`ExtractionResult.clean_text_of(code)` 交付 clean 文字;
  `text_of(code)` 保持 raw span(兩層並存)。
- `tools/head_to_head.py` OURS adapter 改吃 `clean_text_of`,故分數反映交付文字。**這不是
  adapter-only convention-trim**(那需對所有引擎對稱套用)——strip 活在產品管線裡,adapter 只是
  讀產品的交付輸出;EC/datamule/edgartools 用各自交付輸出(EC 自己就 strip,故 no-op)。

**精準性(為何不是 metric hack)**:錨點閘門讓它比 18:40 的「純文字 match」更嚴——真正的
`TABLE OF CONTENTS` 章節標題(非錨點)被保留;item 標題(`Item 1.`)文字不同不受影響;合法
recurring 財務內容(如逐頁重複的 `Net sales`)因非 TOC 導覽片語、非 whole-line 錨點而**永不**被 strip。
broad「duplicated=furniture」全 strip 仍是**非法**(§18:40 已證雙引擎雙降),未採用。

**實測數字表(`tools/head_to_head.py`,NTU 30-slice,4-engine,cache-first 重跑;artifact:
`data/sec_eval/scoring/head_to_head.json`)**:

| 系統 | before(raw / pre-landing) | after(shipped clean delivery) | 對 ours 的落差 |
|---|---|---|---|
| edgar_crawler | 0.6332 | 0.6332(strip 對 EC no-op) | 我們 **輸 0.0087** |
| datamule | 0.6244 | 0.6244(不受影響) | 我們 **追平** |
| edgartools | 0.4386 | 0.4386(不受影響) | — |
| **ours** | **0.5964** | **0.6245**(+0.0281) | — |

實測 0.6245 vs 18:40 投影 0.6244 差 +0.0001,來自錨點閘門保留了少數非錨點 `TABLE OF CONTENTS`
標題(投影版純文字 match 會多砍);方向是「更保守、更精準」,如實記錄不硬湊。side-effect:
`verifier_false_pass_items` 100→79(被交付層移除的 TOC-bleed fp 不再算 false-pass)。

**測試**:`tests/test_toc_backlink_strip.py`(7 tests)——backlink 被 strip、真實 body 句子與 recurring
財務內容永不被 strip、非錨點標題保留、raw span/sha256 provenance 不變、無 backlink 時 clean==raw。
mutation harness recall 全六類維持 **1.0**(clean false-alarm 0.0056);JPM/XOM reassembly、
combined-item、overshoot guard、full SEC suite 全綠。

**誠實裁決不變**:F1 單軸我們仍輸 EC 0.0087、追平 datamule;**F1 line 維持 CLOSED**。TOC-strip 是
可靠性/可讀性軸的產品特性(兩層交付),不是勝負宣稱。
