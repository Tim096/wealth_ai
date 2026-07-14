# Failure Gallery

每個 failure 都是事故報告。Failure 不是扣分項,沒有 failure analysis 才是。

---

## FG-SEC-001: Cross-reference stub 被標 pass(silent failure)

| 欄位 | 內容 |
|---|---|
| Failure ID | FG-SEC-001 |
| App | sec_extractor |
| Input | JPM 10-K, accession 0001628280-26-008131 (FY2025) |
| Expected | Item 11 應反映「內容在別處」——不是完整正文 |
| Actual | Item 11 標 `pass`、confidence 0.96,但整個 body 只有 51 字元:`"Refer to Item 10."` |
| Status | fixed |
| Failure Type | silent_failure(錯了卻標成功)|
| Evidence | smoke run 輸出 + `r.text_of('11')` == `'Item 11. Executive Compensation.\nRefer to Item 10.\n'` |
| Root Cause | `_INCORPORATED_RE` 只匹配 "incorporated by reference" 字樣;JPM 用 "Refer to Item 10." 措辭,不含該片語,於是 stub 通過 verifier(heading 對、span 非空、順序對)拿到高 confidence |
| Repair Attempt | 初版(commit 9ed8dd2):新增 `_CROSS_REF_RE`(`refer to / see item N`),body < 600 且命中 → `incorporated_by_reference`。**此機制後於 FG-SEC-002 的 refine 重構(commit 311d2f6)被 `sec_core/refine.py::classify_reference_stub`(廣義 reference cue,body < 900)取代並移除**——故現行 code 已無 `_CROSS_REF_RE` 符號,見 refine.py |
| Why It Still Failed | (已修復)殘餘風險:非 Part III 的極短 cross-ref 措辭變體(如 "included in Item 8")尚未覆蓋,由 boundary_length_sanity confidence 分量部分攔截 |
| Next Fix | eval sweep 擴大公司樣本,收集更多 cross-ref 措辭變體 |
| Related Prompt | prompts/failure_triage/2026-07-10-jpm-cross-ref-stub.md |
| Related Commit | fix(sec): classify cross-reference stub bodies as incorporated_by_reference |

**附註(同次 smoke run 的正確行為驗證):** JPM 沒有 Item 16(選填項,raw HTML 0 hits)→ pipeline 標 `missing`,是正確的誠實判定,計入 missing item correctness。

---

## FG-SEC-002: Reference-stub 措辭變體大規模逃過偵測(silent failure class)

| 欄位 | 內容 |
|---|---|
| Failure ID | FG-SEC-002 |
| App | sec_extractor |
| Input | 11 家真實 10-K(sweep1);對抗式稽核發現 |
| Expected | 只指向他處的短 body 應標 incorporated_by_reference,不是 pass |
| Actual | MSFT/NVDA/CAT Item 3、JPM 1C/7/7A/8、GS 1C/7A/11/13/14、XOM 3/7/7A/8、NVDA 8 全被標 pass、confidence ~0.958 |
| Status | fixed |
| Failure Type | silent_failure(FG-SEC-001 的一般化)|
| Evidence | 11-company accession sweep 的重複 failure class；例：GS Item 11 body = 「...is incorporated in this Form 10-K by reference.」regex `incorporated\s+(?:herein\s+)?by\s+reference` 因中間夾「in this Form 10-K」而不命中。逐 accession artifacts 位於 `data/sec_eval/records/sweep2/` 與 `sweep3/`。 |
| Root Cause | FG-SEC-001 的修復 `_CROSS_REF_RE` 只認「refer to/see Item N」;真實 filing 用大量其他措辭指向 Note、named section、page range、proxy(不同 word order)。單一狹窄 regex 是脆弱設計 |
| Repair Attempt | 新 `refine.classify_reference_stub`:body < 900 字且命中廣義 reference cue → incorporated_by_reference,並用 `_describe_target` 標明指向 proxy / Note / Item / Financial Section / page range |
| Why It Still Failed | (已修復)內容還原已做:page-anchor 把 MD&A/財報接回 source-exact span(見 FG-SEC-005 / insights §2)。殘留:頁碼 over-claim 時 span 可能重疊,故標 heuristic partial + needs_review |
| Next Fix | cross-reference resolution 第二遍 |
| Related Commit | fix(sec): kill three silent-failure classes found by 11-company audit |

---

## FG-SEC-003: Part divider / 頁碼 / running header 洩漏進 span 尾端

| 欄位 | 內容 |
|---|---|
| Failure ID | FG-SEC-003 |
| App | sec_extractor |
| Input | 幾乎每家的 Item 4 / 9C / 16(Part 邊界上的 item)|
| Expected | span 只含 item body |
| Actual | AAPL Item 4 span = 「Not applicable. / Apple Inc. \| 2025 Form 10-K \| 18 / PART II」;confidence 0.958、無警告 |
| Status | fixed |
| Failure Type | boundary_leak |
| Root Cause | span end = 下一個 item heading 的 start;兩者間夾著 Part divider、頁碼、running header,全被吃進 span。normalizer 保留這些為獨立行卻無人裁切 |
| Repair Attempt | `refine.trim_trailing_furniture`:從 span 尾端逐行裁掉符合 furniture pattern(PART [IVX]、bare page number、Table of Contents、含 Form 10-K 的短行、公司 banner)的行,遇實質內容即停,並記錄裁掉了什麼 |
| Why It Still Failed | (已修復)|
| Related Commit | 同上 |

---

## FG-SEC-004: Terminal item 吞掉整本 appended 財報(最嚴重)

| 欄位 | 內容 |
|---|---|
| Failure ID | FG-SEC-004 |
| App | sec_extractor |
| Input | XOM 10-K(Item 16)、JPM 10-K(Item 15)|
| Expected | XOM Item 16 body = 「None.」;JPM Item 15 = exhibit 清單 |
| Actual | **XOM Item 16 = 311,785 字**(吞掉整個 FINANCIAL SECTION:MD&A、財報、附註、油氣補充資料)、confidence 1.0、無警告;**JPM Item 15 = 985,564 字**(吞掉整本 annual report)|
| Status | fixed |
| Failure Type | boundary_runaway |
| Evidence | 稽核 dump:XOM Item 16 span 開頭「None. / 27 / FINANCIAL SECTION / TABLE OF CONTENTS / ...」;JPM Item 15 中段出現「Return on tangible common equity (ROTCE)」MD&A 表格 |
| Root Cause | **wrapper 10-K 模式**:公司把 Item 7/8 寫成一句指向「Financial Section / annual report」的 stub,真正內容以獨立區塊接在最後一個 item heading 之後。末項 span 定義為「到下一個 item heading 或 end-of-doc」→ 吃光後面全部。**這正是我們鎖定的 Intel/Citi corner case。** |
| Repair Attempt | `refine.detect_appended_section_cut`:僅對 terminal item 且 span > 20K 時,偵測 section break(hard:「FINANCIAL SECTION」立即切;soft:「Report of Independent...」「MD&A of Financial Condition」「Consolidated Statements of」等保留 ≥1000 字 body 後切),並警告排除了多少字 |
| Why It Still Failed | (已修復 boundary;內容還原見 insights §2)結果:XOM Item 16 → 33 字 + 警告排除 311,749 字;JPM Item 15 → 15,529 字 + 警告排除 970,031 字 |
| Related Commit | 同上 |

---

## FG-SEC-005: Cross-reference-index filing(Intel/Citi)被抽成碎片或 missing

| 欄位 | 內容 |
|---|---|
| Failure ID | FG-SEC-005 |
| App | sec_extractor |
| Input | INTC FY2019/FY2020/FY2025、Citi FY2025 |
| Expected | 正確辨識「主文件是交叉引用索引、正文在年報」,誠實標示 |
| Actual(修復前) | INTC:所有 item 被抽成 33–330 字的碎片、標 `ambiguous`;Citi:0 candidates → 全 `missing`。**我們自查鎖定的高風險失分點:此類 filing 的 Item 14 極易被誤標成 extracted/ok。** |
| Status | fixed(偵測+分類+頁碼錨點正文還原) |
| Failure Type | filing_class 誤判 |
| Root Cause | Intel 把正文放在前段(以「Risk Factors」等**無 Item 前綴**的標題),正式的 Item N 交叉引用索引放在文末指向年報頁碼;Citi 更把索引寫成「1A.Risk Factors49-62」完全無「Item」字樣。單一「Item N」regex 只打到索引或全打不到 |
| Repair Attempt | 新 `cross_ref.py`:偵測 item heading 群聚 +(頁碼指標 OR 極小行間距),且群聚外無正文候選;`scan_bare_index` 處理 Citi 無前綴格式。歸類為 `cross_reference_index`,items 標 `incorporated_by_reference`/`needs_review`/`cross_reference_pointer` |
| Why It Still Failed | (已修復)正文還原已做:`resolve_page_ref`/`build_page_map` 跟索引頁碼範圍在主文件內定位 source-exact span(`resolved_from_page_anchor`,partial+needs_review)。Citi 解出 9 個 item(Risk Factors 88K、MD&A 86K、Financials 577K 字)。殘留:頁邊界啟發式;proxy-only 的 Item 10–14 維持誠實 pointer。另修 `_BARE_INDEX_RE` title cap 70→110(MD&A 85 字標題曾被漏成 missing)、多 range 挑 earliest-start + 碰撞防護(不同 item 不共用 span) |
| Independent check | INTC/Citi Item 8 page-anchor 還原 span 經 SEC XBRL headline 3/3 認證,獨立佐證正文確實**在主文件內**(以印刷頁碼分頁,非另冊 exhibit) |
| Related Commit | feat(sec): detect cross-reference-index filings (Intel/Citi/GE class) |

---

## 元層次(2):status 可信度的獨立驗證(XBRL)

FG-SEC-001~004 是「pipeline 內部把 silent failure 修掉」。FG-SEC-005 加上一層**外部 oracle**:Item 8 對照 SEC XBRL companyfacts 的營收/淨利/總資產。11 家 sweep 現行結果(P0-10 wrapper 重組後,artifact 2026-07-11 重生):**certified 10 / contradicted 1**——NVDA 是唯一 contradicted(item8_status=incorporated_by_reference,誠實指標 stub,headline 數字確實不在 span);JPM/XOM 原為 contradicted,P0-10 重組後 span 各含 3/3 headline 轉 certified(artifact:`data/sec_eval/certification/item8_certification.json`)。注意 artifact 的 `disagreements=["JPM","XOM"]` 是 `agrees_with_pipeline` 欄位定義過窄(`tools/certify.py:49` 只認 status=="pass",重組後的 `partial` 被記為不一致),非 verdict 錯誤。這回答核心問題「如何確保 status 可信」——不是 AI 自述,是對照結構化事實。詳見 `prompts/eval_design/2026-07-10-xbrl-and-cross-ref.md`。

## FG-BROWSER-001: v2 UI 漂移導致 selector 全失效 + decoy button 陷阱

| 欄位 | 內容 |
|---|---|
| Failure ID | FG-BROWSER-001 |
| App | browser_agent |
| Input | mock site v2 上執行「搜尋 widget」;selector memory 帶著 v1 學到的 `#search-box` / `#search-btn` |
| Expected | 找到搜尋框、送出、看到結果 |
| Actual(修復前 / 無 repair) | `#search-box` 命中 0 元素(v2 移除該 id);cookie modal 攔截點擊;頁面有一個 text=「Search」的 **decoy button**(`#fake-search`)什麼都不做 |
| Status | fixed(repair 迴圈處理)|
| Failure Type | selector_not_found + modal_blocking + deceptive_button |
| Evidence | `runs/browser_demo/trace.json`:step traces 含 diagnosis、considered candidates、chosen selector、screenshots |
| Root Cause | UI 漂移:id 移除、button→icon(`#go` aria-label=Search)、cookie modal、decoy button、lazy render |
| Repair Attempt | (1) 偵測 modal_blocking → 關閉;(2) selector_not_found → a11y 樹枚舉候選,依 purpose 評分:search_box 找到 `input[name=query]`(placeholder/aria 命中),submit_button 找到 `#go`(type=submit,score 5.5)**而非 decoy**(decoy score −1);(3) 小步驗證 → verifier pass;(4) 更新 selector memory |
| Why It Still Failed | (已修復)|
| Self-maintenance 證據 | 下一個 v2 task(gizmo)**0 repair**——memory 已學到新 selector,漂移成本攤平 |
| Related Prompt | prompts/browser_agent/2026-07-10-selector-repair-design.md |
| Related Commit | feat(browser): implement capability-aware agent with selector self-repair |

**誠實邊界:** 這是 local mock site 的注入式漂移(可控、可重現);真實網站泛化已有初步外部量測——Online-Mind2Web 20-task live subset 自跑 33.3%(6/18)→ bucket-fix 44.4%(8/18)→ abstain-fix 合成 11/18 ≈ 61.1%(明標合成估計、n 小,vs naive baseline 20%;artifact `runs/browser_eval/m2w_rerun/`、`m2w_rerun_20260710/`、`m2w_abstain_fix_20260710/`、`m2w_abstain_fix2_20260710/`(gitignored 原始 run)+ tracked 快照 `data/browser_eval/external_runs/` 同名目錄,詳見 `docs/eval_report.md`;不可與官方 Online-Mind2Web leaderboard 直接比較,聲明見該節)。

## 稽核方法本身(元層次)

這四個 FG 來自一次 multi-agent 對抗式稽核，再由獨立 verifier 嘗試反駁。**證據限制**:per-agent 逐一輸出未完整留存，不能把 agent 數量或內部投票統計當成可重現 claim；留存且可驗證的是 workflow 方法(`prompts/eval_design/2026-07-10-adversarial-audit-workflow.md`)與後續修復(FG-SEC-001~004 各有 accession-level evidence/tests)。這個「用 AI 對抗式驗證 AI 產出」的方法是發現工具，最終裁決仍由可重跑的 fixture、oracle 與 regression test 負責。

---

# 2026-07-10 eval 升級波新增

以下 8 條由 11 項 eval 升級(verifier 校準、擾動矩陣、impossible set、三角驗證、CYD oracle、分層抽樣)量測抓出。Browser 4 條(FG-BROWSER-002~005)原為 **measure-first 刻意不修**——先讓校準/量測誠實呈現系統現狀,每條各有 pure-logic test 鎖住。**2026-07-10 修復波已全數修復**(commit bcdc9cf / d5481eb),原 `test_known_*` 已翻寫為 `test_fixed_*` 並重跑 artifact;每條的「Status」「Repair」欄已更新為修復後量測。這正是 measure-fix-remeasure 方法論的收尾:弱點先被誠實量測、再被修掉、再重新量測驗證。

---

## FG-SEC-006: edgartools 第三引擎 Item 16 section misattribution(三角驗證抓到引擎端錯誤)

| 欄位 | 內容 |
|---|---|
| Failure ID | FG-SEC-006 |
| App | sec_extractor(third-engine triangulation)|
| Input | NEM / NVDA / WMT FY2025 10-K,Item 16 |
| Expected | edgartools item 16 = "Form 10-K Summary / None." |
| Actual | edgartools 的 part_iv_item_16 section 裝的是 Item 1 TOC 行(NEM:「ITEM 1.BUSINESS6Introduction6...」)、MD&A 所得稅段(NVDA)、Item 1 Business 內文(WMT)——engine 端 section misattribution |
| Status | 我方 span 正確("None." 7 詞);verdict=disagree、needs_review=true(三角驗證無仲裁者,不能單方判自己贏)|
| Failure Type | 第三引擎 section misattribution(被三角驗證正確呈現為歧異)|
| Evidence | `data/sec_eval/triangulation/triangulation.json` records[NEM/NVDA/WMT].items['16'](overlap 0.0)|
| Root Cause | edgartools TOC-based 偵測抓錯區段 |
| Repair Attempt | 無(engine 端問題;我方策略是 disagree 一律扣 confidence + needs_review)|
| Related Commit | ea9f782 |

---

## FG-SEC-007: wrapper 10-K 的 Item 7/8 邊界定義歧異(兩引擎各自誠實)

| 欄位 | 內容 |
|---|---|
| Failure ID | FG-SEC-007 |
| App | sec_extractor(third-engine triangulation)|
| Input | JPM / XOM FY2025 wrapper 10-K,Items 7/8 |
| Expected | 兩引擎對 item 內容位置一致 |
| Actual | 我方標 incorporated_by_reference(指標 stub 40–96 詞),edgartools 直接抽出附綁年報全文(19,548–90,470 詞),overlap ≤0.21 → disagree,我方 confidence 降至 0.51–0.64 |
| Status | **fixed**(commit 84ecea7,`cross_ref.reassemble_wrapper_bodies`):指向本檔附綁區塊的 stub 解析回 source-exact span——JPM 走 page-range anchor(Item 7 → 390,734 chars、7A → 35,632、8 → 528,433,provenance `resolved_from_page_anchor`),XOM 走 quoted-section-title anchor(Item 7 → 89,501、7A → 30,817、8 → 165,993,provenance `resolved_from_section_anchor`);兩家 Item 8 重組 span 均被 XBRL 獨立認證 3/3。解析後標 `partial` + needs_review(頁界/節界對齊是啟發式,如實揭露)|
| Failure Type | wrapper 10-K 邊界定義歧異(修復前正是此 class 需要人審的證據)|
| Evidence | `data/sec_eval/triangulation/triangulation.json` records[JPM/XOM].items['7'/'8'];`tests/test_wrapper_reassembly.py`(10 tests);manifest FG-SEC-007 checks |
| Root Cause | wrapper filing 的 item body resolution 原為 documented next step(見 FG-SEC-004/005、insights §2)——已由 P0-10 落地 |
| Repair Attempt | `reassemble_wrapper_bodies()`:僅處理指向本 filing 的 stub(proxy/note pointer 不動),page-range stub 用區域限定 page map 取第一個提及區間;section-title stub 錨定附綁年報自身節標題並跳過其內部 TOC |
| Related Commit | ea9f782(偵測)→ 84ecea7(body 重組)|

---

## FG-SEC-008: CYD oracle 證實 JPM/GS wrapper 的 Item 1C coverage 0%(並給出精確目標位置)

| 欄位 | 內容 |
|---|---|
| Failure ID | FG-SEC-008 |
| App | sec_extractor(CYD iXBRL oracle)|
| Input | JPM / GS FY2025 wrapper 10-K,Item 1C |
| Expected | Item 1C segment 含 SEC 強制 CYD block-tag 的 cybersecurity disclosure |
| Actual | 我方 1C 是 170/247 char 的 incorporated_by_reference 指標 stub;官方 tagged span(6,871/7,402 chars)在同一份 HTML 的年報區(JPM 落在所有 item segment 之外;GS 落在我方 Item 7 內),coverage 0% |
| Status | **JPM fixed / GS open**(commit 84ecea7):JPM Item 1C 170-char stub → 20,610-char span(pages 146-149 Operational Risk,`resolved_from_page_anchor`),**CYD coverage 0% → 100%**、verdict disagree→agree(corpus CYD agreement 9/11 → 10/11)。GS 維持誠實 pointer:其 stub 指向**自身已抽出的 Item 7 內部子節**(無附綁 wrapper 區塊),是另一個 class,見 manifest FG-SEC-008 |
| Failure Type | wrapper-10-K body 未解析(既知 class);CYD oracle 首次給出可機讀的目標位置 |
| Evidence | `data/sec_eval/cyd_groundtruth/cyd_agreement.json` records[JPM/GS](official_intervals 有精確 normalized offsets)|
| Root Cause | cross-reference/wrapper filing 的 item body resolution 原為 documented next step;CYD tag 證明 body 就在同檔可定位——JPM class 已由 P0-10 落地 |
| Repair Attempt | `cross_ref.reassemble_wrapper_bodies()`(JPM class);GS 的 intra-item subsection pointer 超出本 pass 範圍,official_intervals 仍是其直接輸入 |
| Related Commit | f55c650 |

---

## FG-SEC-009: pre-2001 純文字 SGML filing 完全不支援(誠實 unsupported,非 crash 非假 pass)

| 欄位 | 內容 |
|---|---|
| Failure ID | FG-SEC-009 |
| App | sec_extractor(format-source stratification)|
| Input | AAPL FY1996(0000320193-96-000023)、KO FY1997(0000021344-98-000004)pre-2001 純文字 SGML 10-K |
| Expected | 切出 Item 1/1A/7/8 等 body span |
| Actual | normalize 正常(256,658 / 315,036 chars 保留)但 detect_candidates 回 0(HTML-oriented,依賴 block-tag line 結構),22 item 全 missing + 1 reserved,coverage 0.0,filing_class 降為 non_10k |
| Status | 誠實 unsupported;partition invariant 仍成立(tiled=true,整份為單一 unclassified block,零 silent drop)——「先全抓再分類」原則的正面示範 |
| Failure Type | format-era 不支援(HTML normalizer 用在 plain-text SGML)|
| Evidence | `data/sec_eval/stratification/stratification.json` era_strata_runs[text_pre2001] |
| Root Cause | normalize 只在 BLOCK_TAG 邊界 emit newline,純文字的 `\n` 被 `_emit_text` 當一般空白折疊 → heading 不在 line start、無 bold/heading flag → 0 candidate |
| Repair Attempt | 無(pre-2001 世代非本波範圍;正解是 text-mode normalizer,或維持 unsupported class)|
| Related Commit | a55d773 |

---

## FG-BROWSER-002: verifier filename-needle bypass(download 內容錯但檔名對 → FP)

| 欄位 | 內容 |
|---|---|
| Failure ID | FG-BROWSER-002 |
| App | browser_agent / verifier(download_exists)|
| Input | calibration case `cal-bad-dlname-annual-report`——needle="annual report",檔名 "annual report 2025.htm",檔案內容是 captcha 擋頁("Are you a robot?...")|
| Expected | fail(內容不含 needle)|
| Actual(修復前) | pass(verifier FP;T1-1 校準 46 triples 中唯一 FP,即 specificity 0.9583 的來源)|
| Status | 已修(commit bcdc9cf)|
| Failure Type | verifier filename-needle bypass |
| Evidence | `data/browser_eval/calibration/calibration_results.json` per_case `cal-bad-dlname-annual-report` verdict=fail;`tests/test_calibrate_verifier.py::test_filename_needle_bypass_fixed_content_first` |
| Root Cause | `packages/browser_agent/verifier.py` `_download_ok` 舊版 `return "pass" if (n in content or n in os.path.basename(path).lower()) else "fail"`——basename 單獨即可授予 pass,與檔頭註解「filename is a weak secondary signal」矛盾 |
| Repair(commit bcdc9cf) | 改為 content-first:內容**可讀**(UTF-8 decode 後 U+FFFD 替換字元比例 ≤5%)時只認內容,檔名不再單獨授 pass。本 case 的 captcha bytes 是可讀 UTF-8 且不含 needle → 正確判 **fail**。filename fallback 僅保留給不可讀 binary + 檔名命中的路徑(回 unknown 而非 pass,新單元測試覆蓋)。**量測後果**:此 case pass(FP)→fail;校準 specificity 0.9583→**1.0**、FP rate 0.0417→**0.0**、confusion FP 1→**0**、corrupted 三態 {pass1,fail20,unknown3}→{pass0,fail21,unknown3}、Rogan-Gladen corrected 0.7913→**0.8**(sensitivity 1.0 不變)。重跑 `.venv/Scripts/python tools/calibrate_verifier.py`,artifact `data/browser_eval/calibration/calibration_results.json` |
| Related Commit | 67eb56f(引入)→ bcdc9cf(修復)|

---

## FG-BROWSER-003: needle-in-query-echo silent failure(impossible set 抓到的真實 FP)

| 欄位 | 內容 |
|---|---|
| Failure ID | FG-BROWSER-003 |
| App | browser_agent / verifier(text_visible)|
| Input | impossible case `imp-product-teleporter`——site=v3_heldout,query="teleporter"(catalog 無此商品),success_conditions=[text_visible "Teleporter"],無 forbidden |
| Expected | fail(商品不存在,0 hits,無 Teleporter 商品列)|
| Actual(修復前) | pass(verifier FP → silent failure;silent_failure_rate 0.1 的那 1/10)|
| Status | 已修(commit bcdc9cf)|
| Failure Type | needle-in-query-echo(success needle 命中「結果頁回顯的查詢字串」而非真商品列)|
| Evidence | `data/browser_eval/impossible/impossible_results.json` per-task imp-product-teleporter status=fail;`tests/test_impossible_tasks.py::test_teleporter_query_echo_is_honest_fail` |
| Root Cause | v3 doSearch 對 0 hits 仍插入 status 文字 `0 results for "teleporter"`;verifier text_visible 做 substring 比對,needle 命中回顯而非商品。同家族:commit d27c2c0「stop mining a URL token as success needle」、論文 One-Token-to-Fool-Judge(arxiv 2507.08794)。對照組 imp-product-hoverboard 同樣 leak,但因帶 forbidden `error_text_visible "0 results"` 被擋下 |
| Repair(commit bcdc9cf) | text_visible 逐行遮罩空結果回顯行(通用 regex:0/no/zero + results/matches/items/hits/products、not(hing) found、did not match、找不到/查無/沒有結果…),needle 只在被遮罩行內命中就不算 pass。非零結果回顯(如 "3 results for widget")不遮罩,合法 pass 全保留。**量測後果**:imp-product-teleporter pass→**fail**;silent_failure_rate 0.1→**0.0**、honest_fail 7→**8**、honest_outcome_rate 0.9→**1.0**、expect_status_accuracy 0.9167→**1.0**。校準 sensitivity 維持 1.0(合法 pass 不受影響)。重跑 `.venv/Scripts/python tools/impossible_tasks.py` |
| Related Commit | a79f3c7(引入)→ bcdc9cf(修復)|

---

## FG-BROWSER-004: repair fallback 到不可行元素(silent wrong-element click)

| 欄位 | 內容 |
|---|---|
| Failure ID | FG-BROWSER-004 |
| App | browser_agent / repair(repair_target submit_button)|
| Input | mutation 矩陣 action-heavy cell——submit 是無 role 的 `<span onclick>`,不進 a11y 枚舉;頁上唯一候選是搜尋 input(aria-label "Search products")|
| Expected | repair 回報 no viable candidate(誠實找不到)|
| Actual(修復前) | repair「修復」到搜尋 input 並點擊之,click 回 ok(silent wrong-element click),trace 全綠,只有最終 verifier 擋下(fail)|
| Status | 已修(commit d5481eb)|
| Failure Type | repair fallback to non-actionable element(weak word-match score 2.0 > 0 門檻)|
| Evidence | `data/browser_eval/artifacts/degradation_curve.json` runs[action-heavy] repairs=2 status=fail honest_refusals=1;`tests/test_mutation_sites.py::test_fixed_submit_repair_refuses_infeasible_input` |
| Root Cause | `packages/browser_agent/repair.py` `_score_candidate`——submit_button purpose 對 input 仍給 word-match +2.0,repair_target 只要 score>0 就選,無「動作可行性」檢查 |
| Repair(commit d5481eb) | FG-BROWSER-004 加**可行性 gate**(`_feasible()`):每種 purpose 對應可執行元素類別(submit/download→button/a/[role=button\|link]/input[type=submit…]、fill→可填 input/textarea/[role=searchbox\|textbox]、result_link→a/link、filter_dropdown→select/listbox/combobox),不符者 score=-1 直接出局,保證入選者至少一項結構訊號命中。**量測後果**:action-heavy 仍 fail(submit 真的不存在),但**fail 得誠實**——3/3 run honest_refusals=1(repair 回 "no viable candidate" 而非點 input 的 silent wrong click);checkpoint 1.0、curve monotone 均不變。degradation artifact 新增 `honest_refusals` 欄位把「誠實 fail vs silent wrong click」寫進 committed 數字。重跑 `.venv/Scripts/python tools/degradation_curve.py` |
| Related Commit | a51361e(引入)→ d5481eb(修復)|

---

## FG-BROWSER-005: bait-field DOM-order tie-break(誘餌欄位搶走 query)

| 欄位 | 內容 |
|---|---|
| Failure ID | FG-BROWSER-005 |
| App | browser_agent / repair(repair_target search_box)|
| Input | mutation 矩陣 perception-heavy cell——可見 "Promo code" 誘餌欄位在前,真搜尋框無 aria、generic placeholder("Type here...")|
| Expected | 填入真搜尋框(表單內、緊鄰 submit)|
| Actual(修復前) | 兩欄位同分 2.5,tie 由 DOM 順序決定 → query 填進 Promo 欄位 → 空查詢 → fail(checkpoint 也 fail:degradation curve 上可見失敗發生在輸入階段)|
| Status | 已修(commit d5481eb)|
| Failure Type | bait-field DOM-order tie-break |
| Evidence | `data/browser_eval/artifacts/degradation_curve.json` curves[perception] points[3] success_rate=1.0、cells[perception-heavy] checkpoint_rate=1.0;`tests/test_mutation_sites.py::test_fixed_bait_field_loses_to_form_context` |
| Root Cause | `repair.py` `_score_candidate` 無 form-context/鄰近性訊號,unlabeled 真欄位無法勝出;want_value 對兩者皆不命中 |
| Repair(commit d5481eb) | FG-BROWSER-005 由 observer 新增 `form` 欄位(closest('form') 的 id/index),repair 先算 submit_forms(含可行 submit 候選的 form 集合);fill 類 purpose 對同 form +1.0、任一 form 內 +0.5,bait 字樣(promo/coupon/discount/voucher/gift card)在無 purpose word 時 -1.0。真搜尋框在 submit 所在 form,誘餌 Promo 欄位在 form 外 → 真欄位勝出。**量測後果**:perception-heavy success 0.0→**1.0**、checkpoint 0.0→**1.0**、recovery 0.0→**1.0**;perception curve 1.0→1.0→1.0→0.0 變 **1.0→1.0→1.0→1.0**(仍 monotone non-increasing)。未引入 vision。重跑 `.venv/Scripts/python tools/degradation_curve.py` |
| Related Commit | a51361e(引入)→ d5481eb(修復)|

---

## FG-BROWSER-006: 開放式(零條件)任務讓整個 run crash(ValidationError → status=ERROR)

| 欄位 | 內容 |
|---|---|
| Failure ID | FG-BROWSER-006 |
| App | browser_agent / contract + verifier(open-ended task 路徑)|
| Input | 無可機讀驗證條件的開放式任務(如「隨便逛逛看有什麼有趣的」「看看現在流行什麼」)——success_conditions 應為空陣列 |
| Expected | 執行、錄 trace,verifier 因無可機讀證據回 **unknown**(交人工審 trace)|
| Actual(修復前) | `BrowserTaskContract` 的 `success_conditions` 有 `min_length=1`,空陣列直接 ValidationError → run status=**ERROR**,開放式任務 0% 可跑;且若繞過(給空 success + forbidden 全過),`combine_checks` 會 **vacuous pass**(什麼都沒證明卻回 pass)|
| Status | 已修(commit f535c93)|
| Failure Type | crash on honest input + vacuous-pass 風險(誠實路徑被當非法輸入懲罰)|
| Evidence | `data/browser_eval/open_ended/open_ended_results.json` metrics crashes=0 / vacuous_passes=0 / honest_unknown=3 / honest_unknown_rate=1.0 / traces_recorded=3;`tests/test_open_ended_tasks.py` |
| Root Cause | contract schema `min_length=1` 把「誠實的空條件」當非法輸入;verifier `combine_checks` 在 forbidden-only 全過時會回 pass(結構性 vacuous pass 漏洞)|
| Repair(commit f535c93) | (1) contract `success_conditions` min_length 1→0(附註解:誠實路徑不可是非法輸入);(2) `verify_contract` 加結構性守門:空 success 時先跑 forbidden checks,違規照樣 fail,否則短路回 **unknown** + missing_evidence 明講需人工審 trace;(3) run 迴圈 verdict 起始即 unknown,agent 照常執行、trace/screenshots 照錄。**量測後果**:3/3 開放式 case status=unknown、crashes **0**、vacuous_passes **0**、honest_unknown_rate **1.0**,每個 case trace steps>0(2/3/2)。新 runner `tools/open_ended_tasks.py`。重跑 `.venv/Scripts/python tools/open_ended_tasks.py` |
| Related Commit | f535c93 |

---

## FG-BROWSER-007: INTC 營收任務 false pass(task-echo landmark + 無交付通道,使用者親測)

| 欄位 | 內容 |
|---|---|
| Failure ID | FG-BROWSER-007 |
| App | browser_agent / planner + verifier + agent(answer-type 任務全鏈)|
| Input | 使用者親測任務:「找到 intc 10-k 的財報 找到裡面的最新的營收數字給我」;preflight 自選 success 條件 `text_visible:intc` |
| Expected | 要嘛把營收數字交到使用者手上(pass + 答案),要嘛誠實說「無法機器驗證」(unknown)——絕不在沒交付任何答案時判 PASS |
| Actual(修復前) | agent 開了 EDGAR 搜尋頁 → `text_visible:intc` 命中(任務句自帶 token)→ **PASS,confidence 高**;而即使 agent 有 extract_text 抓到營收,結果也被丟棄、從不回傳 |
| Status | 已修(三重根因分別 commit 8437826 / 3431335 / 1c8f103)|
| Failure Type | premature-landmark false pass + 答案交付通道缺失(silent value-zero pass)|
| Evidence | `tests/test_premature_landmark.py`(baseline-subtraction:INTC repro pass→unknown,9 passed);`data/browser_eval/answer_channel/answer_channel_results.json`(silent_failures=0、matches_expected 3/3);`data/browser_eval/calibration/calibration_results.json`(answer_wrong class 0 pass)|
| Root Cause | 三個獨立缺陷疊加:(1) **premature landmark** —— preflight 條件是任務句自帶 token,任何搜尋頁都為真;(2) **無交付通道** —— `run_agentic` 的 `extracted` 只放 `__download__`,extract_text 結果既不進 verifier 也不回 UI,答案型任務結構性零交付卻記 pass;(3) **卡住時無視覺升級** —— 找不到目標只能重試到 give_up。同族論文:One-Token-to-Fool-Judge(arxiv 2507.08794,needle 命中回顯而非事實)|
| Repair(根因 1,8437826) | verifier **baseline-subtraction**:t0(agent 動作前)以空 extracted 跑 `_check_success`,t0 即成立的條件視為 landmark 剔除;全剔除後空條件流進 open-ended gate → 誠實 **unknown**,絕不 vacuous pass(`download_exists` t0=unknown 不誤剔)。planner 端 `_task_echo` guard 擋任務句 echo 條件 |
| Repair(根因 2,3431335) | extract_text 成功結果 append 進 `extracted['answer']`(存 `TaskRun.answer` + UI「📋 擷取內容」);verifier 新條件型別 **answer_matches**(有 answer 且 regex match→pass;不 match→fail;沒 answer→fail,不吃自述;regex 不可編譯→unknown)。verifier 校準集加 answer_wrong corruption class(2 case 全 fail),46→50 |
| Repair(根因 3,1c8f103) | `vision_escalation_reason` 卡住偵測 → auto 切入 Set-of-Marks + gpt-5.5 視覺(`AGENT_VISION` 未設=auto 新預設);scroll PLAYBOOK(off-screen 目標);executor 新分頁跟隨。vision 純感知,verifier 仍唯一裁判(escalation 測試斷言 status!=pass)|
| Why It Still Failed | (已修結構性根因;wrapper 10-K 正文還原仍是 documented next step,見 FG-SEC-004/005)|
| Related Prompt | prompts/browser_agent/(preflight 條件品質、answer channel 設計)|
| Related Commit | 8437826(baseline-subtraction)+ 3431335(answer channel)+ 1c8f103(auto vision / scroll / new-tab)|

---

## FG-BROWSER-008: gov.uk 題 verifier 判 pass,但 answer 是導航殘渣「Skip contents」(user-value false success,誠實列帳)

| 欄位 | 內容 |
|---|---|
| Failure ID | FG-BROWSER-008 |
| App | browser_agent / verifier(open-ended scoring)+ answer channel |
| Input | Online-Mind2Web live 題 `m2w-6ca20f1da01e`(gov.uk,medium):「Find the Eligibility to get the child benefit and How it works and how to claim」(abstain-fix 定向重跑批次)|
| Expected | pass 應伴隨對使用者有價值的交付內容 |
| Actual | verifier 判 **pass**(open-ended scorer:3/3 key points grounded-satisfied,confidence 1.0),但 `answer` 欄位內容是「Skip contents」——gov.uk 頁面導航 skip-link 的殘渣,對使用者零價值。second judge(advisory)判 **no** |
| Status | **fixed locally**(2026-07-12:answer channel 拒絕已知 skip-link 導航殘渣;新增 regression test)|
| Failure Type | user-value false success(landmark/grounding 契約成立,交付內容無價值)|
| Evidence | `runs/browser_eval/m2w_abstain_fix2_20260710/results.json` task `m2w-6ca20f1da01e`(gitignored 原始 run);tracked 快照 `data/browser_eval/external_runs/m2w_abstain_fix2_20260710/results.json`(同 task id)|
| Root Cause | open-ended scorer 的 key-point grounding 以最終頁 `inner_text` 為證據——agent 確實抵達了含 eligibility / how-it-works / how-to-claim 內容的正確頁面,3 個 key point 全部 grounded,契約如實成立;但 answer channel 抓到的是 extract_text 命中的第一個元素(skip-link)。「頁面對」與「交付對」是兩件事,verifier 的 landmark/grounding 契約量的是前者——這是 verifier landmark 契約的已知結構性弱點(同 eval_report M2W 節「弱 proxy」聲明)|
| 為什麼不改判 | second judge 是 **advisory-only**(設計鐵律:verifier 唯一裁判,judge 分歧只記錄不改判)。讓 judge 翻案等於引入一個未經 sens/spec 校準的第二裁判,已校準 verifier 的可信度基礎會被繞過;一致的規則比單案好看的數字重要。本案已如實計入 61.1% 合成 topline 的分子——這正是該數字須標「方向指標、不可與官方 leaderboard 比較」的原因之一 |
| Remaining Fix | answer-quality gate 已完成已知 skip-link 規則;(1)擴充前需由新失敗樣本驅動,避免過濾正常短答案;(2) open-ended scorer 把 answer 內容納入 grounding 證據;(3) live 契約升級為「答案軸」條件(answer_matches 已有機制,這批外部題的契約未帶)|
| Related Commit | 9a40ae2(open-ended scorer verdict-time 武裝——本案即其量測中暴露的殘餘弱點)|
