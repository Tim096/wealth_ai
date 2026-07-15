# Insights & Optimization Directions

> 這份文件不是功能清單,是思路。多數方向「有方向、不一定做出來」;做出來的部分會標明。目的:證明我知道這兩個任務在實務上會遇到什麼、現有作法的邊界在哪、往哪優化。

## 先給地圖:這份怎麼讀?

九段,由淺入深,推進方向固定是「論點 → 對照 → 已做出來的 → 該怎麼驗 → 前沿作法 → 真實場景 → 人怎麼決定信不信 → 一頁總結」。每個標題都是問句,答案在內文。

| 段 | 問題 | 一句話 |
|---|---|---|
| [0](#0-一句話論點這整個專案在賭什麼) | 這整個專案在賭什麼? | 稀缺的不是產出,是驗證 |
| [1](#1-直接把這兩題丟給-autonomous-coding-agent-會怎樣) | 丟給 OpenClaw/Hermes 會怎樣? | 我不用猜——我把它做出來了,能直接對照 |
| [2](#2-secwrapper-10-k-的正文我到底抽回來了沒已實作) | wrapper 10-K 的正文抽回來了沒? | **已實作**,而且被獨立方法佐證 |
| [3](#3-驗證的正確基材是-llm-as-judge-嗎) | 驗證該用 LLM 當裁判嗎? | 不是,是結構化 ground truth |
| [4](#4-browser-agent-的真實場景是什麼) | Browser Agent 的真實場景? | 痛點不是點得到,是改版後靜默壞掉 |
| [5](#5-harness-engineering本專案用到哪些前沿作法) | 用了哪些前沿作法? | 四項,加一個下一個前沿 |
| [6](#6-這兩個東西實際能拿去做什麼) | 實際能拿去做什麼? | 兩張場景表 + 一條共同優化主線 |
| [6.5](#65-人到底憑什麼信一個-agent2026-07-10) | 人憑什麼信一個 agent? | 不是 pass rate;附下一波優先序 |
| [7](#7-給評審的一頁總結) | 給評審的一頁總結 | 六句話 |

---

## 0. 一句話論點:這整個專案在賭什麼?

**AI coding 把「寫出來」變便宜了,所以稀缺的不是產出,是驗證。** 這個專案的主體不是兩個 demo,是一套能證明自己何時對、何時錯、何時證據不足的 reliability 基礎設施。Browser Agent 與 SEC Extractor 只是拿來壓力測試它的兩個高難度負載。

翻成一般人能懂的版本:程式碼現在像自來水一樣便宜,誰都能生一堆。變貴的是「你怎麼知道這堆東西是對的」。所以我沒把力氣花在多做一個 demo,花在做一台**照妖鏡**。

而這不是口號,有實例:

這在本次開發中不是口號:SEC pipeline 通過早期 smoke test 後仍被 multi-agent **對抗式稽核**找出 reference stub、末項吞掉整本財報等 false-pass classes，之後以 accession-level fixtures 與 regression tests 重現並修復。內部 per-agent 輸出未完整留存，所以這裡不宣稱可重放的 agent 數量或逐-agent 統計；可驗證證據是 `prompts/eval_design/2026-07-10-adversarial-audit-workflow.md` 記錄的方法、`docs/failure_gallery.md` 的案例與對應 tests。**稽核抓到了系統在說謊,然後才修。** 這就是「demo 不可信,所以要做 eval」的實例。

注意中間那句自我縮限:**per-agent 輸出未完整留存,所以我不宣稱可重放的 agent 數量或逐-agent 統計。** 我大可以寫「N 個 agent 交叉稽核」聽起來很厲害,但我拿不出逐 agent 的紀錄,那就不寫。

> **不是「我們做了很嚴謹的稽核」,是「稽核抓到系統在說謊,然後才修」——前者是形容詞,後者是事件。**

---

## 1. 直接把這兩題丟給 autonomous coding agent 會怎樣?

(OpenClaw / Hermes 類。)

**我不用猜——我把「用 LLM 驅動瀏覽器」真的做出來了(Agent Mode,`browser_agent/planner.py` + Codex gateway,預設接 Codex OAuth),所以能直接對照。**

OpenClaw / Hermes 這類「LLM 自主驅動瀏覽器」的核心迴圈就是:看畫面 → LLM 決定下一步 → 執行。我的 Agent Mode 用同一個迴圈,差別在**周邊約束**:

| 面向 | 純 OpenClaw/Hermes | 我的 Agent Mode(同樣 LLM 驅動) |
|---|---|---|
| LLM 輸出 | 任意工具 / 甚至改檔案 | 只能回**受控 action JSON**,target 只能選現有元素 aid,不能寫 code、不能造 selector |
| 危險操作 | 靠 prompt 自律 | `capability.screen_action` **程式攔截** login/購買/送出 |
| 成敗判定 | LLM 自評「完成了」 | **verifier 依 task contract 判**,LLM 說 done 不算數;缺證據 → unknown |
| 失敗 | 靜默重試 | diagnosis-driven repair + selector memory |
| 可稽核 | 難 | 每步 EvidenceRecord + 截圖 + trace |

這張表最關鍵的是第一列與第三列——**同一顆 LLM,同一個迴圈,差在它被允許說什麼、以及誰有權宣布勝負。**

**同樣「LLM 會亂點」的擔憂,我用「限制輸出空間 + guard + verifier + evidence」把它馴服。** 不是不用 LLM,而是**用 LLM 但不相信 LLM 自評**——「AI 生成能力愈強,愈稀缺的是可重驗的驗證」,這正是我把整條 pipeline 圍繞驗證軸設計的原因。

### SEC 那題丟給 autonomous agent 會怎樣?

- **SEC 若丟給 autonomous agent**:它會 regex 切 Item、跑 AAPL/MSFT 很漂亮就宣稱完成;不會自己去跑 JPM/XOM/Intel 這種 wrapper 10-K,更不會發現 Item 16 吞了 31 萬字還標 confidence 1.0——因為沒有動機**反駁自己**。這就是「SEC 跑出來不完整但 AI 自報完成度很高」的結構性原因。我的對策:multi-agent 對抗式稽核找 failure classes + XBRL/topic 雙獨立 oracle + page-anchor 還原可驗證的 same-file wrapper 正文。

「Item 16 吞了 31 萬字還標 confidence 1.0」值得停一下:31 萬字不是一個 item,那是**整本財報被最後一個章節吞進去了**,而系統對此的自我評分是滿分 1.0。這就是 false pass 的長相——它不是錯得很難看,是錯得很好看。

- **一句話**:差異不在會不會寫,而在**會不會不相信自己**。我把「不相信自己」制度化。

---

## 2. SEC:wrapper 10-K 的正文我到底抽回來了沒?(**已實作**)

**現狀(已完成)**:Intel/Citi 這類 cross-reference-index 10-K,主文件是索引,正文在另外裝訂的 annual report。`sec_core/page_map.py` 用**正文印出的頁碼 footer**(normalize 後的 bare-number 行)以 LIS 重建 page→offset 對應,再把索引的「Item 1A → Pages 37-51」解析成**真實 source-exact span**。

白話整個機制:這種 10-K 的主文件像一本**目錄**,真正的內容在後面那本年報裡,而目錄唯一給你的線索是「第 37 到 51 頁」。所以我做的事是——把年報每一頁**印出來的頁碼**(就是紙本頁腳那個數字)找出來,建一張「第幾頁 = 檔案第幾個字元」的對照表,然後照著目錄給的頁碼去取字。

(LIS = Longest Increasing Subsequence,最長遞增子序列;白話:頁碼理論上該是 1,2,3… 一路遞增,但文件裡難免混進不是頁碼的數字,LIS 就是從一堆數字裡挑出「最長的一串遞增數列」,把雜訊剔掉。)

**實測(Intel FY2025)**:12 個 item 從 page anchor 抽回真實正文——Item 1A = 96,213 字 Risk Factors、**Item 8 = 204,301 字財報**。而且解出來的 Item 8 **被 XBRL 獨立認證**(營收/淨利/總資產全中)——page-anchor 與 XBRL 兩個獨立方法互相佐證。標 `partial` + provenance `resolved_from_page_anchor` + needs_review(頁界對齊是啟發式,如實揭露)。Citi FY2025 同法解出 9 個 item(Risk Factors 88K、MD&A 86K、Financials 577K 字)。

【自我攻擊】抽回 204,301 字,怎麼知道抽回來的是財報而不是隔壁章節?
【假說】若真的是財報,那 SEC 自己標的營收/淨利/總資產三個數字必須出現在這段字裡。
【去測】XBRL 獨立認證。
【判定】營收/淨利/總資產**全中**——**page-anchor 與 XBRL 是兩個完全獨立的方法,它們互相佐證。** 一個靠紙本頁碼,一個靠 SEC 的結構化標記,兩者沒有共用任何假設。

誠實那一半也講清楚:標的是 `partial` + needs_review,不是 `pass`。因為**頁界對齊是啟發式**——我知道第 37 頁大概從哪個字元開始,但不敢說精準到字。

**為何用頁碼而非標題**:我原本拒絕 title-based 抽取(Intel 標題無 emphasis、重複當頁首,會出錯)。頁碼是**印出來的資料**,不是猜的——這是「站得住腳的 robust 版」與「脆弱猜測」的差別。

> **不是找標題,是找頁碼——標題是我猜出來的,頁碼是印刷廠印上去的。**

### 延伸:同一原理推到 JPM/XOM

**延伸(P0-10,commit 84ecea7)**:同一原理推廣到 JPM/XOM class 的 wrapper 10-K——item 是 IBR stub、正文附綁在最後一個 item heading 之後。`cross_ref.reassemble_wrapper_bodies` 兩條錨定路徑:(a) page-range stub(JPM「appears on pages 46-160」)用區域限定 page map;(b) quoted-section-title stub(XOM『section entitled "Market Risks"』)錨定附綁年報自身節標題並跳過其內部 TOC。實測:JPM 1C/7/7A/8 與 XOM 7/7A/8 全數還原(JPM Item 8 = 528,433 chars、XOM Item 8 = 165,993 chars),兩家 Item 8 均 XBRL 認證 3/3,JPM 1C 的 CYD coverage 0%→100%。

(IBR = incorporated by reference,以引用方式併入;白話:「這段我不寫,詳見別處」。stub = 只有那一行指路的紙條,沒有內容。)

JPM 1C 的 CYD coverage **0%→100%** 是這波最乾淨的對照錨:同一個 item、同一把官方尺,重組前 0%、重組後 100%。**不是我自己說變好了,是 SEC 的 oracle 說的。**

**剩餘方向**:GS class——stub 指向自身已抽出 item 的內部子節(無附綁區塊),維持誠實 pointer;頁界/節界對齊可再精修(目前 needs_review)。

---

## 3. 驗證的正確基材:是 LLM-as-judge 嗎?

**我的立場並想往前推一步:用 LLM 判斷財報對不對是壞主意(貴、不可重現、會 hallucinate)。** 我的 pipeline 已經不讓 LLM 產生或判斷 item 內容——它只做 offset-exact span 抽取,LLM 只在 ambiguous boundary 當裁判。但驗證還能更硬:

(LLM-as-judge:拿一顆語言模型去評分另一顆語言模型的產出。白話:找學生改學生的考卷。)

**SEC filing 自帶結構化 ground truth,大多數作業沒用到——這一條我已經實作了(`sec_core/xbrl.py`):**

一句話:**SEC 已經把答案卷附在題目後面了,只是大部分人沒翻到那一頁。**

- **Inline XBRL / `companyfacts` API**(`https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`):SEC 已把財報數字(Revenues、NetIncomeLoss、Assets…)結構化成機器可讀 fact。這是**免費、權威、非 LLM 的 cross-check**:
  - **[已實作]** 驗證 Item 8 抽對了——抽出的財報 span 必須含 XBRL 的營收/淨利/總資產(各種 scale);對不上就是 wrapper/boundary 的硬證據。實測 11 家(P0-10 wrapper 重組後):**certified 10 / contradicted 1**(NVDA 未重組的 IBR stub,誠實指標);JPM/XOM 原 contradicted,重組 span 各含 3/3 headline 後轉 certified(`tools/certify.py`,artifact `data/sec_eval/certification/item8_certification.json`)。
  - **[方向]** 反向定位:當 Item 8 被 XBRL contradicted,可全文搜尋這些數字出現在哪,自動指出真正財報位置 → 觸發 §2 的 wrapper resolution。
  - **[方向]** confidence calibration 黃金線:以 XBRL certified 與否當標籤,校準 confidence 對應實際正確率。

- **`_looks_like_reference_stub` 的下一步**:與其擴充 regex(脆弱),不如用 XBRL 反向驗證——「這個 item 該有數字但 span 裡沒有」比措辭偵測穩固。

三個 bullet 的身分差很多,我標清楚:第一個是 **[已實作]**、有 artifact、有 11 家實測數字;後兩個是 **[方向]**,還沒做。**不把方向寫成戰功。**

XBRL 這條路的邏輯之所以硬,在於它是**必要條件**而不是相似度:真財報一定含營收/淨利/總資產,wrapper stub 一定不含。所以 contradicted 不是「分數低」,是**硬證據**。而 11 家裡那唯一的 contradicted 1(NVDA)是誠實指標,不是失分——它本來就是一張沒重組的 IBR stub。

**OCR path(掃描版 / 老 filing)**:1990 年代的 10-K 是掃描 PDF,沒有 HTML 結構。這裡 OCR 才是對的工具(不是 LLM 猜)。方向:偵測到掃描 PDF → 標 `unsupported`(現狀)或走 OCR pipeline(Tesseract / textract)→ 得到帶座標的文字層 → 同一套 heading/boundary 邏輯。OCR 的正確率與成本都遠優於「餵圖給 LLM 讀」。

**買 vs 建(data vendor)**:如果目標是「拿到乾淨的 10-K item 文字」,訂閱資料商(你提到的 massive 之類,或 Intrinio / S&P Capital IQ / Bloomberg)在**覆蓋率與維護成本**上會贏過自建 parser——尤其是 edge case 的長尾。自建的價值在:(a) 可控、可審計、無授權限制的 source-exact span;(b) 資料商沒有的 item-level boundary evidence 與 confidence。**實務決策**:核心財報數字買(XBRL 免費、深度數據訂閱),item-level 結構化文字自建(可驗證性是賣點)。這個 trade-off 本身應寫進 `cost_latency_report.md` 的 scalability 段。→ 如果團隊要走這條,我需要知道預算與授權立場(見文末問題)。

買 vs 建這段講白了就是一筆**「X 換 Y」的交易**:買,換到覆蓋率與別人幫你維護長尾;建,換到可稽核性與無授權限制的 source-exact span。我沒有主張全買或全建——**核心財報數字買、item-level 結構化文字自建**,因為後者的賣點正是前者給不了的可驗證性。

> **不是 LLM 當裁判,是讓 SEC 自己當裁判——它免費、權威、而且不會 hallucinate。**

---

## 4. Browser Agent 的真實場景是什麼?

現有設計(受控 action space、task contract verifier、selector memory、failure taxonomy)對應的真實場景:

- **監控型爬蟲**(法遵、價格、政府公告):真實痛點不是「點得到」,是「網站改版後靜默壞掉沒人知道」。selector memory + DOM fingerprint + 對抗式 mock site 正是為此設計——UI 一變,repair 有 evidence,不是靜默回傳舊資料。
- **RPA / 表單自動化**:企業內部系統。這裡「可逆、無登入、無金流」的邊界不是保守,是**責任邊界**——由 code-enforced capability guard(`packages/browser_agent/capability.py`:`screen_task` / `screen_action`)把 login/purchase/checkout/submit 擋在外,task 回 `refused`。這是能不能上 production 的關鍵,且已是程式強制,非文件宣示。
- **Agent 評測基建**:更大的機會是把這套 verifier + evidence + 對抗式 eval 抽出來,當成「別人的 browser agent 的評測平台」。市面上 browser agent 很多,能證明它何時失敗的很少。

第一條的白話:爬蟲真正會害死你的不是「今天點不到」——點不到你馬上會知道。是「網站改版了,你的爬蟲還在很順地回傳去年的舊資料」,而且沒有任何人發現。**不是怕它壞,是怕它壞得很安靜。**

**Killer demo 的意義**(mock site v1→v2、selector 故意失效、agent 用 accessibility tree 找候選、小步驗證、verifier pass、記憶更新):它證明的不是「能點網站」,是「網站變了我能自己修並拿出證據」。這是 production 可靠性的核心,也是 autonomous agent 最不會主動做的。

---

## 5. Harness engineering:本專案用到哪些前沿作法?

「駕馭工程 / harness engineering」在這個專案的具體體現。白話:harness 就是**跑道加護欄**——不是把車開得更快,是讓車不會衝出去、而且衝出去時你會知道。

1. **對抗式稽核 harness**(已用):不是叫一個 agent 說「看起來對嗎」,而是 fan-out audit → 每個 anomaly 交獨立 verifier「盡力反駁」→ 多數決。這把「AI 自我感覺良好」換成「AI 互相證偽」。12 個 anomaly 被反駁層擋掉(它們其實是誠實行為),說明反駁層真的在工作。
2. **受控 action space / 受控輸出**:LLM 不輸出任意 code,只輸出 schema 驗證過的 action / decision。錯誤面積可控、可重播、可評估。
3. **證據鏈優於自述**:每個 pass 都要有 evidence chain,verifier 判不了就標 unknown。lack of evidence 結構上不能升級成 success。
4. **確定性優先,LLM 只在不確定時升級**:SEC 主路徑 0 個 LLM call(sweep LLM 成本 $0),LLM 只當 boundary 裁判;Browser 已知任務走 Script Mode 不動 LLM。成本與 hallucination 同時歸零。

第 1 條的那個 12 值得問 why:**12 個 anomaly 被反駁層擋掉,而它們其實是誠實行為。** 這是反過來的證據——如果反駁層是個橡皮圖章,它會全部放行;它擋掉 12 個假警報,說明它真的在工作。

第 4 條的兩個 0 是同一件事的兩面:**SEC 主路徑 0 個 LLM call、sweep LLM 成本 $0。** 這不是省錢的巧合——**LLM 呼叫次數是 0,hallucination 的機會就結構性地是 0。成本與幻覺是同一顆按鈕。**

**下一個前沿**:把 XBRL cross-check(§3)接進對抗式稽核,讓 verifier 不只靠 LLM 判斷,而有一條結構化事實線——**AI 驗證 + 結構化 ground truth 的混合**,比純 LLM-judge 或純規則都強。

---

## 6. 這兩個東西實際能拿去做什麼?

(更多應用 / 會遇到什麼場景 / 如何優化。)

### SEC Extractor 的真實應用

| 場景 | 會遇到什麼 | 現有作品如何適配 / 優化 |
|---|---|---|
| **投研 / 量化前處理** | 要把數千份 10-K 的 Item 1A/7/8 結構化餵下游模型;wrapper filing(Intel/Citi/GE)佔比不低 | 已有:source-exact span + XBRL 認證 + page-anchor 還原。優化:批次化(process pool)、把 XBRL 反向定位自動化 |
| **法遵 / 揭露監控** | 逐年比對某公司 Risk Factors / Cybersecurity(1C)變化 | item-level boundary + sha256 讓 diff 精準到段落;topic oracle 防止比錯段 |
| **審計 / 盡職調查** | 需要「這段話出自 filing 哪個 offset」的可稽核性 | provenance + char_range + evidence chain 正是為此;LLM 生成的摘要做不到 |
| **老 filing / 掃描檔** | 1990s 10-K 是掃描 PDF | 現狀 code-enforced `unsupported`;優化:OCR path(Tesseract,不是餵圖給 LLM)→ 同一套 boundary 邏輯 |

第三列是這張表的靈魂:審計要的是「這句話出自 filing 第幾個字元」。**LLM 生成的摘要做不到——因為它產出的是新寫的字,不是原檔的座標。**

### Browser Agent 的真實應用

| 場景 | 會遇到什麼 | 現有作品如何適配 / 優化 |
|---|---|---|
| **監控型爬蟲**(價格/公告/法遵) | 痛點不是「點得到」,是**改版後靜默壞掉**沒人知道 | selector memory + DOM fingerprint + repair evidence:UI 一變就有 repair 紀錄,不是靜默回傳舊資料 |
| **RPA / 內部系統自動化** | login/金流/送出是紅線 | capability guard **程式攔截**,task 回 refused——上 production 的前提 |
| **未知網站 / 一次性任務** | 沒有預寫 script | Agent Mode(LLM 驅動)接手,但輸出受限 + verifier 把關 |
| **別人的 agent 的評測平台** | 市面 browser agent 多,能證明何時失敗的少 | 把 verifier + evidence + 對抗式 mock drift eval 抽出來當 SaaS——這可能是**比兩個 demo 更大的產品** |

**共同優化主線**:真實網站廣度(接 WebArena/WebVoyager 對標)、把 XBRL/topic 這種「獨立結構化 oracle」的思路推廣到更多 item / 更多網站驗證面。

---

## 6.5 人到底憑什麼信一個 agent?(2026-07-10)

> 完整情境表(24 個具體情境,含程式碼佐證與 cheap fixes)在 `docs/usage_scenarios.md`。這裡收核心論點與下一波優先序。

### 兩個核心論點

**Browser Agent:人不是用 pass rate 信任 agent。** 人類(含評分者)用三個量化指標看不到的判準:(1) **結論與人眼是否一致**——silent false pass(preflight 自選 landmark 太早為真)、明明在播卻 FAIL(媒體任務)、誤殺 REFUSED(裸字 `post` 命中 guard),每次背離都是信任歸零事件,而它們在 eval 數字裡分別記成 pass、fail、refused,全部「正常」;(2) **失敗時系統知不知道自己為什麼失敗**——REFUSED+理由、unknown+trace 是誠實,raw `TimeoutError` 裸奔、新分頁追丟後自述「點了沒效果」是出糗,分界不在結局對錯,在自述與事實是否一致;(3) **成果有沒有交到人手上**——extract_text 的答案被丟棄(`agent.py` 只回傳 `__download__`)、截圖存了不顯示、下載檔只給 server 本機路徑,90% 工程投資花在 verdict 可信,deliverable 卻沒接到人面前,造成「pass rate 完美、使用者價值為零」的結構性盲區。最大的兩個一日內可修的信任洞:capability guard 的英文裸字誤殺與中文穿透——直接打穿 README 最引以為傲的「code-enforced 責任邊界」宣稱,是面試必問點。

把上面那段拆成一句話:**三種背離,在 eval 數字裡全部長得像「正常」。**

| 人眼看得到、eval 看不到的 | 它在數字裡被記成 |
|---|---|
| silent false pass(preflight 自選 landmark 太早為真)| `pass` |
| 明明在播卻 FAIL(媒體任務)| `fail` |
| 誤殺 REFUSED(裸字 `post` 命中 guard)| `refused` |

這張表是我對自己最狠的一刀:**每一次背離都是信任歸零事件,而它們在 eval 數字裡分別記成 pass、fail、refused,全部「正常」。** 也就是說,我的 pass rate 對這三種病症完全失明。

第 (2) 點的分界線我要講精確:**分界不在結局對錯,在自述與事實是否一致。** REFUSED+理由、unknown+trace 是誠實;raw `TimeoutError` 裸奔、新分頁追丟後自述「點了沒效果」是出糗。

第 (3) 點是整份文件最刺的自我攻擊:**90% 工程投資花在 verdict 可信,deliverable 卻沒接到人面前。** extract_text 的答案被丟棄(`agent.py` 只回傳 `__download__`)、截圖存了不顯示、下載檔只給 server 本機路徑。結果是「pass rate 完美、使用者價值為零」的結構性盲區。

而最大的兩個洞直接打穿我自己最得意的宣稱:**capability guard 的英文裸字誤殺與中文穿透,直接打穿 README 最引以為傲的「code-enforced 責任邊界」——是面試必問點。** 一日內可修,但現在還沒修,所以我把它寫在這裡而不是藏起來。

**SEC Extractor:人用「錯誤的形狀」決定信不信。** 人靠兩件事建立信任:抽查一兩個自己熟的 item 看邊界對不對;丟一個刁鑽輸入(20-F、pre-2001、wrapper)看系統「知不知道自己不知道」。本系統的誠實內核(三態 status、XBRL/topic oracle、gap 保底)正中這兩點,但表達層仍是機器語彙(`filing_class=non_10k`、`conf 0.67`)。量化沒捕捉到的是錯誤的形狀:「誠實拒絕+說明原因+指出內容位置」與「靜默給錯」在 F1 上可能同分,對人卻是 A 級與 C 級的分水嶺。各族的一票否決各不同:律師要可獨立重驗的 offset 配方(sha256 對 normalized text 算,raw 下載卻是原始 HTML——斷鏈)、量化要無共享狀態的批次 API(全域 `_SEC_STATE` 併發下會串台)、基本面分析師要 stub 一鍵跳到正文(誠實但沒用=沒用)、評分者要系統對不支援輸入的第一句話。修這些多半不是改 pipeline,是把已存在的證據(warnings、gap offsets、filing_class、accession)翻譯成人話並接上連結。

「錯誤的形狀」這個詞是這段的核心,值得釘住:**「誠實拒絕+說明原因+指出內容位置」與「靜默給錯」在 F1 上可能同分,對人卻是 A 級與 C 級的分水嶺。** 這正好是我的 F1 指標量不到的那一維。

四個族群、四種一票否決,每一種都是硬傷:

| 族群 | 一票否決 | 現況 |
|---|---|---|
| 律師 | 要可獨立重驗的 offset 配方 | sha256 對 normalized text 算,raw 下載卻是原始 HTML——**斷鏈** |
| 量化 | 要無共享狀態的批次 API | 全域 `_SEC_STATE` 併發下會**串台** |
| 基本面分析師 | 要 stub 一鍵跳到正文 | **誠實但沒用=沒用** |
| 評分者 | 要系統對不支援輸入的第一句話 | 表達層仍是機器語彙(`filing_class=non_10k`、`conf 0.67`)|

好消息是這些的修法很便宜:**修這些多半不是改 pipeline,是把已存在的證據(warnings、gap offsets、filing_class、accession)翻譯成人話並接上連結。** 證據早就在了,只是沒翻成人話。

### 下一波優先序(依嚴重度)

**breaks_trust(先修,多數半天內)**
1. guard 裸字誤殺:`post/publish/pay` 改需接受詞 pattern + 誤殺回歸測試(`capability.py`)
2. guard 中文穿透:三個 regex 加中文詞(登入/購買/結帳/密碼/信用卡)+ 中文 refused 測試
3. SEC 併發串台:/api/sec/item 帶 accession 與全域 state 比對,不符明講(`test_center.py`)
4. SEC 拒絕要有理由:20-F 公司回「foreign private issuer,申報 20-F 非 10-K」而非「找不到 10-K」
5. 律師的驗證配方:/api/sec/normalized + item 標頭附 sha256 重現 one-liner
6. answer channel:extract_text 結果回傳 UI(問答/翻譯類任務目前 pass 也交不出答案)
7. verifier 條件品質(premature landmark、media_playing)——與本日平行 workflow 的 verifier/repair 修復同步,勿重工

**friction(其次,多為 UI 接線)**
- 最終截圖進 UI(unknown 從「機器聳肩」變「邀請人裁決」——最便宜的信任槓桿)
- error 人話映射(raw TimeoutError 不裸奔)、下載檔 HTTP route、queue_position、mock 模式二次確認
- EDGAR URL 直接餵入、IBR stub→gap 跳轉、不支援格式的敘事 banner、review_summary 總覽
- scroll prompt(PageDown 一行 PLAYBOOK)、新分頁跟隨、YoY diff、批次路徑文件化

**polish(最後)**
- verifier reason 人話翻譯、unknown 不顯示偽精度 confidence、amendment 在 picker 現身、pipeline_rev 版本戳記、表格核對導引

排序的依據不是「哪個好做」,是**哪個會讓人不再信任這個系統**:breaks_trust 的七項每一項都是信任歸零事件,friction 只是不順手,polish 只是不夠漂亮。

---

## 7. 給評審的一頁總結

- 我沒有向你們要 API key(資安考量);SEC 走公開 EDGAR,Browser 的 Codex 由**你自己的 OAuth** 經 gateway 驅動,key 從不進 repo。
- 我沒有相信自己的 pass rate;我用 sweep1/sweep2 artifacts、accession fixtures 與 regression tests 驗證 status reclassification。
- **Intel/Citi 我不只誠實標示,還用 page-anchor 把正文真的抽回來了**(INTC Item 1A 96K 字、Item 8 204K 字且 XBRL 認證;Citi 9 個 item 含 MD&A 86K、Financials 577K 字)。
- status 可信不只靠 Item 8 XBRL——每個 item 都有獨立的 topic-consistency oracle。
- 「丟給 OpenClaw/Hermes 會怎樣」我直接做了(Agent Mode),證明差異在**用 LLM 但不信 LLM 自評**。
- 這套東西的真正產品可能不是兩個 demo,是底下那套「能證偽 AI 產出」的 harness。

> **炫技的正確姿勢不是堆滿技巧報喜,是讓自己的每一個強主張都先被自己攻擊一次——這份文件裡最有價值的段落,全部是我在打自己。**
