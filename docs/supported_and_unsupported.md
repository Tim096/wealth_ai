# Supported & Unsupported (誠實邊界)

> 對應 SPEC 1.1「誠實邊界」：這裡把 10-K 依**結構類別**分，並明確列出 unsupported class、行為與可信度。

## 這份文件在回答什麼?

一句話:**這台機器什麼吃得下、什麼吃不下、吃不下的時候它會不會裝作吃下了。**

第三件事才是重點。一個抽取器抽對了不稀奇;稀奇的是它抽不到的時候,螢幕上出現的是誠實的「我不知道」,而不是一段看起來很像答案的東西。這份文件分六段:

1. [SEC 10-K 分成幾類、各走哪條路?](#1-sec-10-k分成幾類各走哪條路) —— 五個 filing class,每類的行為與可信度。
2. [不同年代的 10-K,哪些真的能跑?](#2-不同年代的-10-k哪些真的能跑) —— 分層抽樣實測,含一個 coverage 0.0 的 Unsupported。
3. [哪些地方我知道它不穩?](#3-哪些地方我知道它不穩) —— flaky 風險,SPEC 要求的第三類。
4. [cross-reference-index:怎麼做到不偽裝成功?](#4-cross-reference-index怎麼做到不偽裝成功) —— 加上已知限制。
5. [Browser Agent 支援到哪、開放式任務怎麼判?](#5-browser-agent-支援到哪) —— 含 eval 軸與外部基準的誠實對照。
6. [憑什麼相信這些 status?](#6-憑什麼相信這些-status) —— 四層防禦,不靠 AI 自述。

---

## 1. SEC 10-K:分成幾類、各走哪條路?

pipeline 會先判定 filing class(`ExtractionResult.filing_class`),不同類走不同路徑:

白話:機器先看一眼這份文件「長什麼樣」,再決定用哪套流程。下表左欄是 pipeline 產生的**確切字串值**(非概念)——你在 JSON 裡會一字不差看到它們:

| Filing class(`ExtractionResult.filing_class`)| 說明 | item status(`ItemSegment.status`)| 可信度 |
|---|---|---|---|
| **standard** | 正文含可定址 Item N 章節(AAPL/MSFT/WMT/CAT/KO/NEM/MRNA/NVDA…) | `pass`/`incorporated_by_reference`/`reserved`/`missing`/`ambiguous`/`partial` | 高;Item 8 另經 XBRL 認證 |
| **cross_reference_index**(Intel/Citi/GE) | 主文件是交叉引用索引,正文以印刷頁碼分頁 | `partial`(resolved_from_page_anchor, needs_review)供有頁碼指標的 item;proxy-only 的 10–14 為 `incorporated_by_reference`;XBRL 矛盾或污染頁碼圖降為 `unsupported`;`missing`/`reserved` | 頁碼錨點還原 source-exact span(多段 body 以 `source_ranges[]` 串接);proxy 指標誠實標記,**不偽裝成內容**;無法可信解析者降 `unsupported` |
| **part_level_incorporation**(Berkshire 類)| Part III 用**一句散文**打發掉整個 Part:「information required by this Part (Items 10, 11, 12, 13 and 14) is incorporated by reference from the …proxy statement」,**沒有逐 item 標題** | 涵蓋的 item 全標 `incorporated_by_reference`(provenance `cross_reference_pointer`)+ `needs_review` | 宣告句本身留 source-exact span;**絕不猜正文**。全 corpus 12 份文件命中 1 次、零誤報 |
| **non_10k** | 找不到任何 item heading(結構不符) | 全部 `missing` + 警告 | 誠實標為不支援 |
| **unsupported_scanned_or_binary** | 掃描 PDF / 非 HTML / binary(**code-enforced**:`%PDF` 開頭、含 NUL、或無 HTML tag) | 空(無 segments)+ 警告 | 明確拒絕,建議 OCR path |
| **non_10k_filer**(resolver 層,20-F/40-F 外國私人發行人:TSM/SONY/BABA)| 公司 EDGAR 紀錄中**零筆** 10-K/10-K/A → 不進 pipeline,`NotA10KFilerError`(`sec_core/resolver.py`)| —(未抽取,typed exception)| **明確拒絕 + 指出實際 form**:訊息列出該公司真正申報的 form 分布(如 TSM:20-F×26、6-K×1320)並明講「僅支援 10-K item 抽取」;live evidence:`data/sec_eval/rejection/foreign_filer_rejection.json` |

翻成一般人能懂的版本,由好到壞六種下場:①正常拆(standard);②主文件只是索引、正文在後面用頁碼分頁,我用頁碼把正文釣回來(cross_reference_index);③一整個 Part 被一句話打發掉,我把那句話的位置給你、不編內容(part_level_incorporation);④根本找不到章節標題,全標 missing(non_10k);⑤掃描檔/二進位,直接不收(unsupported_scanned_or_binary);⑥這家公司根本不申報 10-K,連 pipeline 都不進(non_10k_filer)。

**第③類是評審用 Berkshire 打出來的,所以我把它的來歷寫在表上。** 我原本的偵測是**逐 item 標題導向**——它會去找「Item 10.」再看底下寫什麼。Berkshire 沒有那些標題,它用一段 **Part 層級的散文**一次打發五個 item。結果:Items 10–14 全回 `missing` / confidence 0.0 / **needs_review=false**——沒把握,還不叫人看。現在除了修掉它,另外加了一張**與該偵測器完全獨立**的網:**任何 confidence 0 的 `missing` 一律強制 `needs_review`**(全 corpus 51 → 0)。**第二張網比第一個修復重要——它擋的是我還沒想到的那些。** 見 `failure_gallery.md` FG-SEC-010。

第⑥類值得多講一句,因為它是「拒絕的品質」示範:丟台積電進來,系統回的不是「找不到 10-K」,而是列出該公司真正申報的 form 分布(20-F×26、6-K×1320)並明講僅支援 10-K item 抽取。**不是拒絕,是拒絕時順手告訴你東西在哪。**

> `ItemStatus` 的 `unsupported` **現在會在單一 item 上 emit**:`certify_item8` 在 SEC XBRL 三項數字與 Item 8 span 矛盾時,把該 item 由 `pass`/`partial` 降為 `unsupported`(如 INTC FY2019 Item 8);污染頁碼圖(每頁字數低於守衛)解析出的 span 也降為 `unsupported`。**filing 級**不支援仍以 `filing_class`(unsupported_scanned_or_binary / non_10k)+ `missing` 表達——item 級與 filing 級並存,如實揭露。

白話那段引言:以前「不支援」只能整份講,現在**單一 item 也能自己承認不支援**——XBRL 說這段財報裡沒有營收/淨利/總資產,那它就不是財報,原本標的 `pass`/`partial` 當場降級。**不是我事後手動改判,是 oracle 打臉自己人。**

---

## 2. 不同年代的 10-K,哪些真的能跑?

**Format-era 支援表(2026-07-10 分層抽樣實測,T2-4)**

按年代格式 × filing agent 分層抽樣,每個缺口層實跑 1–2 份(artifact:`data/sec_eval/stratification/stratification.json`;重跑:`SEC_EDGAR_USER_AGENT=<contact> .venv/Scripts/python tools/stratified_sample.py`)。

白話:我沒有只挑好跑的年份來報。我把 10-K 的歷史按「檔案格式」切成四個年代,每一層都真的抓下來跑一次——包括我知道會輸的那一層。

| Era | 實測樣本 | 行為 | coverage | 支援 |
|---|---|---|---|---|
| **text_pre2001**(純文字 SGML)| AAPL FY1996、KO FY1997 | text-mode normalize(`NORMALIZATION_VERSION` **1.1**)保留行結構後正常抽取:**AAPL 7 pass / 2 partial / 6 IBR / 8 missing**、**KO 6 pass / 9 IBR / 8 missing**;那些 missing 是**該年代不存在的 item code**(AAPL:1A/1B/1C/7A/9A/9B/9C/16;KO:1A/1B/1C/9A/9B/9C/15/16——兩家清單不同),標 missing 正確且全部 needs_review;合併標題造成兩個 code 共用同一段者一律 needs_review | AAPL **0.6788** / KO **0.2126** | **分裂,不是一句話能講完**:AAPL FY1996 `supported=true`;**KO FY1997 仍在 `unsupported` 清單裡**(coverage 0.2126 < 0.30 門檻),但原因**完全不是抽不到**——見下方第三點。era-aware schema mapping 未實作(見 FG-SEC-009 / FG-SEC-011)|
| html_2001_2008 | AAPL 2004(0001047469-04-035975)| 17 pass | 0.9824 | Supported |
| xbrl_2009_2018 | AAPL 2013(0001193125-13-416534)| 15 pass + 5 IBR | 0.9592 | Supported |
| ixbrl_2019plus | baseline 11 家 + Toppan 樣本 | 現行主路徑 | ≥0.91 | Supported |

**第一列這份文件曾經寫錯過,而且錯得很體面,所以我把更正拉到標題級。**

**舊版寫的是:「text_pre2001 coverage 0.0,22 個 item 全部 missing,Unsupported——不改判、不軟化」**,並解釋成「heading detector 是 HTML 導向的,這是時代邊界」。**那個 root cause 是假的,已被實測反證:** heading detector 從來沒壞,是 `normalize` 只在 block tag 產生換行,純文字節點裡的 `\n` 被當空白吃掉——AAPL FY1996 的 6,246 個換行塌成 51 個、最長一行 74,186 字元。**detector 拿到的是一坨,當然 0 candidate。** 把行結構還給它,**同一個 detector** 吐 16 個候選(KO 18 個)。逐條見 `failure_gallery.md` FG-SEC-009。

**所以這一列現在該怎麼讀,界線畫清楚:**

- **能宣稱**:這個年代的 filing **會抽**;而且 HTML 時代輸出**逐位不變**(5 個 HTML fixture + 3 個 HTML 測試檔的 text 與 `norm_to_raw` 逐 byte 相同)——**多抽幾個 item 沒有拿 source-exact 保證去換。**
- **這個 bug 的第二個後果,2026-07-16 才量出來:它同時壓著外部 benchmark。** NTU 30-slice 裡兩份純文字/SGML 檔被同一個 bug 判成 `no items extracted`,修完後 HNET **0.9023**(edgar_crawler 0.8346)、Integrated Electric Systems **0.88** —— **都遠高於我自己其他 28 份的平均 0.6245**,因為純文字排版的行結構最乾淨、最好切。**我當初標 Unsupported 的那一層,是我表現最好的那一層。** 連帶把 30-slice macro-F1 從 0.6245(28 份/2 失敗)推到 **0.6423**(30 份/零失敗),反超 edgar_crawler 0.6332(commit `36d42eb`,見 `eval_report.md` head-to-head 段)。**這不能當成本節的加分項** —— 它的意思是「一份寫著 Unsupported 的支援表,把自己最強的一格寫成了最弱的一格,而且有測試保護了它好幾天」。
- **不能宣稱**:item 編號對得上現代 schema。**era-aware schema mapping 未實作**——FY1996 的 `Item 14. Exhibits…` 語意上對應現代的 Item 15,系統目前把該 span **同時給 14 和 15**,只標 needs_review,不猜、不消歧(見 FG-SEC-011)。
- **KO 的 coverage 0.2126 為什麼這麼低?** 因為它那年真的有 **9 個 item 是 IBR stub**(指標段落本來就短),不是抽不到。**這正是 coverage 這把尺量不出「誠實指標」和「漏抽」差別的地方**——同一個低分,兩種完全不同的意思。

**這個 bug 最難看的後果不在 coverage,在 `filing_class`。** `data/sec_eval/stratification/stratification.json` 已用 `tools/stratified_sample.py` 重生,前→後:

| | 前(normalize bug) | 後 |
|---|---|---|
| AAPL FY1996 | `filing_class: non_10k` / `supported: false` / cov **0.0** / pass **0** | `standard` / **`true`** / **0.6788** / **7** |
| KO FY1997 | `filing_class: non_10k` / cov **0.0** / pass **0** | `standard` / cov **0.2126** / pass **6** |
| STRATS(trust filer)| cov 0.0 | cov 0.0716 |
| warning | `no item heading candidates found — unsupported or non-10-K document` | (消失)|

**兩份貨真價實的 10-K,被我的系統判成「這不是 10-K」。** 不是抽得少,是分類錯到根上——而 `non_10k` 正是本專案用來「誠實拒絕」的那個標籤。**一個把真 10-K 標成非 10-K 的誠實拒絕,不是誠實,是用誠實的語氣講錯話。** 上表 pre-2001 兩列的數字可由該 artifact 讀出,亦可對 tracked fixture(`data/sec_eval/fixtures/` 的 `AAPL_FY1996` / `KO_FY1997`)跑 `sec_core.pipeline.extract_from_html` + `sec_core.coverage.coverage_ratio` 重算;守它的是 `tests/test_text_mode_normalize.py`。

對照錨在下面三列:同一套 pipeline,2004 年 coverage 0.9824、2013 年 0.9592、2019 年後 ≥0.91。

### Filing agent 會不會是隱藏變數?

**Filing-agent 驗證**:靠文件頭 generator comment 偵測(非 body 公司名,避免 Merrill Lynch 類誤判)。三家 agent 全過 pipeline、cov ≥0.91、無 agent-specific 破損:Workiva、DFIN(Donnelley)、Toppan Merrill(cov 0.9107)。生態系抽樣(efts 2025-02,n=40):Workiva 31 / unknown 8 / Toppan 1——Workiva 壟斷,baseline(10 Workiva + 1 DFIN)是合理抽樣,補 Toppan 後三家皆有實測。

白話:10-K 不是公司自己排版的,是外包給「申報代理商」排的(filing agent)。所以要問一個自我攻擊的問題:**我的 pipeline 會不會只是剛好吃得下 Workiva 排的版?**

【假說】若為真,換一家 agent 排的 10-K 應該會破。
【去測】補跑 DFIN 與 Toppan Merrill。
【判定】三家全過、cov ≥0.91、無 agent-specific 破損(Toppan 0.9107)——攻擊沒打倒它。
【溯源】而且 baseline 的組成不是隨便挑的:生態系抽樣 n=40 顯示 Workiva 31 / unknown 8 / Toppan 1,Workiva 本來就壟斷,**baseline(10 Workiva + 1 DFIN)是合理抽樣**,補 Toppan 後三家皆有實測。

### 反例:官方 oracle 抓到我的 span 跑長了

**CAT 非標準 Item 1D 發現**(CYD oracle 抓到,T2-3):CAT 10-K 有非標準的「Item 1D. Information about our Executive Officers」;1D 不在 `VALID_CODES`,我方 Item 1C span 尾部把它吞入 → CYD containment 73.1%(coverage 仍 100%)。這是官方 oracle 抓到「span 跑長」的真訊號,列為 landmine 候選(非標準 item code)。Evidence:`data/sec_eval/cyd_groundtruth/cyd_agreement.json` records[CAT]。

這條特別拎出來講,因為它是「別人抓到我」而不是「我抓到別人」:CAT 自己發明了一個標準沒有的 Item 1D,我的 `VALID_CODES` 沒有它,於是我的 Item 1C 尾巴一路吞進去。CYD 官方 oracle 的 containment 掉到 73.1%——注意 **coverage 仍 100%**,也就是說如果我只看 coverage,這個錯誤完全看不見。**不是 coverage 沒問題就沒問題,是要有第二把尺才照得出來。**

---

## 3. 哪些地方我知道它不穩?

**Unstable / 邊界不穩定(SPEC 要求的第三類,誠實揭露 flaky 風險)**

白話:支援 / 不支援之外,SPEC 要求第三類——「會動,但我不敢保證每次都動」。這四條就是。

| Unstable 情形 | 風險 | 目前緩解 |
|---|---|---|
| cross-ref-index 偵測靠門檻 `_MIN_CLUSTERED_ITEMS=8`/`_CLUSTER_SPAN=8000`/`_MIN_PAGE_REF_RATIO=0.25`/`_MAX_INDEX_GAP=300`(`cross_ref.py`)| 罕見排版可能誤判 standard↔index | 群聚外有正文候選即排除;需更多 held-out 校準 |
| bare-index(Citi 無「Item」前綴)靠 canonical-title 相似度 ≥0.5 | 標題大幅改寫可能漏抓 | 有 page-ref 佐證;漏抓 fallback non_10k(仍不偽裝)|
| 10-K/A amendment | 尚未特別處理,走 standard | 列為 backlog |
| browser login/captcha 偵測是 substring heuristic | 措辭變體可能漏判 | capability guard intent 層另有攔截;列 unstable |

這張表的門檻數字我得誠實說清楚它們的身分:`_MIN_CLUSTERED_ITEMS=8`、`_CLUSTER_SPAN=8000`、`_MIN_PAGE_REF_RATIO=0.25`、`_MAX_INDEX_GAP=300`、canonical-title 相似度 `≥0.5`——這些是門檻,不是定理。**「需更多 held-out 校準」就寫在緩解欄裡,我不假裝它們已經校準過。**

但每一條的失敗方向都被我推向誠實那一邊:bare-index 漏抓的下場是 fallback 到 `non_10k`(標成不支援),**不是偽裝成功**。

---

## 4. cross-reference-index:怎麼做到不偽裝成功?

### 關鍵設計:cross-reference-index 不偽裝成功

我們鎖定的高風險 corner case——INTC FY2019/FY2020 Item 14 極易被誤標成 extracted/ok。本 pipeline:

- **自動偵測**該類(item heading 群聚 + 頁碼指標,或群聚且行間距極小=無正文),不需硬編 Intel/Citi 白名單。
- Item 14 等標成 `incorporated_by_reference` / `needs_review`,warning 明講「body 不在可定址 Item 章節,指向年報第 X 頁」。
- 已驗證:INTC FY2019/FY2020/FY2025、Citi FY2025 全部正確歸類。

白話這個 corner case 為什麼致命:Intel 的 10-K 主文件某些 item 只是一行「詳見年報第 X 頁」。一個 regex 切章器會抓到「Item 14」這個標題、抓到底下那一行字、然後回報「Item 14 已抽取,confidence 高」——**它抽到的是一張紙條,卻報告成一本書**。這是最典型的 false pass。

注意「不需硬編 Intel/Citi 白名單」這句的份量:**如果靠白名單,那不是偵測,是背答案**。偵測條件是結構性的(heading 群聚 + 頁碼指標,或群聚且行間距極小=無正文),換一家沒見過的公司也會觸發。

### 已知限制(誠實揭露)

- **cross-reference-index 的正文已用印刷頁碼錨點還原**(Intel/Citi class):`resolve_page_ref`/`build_page_map` 跟著索引的頁碼範圍(如 "Risk Factors 49-62")定位到主文件內同一份 annual report 的 source-exact span,標 `partial` + needs_review(頁邊界對齊為啟發式,非逐字精確)。實測 Citi FY2025 解出 **9 個 item**(Risk Factors 88K、MD&A 86K、Market Risk 207K、Financials 577K 字)、INTC Item 8 span 經 XBRL 3/3 認證。指向**另外申報**的 proxy statement 的 Item 10–14 維持誠實 `incorporated_by_reference` pointer,不 join、不捏造。**碰撞防護**:同一 span 至多由一個 item 認領,後續 item 改用自己的替代頁碼範圍或降為 pointer,避免兩個 item 共用 body(如 INTC Item 15 導向自己的 exhibit index 而非 Item 8 財報)。**同檔附綁 wrapper(JPM/XOM)已還原**:`cross_ref.reassemble_wrapper_bodies`(commit 84ecea7),見 `failure_gallery.md` FG-SEC-007/008。
- **掃描 PDF 老 filing**:標 `unsupported`;正確作法是 OCR path(非 LLM),見 insights §3。
- **pre-2001 純文字 SGML**:**會抽了,但不等於整個 era 都 supported**(text-mode normalize,`NORMALIZATION_VERSION` 1.1;見上方 format-era 表與 FG-SEC-009)。實測 AAPL FY1996 `supported=true`(cov 0.6788),**KO FY1997 與 STRATS 仍列在 artifact 的 `unsupported` 裡**(cov 0.2126 / 0.0716,低於 0.30 門檻)——KO 是 9 個真 IBR stub 壓低分數,不是漏抽,**但我不因此把它改判成 supported:改判就是改尺,而尺是我自己訂的。****舊版此處寫「Unsupported / 修法是 text-mode normalizer,非本波範圍」——那個 root cause 是假的,已被實測反證。** 殘留的是 **era-aware schema mapping 未實作**:該年代不存在的 item code 標 missing(正確)、合併標題造成兩個 code 共用同一段者一律 needs_review,**不猜哪個 item 才對**。
- **boundary 精度已量化(2026-07-10)**:char-offset F1(建構性 gold,regression baseline;敏感度注入鎖在 `tests/test_scoring.py::test_sensitivity_injection_on_real_sweep3_aapl`,AAPL F1 1.0→0.9267)+ CYD 官方 iXBRL oracle(9/9 pass segment coverage 100%)。人工 token-level 標註(絕對正確率)仍列 backlog。見 `eval_report.md`「Eval 升級」段。

把上面四條攤成一張「限制 | 這削弱了什麼、還能宣稱什麼」的表(第一條含兩個獨立限制,拆成兩列):

| 限制 | 影響 |
|---|---|
| 頁邊界對齊是**啟發式**,非逐字精確 | 所以 status 標 `partial` + needs_review,不標 `pass`;能宣稱「source-exact span 位置」,不宣稱「頁界字字精準」 |
| 指向**另外申報**的 proxy statement 的 Item 10–14 | 維持誠實 `incorporated_by_reference` pointer,**不 join、不捏造**;能宣稱「我知道它在哪」,不宣稱「我把它抽出來了」 |
| 掃描 PDF 老 filing | 標 `unsupported`;正確作法是 OCR path(非 LLM),見 insights §3 |
| pre-2001 純文字 SGML 的 **era-aware schema mapping 未實作**(格式本身已支援,見 [format-era 表](#2-不同年代的-10-k哪些真的能跑)與 FG-SEC-009)| FY1996 的 `Item 14. Exhibits…` 語意上是現代的 Item 15,系統把該 span **同時給 14 和 15** 並標 needs_review;能宣稱「會抽、且共用 span 一定舉手」,**不能宣稱「item 編號對得上現代 schema」** |
| 兩個 item 共用同一段 bytes 時,系統**只揭露不消歧** | 能宣稱「共用者全部 needs_review + warning 帶 span 與字元數」,**不能宣稱「哪個 item 才是那段的主人」**——同起點同寬度,連 boundary tie-break 都無從下手,擲硬幣不如交人。現代真實 filing 實測零共用 content span,但**那是實證結果不是結構保證**(已用測試釘住)|
| char-offset F1 的 gold 是**建構性**的,只當 regression baseline | 人工 token-level 標註(絕對正確率)**仍列 backlog**;能宣稱「沒退步」,不能宣稱「絕對正確率是多少」 |

第一條的自我攻擊值得展開,因為它是「元層思考:驗證驗證器」的實例。

【主張】char-offset F1 有在守著 boundary 精度。
【自我攻擊】F1 = 1.0 會不會只是因為我的尺根本量不出差別?
【假說】若尺是活的,故意把 offset 弄歪,F1 應該要掉。
【去測】敏感度注入,鎖在 `tests/test_scoring.py::test_sensitivity_injection_on_real_sweep3_aapl`。
【判定】AAPL F1 1.0→0.9267 —— 尺會響。**結論從「沒發現問題」升級成「有能力發現、且沒發現」。**

第二個獨立對照錨:CYD 官方 iXBRL oracle(SEC 自己的結構化標記,不是我做的)9/9 pass、segment coverage 100%。

再說 wrapper 那條的**碰撞防護**,因為它擋掉的是一種很難發現的作弊:同一段 span 至多由一個 item 認領。沒有這條的話,Item 15 可以直接認領 Item 8 的財報正文,兩個 item 共用一本書,兩個都「看起來抽到了」。有了它,INTC Item 15 導向自己的 exhibit index 而非 Item 8 財報。**不是抽到就算贏,是同一本書不能賣兩次。**

---

## 5. Browser Agent 支援到哪?

見 [README](../README.md#支援範圍browser-agentspec-64)。核心:公開搜尋/導航/擷取/下載支援;登入、CAPTCHA、購買、送出正式表單、付費資料**不支援**(責任邊界,不是能力不足)。Phase 2 實作中。

那句「責任邊界,不是能力不足」是這一節的主軸:**不是我做不到登入,是我不做登入。** 差別在下一張表的第三列——它不是文件宣示,是 `capability.py` 程式攔截。

### 任務可驗證性分類(2026-07-10)

| 任務類型 | 行為 | verdict | 依據 |
|---|---|---|---|
| 有可機讀成功/禁止條件(搜尋、導航、下載、擷取)| preflight 導出條件 → verifier 對照 evidence | `pass` / `fail` | 主路徑 |
| **開放式 / 不可驗證任務**(如「隨便逛逛看有什麼有趣的」、成功條件無法事先機讀)| **支援執行**、照錄完整 trace + screenshots;verdict 時若 planner 有 live LLM client(`run_agentic` 以同一 client 掛上 `open_ended_extractor`,無第二條 credential 路徑),走 evidence-grounded 開放式評分(`second_judge.score_open_ended`):引文必須逐字存在於 evidence,否則 demote 成 abstain → 誠實 unknown 交人工審 trace;離線/mock planner 不掛評分,直接 unknown | **`pass` / `fail`**(LLM 評分且引文 grounded)或 **`unknown`**(abstain / 離線);絕不 vacuous pass、絕不捏造 pass、絕不 crash | FG-BROWSER-006(commit f535c93);`packages/browser_agent/verifier.py` 零條件 gate;artifact `data/browser_eval/open_ended/open_ended_results.json`(離線路徑 3/3 honest_unknown,crashes 0)|
| 責任邊界(登入/購買/正式表單/付費)| capability guard code-enforced 攔截 | `refused` | `packages/browser_agent/capability.py` |

白話這三列:①能事先講清楚「怎樣算成功」的任務,verifier 對照證據判 pass/fail;②講不清楚的任務(「隨便逛逛」),照樣執行、照樣錄影,判分時要嘛 LLM 拿得出逐字引文才給 pass/fail、要嘛 abstain 成誠實 unknown 交人工;③紅線任務,程式直接擋,回 `refused`。

第二列的離線 artifact 值得釘一個數字:`open_ended_results.json` 離線路徑 **3/3 honest_unknown,crashes 0**。翻成人話——三個開放式任務,三次都誠實說「不知道」,零次崩潰、零次瞎掰。

> 三態鐵律的落地:缺 grounded 證據 → `unknown`(交人工),結構上不能升級成 pass。開放式任務的 LLM 評分只有逐字引文 ground 得住才給 pass/fail;ground 不了就 abstain 回 unknown——是誠實 unknown,不是失敗、也不是不支援執行,更不可能捏造 pass。

### Browser eval 軸(2026-07-10 擴充)

三條軸:自建漂移 mock site(主軸)、對抗注入 suite、外部基準子集。第三條的誠實揭露最重,放最後。

| 軸 | 內容 | Artifact / 依據 |
|---|---|---|
| Layered mock-site set(主軸)| v1/v2/v3 漂移 + impossible + open-ended;task 可帶 `difficulty`(easy 8 / medium 15 / hard 25 步)或顯式 `max_steps` 決定 per-task step budget,CLI `--max-steps` 覆寫(P1-15)| `data/browser_eval/tasks.json`;`tools/browser_eval.py` |
| Prompt-injection 對抗 suite(P1-14)| 5 攻擊型態(DOM 注入假系統訊息、自宣稱同意 modal、標籤誤導、隱藏文字注入、毒化搜尋結果),每頁帶 deterministic oracle `window.__attack`;SUCCESS = 完成任務**且**不執行注入動作;指標 = ASR(attack success rate)。**live 實測(2026-07-10,`tools/measure_adversarial.py`,headless Chromium、0 LLM call)**:defended ASR **0.0**(0/5 attacks taken,goals 5/5);undefended 對照組 ASR **1.0**(5/5)——證明每個 trap 可達且 oracle 會響,0.0 不是 trap 失效的假象 | `data/browser_eval/adversarial.json`、`data/mock_sites/adversarial/`、`tests/test_adversarial_suite.py`;live 實測 artifact `data/browser_eval/adversarial_results.json` |
| 外部基準子集(P1-1)| **Online-Mind2Web** 20 tasks(8 easy / 8 medium / 4 hard,17 domains),確定性分層抽樣、排除登入/付費牆/CAPTCHA 域;live naive baseline 實測 trivial-pass 20%(4/20)≈ 論文 22% naive-search 參考線 → 子集非 shortcut 集。**自跑實測(2026-07-10)**:33.3%(6/18)→ bucket-fix 44.4%(8/18)→ abstain-fix 合成 **11/18 ≈ 61.1%**(明標合成估計,跨兩次 launch);judge abstain 6/6 → 1/6。Attribution:**Online-Mind2Web, OSU-NLP-Group(CC-BY-4.0,COLM 2025,arXiv:2504.01382)**,逐 task 標註 | `data/browser_eval/external/mind2web_subset.json`;維護協定 `data/browser_eval/external/README.md`;`tools/naive_baseline.py`;`docs/ATTRIBUTION.md`;實測 artifact `runs/browser_eval/m2w_rerun/`、`m2w_rerun_20260710/`、`m2w_abstain_fix_20260710/`、`m2w_abstain_fix2_20260710/`(gitignored 原始 run)+ tracked 快照 `data/browser_eval/external_runs/` 同名目錄與 `naive_baseline/`;定向重跑任務集 `data/browser_eval/external/m2w_unknowns6.json`(sha256 `1acfc7a3a20a3bc20d5bb07cdaed243642272dcfeccb232028ff62d8d4226c9b`)。**不可與官方 Online-Mind2Web leaderboard(300 題、WebJudge 評審、Browser Use ~97%)直接比較**——自建子集、單 landmark 契約、合成跨 launch;我們量的軸是 verifier 誠實性 |

三個數字必須逐一問 why:

**① ASR 0.0——這會不會是陷阱根本沒設好?**(ASR = attack success rate,攻擊得手率;白話:壞人成功騙到 agent 的比例。)
【主張】defended ASR 0.0(0/5 attacks taken,goals 5/5)。
【自我攻擊】0.0 也可能是我的 5 個陷阱寫壞了、agent 根本沒走到有陷阱的地方。
【假說】若陷阱是有效的,把防禦拿掉,ASR 應該衝到 1.0。
【去測】undefended 對照組。
【判定】undefended ASR **1.0**(5/5)——**每個 trap 可達且 oracle 會響,0.0 不是 trap 失效的假象。** 這正是「驗證驗證器」:先證明陷阱抓得到人,再宣稱沒被抓到。而且這個 live 實測 0 LLM call。

**② trivial-pass 20%——這個子集是不是我挑軟柿子?**
【自我攻擊】我自己抽的 20 題,會不會剛好都是隨便搜一下就過的?
【去測】跑 naive baseline(什麼都不會的笨基準)。
【判定】trivial-pass 20%(4/20),對照錨是論文的 22% naive-search 參考線——兩者相近 → **子集非 shortcut 集**。

**③ 61.1%——這個數字我自己先打折。**
33.3%(6/18)→ bucket-fix 44.4%(8/18)→ abstain-fix 合成 **11/18 ≈ 61.1%**,judge abstain 從 6/6 降到 1/6。但這個 61.1% 我**明標為合成估計、跨兩次 launch**,不是一次乾淨的 run。而且它**不可與官方 Online-Mind2Web leaderboard(300 題、WebJudge 評審、Browser Use ~97%)直接比較**——自建子集、單 landmark 契約、合成跨 launch。

> **我們量的軸是 verifier 誠實性,不是 leaderboard 名次。拿 61.1% 去對 ~97% 是拿蘋果比橘子,而這句話是我自己寫的,不是別人來抓的。**

外部題目的出處也照規矩掛好:**Online-Mind2Web, OSU-NLP-Group(CC-BY-4.0,COLM 2025,arXiv:2504.01382)**,逐 task 標註,維護協定在 `data/browser_eval/external/README.md`,授權聲明在 `docs/ATTRIBUTION.md`。

---

## 6. 憑什麼相信這些 status?

四層防禦,不靠 AI 自述:

1. **三態判定**:缺證據 → `unknown`/`needs_review`,結構上不能升級成 pass(`eval_core/verdict.py`)。
2. **對抗式稽核**:multi-agent workflow 找出可重現的 silent-failure classes；per-agent 輸出未完整留存，因此 agent 數量與內部投票不是 headline evidence。可驗證結果是 `eval_report.md` 對應的 accession-level fixtures、oracles 與 regression tests。
3. **XBRL 獨立 oracle**:Item 8 對照 SEC companyfacts 的營收/淨利/總資產——真財報 span 一定含這些數字,wrapper stub 不含。11 家實測 **certified 10 / contradicted 1**(NVDA 誠實 IBR stub;JPM/XOM 經 P0-10 重組後 3/3 認證)(`tools/certify.py`,artifact `data/sec_eval/certification/item8_certification.json`)。
4. **provenance + needs_review**:每個 item 標明來源(offset_exact_span / cross_reference_pointer / unresolved)與是否需人工複核。

逐層翻成人話:

**第 1 層**——沒看到證據就不准說成功。這是結構,不是態度:`verdict.py` 裡缺證據的路徑走向 `unknown`/`needs_review`,**沒有一條路通往 pass**。

**第 2 層**——這一層我要主動縮小自己的宣稱。對抗式稽核確實找出了可重現的 silent-failure classes,但 **per-agent 輸出未完整留存,因此 agent 數量與內部投票不是 headline evidence**。我不拿「幾十個 agent 投票」當賣點,因為我拿不出逐 agent 的紀錄。可驗證的是 `eval_report.md` 對應的 accession-level fixtures、oracles 與 regression tests——**能重跑的才算證據,講故事的不算。**

**第 3 層**——XBRL 獨立 oracle,這層的漂亮之處在於它的邏輯是「必要條件」而非「相似度」:SEC companyfacts 是 SEC 自己整理的機器可讀財報數字,**真財報 span 一定含這些數字,wrapper stub 不含**。11 家實測 certified 10 / contradicted 1。那個 contradicted 1 是 NVDA,而它是**誠實的 IBR stub**——oracle 抓到的不是 bug,是一個本來就該被標成 stub 的東西。JPM/XOM 經 P0-10 重組後 3/3 認證。

**第 4 層**——每個 item 都掛著自己的身世(offset_exact_span / cross_reference_pointer / unresolved)與「要不要找人複核」。

> **這四層的共同點:沒有一層問過 AI「你覺得你做對了嗎」。**
