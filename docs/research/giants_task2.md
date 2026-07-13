# Giants Research — Task 2 SEC 10-K Item Extraction 對照研究與 backlog
> 2026-07-13 自工作筆記濃縮;完整跑分紀錄與逐段敘事見 git history(`git log --follow docs/research/giants_task2.md`),canonical 數字以 `docs/eval_report.md` 為準。
> 六份「巨人 vs 本 repo(packages/sec_core)」逐項驗證的合併總結;所有 status 經實際 grep / 執行 regex / 讀碼驗證,非僅文獻比對。巨人:edgar-crawler(nlpaueb)、edgartools、sec-parser(alphanome-ai)、sec-api.io(商業)、EDGAR-CORPUS(資料集)、NTU itemseg(arXiv 2502.08875,外部 benchmark)。
> 第二波(2026-07-10,回應 §5 完整性批判):SRAF/Loughran-McDonald 10-X Parse、OpenEDGAR(LexPredict)、doc2dict、datamule(皆實際 clone 讀碼或實測 EDGAR index)+ 10-K405/10-KSB form-variant 普查。判定見 §1.5,引用見 §4,處理狀態見 §5。

## 1. 對照表:本 repo vs 各巨人(依評分維度)
評等:**優** / **平** / **劣**(對方有、本 repo 沒有)。
### 1.1 Format-variance robustness(格式變異穩健性)
| 巨人 | 對方做法 | 本 repo 現況 | 評等 |
|---|---|---|---|
| edgar-crawler | flat regex + 字距修復('I T E M 1');'Item No. 1' 仍是 open issue #37 | streaming char-flag normalizer(normalize.py)+ 4 detector(strict/loose regex、dom_heading、visual_layout);mid-word `<span>` 拆字 by construction 免疫;'Item No. 1'/roman 同樣不匹配 | 平(backlog 後轉優) |
| edgartools | anchor/TOC 主路徑 + body-scan fallback、'<8 items → 換策略' 閘 | 主路徑即 body-scan;pipeline.py:74-77 已有 <8 → scan_bare_index 升級閘;cross_ref.py 處理 Intel/Citi/GE index 類 | 優 |
| sec-parser | inline-CSS style-fingerprint 辨識 heading | 只有 tag-level flags;`<span style="font-weight:700">` 全盲;CSS margin-as-newline 也缺 | 劣(P1) |
| sec-api.io | 自承 Citi Item 7、GE Item 1、Intel 為其 failure;pre-2002 不支援 | 同名 filer 已修復並有 fixture(FG-SEC-005);pre-2001 誠實標 unsupported | 優 |
| EDGAR-CORPUS | remove_tables=True 的 regex 切分,1993+ 全覆蓋 | 保留 table 內文、offset+sha256 source-exact;pre-2001 SGML 不支援 | 平 |
### 1.2 Self-verification without ground truth(無標註自我驗證)
| 巨人 | 對方做法 | 本 repo 現況 | 評等 |
|---|---|---|---|
| edgartools | 54-filing fixture corpus CI 重測;flag 後照常回傳、caller 不看 warning | partition invariants(coverage.py)、7 值 typed ItemStatus、needs_review 一級欄位、3-engine triangulation(240 agree / 12 disagree)、8 組 named confidence components | 優 |
| sec-parser | per-element ProcessingLog 審計鏈 | BoundaryEvidence + ConfidenceComponent + toc_reasons 機器可讀;缺純分數落選候選 disposition(P1-7) | 平偏優 |
| sec-api.io | 'processing' 空字串反模式(issue #34:partial text + HTTP 200) | typed absent/failed 區分是 design center(scoring.py tri-state、IBR typed status) | 優 |
| NTU itemseg | 3,737 份人工標註 benchmark(無公開 leaderboard,§4 小節) | 自家 gold 僅 5 份 self-frozen(F1 1.0 無誤差訊號可校準)→ P0-2/P0-3 | 劣(P0) |
### 1.3 Edge cases(地雷覆蓋)
| 巨人 | 對方做法 | 本 repo 現況 | 評等 |
|---|---|---|---|
| edgar-crawler | issue #35 combined items 兩邊皆空、#37 'Item No. 1' 未修 | 'Items 1 and 2' 顯式 combined 端到端建模(覆蓋 #35 案例);缺 singular-header 隱含合併推斷(P0-9)、'Item No. 1'/roman(P1-1) | 優(2 缺口在 backlog) |
| edgartools | items 10-16 rescue path bug(_ITEM_TITLE_PATTERNS 止於 9C;**pinned @ 5.42.0**,升版需重驗)、terminal EOF-runoff | SIGNATURES body-scan 終界 + detect_appended_section_cut(XOM 311,785→33 字);12 disagree 中 8 個是 item 16 → P0-5 down-weight | 優 |
| sec-api.io | 自承 STRATS/CorTS trust(MD&A 合法缺席)為難例 | 語彙支援 9C/16/1C;corpus 無 trust 10-K、無 legitimately-absent 測試(P0-6) | 平(P0 fixture) |
| NTU 論文 | 錯標 heading(9A 標成 14)、<100 行 stub、7A 巢狀於 7 | landmine L1-L10 + 15 tests;上述三類無 fixture(P0-6) | 平(P0 fixture) |
### 1.4 Cost discipline(成本紀律)
| 巨人 | 對方做法 | 本 repo 現況 | 評等 |
|---|---|---|---|
| doc2dict/datamule 路線 | deterministic style-aware parser first、LLM 僅 invariant failure | 同構且已文件化;LLM tier 未 wired/量測($/filing 是估計)→ P0-12 | 平(P0-12 補量測) |
| sec-api.io | $49-599/mo 商業 API | 全免費;其 free tier(100 lifetime calls)可當外部仲裁票(P0-7b) | 優 |
| EDGAR-CORPUS | 一次性離線 corpus,零邊際成本 | join 當 weak-label 額外一票,批次成本近零(P0-1) | 平 |
### 1.5 第二波巨人(2026-07-10 調研,誠實判定)
| 巨人 | 有無 item segmentation | 維護狀態(pinned) | 判定 |
|---|---|---|---|
| **SRAF / Loughran-McDonald 10-X Parse**(Notre Dame) | **無**:Stage One parse 是整份清洗,衍生資料集皆 whole-filing 粒度;公開 `Generic_Parser.py`(2016/06 鏡像實讀)無 item 邏輯 | 資料持續更新(Summaries 至 2025);血統與 edgar-crawler/edgartools 完全獨立 | **不是 boundary teacher,不能當 P0-7 票**;實際價值:LM_10X_Summaries 對帳 oracle、sum-of-items 不變式(P0-11)、10-X Header Data(140 萬筆,1993–2025)master index、清洗規範參照;>10% numeric 表格被刪 → Item 8 文字殘缺,不可當內容 gold |
| **OpenEDGAR**(LexPredict) | **無**:`parsers/edgar.py`(398 行全讀)僅 SGML 切分 + Tika 全文抽取,grep item/section 零命中(paper arXiv 1806.04973 自述同) | dead:最後實質 commit `1d1b8bc` 2019-05-15 | **not applicable**;僅 pre-2001 SGML/uudecode fallback 鏈(edgar.py:55-88, 328-383)可回頭參考 |
| **doc2dict**(john-friedman) | 引擎層:regex 主裁判 + bold/font-size 樣式 fallback 分層(`convert_instructions_to_dict.py:229-271`) | 活躍:commit `01e6d0c` 2026-02-02;README 自承 early stage | **borrow techniques**:樣式佐證 header(P1-3 參照)、repetitive-text 頁首尾去除、TOC 免疫;弱點:regex 命中即給 level、不要求樣式佐證 |
| **datamule**(john-friedman;後端=doc2dict) | **有,一級公民**:per-form mapping(~40 form),`document.py:291` `parse()` → `:539` `get_section('item1a')`;pre-2001 .txt 有路徑 | 非常活躍:commit `122fc54` 2026-06-25 | **usable as triangulation vote**(P0-7c);**無公開 accuracy benchmark——當票不當 gold** |

## 2. Prioritized backlog(已去重;僅列 status = missing / partial)
指定必須處理的四個 known gaps 對應:verifier calibration curve → **P0-3**;runtime verifier mutation harness → **P0-4**;golden-set expansion via multi-teacher pseudo-gold → **P0-1**;wrapper reassembly → **P0-10**。
### P0
| # | What(one line) | Status / 落點 |
|---|---|---|
| P0-1 | Multi-teacher pseudo-gold 擴充 golden set:EDGAR-CORPUS join + era-stratified 抽樣 + 3-way vote + lineage discount(corpus 與 crawler 同血統折一票)+ table-strip 比對視圖 + §2.1 form-schema 對映;供 P0-3 時投票排除 edgartools(teacher/引擎雙重身分) | 部分落地:tools/mine_pseudo_gold.py + data/sec_eval/pseudo_gold/pseudo_gold_candidates.json |
| P0-2 | NTU itemseg 外部 benchmark(3,737 份標註 10-K,arXiv 2502.08875)+ 交付物 A(head-to-head per-item F1 對照表)+ 交付物 B(verifier false-pass rate on external benchmark) | 已落地:tools/fetch_ntu_itemseg.py、tools/head_to_head.py;無公開 leaderboard(§4 NTU 小節);30-slice 數字見終判各節與 docs/eval_report.md |
| P0-3 | Verifier calibration curve:per-item confidence vs 正確性 AUROC/ECE/risk-coverage;human-labeled subset 為主曲線、pseudo-gold 僅輔助;顯式標 verifier false-pass rate | 已落地:tools/calibrate_sec_confidence.py + data/sec_eval/calibration/calibration.json;gate 進度見 Gate rerun 各節 |
| P0-4 | Runtime verifier mutation harness:注入截斷/錯位/TOC-anchored/wrapper-swallow + 開放類 mutation;硬門檻 per-mutation-class detection recall ≥0.95、clean false-alarm ≤0.05 | 已落地:tests/test_verifier_mutations.py;recall 六類全 1.0、clean false-alarm ≤0.0056 |
| P0-5 | Triangulation engine-blind-class down-weighting:item 10-16 disagree 輸出 engine_suspect 而非扣分(12 disagree 中 8 個實為 edgartools 5.42.0 rescue bug,FG-SEC-006 已歸因) | 開放;third_engine.py:98-158 / :181-193 |
| P0-6 | Adversarial fixture suite L11+:trust 10-K(MD&A 合法缺席期望)、'Item No. 1'、錯標 heading(至少 needs_review)、<100 行 stub、7A-in-7 | 開放;tests/test_landmines.py + data/sec_eval/fixtures/ |
| P0-7 | 第四/五仲裁票 + 2-of-N 投票:(a) vendor edgar-crawler regex core;(b) sec-api.io free-tier 仲裁協定(100 lifetime calls,回應立即 cache);(c) datamule(`122fc54`)第五票;明確排除 SRAF(§1.5) | 部分落地:edgar_crawler/datamule 已為 head-to-head 參賽 engine;triangulation 2-of-N 開放 |
| P0-8 | CI golden-drift harness + typed known-bad manifest:raw HTML 凍結 fixtures、FG-SEC-001..009 machine-readable、pytest 對凍結 gold 重測 | 部分落地:data/sec_eval/fixtures/manifest.json |
| P0-9 | Combined-item 推斷 fallback:singular header 含缺項 canonical title → 標 combined 而非靜默 missing | 部分落地(status partial,見 tests/test_overshoot_guard.py);boundary.py resolve_items |
| P0-10 | Wrapper body reassembly(JPM/XOM class)+ cross_ref.py stale docstring 修正 | ✅ 2026-07-11 收尾:CYD 11 agree / 0 disagree(見「Wrapper section-anchor 收尾」節) |
| P0-11 | Per-(form,item) 經驗 size band 硬性 guardrail + SRAF sum-of-items 全檔上界不變式(SRAF 為 whole-filing 粒度,不能供 per-item band) | 部分落地:sec_core/size_bands.py(見 §外部量測 rerun);SRAF 不變式開放 |
| P0-12 | Cost discipline 落地量測:LLM adjudicator wire 一次 + 實測 $/裁決 + per-filing 成本欄(sweep_metrics.py 現只聚合 latency_ms;cost_latency_report.md:42 自承估計無量測) | 開放(自 P2-6 升級,§5.2) |
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
- P1-1 heading 變體:'Item No. 1'(edgar-crawler open issue #37)+ roman numeral alternates — headings.py。
- P1-2 CSS margin-as-line-break 補 newline(heading 黏上前行 → line-anchored regex 靜默失敗)— normalize.py。
- P1-3 inline-CSS style fingerprint FLAG + 已確認標題 style consensus 裁決模糊候選 — normalize.py + boundary.py。
- P1-4 Gold 保護:freeze overwrite guard + κ-gated 人工標註協定(double-annotate 10%,Cohen's κ≥0.8)— tools/freeze_offset_gold.py。
- P1-5 Runtime era/reliability tier(classify_format 移入 sec_core,ExtractionResult 帶 era 欄位)— pipeline.py。
- P1-6 Near-miss bucket(off by ≤N chars 分箱;可選 Pk/WindowDiff)— scoring.py。
- P1-7 落選候選 disposition evidence(純分數輸家無記錄)— boundary.py:78-79。
- P1-8 Era-conditional item-emptiness prior(gated on P0-1;規則初稿 §2.1 第 5 點;SRAF 不能供 per-item)— items.py + boundary.py。
- P1-9 Early-HTML era(2001-2010)真實 filing 凍結 gold 進 pytest(現有 5 份 offset-gold 全是 2025-26 iXBRL)。
- P1-10 免疫證據 fixtures:no-Part-heading、accented-title synthetic(§3.1 caveat 同綁)。
- P1-11 文件宣稱補齊:sec-api 缺 9C/16、Citi/GE typed 修復 + fixture、issue #34 對比 — docs/prior_art.md + README。
- P1-12 Longest-span-after-previous-end 第二選擇函數,與 score-rule 不一致時 flag hard case — boundary.py。
### P2
- P2-1 Case-sensitive-first 兩段式 heading match(意圖已被 line-anchoring + is_uppercase 弱機制覆蓋)。
- P2-2 Letter-spaced 修復('I T E M 1';病灶集中 pre-2001,現行宣告 unsupported)。
- P2-3 PART divider 狀態機(本 repo 以 item code 唯一鍵,該 bug class 主後果結構性不成立)。
- P2-4 ##TABLE_START/END sentinel 僅放 export/比對層,**絕不進 normalize.py**(會破壞 offset+sha256 source-exact 不變量)。
- P2-5 detect_agent(Workiva/DFIN/Toppan)移入 sec_core 當 metadata 欄位。
- P2-6 ~~LLM tier 量測~~ 已升級為 **P0-12**(§5.2)。
- P2-7 Content-based item 重新指派(研究性;論文顯示所有自動方法在此類全滅,不建議近期做)。

## 3. Per-criterion 定位(依評分維度)
### 3.1 Format-variance robustness
對照基準:sec-parser 的 style-fingerprint heading 偵測 + edgartools 的 multi-strategy fallback。本 repo:streaming char-flag normalizer 使 mid-word `<span>` 拆字 by construction 不存在(架構論證;直接測試佐證尚缺,與 P1-10 同綁,fixture 落地前此句不得單獨外引);4-detector body-scan 主路徑;Intel/Citi/GE cross-reference-index typed 修復 + 真實 accession fixture(Citi Item 7 / GE Item 1 為 sec-api 官方文件自承 failure)。缺口:P1-1/P1-2/P1-3;P0-10 已收尾。
### 3.2 Self-verification without ground truth
對照基準:edgartools 54-fixture CI 重測(但 flag 後照常回傳、caller 不看 warning)。本 repo:multi-oracle triangulation(240 agree / 12 disagree 全路由 needs_review)、capture-first coverage(每 char 屬於恰一 block,「先全抓再分類」)、offset+sha256 source-exact span(LLM 永不生成 filing 文字,AdjudicatorDecision 無 evidence quote 即拒絕)、7 值 typed status(absent≠failed,對照 sec-api issue #34)、honest failure gallery(FG-SEC-001..009)。配套:P0-3 calibration、P0-4 mutation harness、P0-5/P0-7/P0-11——在逐項驗證過的十個公開實作/資料源中,無一同時校準並 mutation-test 驗證器本身(範圍限定於已驗證清單)。
### 3.3 Edge cases
對照基準:sec-api 自承難例清單 + NTU 論文錯誤分類法(知道坑在哪,多數沒修)。本 repo:landmine L1-L10 + 15 tests;combined 'Items 1 and 2' 端到端建模(覆蓋 edgar-crawler #35);IBR typed status + Item 8 stub 指路;SIGNATURES body-scan + appended-section cut(XOM Item 16 從 311,785 字修到 33 字);TOC 5-signal 加權拒絕。缺口:P0-6、P0-9、P1-10。
### 3.4 Cost discipline
對照基準:doc2dict 路線的 deterministic-first 分層。本 repo:主管線 deterministic $0,LLM adjudicator schema-gated 且從未需要啟動(誠實記於 cost_latency_report.md);eval 用 era×agent 分層抽樣。缺口:P0-12(實測 $/裁決 + per-filing 成本欄)、P0-7b(sec-api 免費仲裁票)、P0-1(corpus join 近零邊際成本)。

## 4. 引用來源與使用限制
| 來源 | 用途 | 限制 / attribution |
|---|---|---|
| nlpaueb/edgar-crawler(GitHub) | heading 變體、字距修復、issues #35/#37 對照與 fixture 來源;P0-7a 擬 vendor regex core | **Vendoring 前必查 LICENSE 並保留原始授權與版權聲明**;授權不相容(GPL 系)則 subprocess 隔離或重實作;README 要求引用 Loukas et al. 2021 |
| EDGAR-CORPUS(HF: eloukas/edgar-corpus;Loukas et al., ECONLP 2021) | P0-1 pseudo-gold corpus join | **標籤是 edgar-crawler 機器產生的 weak labels——只當額外 engine vote,絕不可當 gold**;與 crawler 同血統折一票(lineage discount);remove_tables=True 需 table-strip 視圖;組成 = 10-K∪10-K405∪10-KT、無 /A 無 KSB(config @`058a121a41`,下載邏輯 @`5823367ae1` L45/L295);引用其論文 |
| dgunning/edgartools(GitHub, MIT) | 既有第三引擎(**5.42.0**);items 10-16 rescue bug / EOF-runoff 為 P0-5 依據(pinned @ 5.42.0,升版重驗) | 保留 MIT 聲明(已列 docs/ATTRIBUTION.md 者免重複) |
| **SRAF / Loughran-McDonald**(sraf.nd.edu:Cleaned 10-X Files、LM_10X_Summaries、10-X Header Data、Stage One Parsing Documentation) | cleaning norms + 血統獨立 master index(非 boundary teacher,§1.5):P0-11 不變式、召回普查、清洗規範參照 | **"as is … for non-commercial purposes"**,商用需洽作者;無正式 license 文本 → 資料不入 repo,fetch-on-demand;引用 Loughran & McDonald (2011, JF) / (2016, JAR);>10% numeric 表格刪除 → Item 8 文字殘缺,不可當內容 gold |
| **LexPredict/openedgar**(GitHub;arXiv 1806.04973) | gap-scan 完成:not applicable(§1.5);僅 pre-2001 SGML/uudecode fallback 鏈可回頭參考 | MIT(clone 內 LICENSE 實讀,LexPredict 2018);想法層,無 vendor 計畫 |
| **john-friedman/doc2dict**(GitHub,pinned @ `01e6d0c` 2026-02-02) | P1-2/P1-3 技術參照(僅借想法,未 vendor) | MIT;想法層引用註明出處;README 自承 early stage |
| **john-friedman/datamule-python**(GitHub,pinned @ `122fc54` 2026-06-25) | P0-7c 第五仲裁票;P0-2 head-to-head 參賽 engine | MIT;**無公開 accuracy benchmark——當票不當 gold**;解析品質 = doc2dict 品質 |
| **SEC full-index form.idx 實測(1993–2009)+ 樣本 filings**(SanDisk 10-K405 `0001000180-99-000003`、Nicholas Financial 10KSB `0001000045-97-000004`、Broadway Financial 10KSB `0001193125-05-065205`、Paramount 10-K/A `0000950120-99-000136`)+ SEC Releases 33-8230/33-8183/33-8876/33-8591 | §2.1 form-type→schema 規格的一手證據 | 公開資料;計數腳本 tools/count_forms.py |
| alphanome-ai/sec-parser(GitHub) | style-fingerprint、ProcessingLog、eval harness 設計參照(僅取想法,未 vendor) | 想法層引用,註明出處即可 |
| sec-api.io Extractor API + janlukasschroeder/sec-api-python | P0-7b 外部仲裁票;其文件自承難例(Citi/GE/Intel/STRATS/pre-2002)與 issue #34 為對照證據 | 商業 ToS:cached responses 僅供內部 eval,**不可再散布原文 payload**;free tier 100 lifetime calls,回應必須立即 cache |
| NTU itemseg dataset(arXiv 2502.08875) | P0-2 外部 benchmark | research-only tier,fetch-on-demand 不入庫;授權判定與 adapter 度量見下方小節;引用論文 |
| 本 repo 既有文件 | docs/prior_art.md、docs/failure_gallery.md(FG-SEC-001..009)、docs/eval_report.md、docs/cost_latency_report.md、docs/ATTRIBUTION.md | 新增引用一律同步 ATTRIBUTION.md |

**SEC EDGAR 本身**:原始 filings 為公開資料;快取 raw HTML 進 fixtures(P0-8)無授權問題,但需遵守 SEC fair-access rate limit(既有 fetch 工具已處理)。
### NTU itemseg dataset:授權判定與 adapter 度量(原 external_benchmark_spike.md)
- **授權判定(three-tier rule,2026-07-10 spike 實測)**:論文 arXiv 頁 CC BY 4.0(僅涵蓋論文文字);程式碼 repo `hsinmin/itemseg` README 明載 **CC BY-NC 4.0**;dataset 壓縮檔(`itemseg10kdata.7z`,3,741 entries 全列過)**無任何 LICENSE/README**,期刊版 Data Availability 又寫 "upon request"。訊號矛盾、取最嚴格解讀 → **tier「unclear/research-only」→ download-script route**:`tools/fetch_ntu_itemseg.py` fetch-on-demand(sha256 凍結 `769bc7da89cdd0c53f8182f74d294be23839607ad9e75735767be445d1efd727`,重跑必驗)至 gitignored `data/raw_filings/external/ntu_itemseg/`(位於 `data/raw_filings/` 之下,結構上不可能被 commit);**不 vendor、不節錄 fixture**(逐行內容即標註資產本體);任何使用其數字的文件引 arXiv 2502.08875。
- **無公開 leaderboard(backlog 原文更正)**:GitHub repo、paperswithcode、論文正文皆無;外部對標的形狀是「同一 test fold 上與論文自報數字並列」,不是排行榜提交。
- **Containment-adapter 度量定義(tools/head_to_head.py)**:每 engine 統一介面 `item_code -> text`;NTU 每條非瑣碎 gold line(alnum-normalized 後 ≥8 字元)測其是否為某 item 正規化全文的 substring → per-item tp/fn/fp 與 P/R/F1;macro-F1 只平均「有 gold lines 的 item」(fp-only item 列出但不進 macro);正規化 = lowercase + 只留 alnum(對 inscriptis/本 repo normalizer/edgartools renderer 三種渲染差異穩健)。
- **下界、不可與 BIO-F1 互比(誠實記錄)**:論文自報數字(BERT4ItemSeg core-item macro-F1 0.9825、GPT4ItemSeg 0.9567)是 **per-line BIO 分類 F1** 且為監督式訓練;containment adapter 是把 span 輸出投影回行的**下界**(engine 內文任何渲染丟字都算 fn)。兩組數字同表並列必帶此註;引擎間比較只在同一 adapter 欄位間成立,不可跨到論文欄位(另見「NTU benchmark 軸差異聲明」節)。

正式 30-slice 跑分見本文件終判各節與 `docs/eval_report.md`(canonical)。

## 5. 完整性批判
> Completeness critic pass(2026-07-10),針對完整性目標的具體缺漏;✅ = 已落地,⏳ = 開放。
### 5.1 漏掉的巨人 / 資料集
- **SRAF / Loughran-McDonald**:✅ 調查完成(§1.5)——無 item segmentation,不能當 P0-7 票或 teacher,whole-filing 粒度不能餵 per-item band/emptiness prior;落地為 P0-11 不變式 + master index + 清洗規範參照;入 §4(non-commercial 註記)。
- **OpenEDGAR**:✅ gap-scan 完成(§1.5)——無 item 邏輯、dead → not applicable;入 §4;⏳ prior_art.md 未同步。
- **doc2dict/datamule**:✅ 逐項驗證完成(clone 讀碼,§1.5)——datamule → P0-7c 第五票 + head-to-head 參賽;doc2dict 技術借鑑(P1-2/P1-3 參照);皆入 §4 並 pin commit。
- **10-K405/10-KSB form variants**:✅ 完整規格落地(§2.1,實測 form.idx 1993–2009 + 4 份真實樣本):corpus 組成證實為 10-K∪10-K405∪10-KT;g1–g7 guardrails 折入 P0-1。
### 5.2 評分維度缺 P0
- Cost discipline 無真 P0:✅ 已落地為 **P0-12**(現況已驗證:sweep_metrics.py 只聚合 latency_ms、cost_latency_report.md:42 自承估計無量測);P2-6 註銷併入。其餘三維度皆有 ≥2 個 P0,無缺口。
### 5.3 Who-judges-the-judge:未完全終結
1. 校準循環未斷:✅ 修法入 P0-1(pseudo-gold 投票排除 edgartools 或分層)與 P0-3(human-labeled subset 為主曲線、pseudo-gold 僅輔助);真正終點是人工標籤。實跑見 Gate rerun 各節。
2. 既有 mutation test 只覆蓋 scorer,runtime 驗證訊號本身(confidence/needs_review/triangulation/topic_check/size band)未被 mutation 測試——「驗證器自己被驗證」缺口:✅ P0-4 harness 已落地。
3. 無量化門檻的 harness 只是存在性證明、不可引用:✅ P0-4 已加硬門檻(per-class recall ≥0.95、clean false-alarm ≤0.05)+ 開放類 mutation(±N% 邊界抖動、跨 item 換文)。
4. 閉環:✅「verifier false-pass rate on external benchmark」為 P0-2 交付物 B;P0-3 risk-coverage 曲線顯式標出。
### 5.4 缺證據的宣稱
- §3.2 全稱否定「沒有任何公開實作做到」:✅ 改為「逐項驗證過的十個公開實作/資料源中無一做到」。
- P0-3「0.962 vs 0.666」:✅ 註明為 sweep2 數字;sweep3 pass mean 已漂移至 0.975(eval_report.md:91),校準以 sweep3 為準。
- P0-2「對照公開 leaderboard」:✅ spike 實查:無公開 leaderboard(§4 NTU 小節)。
- §3.1「mid-word 拆字 by construction 免疫」以事實陳述:✅ 已帶 caveat 並與 P1-10 同綁(fixture 落地前不得單獨外引)。
- 競品 bug 未 pin 對方版本:✅ 部分——edgartools @5.42.0、新巨人皆 pin commit(doc2dict `01e6d0c`、datamule `122fc54`、OpenEDGAR `1d1b8bc`、crawler config `058a121a41`/`5823367ae1`);⏳ crawler issues #35/#37 與 sec-parser 缺陷宣稱未 pin 對方 commit。
- sec-api「自承 failure」引註應與使用同時:⏳ URL/原文引註排在 P1-11,未提前。
### 5.5 缺席的直接對決
✅ 已落地為 P0-2 交付物 A(tools/head_to_head.py):edgar-crawler、edgartools(5.42.0)、datamule 跑在同一份 gold set,輸出 per-item F1 對照表;sec-parser 因無 end-to-end item extractor(heading 偵測層)不參賽,如實註記。實跑數字見終判各節。

## 外部量測 rerun 2026-07-10(post wave-2)
> 結論:overshoot guard(`60fe10f`)上線後 17:22–17:23 完成 4-engine 30-slice rerun(artifacts committed `4d3b3a5`),macro-F1/ECE/攔截拆帳全數由獨立腳本手工重算吻合;三個主 gate 全 MISS。
> 殘餘:123/141 boundary-bleed 主導桶對 guard 幾乎無感——containment 前提(下一 item heading 可被 detector 找到)在 NTU 多不成立(bare/變體/表格內 heading);在新訊號落地前,AUROC ≥0.75 與 ≥50% 攔截維持未達成,不得引用 0.63 為「可接受」。流程教訓:calibration 重跑前必驗 head_to_head schema(4-engine)與 mtime 配對,否則重演「數字全同」假象。Artifacts:`data/sec_eval/scoring/head_to_head.json`、`data/sec_eval/calibration/calibration.json`。
### 數字表(before = pre-wave 實測;after = post overshoot-guard rerun 實測)
| 指標 | 來源 | before(pre-wave) | after(post-fix) | 手工重算驗證 |
|---|---|---|---|---|
| macro-F1(ours, n=28) | head_to_head.json, NTU 30-slice | 0.5961 | **0.5964** | 0.5964 ✓(filings 逐筆平均) |
| macro-F1(edgartools, n=26) | 同上 | 0.4386 | 0.4386 | 0.4386 ✓ |
| macro-F1(edgar_crawler, n=30) | 同上(wave-2 新參賽) | — | 0.6332 | 0.6332 ✓ |
| macro-F1(datamule, n=28) | 同上(wave-2 新參賽) | — | 0.6244 | 0.6244 ✓ |
| AUROC(ntu_human_labeled, n=512) | calibration.json | 0.6277 | **0.6307** | binned 下界 0.5984 一致 ✓ |
| ECE(ntu_human_labeled) | 同上 | 0.1753 | 0.1762 | 0.1762 ✓(10-bin 重算, exact) |
| verifier false-pass rate | 同上(gate: conf≥0.6 ∧ ¬needs_review) | 0.2410(107/444) | **0.2519(100/397)** | 100/397=0.2519 ✓;coverage 0.7754 ✓ |
| AUROC(pseudo_gold_corpus_only, n=275) | calibration.json | 0.4288(比丟銅板差) | 0.4139 | —(aux,維持煙霧偵測定位) |
### 驗收門檻判定(§下一步修法設的 gate,誠實記帳)
| Gate | 目標 | after 實測 | 判定 |
|---|---|---|---|
| needs_review 錯誤攔截率 | 19/141 → **≥50%** | 29/141 = **20.6%** | **MISS**(+10 items,遠不及) |
| conf≥0.9 桶內錯誤 | 87 → **減半(≤44)** | **83** | **MISS**(−4) |
| AUROC(NTU) | 0.6277 → **≥0.75** | **0.6307** | **MISS**(+0.003) |
| macro-F1(副產品) | 上漲 | 0.5961 → 0.5964 | PASS(邊際) |

診斷(512 筆 raw data,非臆測):主導桶 boundary bleed 123/141(87%;121 筆 fp 行數 > gold,recall≈1、起點對、不知道停;徹底 miss 僅 18)——引用「87% boundary bleed」須註明含 TOC artifact 膨脹(18:40 更正);conf 飽和使 verifier 對主導桶全盲(87/141 錯落在 conf≥0.9,needs_review 僅攔 19/141);items 10–13 IBR 次要桶 40/141;pseudo_gold AUROC 0.4288 < 0.5 → weak-label 僅當煙霧偵測、不調參。下一步修法(overshoot 訊號、驗收 gate、mtime 配對流程)已依原文執行,結果見終判與 Gate rerun 各節。
### 終判 2026-07-10 18:05(end-boundary fix `3ba717b` 之後,fresh foreground rerun)
結論:**raw 單引擎 macro-F1 我們沒有贏**——ours 0.5964 < datamule 0.6244(差 0.0280)< edgar_crawler 0.6332(差 0.0368)。end-boundary fix 上線且 707 tests 全過,但 rescan cut 在 30-slice 觸發 0 次(A-bucket 案例 per-item delta 全 0)——修法落地但在量測 slice 上無效,實測事實照錄。adapter 未做任何 convention-trim。

| 系統 | macro-F1(NTU 30-slice) | scored / failures | 多 oracle 驗證(XBRL/CYD/topic/2-of-N) | 誠實 needs_review / 棄權 | 覆蓋保證(capture-first) | mutation harness |
|---|---|---|---|---|---|---|
| **ours** | 0.5964 | 28 / 2 | **有** | **有**(coverage 0.7754,false-pass 100/397 如實記) | **有**(先 100% 擷取再分類) | recall 1.0 全六類,clean false-alarm ≤0.0056 |
| edgar_crawler | **0.6332** | 30 / 0 | 無 | 無(silent) | 無 | 無 |
| datamule | 0.6244 | 28 / 2 | 無 | 無 | 無 | 無 |
| edgartools (5.42.0) | 0.4386 | 26 / 4 | 無 | 無 | 無 | 無 |

定位:以 precision 換 capture-first recall(bleed 是這筆 trade 的帳單),換得的是唯一附驗證層、可自我審計的輸出(false-pass 100 筆為自行量測公布;其他引擎的 false-pass rate 為未知);F1 單軸落後如實記。殘餘:heading-undetectable cascade 為主血源(counterfactual ceiling 僅 +0.0026);2 筆 no-items filings(EC 該兩筆 ~0.9–0.99)為最高槓桿;C-bucket furniture「對稱/公平」判斷有誤,已於 18:40 終判更正。Artifact:`data/sec_eval/scoring/head_to_head.json`(mtime 18:05,30 filings,4 engines)。
### 終判 2026-07-10 18:40(furniture-strip 對抗裁決後,F1 線收束)
結論:即使套用合法 TOC-strip,F1 仍未反超——post-strip 0.6244(投影,後經 landed 節實測)追平 datamule(0.6244,非「贏」),仍輸 edgar_crawler 0.0088;**F1 tuning 就此 CLOSED**,敘事轉可靠性/可驗證性差異化。
錯誤更正(誠實記帳):18:05 點 3 判 furniture-fp「對雙方對稱、公平」**是錯的**,per-item probe 拆帳為混合——`Table of Contents` 導覽 backlink 一類**非對稱**(EC strip 掉、我們留著;典型 2713014 item14 一個 315-char span 因 doc-wide substring containment 灌 fp=100);非-TOC recurring furniture(公司頁眉)兩引擎逐筆相同,對稱;高-fp item(item15 fp=402、10216298 item2 fp=284)是真過抽,非 scorer artifact——殘餘 0.0088 是真 boundary bleed。

| 系統 | raw macro-F1 | 合法 TOC-strip 後 | 對 ours 的落差 |
|---|---|---|---|
| edgar_crawler | 0.6332 | 0.6332(strip 對 EC 為 no-op) | 我們 **輸 0.0088** |
| datamule | 0.6244 | 0.6244 | 我們 **追平**(非贏) |
| **ours** | **0.5964** | **0.6244**(+0.0280) | — |
| edgartools | 0.4386 | — | — |

殘餘:broad「duplicated=furniture」全 strip 為**非法**——吃掉真實 recurring 財務內容,雙引擎雙降(ours 0.5964→0.57、EC 0.6332→0.5905),不採用(`prompts/rejected_prompts/2026-07-10-broad-furniture-strip-for-f1.md`);TOC-strip 為雙層輸出產品特性(clean text 交付 + source offsets 保留),獨立於評分存在,非 metric hack——且它沒讓 F1 反超,是特性揭露不是勝負宣稱。
### 終判 2026-07-10 landed(TOC-navigation-backlink stripping 出貨,投影→實測)
結論:TOC-strip 從投影升級為 shipped 兩層特性 + 實測——`normalize.py` `clean_slice()`(delivery 層;`_is_toc_backlink_line()` 要求整行 ∈ `_TOC_BACKLINK_PHRASES` 且整行非空白字元皆在 `FLAG_TOC_LINK` 錨點內)+ `pipeline.py` `clean_text_of()`;provenance 層 `slice()`/offsets/sha256/coverage 不動;head_to_head OURS adapter 改吃交付輸出(非 adapter-only trim;EC 自身就 strip,故對 EC no-op)。

| 系統 | before(raw / pre-landing) | after(shipped clean delivery) | 對 ours 的落差 |
|---|---|---|---|
| edgar_crawler | 0.6332 | 0.6332(strip 對 EC no-op) | 我們 **輸 0.0087** |
| datamule | 0.6244 | 0.6244(不受影響) | 我們 **追平** |
| edgartools | 0.4386 | 0.4386(不受影響) | — |
| **ours** | **0.5964** | **0.6245**(+0.0281) | — |

殘餘:實測 0.6245 vs 18:40 投影 0.6244 差 +0.0001——錨點閘門更保守(保留非錨點 `TABLE OF CONTENTS` 標題),如實記錄;真正章節標題、item 標題、recurring 財務內容永不被 strip,broad strip 維持非法不採用;side-effect `verifier_false_pass_items` 100→79;**F1 單軸仍輸 EC 0.0087、追平 datamule,F1 line 維持 CLOSED**。守門:`tests/test_toc_backlink_strip.py`(7 tests);mutation recall 六類維持 1.0(clean false-alarm 0.0056);JPM/XOM reassembly、combined-item、overshoot guard、full SEC suite 全綠。Artifact:`data/sec_eval/scoring/head_to_head.json`。
### NTU benchmark 軸差異聲明(2026-07-11,防誤讀)
NTU ItemSeg 論文(arXiv 2502.08875)報的 **BERT4ItemSeg macro-F1 0.9825** 量的是 **per-line BIO 邊界分段分類**,且為**監督式訓練**(見 §4「NTU itemseg dataset:授權判定與 adapter 度量」小節);本文件所有 head-to-head 數字量的是 **item 全文抽取 F1**(30-filing slice、**zero-training**,未在 NTU gold 上調任何參數)。兩者不同軸、不可直接比較——0.9825 **不是** 0.62x 的同軸天花板,並排比大小是誤讀。NTU gold 在本 repo 的角色是**外部弱老師(head-to-head 的一票),不是 gold 真值**(§4 引用限制;MEMORY 引用原則:外部老師當弱老師/一票,不當 gold)。
### Gate rerun 2026-07-11(gold-free per-item length prior 落地,§gate 表後續)
結論:三個主 gate 仍 MISS——訊號有真實貢獻(攔截 +9.4pt、conf≥0.9 桶錯 −15、ECE −0.022)但 AUROC 微降且距 0.75 甚遠,照實記錄,不引用為達標。
落地:`packages/sec_core/length_prior.py`(全 gold-free,NTU 零參與調參)——span 占 filing normalized 總長**占比**的 per-(form, schema, item) [p05, p95] band,由 corpus-only 317 筆導出(artifact `data/sec_eval/calibration/length_prior.json`,in_band_fraction 0.8457);雙向執法 → needs_review + 零分 3.5 權重 component 封頂 confidence(≤~0.74);**span 永不改動**;kill-switch `SEC_LENGTH_PRIOR=0`;`tests/test_length_prior.py` 20 tests。
Pairing 更正(process-fix 首次執行):§gate 表引用的 before(AUROC 0.6307/29/83)是 **stale pairing**(calibration 讀了 furniture-strip 之前的 head_to_head);可比 before = 18:42 h2h 重算(AUROC 0.6711 / 118 錯);本波 rerun 已驗 mtime 配對,gate 對照以可比 before 為準。
#### before/after(strata `ntu_human_labeled`,n=512;artifact `data/sec_eval/calibration/calibration.json`)
| 指標 | doc-stated before(stale pairing) | 可比 before(18:42 h2h、無 prior) | **after(prior 上線)** | Gate | 判定 |
|---|---|---|---|---|---|
| AUROC | 0.6307 | 0.6711 | **0.6621** | ≥0.75 | **MISS**(且較可比 before −0.009) |
| needs_review 錯誤攔截 | 29/141=20.6% | 28/118=23.7% | **39/118=33.1%** | ≥50% | **MISS**(+9.4pt) |
| conf≥0.9 桶內錯誤 | 83 | 62 | **47** | ≤44 | **MISS**(−15,差 3) |
| ECE | 0.1762 | 0.1352 | **0.1133** | —(副指標) | 改善 |
| verifier false-pass | 0.2519(100/397) | 0.1990(79/397) | 0.2048(68/332) | — | coverage 0.7754→**0.6484** |
| macro-F1(ours) | 0.6245 | 0.6245 | **0.6245**(4 engine 全逐位一致) | 不變 | **PASS**(confidence 不動 span) |
#### 歸因(每一格都是前景實測;artifact `data/sec_eval/calibration/length_prior_attribution.json`)
| 變體 | AUROC | ECE | 攔截 | conf≥0.9 錯 | 火在 correct/error |
|---|---|---|---|---|---|
| baseline(無 prior) | 0.6711 | 0.1352 | 28/118 | 62 | — |
| 只 overshoot(>p95) | 0.6616 | 0.1169 | 39/118 | 50 | 58/16 |
| 只 undershoot(<p05) | 0.6720 | 0.1289 | 28/118 | 59 | 13/3 |
| **雙向 flat(shipped)** | **0.6621** | **0.1133** | **39/118** | **47** | 71/19 |

護欄:sweep3 clean corpus 前景重跑誤報 12/178 = 6.7%(分位數構造的預期代價,**高於** size-band 的 0.05 benchmark,照實揭露);mutation recall 六類全 1.0 不變;pytest 763 passed;aux `pseudo_gold_corpus_only` AUROC 0.4139→0.3459,維持煙霧偵測定位照錄。殘餘:anchor-distance 訊號量測後零收益(觸發 0/1/1 全打 correct)**判死不進 codebase**;未攔 79 錯 = pass 42(內容錯位非尺寸異常)+ IBR 35 + missing 8 + partial 5——長度/位置類 gold-free 訊號天花板已實測見底,AUROC 0.75 與攔截 ≥50% 兩 gate **維持未達成**,需內容歸屬訊號(topic_check 更強版)。
### Wrapper section-anchor 收尾 2026-07-11(P0-10 完成:CYD 11 agree / 0 disagree)
結論:CYD agreement 從 10/1 修到 11/0(11 家,`tools/certify_cyd.py`),F1 與 calibration 零連帶變動(前景重跑實測:ours 0.6245、AUROC/ECE/false-pass 逐位不變、`calibration.json` diff 僅 timestamp),shipped。

| 家 | BEFORE | AFTER |
|---|---|---|
| GS 1C | IBR stub 247 chars(485610–485857),coverage 0.0% / containment 0.0% | partial `resolved_from_section_anchor` 8,650 chars(779931–788581),coverage **100%** / containment **85.6%** |
| JPM 1C | partial `resolved_from_page_anchor` 20,610 chars,coverage 100% / containment **33.3%** | partial 9,745 chars(762158–771903),coverage 100% / containment **70.5%**;終點與官方 CYD 完全一致 |
| 其餘 9 家 | AAPL/MSFT/NVDA/WMT/CAT/XOM/NEM/MRNA/KO 數字逐位不變 | 同(MSFT/MRNA `needs_review_after` false→true 為 length-prior commit 34d31b9 所致,上次 regen 基線在 84ecea7,與 section-anchor 無關) |

根因與修法:GS 類(intra-document pointer,stub 指向 Item 7 span 內部 section)+ JPM 類(page-window 過寬,頁窗開頭是母 section)——同一結構缺口:wrapper body resolution 沒讀「印刷頁面結構」;修法 = `cross_ref.py` page-top section anchoring(通用結構規則,無 ticker 特例)+ `resolve_intra_document_pointers` pass + `_snap_window_to_item_section`,外加 **item-topic guard**(anchored heading 必須與 item canonical title 語彙相關;**wrong body 比 honest pointer 更糟**——GS 7A 曾被解析到母章節總覽,已擋回 honest pointer)。
守門:kill-switch `SEC_WRAPPER_SECTION_ANCHOR=0` 實檔驗證完整還原 before(GS 0%/247、JPM 33.3%/20,610);pytest 772 passed(+9 `tests/test_section_anchor.py`);mutation 全綠;NTU slice(2001–2019)無 CYD 時代 wrapper 1C stub,無交集符合預期。Artifacts:`data/sec_eval/cyd_groundtruth/cyd_agreement.json`、`data/sec_eval/scoring/head_to_head.json`、`data/sec_eval/calibration/calibration.json`;修改檔 `packages/sec_core/cross_ref.py`、`packages/sec_core/pipeline.py`。
### 內容軸 Gate rerun 2026-07-11(gold-free span content-attribution prior 落地,§Gate rerun 後續)
結論:攔截 gate 首次 PASS(65.3% ≥ 50%),AUROC gate 仍 MISS(0.6667 < 0.75)——照實記錄,不引用為達標;三個候選子訊號量測後**出貨兩個、判死一個**(floor 在 held-out 上 20 發中 18 發打在 correct,依 anchor-distance 前例整段移除,非藏在開關後)。
落地:`packages/sec_core/topic_prior.py`(全 gold-free,NTU 零參與調參)——per-item 內容歸屬 lexicon 由 corpus-only 245 個 substantive span 導出(artifact `data/sec_eval/calibration/topic_lexicon.json`);(a) **misattribution margin**(對別的 item lexicon 覆蓋率高出 margin_tau=p99=0.3807,in-sample 已揭露)與 (b) **IBR pointer trust cap**(pointer 文本結構性不可驗證,純結構規則、無調參)→ needs_review + 零分 3.5 權重 component;span 永不改動;kill-switch `SEC_TOPIC_PRIOR=0`(分訊號 `SEC_TOPIC_PRIOR_{MARGIN,IBR}=0`);`tests/test_topic_prior.py` 16 tests。
#### before/after(strata `ntu_human_labeled`,n=512;artifact `data/sec_eval/calibration/calibration.json`,mtime 配對已驗)
| 指標 | before(length-prior 波,無 topic prior) | **after(margin+IBR 上線)** | Gate | 判定 |
|---|---|---|---|---|
| AUROC | 0.6621 | **0.6667**(+0.0046) | ≥0.75 | **MISS** |
| needs_review 錯誤攔截 | 39/118=33.1% | **77/118=65.3%**(+32.2pt) | ≥50% | **PASS**(本波首達) |
| conf≥0.9 桶內錯誤 | 47 | **42**(−5) | ≤44(前波差 3) | **PASS** |
| ECE | 0.1133 | **0.1235**(+0.0102,轉差) | —(副指標) | 照實揭露(IBR cap 壓低 60 個 correct stub 的 conf 所致) |
| verifier false-pass | 0.2048(68/332) | **0.1358(33/243)** | — | coverage 0.6484→**0.4746**(pointer stub 改走 review 通道——review 負載上升是真實代價) |
| macro-F1(ours) | 0.6245 | **0.6245**(4 engine 全逐位一致) | 不變 | **PASS**(confidence 不動 span) |
#### 歸因(每格前景實測,live pipeline per variant;artifact `data/sec_eval/calibration/topic_prior_attribution.json`)
| 變體 | AUROC | ECE | 攔截 | conf≥0.9 錯 | 火在 correct/error |
|---|---|---|---|---|---|
| baseline(無 topic prior) | 0.6621 | 0.1133 | 39/118 | 47 | — |
| 只 margin | 0.6661 | 0.1075 | 42/118 | 42 | 7/3 |
| 只 floor(**判死**) | 0.6535 | 0.1179 | 41/118 | 43 | 18/2 |
| 只 IBR | 0.6602 | 0.1292 | 74/118 | 47 | 60/35 |
| **margin+IBR(shipped)** | **0.6667** | **0.1235** | **77/118** | **42** | 67/38 |
| margin+floor+IBR | 0.6559 | 0.1293 | 78/118 | 40 | 85/39 |

護欄:sweep3 clean corpus margin 誤報 **0/176**(優於 length-prior 6.7% 與 size-band 0.05 benchmark);IBR cap 54/54 全火為設計行為(pointer 一律走 review),review 負載如實列帳;mutation recall 六類全 1.0 不變;pytest 788 passed;lexicon 門檻為 in-sample p99(artifact `gold_free` 欄已揭露),NTU 全程 held-out;aux `pseudo_gold_corpus_only` AUROC 0.3459→0.3389、ECE 0.2168→0.2521 照錄不調參。
殘餘:攔截幾乎全由 IBR 側貢獻(+35 錯全是 Part III proxy stub);未攔 41 錯中 pass 28(conf 0.86–1.0)是 margin p99 門檻逮不到的細粒度邊界/內容混合錯位——需「span 內部逐段歸屬」訊號(per-paragraph attribution 或 boundary bisection);AUROC 0.75 gate 在 cap-to-~0.74 機制下數學上已近不可達(模擬上限 ≈0.747)——下一波換連續值訊號,或承認 needs_review 通道(攔截/false-pass)才是此驗證器的主軸、AUROC 只是排序副指標。Artifacts:`data/sec_eval/calibration/topic_lexicon.json`、`topic_prior_attribution.json`、`calibration.json`、`data/sec_eval/scoring/head_to_head.json`;修改檔 `packages/sec_core/topic_prior.py`、`packages/sec_core/pipeline.py`、`tests/test_topic_prior.py`。
