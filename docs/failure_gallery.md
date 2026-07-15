# Failure Gallery(失敗畫廊)

**一句話:這裡收的不是功能,是事故。** 每一條都是「系統當時說自己做對了,結果做錯了」的現場紀錄——包含我怎麼抓到、怎麼修、修完還剩什麼沒解決。

> 每個 failure 都是事故報告。Failure 不是扣分項,沒有 failure analysis 才是。

## 這份文件怎麼讀?

**先畫地圖。本份分四段 ——**

| 段 | 內容 | 功能一句話 |
|---|---|---|
| 一 | 怎麼讀這份畫廊(骨架 + 白話速查表)| 讓非技術讀者能接住後面每一句話 |
| 二 | 第一波:SEC 抽取器五起事故 FG-SEC-001~005 + 元層次(2)XBRL 外部驗證 | 「系統自己說 pass」為什麼不算數 |
| 三 | Browser agent 第一起事故 FG-BROWSER-001 + 稽核方法本身 | 發現工具長什麼樣、它的證據限制在哪 |
| 四 | 2026-07-10 eval 升級波新增:FG-SEC-006~009、FG-BROWSER-002~008 | 量測 → 修復 → 重新量測的完整收尾 |

### 每個案例的骨架是什麼?

全部用同一副骨架講,因為所有事故的形狀都一樣:

**【系統的主張】** 它說它做對了 → **【我的自我攻擊】** 真的嗎?我拿什麼去戳它 → **【去測】** 實際跑、實際看 → **【判定】** 對或錯,不改判 → 然後才是事故報告表(根因、修復、殘留)。

**這裡的核心矛盾一句話講完:pipeline 說 `pass`,等於考生自己說「我這題對了」。考生的自評不是分數。這整份文件就是在講:我用什麼把考生的自評扒下來。**

### 名詞白話速查表

技術段落裡的每個縮寫,先在這裡翻成人話。

| 術語 | 翻成一般人能懂的版本 |
|---|---|
| span / offset | span 是「文件裡從第幾個字到第幾個字」這一段;offset 就是那個「第幾個字」的號碼。抽取器交出的不是複製貼上的文字,是**座標** |
| stub | 存根。只有一兩句話、內容是「請去別處看」的短段落——一張紙條,不是正文 |
| pass / confidence | pass 是系統自評「這題我做對了」;confidence 是它對這個自評有多少把握(0~1)|
| silent failure | 靜默失敗。錯了,而且系統不知道自己錯了,還標成功。**最貴的一種錯,因為它不會叫** |
| verifier | 驗題的角色。agent 交卷,verifier 打分。設計鐵律:verifier 是唯一裁判 |
| oracle | 標準答案的來源。這裡專指**獨立於我方 pipeline 之外**的事實 |
| regex | 一條字串比對規則(「長得像這樣的字就算命中」)|
| normalizer | 前處理:把原始 HTML 壓成純文字 |
| incorporated_by_reference | 官方講法的「內容不在這份文件裡,在別處」|
| needs_review | 系統自己舉手:這題我沒把握,請人看 |
| partial | 部分還原:切出來了,但邊界靠啟發式,不敢自稱精確 |
| wrapper 10-K | 包裝型 10-K。主文件只寫一句「請看年報」,真正的年報整本接在後面 |
| cross-reference index | 交叉引用索引。主文件根本是一張目錄,每行只寫「這個 item 在第幾頁」(例如 Citi 的「1A.Risk Factors49-62」)|
| XBRL / iXBRL | 財報上的機器可讀標籤;iXBRL 是把標籤內嵌在 HTML 裡的版本 |
| CYD | SEC 強制標記的 cybersecurity disclosure 區塊標籤(Item 1C 的內容)|
| accession | SEC 給每份申報文件的唯一編號 |
| fixture | 凍結下來的原始檔,讓測試可以離線、逐字重跑 |
| a11y 樹 | 無障礙樹:瀏覽器提供給輔助科技的頁面結構 |
| selector | 定位網頁元素用的字串(例如 `#search-box`)|
| decoy | 誘餌元素。長得像目標、點了什麼都不做 |
| FP(false positive)| 偽陽性:該判 fail 卻判 pass。這份文件裡最該死的一類錯 |
| sensitivity / specificity | 抓得到壞的能力 / 不冤枉好的能力 |
| Rogan-Gladen | 用已知的 sensitivity/specificity 反推真實比例的修正法 |
| needle | 驗證條件裡要找的那個關鍵字串 |
| Set-of-Marks | 在截圖上幫每個可點元素編號,讓視覺模型能指名說「點 7 號」|
| provenance | 出處:這段 span 到底是怎麼來的 |
| manifest | 把每條 FG 的可執行檢查列成表的檔案(`data/sec_eval/fixtures/manifest.json`)|

---

# 第二段:SEC 抽取器,第一波五起事故

## FG-SEC-001: Cross-reference stub 被標 pass(silent failure)

**【系統的主張】** JPM 的 Item 11(高階主管薪酬):`pass`,confidence 0.96。
**【我的自我攻擊】** 0.96 是很高的自評——那正文有多長?
**【去測】** 打開來看:整個 body 只有 **51 字元**,全文是 `"Refer to Item 10."`。
**【判定】** 這不是 pass。系統抽到的是一張紙條,然後把紙條當成薪酬正文。

**不是「抽錯位置」,是「抽對了紙條、卻不知道那是紙條」。**

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

**白話拆解根因:** verifier 當時檢查的三件事全部通過——標題對、內容不是空的、順序沒亂。**問題是這三件事一件都沒有在問「內容到底是不是薪酬」。** 檢查表對了,檢查的東西錯了。

**附註(同次 smoke run 的正確行為驗證):** JPM 沒有 Item 16(選填項,raw HTML 0 hits)→ pipeline 標 `missing`,是正確的誠實判定,計入 missing item correctness。

**這則附註不是湊字數,是對照錨:** 同一次 run 裡,系統在「該說沒有的時候說了沒有」。所以 FG-SEC-001 不是「系統整個壞掉」,是「系統在特定措辭下瞎掉」——這兩件事的修法完全不同。

---

## FG-SEC-002: Reference-stub 措辭變體大規模逃過偵測(silent failure class)

**【系統的主張】** FG-SEC-001 修好了。
**【我的自我攻擊】** 修好的是「那一句措辭」,還是「這一類錯」?我補的 `_CROSS_REF_RE` 只認得 "refer to / see Item N"——真實世界的公司,會剛好都用這句話寫嗎?
**【去測】** 11 家真實 10-K sweep,對抗式稽核。
**【判定】** 沒修好。MSFT/NVDA/CAT 的 Item 3、JPM 的 1C/7/7A/8、GS 的 1C/7A/11/13/14、XOM 的 3/7/7A/8、NVDA 的 8,一整排全被標 pass、confidence ~0.958。

最刺眼的一個:GS Item 11 的 body 寫著「...is incorporated in this Form 10-K by reference.」——**它字面上就有 "incorporated by reference"**,但因為中間夾了「in this Form 10-K」四個字,regex 不命中。

**不是規則寫錯,是「用一條窄規則去接一個開放世界」這個設計本身錯。**

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

**這條的價值不在修復,在它證明了 FG-SEC-001 的修復是假修復。** 一個只在原始案例上綠燈的補丁,拿到 11 家真檔上就整排紅——這就是為什麼修完必須重測,而且要在**沒見過的樣本**上重測。

---

## FG-SEC-003: Part divider / 頁碼 / running header 洩漏進 span 尾端

**【系統的主張】** span 裡只有 item 正文。
**【我的自我攻擊】** 那 span 的**尾巴**是什麼?我只看過開頭。
**【去測】** 印出 AAPL 的 Item 4。
**【判定】** 尾巴掛著垃圾:「Not applicable. / Apple Inc. | 2025 Form 10-K | 18 / PART II」——正文只有前三個字,後面全是頁腳、頁碼和下一個 Part 的分隔線。confidence 0.958,零警告。

**白話:** 我剪貼的時候,把兩頁之間的裝訂線一起剪進來了。

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

**根因一句話:** 我把 span 的結尾定義成「下一個標題的開頭」——這等於**預設兩個 item 之間沒有東西**。真實文件的兩個 item 之間,永遠有東西。

---

## FG-SEC-004: Terminal item 吞掉整本 appended 財報(最嚴重)

**【系統的主張】** XOM 的 Item 16 抽到了,confidence **1.0**——滿分,系統百分之百確定。
**【我的自我攻擊】** 滿分?那答案有多長?
**【去測】** 數字元。
**【判定】** **311,785 字**。而正確答案是「None.」兩個字。系統用滿分的把握,交了一份三十一萬字的「無」。JPM 的 Item 15 更誇張:**985,564 字**,整本年報。

**白話比喻:** 考卷最後一題答「無」,系統卻把後面所有空白頁、附錄、參考書全部圈起來,說「這些都是我這題的答案」,然後給自己打滿分。

**這正是我們鎖定的 Intel/Citi corner case。**

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

**修復後的數字為什麼值得看:** XOM 從 311,785 字 → **33 字**,並且**明講排除了 311,749 字**;JPM 從 985,564 字 → **15,529 字**,明講排除 970,031 字。重點不是變短,是**變短的部分有帳可查**——我沒有偷偷丟掉九十七萬字,我列出來我丟了九十七萬字。

**不是「切得比較準」,是「切掉的東西從此有收據」。**

---

## FG-SEC-005: Cross-reference-index filing(Intel/Citi)被抽成碎片或 missing

**【系統的主張】** Intel 和 Citi 這兩份也跑完了。
**【我的自我攻擊】** 跑完不等於做對。這兩家的 10-K 主文件**根本不是正文,是一張目錄**——目錄上每一行寫的是「這個 item 在第幾頁」,不是 item 的內容。系統看得懂這件事嗎?
**【去測】** 跑 INTC FY2019/FY2020/FY2025、Citi FY2025。
**【判定】** 看不懂。INTC 的每個 item 被抽成 33–330 字的碎片、標 `ambiguous`;Citi 直接 0 candidates → 全部 `missing`。

**我們自查鎖定的高風險失分點:此類 filing 的 Item 14 極易被誤標成 extracted/ok。**

Citi 還更狠一層:它的索引寫成「1A.Risk Factors49-62」——**連 "Item" 這個字都沒有**。所有靠「Item N」比對的邏輯,在這裡一個字都打不到。

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

**修復裡最該被攻擊的一步,我自己先攻擊:** 「跟著索引上的頁碼去主文件裡找正文」聽起來很聰明,但**印刷頁碼不是文件座標**——它是啟發式。所以還原出來的 span 一律標 `partial` + `needs_review`,不敢自稱精確。而 `_BARE_INDEX_RE` title cap 從 70 改成 110,理由也是被打出來的:MD&A 的 85 字標題超過 70,曾經被整段漏成 missing。

**這條的收尾不是「我解出來了」,是「我解出來了,而且我有一個獨立於自己的證人」——Item 8 的還原 span 被 SEC XBRL headline 3/3 認證。** 下一節就是講這個證人。

---

## 元層次(2):status 可信度的獨立驗證(XBRL)

**問題是:** 前面五條全是「pipeline 自己抓自己的錯」。可是——**憑什麼相信抓錯的那個人?** 考生自己改考卷,改完說「我全對」,你信嗎?

**答案是:** 找一個不歸我管的證人。

FG-SEC-001~004 是「pipeline 內部把 silent failure 修掉」。FG-SEC-005 加上一層**外部 oracle**:Item 8 對照 SEC XBRL companyfacts 的營收/淨利/總資產。11 家 sweep 現行結果(P0-10 wrapper 重組後,artifact 2026-07-11 重生):**certified 10 / contradicted 1**——NVDA 是唯一 contradicted(item8_status=incorporated_by_reference,誠實指標 stub,headline 數字確實不在 span);JPM/XOM 原為 contradicted,P0-10 重組後 span 各含 3/3 headline 轉 certified(artifact:`data/sec_eval/certification/item8_certification.json`)。注意 artifact 的 `disagreements=["JPM","XOM"]` 是 `agrees_with_pipeline` 欄位定義過窄(`tools/certify.py:49` 只認 status=="pass",重組後的 `partial` 被記為不一致),非 verdict 錯誤。這回答核心問題「如何確保 status 可信」——不是 AI 自述,是對照結構化事實。詳見 `prompts/eval_design/2026-07-10-xbrl-and-cross-ref.md`。

**白話版的這段:** SEC 的 XBRL 是公司自己報給主管機關的結構化數字(營收多少、淨利多少、總資產多少)。我把我切出來的 Item 8 拿去比對——如果我切對了,那三個數字應該就在我的 span 裡面。11 家裡 10 家對上(certified),1 家對不上(contradicted)。

**對不上的那家我沒有藏:** NVDA 的 Item 8 是一張紙條(incorporated_by_reference),headline 數字**確實不在**我的 span 裡——所以 contradicted 是正確的判定,不是我的 bug,而系統標的 stub 也是誠實的。

**還有一個我自己爆的雷:** artifact 裡寫著 `disagreements=["JPM","XOM"]`,看起來像我有兩家不一致。**這是我的欄位定義寫窄了**——`tools/certify.py:49` 只把 status=="pass" 算作一致,而重組後的 JPM/XOM 是 `partial`,於是被記成不一致。verdict 本身沒錯,是計分欄位沒跟上。**我把這件事寫在這裡,而不是悄悄改掉 artifact。**

> **不是「AI 說它抽對了」,是「公司報給 SEC 的數字,出現在 AI 抽出的段落裡」。前者是自述,後者是證據。**

---

# 第三段:Browser agent 第一起事故,與稽核方法本身

## FG-BROWSER-001: v2 UI 漂移導致 selector 全失效 + decoy button 陷阱

**【系統的主張】** 我學過這個網站,我知道搜尋框是 `#search-box`、按鈕是 `#search-btn`。
**【我的自我攻擊】** 那是 v1 學的。網站改版了呢?而且——**如果頁面上有一個寫著「Search」但什麼都不做的假按鈕,你分得出來嗎?**
**【去測】** 在 v2 上跑「搜尋 widget」,帶著 v1 的 selector memory。
**【判定】** 三個坑同時踩:`#search-box` 命中 0 個元素(v2 把 id 拿掉了)、cookie modal 蓋住點擊、頁面上有個 `#fake-search` 誘餌按鈕在等著。

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

**評分機制的白話:** 真按鈕 `#go` 拿到 **score 5.5**(它 type=submit,結構上真的能送出);誘餌拿到 **score −1**(它只有長得像)。**分數的差距不是來自「看起來像不像」,是來自「結構上做不做得到」。**

**最值得看的那個數字是 0:** 下一個 v2 task(gizmo)**0 repair**。第一次修復的代價,第二次就攤平了——這才叫 self-maintenance,不然只是每次都重來一遍。

**誠實邊界:** 這是 local mock site 的注入式漂移(可控、可重現);真實網站泛化已有初步外部量測——Online-Mind2Web 20-task live subset 自跑 33.3%(6/18)→ bucket-fix 44.4%(8/18)→ abstain-fix 合成 11/18 ≈ 61.1%(明標合成估計、n 小,vs naive baseline 20%;artifact `runs/browser_eval/m2w_rerun/`、`m2w_rerun_20260710/`、`m2w_abstain_fix_20260710/`、`m2w_abstain_fix2_20260710/`(gitignored 原始 run)+ tracked 快照 `data/browser_eval/external_runs/` 同名目錄,詳見 `docs/eval_report.md`;不可與官方 Online-Mind2Web leaderboard 直接比較,聲明見該節)。

**這段誠實邊界要拉到眼前,不是塞在附註:** 上面那些 selector 漂移是**我自己注入的**,可控、可重現——所以「修好了」只證明在我出的題目上修好了。真實網站的數字只有 33.3% → 44.4% → 61.1%,其中 61.1% 還是**合成估計**、樣本只有 18 題,而且**不可與官方 leaderboard 直接比較**。

> **不是「我的 agent 很穩」,是「我的 agent 在我自己出的題上很穩,在真實網站上只有方向指標」。**

## 稽核方法本身(元層次)

這四個 FG 來自一次 multi-agent 對抗式稽核，再由獨立 verifier 嘗試反駁。**證據限制**:per-agent 逐一輸出未完整留存，不能把 agent 數量或內部投票統計當成可重現 claim；留存且可驗證的是 workflow 方法(`prompts/eval_design/2026-07-10-adversarial-audit-workflow.md`)與後續修復(FG-SEC-001~004 各有 accession-level evidence/tests)。這個「用 AI 對抗式驗證 AI 產出」的方法是發現工具，最終裁決仍由可重跑的 fixture、oracle 與 regression test 負責。

**翻成一般人能懂的版本:** 我用一群 AI 互相挑毛病,把上面這些洞挖出來。聽起來很威——**但我要主動拆自己的台:那次稽核的每個 agent 講了什麼,我沒有完整留檔。** 所以「幾個 agent、投票幾比幾」這種話,我一句都不能講,講了就是不可重現的吹噓。

留得下來的只有兩樣:**方法**(workflow prompt 還在)和**結果**(FG-SEC-001~004 每條都有 accession 級的證據和測試)。

> **不是「多 agent 稽核證明了系統是對的」,是「多 agent 稽核幫我找到問題,而證明對錯的是可以重跑的 fixture、oracle 和 regression test」。發現工具不是裁判。**

---

# 第四段:2026-07-10 eval 升級波新增

以下 8 條由 11 項 eval 升級(verifier 校準、擾動矩陣、impossible set、三角驗證、CYD oracle、分層抽樣)量測抓出。Browser 4 條(FG-BROWSER-002~005)原為 **measure-first 刻意不修**——先讓校準/量測誠實呈現系統現狀,每條各有 pure-logic test 鎖住。**2026-07-10 修復波已全數修復**(commit bcdc9cf / d5481eb),原 `test_known_*` 已翻寫為 `test_fixed_*` 並重跑 artifact;每條的「Status」「Repair」欄已更新為修復後量測。這正是 measure-fix-remeasure 方法論的收尾:弱點先被誠實量測、再被修掉、再重新量測驗證。

**「measure-first 刻意不修」是什麼意思?白話:** 找到 bug 的當下我**故意先不修**,先讓量測工具把它照出來、把難看的數字寫進 artifact。因為如果邊找邊修,最後只會剩下一份漂亮的成績單,沒人知道原本有多爛、修了多少。**先照鏡子,再化妝,而且鏡子的照片要留著。**

---

## FG-SEC-006: edgartools 第三引擎 Item 16 section misattribution(三角驗證抓到引擎端錯誤)

**【系統的主張】** 我的 Item 16 抽到 "None."(7 個詞),對的。
**【我的自我攻擊】** 憑你自己說?我找第三方引擎 edgartools 來對。
**【去測】** NEM / NVDA / WMT FY2025 的 Item 16,兩邊比。
**【判定】** 兩邊完全對不上(overlap 0.0)——但這次**錯的是對方**:edgartools 的 Item 16 裡裝的是 NEM 的目錄行、NVDA 的所得稅段、WMT 的 Item 1 內文。

**關鍵在這裡:即使我確信自己對,我還是標 disagree + needs_review。** 因為三角驗證裡**沒有仲裁者**——我不能自己當裁判宣布自己贏。

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

> **不是「三角驗證證明我對」,是「三角驗證讓歧異被看見」。看見之後由人決定,不由我決定。**

---

## FG-SEC-007: wrapper 10-K 的 Item 7/8 邊界定義歧異(兩引擎各自誠實)

**【系統的主張】** JPM/XOM 的 Item 7、8 是 incorporated_by_reference(一張 40–96 詞的紙條)。
**【對方的主張】** edgartools 說:Item 7、8 是 19,548–90,470 詞的整本年報。
**【自我攻擊】** 兩邊 overlap ≤0.21,幾乎完全不重疊——**這種時候誰對?**
**【判定(修復前)】** 兩邊各自誠實,但都不完整:我交的是紙條(正確但沒價值),對方交的是整本(有內容但邊界糊)。我的 confidence 誠實地掉到 0.51–0.64。**這個狀態就是「該找人審」的教科書案例。**
**【判定(修復後)】** 我把紙條解回正文了——而且是 source-exact span,不是重打的。

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

**兩家用了兩種不同的錨,理由不是隨便挑的:** JPM 的紙條寫著頁碼範圍 → 走 page-range anchor;XOM 的紙條寫著節標題 → 走 quoted-section-title anchor。**紙條上寫什麼,就用什麼當地址。**

**我對這個修復的自我攻擊,以及它的答案:** 「頁碼/節標題對齊」本質是啟發式,對不準怎麼辦?——所以全部標 `partial` + needs_review,**不冒充精確**。而 Item 8 的重組 span **被 XBRL 獨立認證 3/3**——這不是我自己說對,是外部證人說對。

**還有一條紅線我沒越:** `reassemble_wrapper_bodies()` **只處理指向本檔的 stub**。指向 proxy statement、指向 Note 的紙條一律不動——因為那些內容**真的不在這份文件裡**,硬解就是編造。

> **不是「把紙條變成正文」,是「照著紙條上的地址,回到同一份文件裡把正文找出來,而且承認地址是手寫的」。**

---

## FG-SEC-008: CYD oracle 證實 JPM/GS wrapper 的 Item 1C coverage 0%(並給出精確目標位置)

**【系統的主張】** JPM/GS 的 Item 1C(資安揭露)我抽到了,是 170/247 字元的指標 stub。
**【我的自我攻擊】** SEC **強制**公司在資安揭露上打 CYD 標籤。那官方標籤標的那一段,跟我抽的那一段,重疊多少?
**【去測】** 拿 CYD iXBRL 標籤當 oracle 去比。
**【判定】** **coverage 0%**。官方標的是 6,871/7,402 字元的真正揭露內容,而且**就在同一份 HTML 裡**——JPM 那段落在我所有 item segment 之外,GS 那段落在我的 Item 7 裡面。我的 1C 一個字都沒碰到。

**這個 oracle 的特別之處:它不只說「你錯了」,它直接給了座標。** 一般的 oracle 只能判對錯;CYD 標籤帶著 offset,等於直接告訴我「正確答案在第幾個字到第幾個字」。

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

**修好的只有一半,我把另一半寫在 Status 欄第一個字:** **JPM fixed / GS open**。

JPM:170 字元 → 20,610 字元,CYD coverage **0% → 100%**,verdict 從 disagree 翻成 agree,整個 corpus 的 CYD agreement 從 **9/11 → 10/11**。

GS:**沒修**。因為它是**另一個 class**——GS 的紙條指向的是**它自己 Item 7 裡面的一個子節**,不是附綁的 wrapper 區塊。同一套 `reassemble_wrapper_bodies()` 套不上去,硬套就是把兩件不同的事混為一談。所以 GS 維持誠實 pointer,並標明「超出本 pass 範圍」。

> **不是「CYD oracle 讓我拿到 10/11」,是「CYD oracle 先讓我看到 0%,再告訴我正確答案在哪,我才修得動 JPM;GS 它沒教我,我就不會,我就說不會。」**

---

## FG-SEC-009: pre-2001 純文字 SGML filing 完全不支援(誠實 unsupported,非 crash 非假 pass)

**【系統的主張】** ——這次系統一句話都沒主張。
**【去測】** 丟 1996 年的 AAPL 10-K 和 1997 年的 KO 10-K 進去。那個年代的申報是**純文字**,沒有 HTML 標籤。
**【判定】** 22 個 item 全部 missing,coverage **0.0**。

**這裡有三種可能的死法,我要指出系統死成哪一種:**

| 死法 | 會發生什麼 | 這次是嗎? |
|---|---|---|
| crash | 程式炸掉,什麼都沒有 | 否——normalize 正常,256,658 / 315,036 chars 全部保留 |
| 假 pass | 硬抽一些垃圾出來標 pass | 否——detect_candidates 誠實回 0 |
| 誠實 unsupported | 說「這個格式我不會」,但**一個字都沒丟** | **是** |

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

**「partition invariant 仍成立」翻成人話:** 我把整份文件切成一塊一塊,這些塊拼起來必須**剛好等於原文,不多不少**(`tiled=true`)。這次雖然一個 item 都沒分類出來,但整份文件變成**一個「未分類」的大塊**——**零 silent drop,一個字都沒有偷偷消失。**

**這就是「先全抓再分類」原則的正面示範:** 先保證全部抓進來,再談分類。分類失敗的代價是「不知道這是什麼」,而不是「這段不見了」。

**根因白話:** normalizer 是給 HTML 寫的,它靠 HTML 的區塊標籤決定哪裡換行。純文字檔裡真正的換行符 `\n`,被當成一般空白折疊掉了 → 標題不在行首、沒有粗體旗標 → 偵測器一個候選都找不到。**不是它笨,是我拿量身高的尺去量體重。**

> **不是「系統在 1996 年的檔案上失敗了」,是「系統在 1996 年的檔案上說『我不會』,而且沒弄丟任何一個字」。會做和知道自己不會做,是兩種能力。**

---

## FG-BROWSER-002: verifier filename-needle bypass(download 內容錯但檔名對 → FP)

**【系統的主張】** 這份下載檔通過驗證:pass。
**【我的自我攻擊】** 它憑什麼 pass?
**【去測】** 打開那個檔案。檔名叫 "annual report 2025.htm",內容是……一張 captcha 擋頁:「Are you a robot?...」
**【判定】** **verifier 自己是壞的。** 它看到檔名有 "annual report" 就給 pass,根本沒看內容。

**這條特別重:因為壞掉的是裁判本人。** T1-1 校準的 46 個 triple 裡,這是**唯一一個 FP**——換句話說,`specificity 0.9583` 那個 0.0417 的缺口,就是這一個 case。

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

**根因裡最諷刺的一句話,我原樣抄在這:** 那段 code 的檔頭註解自己寫著「filename is a weak secondary signal」——**註解寫得對,code 寫得錯。** `n in content or n in os.path.basename(path).lower()` 這個 `or`,讓「弱訊號」單獨就能發 pass。

**修法的取捨我講清楚:** 內容**可讀**(UTF-8 decode 後 U+FFFD 比例 ≤5%)時只認內容,檔名不再單獨授 pass。那不可讀的 binary 呢?**檔名 fallback 保留,但回 `unknown` 而非 `pass`**——不知道就說不知道,不猜。

**量測後果一句話:** specificity 0.9583→**1.0**、FP rate 0.0417→**0.0**,而 sensitivity **1.0 不變**——這點很重要:**我沒有靠變嚴格來換掉抓壞的能力。**

> **不是「檔名對就代表下載對」,是「檔名只是命名,內容才是東西」。**

---

## FG-BROWSER-003: needle-in-query-echo silent failure(impossible set 抓到的真實 FP)

**【系統的主張】** 使用者要找 "teleporter",找到了:pass。
**【我的自我攻擊】** 這個目錄裡**根本沒有傳送器這個商品**——這題是我故意出的不可能任務。它憑什麼 pass?
**【去測】** 看結果頁的字。
**【判定】** 頁面上寫著 `0 results for "teleporter"`。verifier 找 "Teleporter" 這個字——**在「查無結果」那句話裡找到了**,於是判 pass。

**白話:** 我問「有沒有傳送器?」店員說「沒有傳送器」,系統聽到「傳送器」三個字,就說「找到了!」。

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

**「impossible set」是什麼?白話:** 一組**故意設計成不可能完成**的任務。正確答案永遠是 fail。**任何一個 pass 都是抓到現行犯。** 這條就是那 1/10——`silent_failure_rate 0.1` 的分子。

**對照錨就在同一批題目裡:** `imp-product-hoverboard` **一模一樣地洩漏**,但它沒 pass——因為它的契約多帶了一條 forbidden `error_text_visible "0 results"`。**同樣的漏洞,一個踩到一個沒踩到,差別只在契約有沒有多寫一行。** 這證明問題不在題目,在 verifier 的比對方式。

**這不是我獨創的發現:** 同家族有 commit d27c2c0「stop mining a URL token as success needle」,也有論文 One-Token-to-Fool-Judge(arxiv 2507.08794)——**judge 被單一 token 騙過**是已知的一整類問題,我只是在自己的系統裡又踩到一次。

**修法的邊界我先自我攻擊:** 遮罩「查無結果」的行,會不會把正常答案也遮掉?——**不會,因為只遮零結果回顯**:「3 results for widget」這種非零回顯不遮,合法 pass 全保留。證據:校準的 **sensitivity 維持 1.0**。

> **不是「頁面上有這個字就算找到」,是「頁面上有這個字,還要看它出現在『有』的句子裡,還是『沒有』的句子裡」。**

---

## FG-BROWSER-004: repair fallback 到不可行元素(silent wrong-element click)

**【系統的主張】** selector 壞了?沒關係,我修好了,點下去 → ok。
**【我的自我攻擊】** 你「修」到了什麼元素?
**【去測】** 看 trace。
**【判定】** 這一格的送出按鈕是個沒有 role 的 `<span onclick>`——**它根本不會出現在 a11y 樹裡,也就是說,repair 根本看不到它。** 頁面上唯一的候選是**搜尋輸入框**。系統把「送出按鈕」修成了輸入框,點它,click 回 ok,trace 全綠。

**只有最後的 verifier 擋下來(fail)。中間每一步都在說謊。**

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

**根因的數學很白痴,也因此很致命:** 「submit_button」這個目的,對一個 `aria-label="Search products"` 的輸入框,因為字面上有 "Search",拿到 word-match **+2.0**。而 repair 的選擇規則是——**只要 score > 0 就選**。2.0 > 0,成交。**整個流程沒有任何一步在問「這個元素到底點不點得下去」。**

**修法:加一道可行性 gate(`_feasible()`)。** 每種目的對應「結構上做得到這件事」的元素類別,不符的直接 score=-1 出局。**不是把分數調高門檻,是先問「這東西是不是那種東西」,再談分數。**

**最重要的量測後果,是一個沒有變好的數字:** action-heavy **仍然 fail**——因為那個 submit 按鈕**真的不存在**,修了也找不到。變的是**fail 的方式**:3/3 run 的 `honest_refusals=1`,repair 回「no viable candidate」,而不是去點一個錯的元素還說 ok。checkpoint 1.0、curve monotone 都沒動。

**而且我把這件事寫成了 committed 數字:** degradation artifact 新增 `honest_refusals` 欄位——**「誠實 fail」和「silent wrong click」從此在成績單上分得開。**

> **不是「修好了所以 pass」,是「修不好,但從此會誠實說修不好」。fail 不是問題,假裝不 fail 才是。**

---

## FG-BROWSER-005: bait-field DOM-order tie-break(誘餌欄位搶走 query)

**【系統的主張】** 我找到搜尋框了,填進去。
**【我的自我攻擊】** 這頁上有兩個輸入框:一個是「Promo code」(優惠碼)誘餌,排在前面、標籤清楚;一個是真搜尋框,**沒有 aria、placeholder 只寫著 "Type here..."**。你怎麼分?
**【去測】** 看評分。
**【判定】** **兩個同分 2.5。** 同分怎麼辦?按 DOM 順序——誘餌在前,誘餌贏。query 填進優惠碼欄位 → 送出空查詢 → fail。

**degradation curve 上看得到失敗發生在輸入階段,不是後面。**

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

**修法的核心洞察:真搜尋框沒有標籤,但它有鄰居。** 它跟送出按鈕在同一個 `<form>` 裡,而誘餌 Promo 欄位在 form 外面。所以我讓 observer 多記一個 `form` 欄位,repair 先算出「哪些 form 裡有可用的 submit」,然後:同 form **+1.0**、任一 form 內 **+0.5**、誘餌字樣(promo/coupon/discount/voucher/gift card)在沒有 purpose word 時 **-1.0**。**認不出它是誰,就看它跟誰站在一起。**

**量測後果:** perception-heavy 的 success **0.0→1.0**、checkpoint **0.0→1.0**、recovery **0.0→1.0**;perception curve 從 1.0→1.0→1.0→**0.0** 變成 1.0→1.0→1.0→**1.0**(仍 monotone non-increasing)。

**最該被指出的一行:未引入 vision。** 這整條是靠 DOM 結構訊號解掉的,**沒有動用視覺模型**——因為能用便宜的結構訊號解,就不該先掏出貴的。

> **不是「靠看得更清楚贏誘餌」,是「靠問『你跟送出按鈕是不是同一個 form』贏誘餌」。**

---

## FG-BROWSER-006: 開放式(零條件)任務讓整個 run crash(ValidationError → status=ERROR)

**【系統的主張】** ——它連話都沒說完就倒了。
**【去測】** 丟一個開放式任務進去:「隨便逛逛看有什麼有趣的」。這種任務**沒有任何可以機器驗證的成功條件**,所以 success_conditions 應該是空陣列。
**【判定】** 契約 schema 上寫著 `min_length=1`——**空陣列直接 ValidationError,run status=ERROR。開放式任務 0% 可跑。**

**這條的性質跟前面都不同:前面是「錯了卻說對」,這條是「誠實地說『我沒有可驗證的條件』,結果被當成非法輸入處死」。**

**而且還有第二層:** 如果硬繞過(給空 success + forbidden 全過),`combine_checks` 會 **vacuous pass**——**什麼都沒證明,卻回 pass。** 空集合的「全部通過」在邏輯上恆真,這是結構性漏洞,不是 bug。

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

**修法的那句註解值得單獨拎出來:`min_length` 1→0,附註解「誠實路徑不可是非法輸入」。** 如果系統只接受「有明確成功條件」的任務,那它會逼所有人**編一個條件出來**——而編出來的條件就是 FG-BROWSER-007 那種災難的溫床。

**三段修法各對一個問題:** (1) schema 放行空條件;(2) `verify_contract` 加結構性守門——空 success 時**先跑 forbidden checks,違規照樣 fail**,沒違規則短路回 **unknown** + missing_evidence 明講「需人工審 trace」,**絕不 vacuous pass**;(3) run 迴圈的 verdict **起始就是 unknown**,agent 照常跑、trace/screenshots 照錄。

**量測後果:** 3/3 開放式 case status=unknown、crashes **0**、vacuous_passes **0**、honest_unknown_rate **1.0**,而且每個 case 的 trace steps>0(2/3/2)——**證明它是真的跑過,不是躺平回 unknown。**

> **不是「這題我不會所以我不跑」,是「這題我跑了、全程錄影,但我沒有機器可讀的證據,所以我說 unknown,請你自己看錄影」。**

---

## FG-BROWSER-007: INTC 營收任務 false pass(task-echo landmark + 無交付通道,使用者親測)

**這條是使用者親自出的題,而且是這份畫廊裡最丟臉的一條。**

**【使用者的任務】** 「找到 intc 10-k 的財報 找到裡面的最新的營收數字給我」
**【系統的主張】** PASS,confidence 高。
**【我的自我攻擊】** 那營收數字呢?**使用者拿到那個數字了嗎?**
**【去測】** 看 preflight 自選的成功條件:`text_visible:intc`。
**【判定】** **災難。** agent 打開 EDGAR 搜尋頁,頁面上有 "intc" 這四個字母——**因為那是使用者輸入的搜尋詞!** 條件成立 → PASS。**使用者要的營收數字,一個都沒拿到。**

**更糟的在後面:** 就算 agent 真的用 extract_text 抓到了營收數字,**那個結果也會被丟棄、永遠不會回傳。** `run_agentic` 的 `extracted` 只放 `__download__`。**答案型任務在結構上零交付,卻照樣記 pass。**

**白話:** 我請人幫我查台積電股價,他去 Google 打了「台積電股價」,看到頁面上有「台積電」三個字,回來說「查到了!」——然後就走了。

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
| Why It Still Failed | (三重結構性根因均已修;附註:wrapper / cross-reference-index 10-K 正文還原此後亦已落地,見 FG-SEC-007/008)|
| Related Prompt | prompts/browser_agent/(preflight 條件品質、answer channel 設計)|
| Related Commit | 8437826(baseline-subtraction)+ 3431335(answer channel)+ 1c8f103(auto vision / scroll / new-tab)|

### 三個根因,三個修法,一個一個講

**根因 1:premature landmark(還沒開始就成立的條件)。**
修法叫 **baseline-subtraction**,白話是:**在 agent 動任何一步之前先驗一次。** 如果某個條件在 agent 什麼都還沒做的時候(t0)就已經成立,那它就不是「做到了」的證據,是**題目自帶的地標**,剔除。全部剔完之後,空條件流進 FG-BROWSER-006 修好的 open-ended gate → 誠實 **unknown**,**絕不 vacuous pass**。細節:`download_exists` 在 t0 回 unknown,不會被誤剔。planner 端另加 `_task_echo` guard,從源頭擋掉「拿任務句當條件」。

**根因 2:沒有交付通道。**
extract_text 的成功結果現在 append 進 `extracted['answer']`,存進 `TaskRun.answer`,UI 上顯示「📋 擷取內容」。verifier 新增條件型別 **answer_matches**——**有 answer 且 regex match → pass;不 match → fail;沒 answer → fail(不吃自述);regex 不可編譯 → unknown。** 「沒 answer → fail,不吃自述」這一條是重點:**agent 說「我找到了」不算數,要把東西交出來。** 校準集也加了 answer_wrong corruption class(2 case 全 fail),46→50。

**根因 3:卡住時只會重試到放棄。**
`vision_escalation_reason` 偵測到卡住 → auto 切入 Set-of-Marks + gpt-5.5 視覺(`AGENT_VISION` 未設 = auto,新預設);加 scroll PLAYBOOK 處理捲軸外的目標;executor 跟隨新分頁。**這裡有一條鐵律我沒鬆:vision 只做感知,verifier 仍是唯一裁判**——escalation 的測試直接斷言 `status != pass`,**視覺模型沒有投票權。**

**同族論文我照樣列:** One-Token-to-Fool-Judge(arxiv 2507.08794)——needle 命中回顯而非事實。**跟 FG-BROWSER-003 是同一種病,在不同器官上發作。**

> **不是「驗證條件成立所以任務完成」,是「使用者手上有沒有東西」。一個 pass 而沒有交付任何答案的任務,叫 silent value-zero pass——它比 fail 更糟,因為 fail 至少會叫。**

---

## FG-BROWSER-008: gov.uk 題 verifier 判 pass,但 answer 是導航殘渣「Skip contents」(user-value false success,誠實列帳)

**【系統的主張】** gov.uk 這題 pass,confidence **1.0**,open-ended scorer 給 **3/3 key points grounded-satisfied**。滿分。
**【我的自我攻擊】** 那交到使用者手上的 `answer` 欄位裡是什麼?
**【去測】** 打開來看。
**【判定】** 「**Skip contents**」——**gov.uk 頁面最上方那個「跳過導覽」無障礙連結的殘渣。** 對使用者的價值:零。

**而 second judge(advisory)判 no。我沒有採納它。理由我寫在下面,而且我不會改判。**

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

### 根因白話:契約沒說謊,契約量錯了東西

open-ended scorer 用最終頁面的 `inner_text` 當證據來檢查 key point 是否 grounded。而 agent **確實抵達了正確頁面**——那頁上真的有 eligibility、how it works、how to claim 三塊內容,3 個 key point 全部 grounded。**契約如實成立,scorer 沒有作弊。**

問題在 answer channel:它抓到的是 extract_text 命中的**第一個元素**,那是 skip-link。

**「頁面對」和「交付對」是兩件事。verifier 的 landmark/grounding 契約量的是前者。** 這是這套契約的**已知結構性弱點**(同 eval_report M2W 節「弱 proxy」聲明)。

### 為什麼我不改判?

second judge 判 no,而且它是對的。**但我還是不改判,理由三句話:**

1. **second judge 是 advisory-only。** 設計鐵律寫死了:verifier 是唯一裁判,judge 分歧只記錄、不改判。
2. **讓 judge 翻案等於引入第二個裁判——而這個裁判沒做過 sensitivity/specificity 校準。** 我花了 46→50 個 triple 去校準 verifier,就是為了讓「pass 有多可信」有數字支撐。放一個沒校準的裁判進來翻案,那些數字全部作廢。
3. **一致的規則比單案好看的數字重要。**

**所以這個 false pass 如實計入了 61.1% 合成 topline 的分子。** 我沒有把它扣掉讓數字好看——**這正是那個數字必須標「方向指標、不可與官方 leaderboard 比較」的原因之一。**

### 修了什麼、還剩什麼

**已修(fixed locally,2026-07-12):** answer channel 拒絕已知 skip-link 導航殘渣,新增 regression test。

**沒修,以及為什麼不急著修:** 「擴充 answer-quality gate」聽起來是明顯的下一步——**但我刻意不擴。** 因為過濾規則寫寬一點,就會開始誤殺正常的短答案。**(1) 擴充前需由新失敗樣本驅動。** 另外兩條是結構性的:**(2)** open-ended scorer 應把 answer 內容也納入 grounding 證據;**(3)** live 契約應升級為「答案軸」條件——`answer_matches` 機制在 FG-BROWSER-007 已經做好了,只是**這批外部題的契約沒帶**。

> **不是「pass 就是成功」,是「pass 只代表契約成立」。當契約量的是「有沒有到對的頁面」,它就量不到「有沒有交出對的東西」——而我選擇讓這個缺口留在成績單上,而不是留在附錄裡。**

---

# 誠實限制:還沒解決的,一張表列完

每一列都直說:**這削弱了什麼、我還能宣稱什麼。** 全部來自上面各條的 Next Fix / Remaining Fix / 殘留 / 證據限制欄,沒有一列是新的。

| 限制 | 影響:削弱什麼、還能宣稱什麼 | 見 |
|---|---|---|
| 非 Part III 的極短 cross-ref 措辭變體(如 "included in Item 8")尚未覆蓋 | 削弱「所有 stub 都抓得到」;還能宣稱「已知措辭抓得到,且由 boundary_length_sanity confidence 分量部分攔截」。Next Fix:eval sweep 擴大公司樣本 | FG-SEC-001 |
| 頁碼 over-claim 時 span 可能重疊 | 削弱「還原的 span 精確」;還能宣稱「標 heuristic partial + needs_review,不冒充精確」。Next Fix:cross-reference resolution 第二遍 | FG-SEC-002 |
| 頁邊界啟發式;proxy-only 的 Item 10–14 維持誠實 pointer | 削弱「cross-reference-index filing 完全還原」;還能宣稱「同檔內的還原有 XBRL 3/3 佐證,跨檔的誠實標 pointer 不編造」 | FG-SEC-005 |
| 三角驗證無仲裁者 | 削弱「我方 span 正確」的宣稱力;還能宣稱「歧異一律扣 confidence + needs_review,不單方判自己贏」 | FG-SEC-006 |
| GS Item 1C 的 intra-item subsection pointer 超出本 pass 範圍(**open**)| 削弱「CYD coverage 全解」;還能宣稱「JPM class 已解(0%→100%,corpus 9/11→10/11),GS 維持誠實 pointer 並標明是另一個 class」 | FG-SEC-008 |
| pre-2001 純文字 SGML 世代**不支援**(無修復)| 削弱「任何年代的 10-K 都能抽」;還能宣稱「誠實 unsupported、partition invariant 成立(tiled=true)、零 silent drop」。正解是 text-mode normalizer 或維持 unsupported class | FG-SEC-009 |
| selector 漂移是 local mock site 的注入式漂移(可控、可重現)| 削弱「真實網站泛化」;還能宣稱「真實網站有初步外部量測 33.3%→44.4%→61.1%(合成估計、n 小),且明標不可與官方 leaderboard 比較」 | FG-BROWSER-001 |
| 對抗式稽核的 per-agent 逐一輸出未完整留存 | 削弱「agent 數量 / 內部投票統計」的一切 claim(**不可重現,一句都不能講**);還能宣稱「workflow 方法留存,FG-SEC-001~004 各有 accession-level evidence/tests」 | 稽核方法本身 |
| verifier landmark/grounding 契約量的是「頁面對」而非「交付對」(**已知結構性弱點**)| 削弱「pass = 使用者拿到有價值的東西」;還能宣稱「已知 skip-link 規則已修 + regression test;false pass 如實計入 61.1% 分子,不扣掉美化」。Remaining:(1) gate 擴充需由新失敗樣本驅動 (2) scorer 納入 answer 內容 (3) live 契約升級答案軸 | FG-BROWSER-008 |

> **這份畫廊的收尾不是「我修好了幾條」,是「我列得出還有幾條沒修、以及每一條各削弱了我哪一句話」。一份沒有 failure gallery 的系統,不是沒有 failure,是沒有人去看。**
