# Prior Art & Positioning:哪一段肩膀是別人的,哪一段路是我自己走的

> 由兩個 research agent(web search)彙整,2026-07-10。目的:誠實對照既有開源、標明我們能借鑑什麼、以及我們的差異化在哪(哪些是 novel、有無 prior art 可 defer)。

**白話:**prior art = 前人已經做過的東西。這份文件在回答一個很不客氣的問題 ——

> 「這些東西 GitHub 上不是都有現成的嗎?你到底做了什麼?」

我不躲這一題,我把它攤開來答。**我不是從零發明,是站在巨人的肩膀上** —— 但一個誠實的人必須講得出:**哪一段肩膀是別人的、哪一段路是我自己走的、哪一段肩膀碰了會有法律麻煩。** 這份文件就是那條界線。

### 這份文件怎麼讀?

| 段落 | 一句話功能 |
|---|---|
| [Task 1 — Browser Agent](#task-1--browser-agent) | 瀏覽器 agent 這條線:巨人是誰、我借了什麼、我多做了什麼 |
| [Task 2 — SEC 10-K Extractor](#task-2--sec-10-k-extractor) | 財報擷取這條線:最接近的對手是誰、我贏在哪、我沒有的又是什麼 |
| [對本專案的行動項](#對本專案的行動項) | 哪些能安全依賴、哪些借思路但絕不能抄 code、對外主打哪三點 |

推進方向由淺入深:**別人做到哪 → 我站上去之後多走了哪一步 → 這一步有沒有 prior art 可以 defer(可以推給前人)。**

---

## Task 1 — Browser Agent

### 巨人的肩膀長什麼樣?

先把表格裡會出現的術語就地翻成人話,免得讀者被縮寫擋在門外:

- **action space**:agent 能對網頁下的動作清單(點、打字、捲動…)。
- **DOM index 標註**:把網頁元素編號,讓 LLM 用號碼指東西,不用寫 CSS selector。
- **self-healing**:網站改版、selector(定位字串)失效時,系統自己找回正確元素。
- **action caching**:同樣的動作記起來,下次不用再問 LLM 一次。
- **a11y-tree(accessibility tree)**:給輔助工具用的網頁語意樹 —— 白話:一份「這頁上有哪些按鈕、叫什麼名字」的乾淨清單,比原始 HTML 好懂得多。
- **DOM distillation**:把又肥又亂的網頁原始碼濃縮成 LLM 讀得動的精華。
- **三態契約**:成功 / 失敗 / **unknown(不知道)** 三種結局,而且 unknown 不准偷偷升級成成功。
- **copyleft**:一種授權條款 —— 白話:你抄了它的 code,你的整份專案就得跟著開源。

| 專案 | 授權 | 我們能借鑑 | 與我們(verification-first)的關係 |
|---|---|---|---|
| [browser-use](https://github.com/browser-use/browser-use) | MIT | 成熟 action space、DOM index 標註;最大宗 prior art | 成功判定多靠 LLM 自評——正是我們三態契約要超越的 |
| [Stagehand](https://github.com/browserbase/stagehand) | MIT | **self-healing + action caching**,與我們 selector memory 幾乎同構;observe() 預檢 | 偏可維護/可快取,我們偏可驗證 |
| [Agent-E](https://github.com/EmergenceAI/Agent-E) | MIT | **與我們最同源**:a11y-tree DOM distillation、注入穩定 id、LLM 限定 skills(非任意 code)——我們 action-JSON + a11y 定位的學術背書(arXiv 2407.13032) | 缺三態契約驗證與 failure taxonomy |
| [Skyvern](https://github.com/Skyvern-AI/skyvern) | **AGPL-3.0** | 視覺定位抗版面漂移的思路(對照我們 v1→v2 drift) | 哲學互補;**勿複製程式碼(copyleft)** |
| [Healenium](https://github.com/healenium/healenium) | Apache-2.0 | selector self-healing 既有領域先例(ML 找最近 locator、持久化) | 純測試域、無 LLM、無任務語意驗證 |

**這張表最誠實的一列是 Agent-E。**它「與我們最同源」—— 白話:我引以為傲的 action-JSON + a11y 定位,人家早就做過,還發了論文(arXiv 2407.13032)。我不會把它寫成「我們獨創」,我把它寫成**學術背書**:別人的論文證明我這條技術路線是對的,這是加分,不是扣分。

### 該跑哪些 benchmark 才算有可信度?

**benchmark(公評的標準考卷)** —— 白話:自己說自己強不算,要去考別人出的題。

> **該跑的 benchmark(建立可信度):** [WebArena](https://github.com/web-arena-x/webarena)(**outcome-based 驗證,與我們 verifier 同哲學**,最該對標)、[WebVoyager](https://github.com/MinorJerry/WebVoyager);經 [BrowserGym/AgentLab](https://github.com/ServiceNow/BrowserGym) 接入最快。

WebArena 為什麼最該對標?因為它跟我一樣是 **outcome-based(看結果,不看 agent 自己怎麼說)**。這是同一種世界觀 —— 對標它,等於讓一個哲學相同的外部裁判來打我。

**誠實標記:這一整段是 roadmap,不是成績。**我在這份文件裡沒有宣稱跑過 WebArena 或 WebVoyager 的任何分數 —— 「該跑」不等於「跑了」。

### 那我到底多做了哪一步?

> **我們的差異化(綜合研究結論):** 沒有任一專案把 **unknown 當一級公民**;a11y-tree self-repair + persistent memory + **綁定三態驗證迴圈**的組合是我們獨有。v1→v2 adversarial drift eval 是現有 benchmark 缺的角度。

翻成一般人能懂的版本:**每一塊積木都是別人發明的,我的貢獻是把它們綁在一起,而且加了一條沒人加的規矩 —— 系統可以說「我不知道」,而且說了就不准反悔。**

> **不是我發明了新積木,是我立了一條新規矩:unknown 是一級公民,不准偷偷升級成 pass。**

---

## Task 2 — SEC 10-K Extractor

### 財報擷取這條線,誰站在我前面?

一樣先翻術語:

- **item regex**:用文字樣式比對去找「Item 1A. Risk Factors」這種章節標題。
- **TOC false-positive filter**:目錄(Table of Contents)裡也寫著「Item 1A」—— 白話:防止系統把目錄的那一行誤認成正文開頭。
- **next-item boundary**:下一個 item 開始的地方,就是這個 item 結束的地方。
- **offset / sha256**:offset = 這段文字在原文的第幾個字到第幾個字;sha256 = 內容指紋 —— 白話:兩個加起來,等於「我從原文第 X 字剪到第 Y 字,剪出來的東西長這樣,你可以自己去對」。
- **XBRL**:公司報給 SEC 的結構化財務數字檔 —— 白話:同一份財報的「機器可讀版數字」。
- **oracle**:獨立的標準答案來源 —— 白話:一個不跟我串供的第三方證人。
- **wrapper 10-K**:正文不在 10-K 本體、而是「以引用方式併入」另一份文件的 10-K。
- **span**:一段有起訖位置的文字。

| 專案 | 授權 | 我們能借鑑 | 與我們(source-exact + XBRL-certified)的關係 |
|---|---|---|---|
| [nlpaueb/edgar-crawler](https://github.com/nlpaueb/edgar-crawler) | **GPLv3** | **最接近的 prior art**:item regex、TOC false-positive filter、next-item boundary、`get_last_item_section()` fallback(WWW 2025 paper)。當作我們超越的 baseline 引用 | regex-only(vs 我們多 detector)、無 offset/sha256、**無 XBRL 驗證**;其 missing-item「抓剩餘文字」正是我們 wrapper handling 修掉的 naive 行為。**copyleft,借思路勿抄 code** |
| [dgunning/edgartools](https://github.com/dgunning/edgartools) | MIT | best-in-class **EDGAR fetch/cache/no-key** + XBRL 標準化財報。可當 fetch/XBRL 依賴或對照 | 用 XBRL *產生報表*,不是*驗證某段文字含報數字*——我們的 novel 之處 |
| [sec-api.io](https://github.com/janlukasschroeder/sec-api-python) | 商用(閉源) | item 變體覆蓋(10-K/A、10-KT)、競品準確度對標 | server-side 閉源,無法借;無 source-exact provenance |
| [alphanome-ai/sec-parser](https://github.com/alphanome-ai/sec-parser) | MIT(停維護) | HTML→semantic tree 當 heading 訊號補強 | 不做 Item 1–16 boundary、無 TOC、無 XBRL |
| [sec-edgar-downloader](https://github.com/jadchaar/sec-edgar-downloader) | MIT | 乾淨 downloader + fair-access user-agent 範式 | 純下載,互補 |

**這張表裡最該講的是 edgar-crawler。**它是「最接近的 prior art」,還有 WWW 2025 paper 背書 —— 白話:**這是我的頭號對手,而且它是有論文的正規軍。**我的態度是把它當**我們超越的 baseline 引用**,不是假裝它不存在。

### 有沒有一份公認的標準答案可以考我?

這是全文最痛的一段,我不藏:

> **Eval 資料集:** EDGAR-CORPUS(crawler 自產,**非 gold label,循環論證**,只能壓力測);KPI-EDGAR(81 份人工標註,但標的是 KPI 關係非 item boundary);**無公開 gold-labeled item-boundary dataset**——手標 ~50 份(含 wrapper)會是可引用貢獻,也是我們的 eval set。

白話拆解這三句:

1. **EDGAR-CORPUS 不能當標準答案。**它本身就是 crawler 跑出來的 —— 拿它當 gold label(標準答案),等於**拿學生自己的答案當考卷解答**,這就是「循環論證」。所以我只把它當壓力測試(看會不會爆),不當評分依據。
2. **KPI-EDGAR 有 81 份人工標註,但標錯東西。**它標的是 KPI 關係,我要的是 item boundary(章節邊界)—— 白話:人家的答案卷是數學,我考的是國文。
3. **結論:這個領域根本沒有公開的標準答案。**所以我手標 ~50 份(含 wrapper)自己造 eval set。

這裡有一個必須說清楚的自我攻擊:**自己出考卷、自己考、自己改,天生就有偏袒的嫌疑。**我不能只說「我的 eval set 很好」,我能誠實說的是:公開 gold-labeled item-boundary dataset 不存在,手標是唯一選項,而我把它公開成可引用的貢獻,讓別人能來查我。

> **不是我不想用公認考卷,是這門課還沒有公認考卷 —— 所以我把出題過程也攤在陽光下。**

### 哪兩件事是真的沒有 prior art 可以 defer 的?

> **兩個 research agent 的關鍵結論(我們的 novel 之處,無 prior art 可 defer):**
> 1. **Cross-reference / wrapper 10-K(Intel/Citi/GE)是真正的 open gap。** 沒有任一 repo 解得好;edgar-crawler 的 `get_last_item_section()` 反而會靜默誤標。我們的 `cross_reference_index` 偵測 + 三態 status 在開源界看似 novel。
> 2. **XBRL 當 span 內容的獨立 oracle 也大致 novel。** 既有專案用 XBRL 產報表,沒人用 companyfacts 去*認證 Item 8 span 真的含申報數字*。我們「XBRL as adversarial validator of a text span」framing 可主張為新。

**第一點白話:**有些 10-K 的正文根本不在 10-K 裡,而是寫「詳見附件」。頭號對手 edgar-crawler 遇到這種狀況,它的 `get_last_item_section()` 會**靜默誤標** —— 白話:它不會報錯,它會很有自信地給你一段錯的文字。這是最糟的失敗形狀:沒有人會發現。我的做法是偵測出來 + 用三態 status 誠實說「這裡我不知道」。

**第二點白話:**別人用 XBRL 這份「機器可讀版數字」去**產生**報表;我反過來用它**查帳** —— 拿 companyfacts 去問「你剪出來的這段 Item 8,裡面真的有公司申報的那些數字嗎?」這就是把 XBRL 從產線工人變成**照妖鏡**:它不幫我做事,它專門抓我說謊。

注意這兩點的措辭我一個字都沒有放大:第一點寫的是「**看似** novel」,第二點寫的是「**大致** novel」、「**可主張**為新」。這是兩個 research agent 查完的結論,不是專利檢索,也不是同儕審查 —— 我不會把「查了沒看到」寫成「世界上沒有」。

> **不是別人做不到,是沒人把 XBRL 當作攻擊自己的工具 —— 我做的不是新積木,是新的敵我關係。**

---

## 對本專案的行動項

把上面兩張表收斂成三條可執行的紀律,外加一句自我檢查:

- **可安全依賴/借鑑(MIT/Apache):** edgartools(fetch/XBRL 參考)、Agent-E(a11y 技術 + 論文引用)、Stagehand(action caching 對照)。
- **借思路勿抄 code(copyleft):** edgar-crawler(GPLv3)、Skyvern(AGPL)、py-sec-edgar(AGPL 商用)。
- **對外可信度:** 把 WebArena / WebVoyager 列為 browser agent 的 roadmap benchmark;SEC 端主打「source-exact + XBRL 認證 + wrapper 處理」三個 novel 點。
- 我們目前的實作與上述結論一致:差異化站得住腳,且我們已經做出別人沒做的 XBRL 認證與 wrapper 分類。

**第二條為什麼是硬紀律?**edgar-crawler 是 GPLv3、Skyvern 是 AGPL —— 白話:**這兩塊肩膀站上去,我整個專案就得跟著開源。**所以規矩是:讀它的論文、學它的想法,**一行 code 都不抄**。這不是道德潔癖,是法律事實。

> **站在巨人的肩膀上不是免費的 —— 有些巨人的肩膀,踩上去要付授權費。這條界線我畫在動手之前,不是被抓到之後。**
