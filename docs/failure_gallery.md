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
| Repair Attempt | 初版(commit 892ae0b):新增 `_CROSS_REF_RE`(`refer to / see item N`),body < 600 且命中 → `incorporated_by_reference`。**此機制後於 FG-SEC-002 的 refine 重構(commit 0c46e9d)被 `sec_core/refine.py::classify_reference_stub`(廣義 reference cue,body < 900)取代並移除**——故現行 code 已無 `_CROSS_REF_RE` 符號,見 refine.py |
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
| Evidence | 對抗式稽核 31 confirmed 中的多數;例:GS Item 11 body = 「...is incorporated in this Form 10-K by reference.」regex `incorporated\s+(?:herein\s+)?by\s+reference` 因中間夾「in this Form 10-K」而不命中 |
| Root Cause | FG-SEC-001 的修復 `_CROSS_REF_RE` 只認「refer to/see Item N」;真實 filing 用大量其他措辭指向 Note、named section、page range、proxy(不同 word order)。單一狹窄 regex 是脆弱設計 |
| Repair Attempt | 新 `refine.classify_reference_stub`:body < 900 字且命中廣義 reference cue → incorporated_by_reference,並用 `_describe_target` 標明指向 proxy / Note / Item / Financial Section / page range |
| Why It Still Failed | (已修復)殘留:內容真正還原(接回 MD&A/財報)尚未做,見 insights §2 |
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
| Root Cause | **wrapper 10-K 模式**:公司把 Item 7/8 寫成一句指向「Financial Section / annual report」的 stub,真正內容以獨立區塊接在最後一個 item heading 之後。末項 span 定義為「到下一個 item heading 或 end-of-doc」→ 吃光後面全部。**這正是主管點名的 Intel/Citi corner case。** |
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
| Actual(修復前) | INTC:所有 item 被抽成 33–330 字的碎片、標 `ambiguous`;Citi:0 candidates → 全 `missing`。**主管點名別的作業把 INTC Item 14 標成 extracted/ok。** |
| Status | fixed(偵測+分類);正文還原待做 |
| Failure Type | filing_class 誤判 |
| Root Cause | Intel 把正文放在前段(以「Risk Factors」等**無 Item 前綴**的標題),正式的 Item N 交叉引用索引放在文末指向年報頁碼;Citi 更把索引寫成「1A.Risk Factors49-62」完全無「Item」字樣。單一「Item N」regex 只打到索引或全打不到 |
| Repair Attempt | 新 `cross_ref.py`:偵測 item heading 群聚 +(頁碼指標 OR 極小行間距),且群聚外無正文候選;`scan_bare_index` 處理 Citi 無前綴格式。歸類為 `cross_reference_index`,items 標 `incorporated_by_reference`/`needs_review`/`cross_reference_pointer` |
| Why It Still Failed | (偵測已修復)正文還原(跟指標進年報 exhibit)未做——刻意不出貨脆弱猜測 |
| Independent check | XBRL oracle 對這些 filing 的 Item 8 判 `contradicted`(財報數字不在該 span),獨立佐證正文確實不在主文件 |
| Related Commit | feat(sec): detect cross-reference-index filings (Intel/Citi/GE class) |

---

## 元層次(2):status 可信度的獨立驗證(XBRL)

FG-SEC-001~004 是「pipeline 內部把 silent failure 修掉」。FG-SEC-005 加上一層**外部 oracle**:Item 8 對照 SEC XBRL companyfacts 的營收/淨利/總資產。11 家 sweep:7 家 pass 全被 XBRL `certified`、3 家 wrapper stub 被 `contradicted`,**pipeline 分類與獨立 oracle 零分歧**。這回答主管的核心問題「如何確保 status 可信」——不是 AI 自述,是對照結構化事實。詳見 `prompts/eval_design/2026-07-10-xbrl-and-cross-ref.md`。

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

**誠實邊界:** 這是 local mock site 的注入式漂移(可控、可重現);真實網站的漂移泛化尚未證明,列為 roadmap(WebArena/WebVoyager,見 prior_art)。

## 稽核方法本身(元層次)

這四個 FG 都不是我「讀 code 想出來的」,而是 **56 個 agent 的對抗式稽核**跑真實 filing 跑出來的,且每個都經過獨立 verifier「盡力反駁」後才留下(12 個被反駁的 anomaly 沒進這裡)。這個「用 AI 對抗式驗證 AI 產出」的 harness 本身,就是 SPEC 17 想證明的「AI 時代最稀缺的是驗證能力」。詳見 `prompts/eval_design/2026-07-10-adversarial-audit-workflow.md`。
