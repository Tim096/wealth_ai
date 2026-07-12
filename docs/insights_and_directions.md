# Insights & Optimization Directions

> 這份文件不是功能清單,是思路。多數方向「有方向、不一定做出來」;做出來的部分會標明。目的:證明我知道這兩個任務在實務上會遇到什麼、現有作法的邊界在哪、往哪優化。

## 0. 一句話論點

**AI coding 把「寫出來」變便宜了,所以稀缺的不是產出,是驗證。** 這個專案的主體不是兩個 demo,是一套能證明自己何時對、何時錯、何時證據不足的 reliability 基礎設施。Browser Agent 與 SEC Extractor 只是拿來壓力測試它的兩個高難度負載。

這在本次開發中不是口號:我的 SEC pipeline 通過 3 家 smoke test 後自報 75.9% pass;接著我用 56 個 agent 的**對抗式稽核**(內部審計過程,per-agent 輸出未完整留存為 artifact;方法與結果摘要見 `prompts/eval_design/2026-07-10-adversarial-audit-workflow.md`)跑 11 家真實 10-K,證明其中 15 個 pass 是 silent failure(reference stub 被當成內容、末項吞掉整本財報)。**稽核抓到了我自己的系統在說謊,然後我才修。** 這就是「demo 不可信,所以要做 eval」的實際演出。

## 1. 如果直接把這兩題丟給 autonomous coding agent(OpenClaw / Hermes 類)會怎樣?

**我不用猜——我把「用 LLM 驅動瀏覽器」真的做出來了(Agent Mode,`browser_agent/planner.py` + Codex gateway,預設接 Codex OAuth),所以能直接對照。**

OpenClaw / Hermes 這類「LLM 自主驅動瀏覽器」的核心迴圈就是:看畫面 → LLM 決定下一步 → 執行。我的 Agent Mode 用同一個迴圈,差別在**周邊約束**:

| 面向 | 純 OpenClaw/Hermes | 我的 Agent Mode(同樣 LLM 驅動) |
|---|---|---|
| LLM 輸出 | 任意工具 / 甚至改檔案 | 只能回**受控 action JSON**,target 只能選現有元素 aid,不能寫 code、不能造 selector |
| 危險操作 | 靠 prompt 自律 | `capability.screen_action` **程式攔截** login/購買/送出 |
| 成敗判定 | LLM 自評「完成了」 | **verifier 依 task contract 判**,LLM 說 done 不算數;缺證據 → unknown |
| 失敗 | 靜默重試 | diagnosis-driven repair + selector memory |
| 可稽核 | 難 | 每步 EvidenceRecord + 截圖 + trace |

**同樣「LLM 會亂點」的擔憂,我用「限制輸出空間 + guard + verifier + evidence」把它馴服。** 不是不用 LLM,而是**用 LLM 但不相信 LLM 自評**——這正是主管說的「AI 之後最稀缺的是驗證」。

- **SEC 若丟給 autonomous agent**:它會 regex 切 Item、跑 AAPL/MSFT 很漂亮就宣稱完成;不會自己去跑 JPM/XOM/Intel 這種 wrapper 10-K,更不會發現 Item 16 吞了 31 萬字還標 confidence 1.0——因為沒有動機**反駁自己**。這就是「SEC 跑出來不完整但 AI 自報完成度很高」的結構性原因。我的對策:對抗式稽核(56 agent 證偽)+ XBRL/topic 雙獨立 oracle + page-anchor 真正把 Intel 正文抽回來。
- **一句話**:差異不在會不會寫,而在**會不會不相信自己**。我把「不相信自己」制度化。

## 2. SEC:wrapper 10-K 的 page-anchor resolution(**已實作**)

**現狀(已完成)**:Intel/Citi 這類 cross-reference-index 10-K,主文件是索引,正文在另外裝訂的 annual report。`sec_core/page_map.py` 用**正文印出的頁碼 footer**(normalize 後的 bare-number 行)以 LIS 重建 page→offset 對應,再把索引的「Item 1A → Pages 37-51」解析成**真實 source-exact span**。

**實測(Intel FY2025)**:7 個 item 從 page anchor 抽回真實正文——Item 1A = 96,213 字 Risk Factors、**Item 8 = 202,858 字財報**。而且解出來的 Item 8 **被 XBRL 獨立認證**(營收/淨利/總資產全中)——page-anchor 與 XBRL 兩個獨立方法互相佐證。標 `partial` + provenance `resolved_from_page_anchor` + needs_review(頁界對齊是啟發式,如實揭露)。

**為何用頁碼而非標題**:我原本拒絕 title-based 抽取(Intel 標題無 emphasis、重複當頁首,會出錯)。頁碼是**印出來的資料**,不是猜的——這是「站得住腳的 robust 版」與「脆弱猜測」的差別。

**延伸(P0-10,commit 84ecea7)**:同一原理推廣到 JPM/XOM class 的 wrapper 10-K——item 是 IBR stub、正文附綁在最後一個 item heading 之後。`cross_ref.reassemble_wrapper_bodies` 兩條錨定路徑:(a) page-range stub(JPM「appears on pages 46-160」)用區域限定 page map;(b) quoted-section-title stub(XOM『section entitled "Market Risks"』)錨定附綁年報自身節標題並跳過其內部 TOC。實測:JPM 1C/7/7A/8 與 XOM 7/7A/8 全數還原(JPM Item 8 = 528,433 chars、XOM Item 8 = 165,993 chars),兩家 Item 8 均 XBRL 認證 3/3,JPM 1C 的 CYD coverage 0%→100%。

**剩餘方向**:GS class——stub 指向自身已抽出 item 的內部子節(無附綁區塊),維持誠實 pointer;頁界/節界對齊可再精修(目前 needs_review)。

## 3. 驗證的正確基材:不是 LLM-as-judge,是結構化 ground truth

**主管的觀點我完全同意並想往前推一步:用 LLM 判斷財報對不對是壞主意(貴、不可重現、會 hallucinate)。** 我的 pipeline 已經不讓 LLM 產生或判斷 item 內容——它只做 offset-exact span 抽取,LLM 只在 ambiguous boundary 當裁判。但驗證還能更硬:

**SEC filing 自帶結構化 ground truth,大多數作業沒用到——這一條我已經實作了(`sec_core/xbrl.py`):**

- **Inline XBRL / `companyfacts` API**(`https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`):SEC 已把財報數字(Revenues、NetIncomeLoss、Assets…)結構化成機器可讀 fact。這是**免費、權威、非 LLM 的 cross-check**:
  - **[已實作]** 驗證 Item 8 抽對了——抽出的財報 span 必須含 XBRL 的營收/淨利/總資產(各種 scale);對不上就是 wrapper/boundary 的硬證據。實測 11 家(P0-10 wrapper 重組後):**certified 10 / contradicted 1**(NVDA 未重組的 IBR stub,誠實指標);JPM/XOM 原 contradicted,重組 span 各含 3/3 headline 後轉 certified(`tools/certify.py`,artifact `data/sec_eval/certification/item8_certification.json`)。
  - **[方向]** 反向定位:當 Item 8 被 XBRL contradicted,可全文搜尋這些數字出現在哪,自動指出真正財報位置 → 觸發 §2 的 wrapper resolution。
  - **[方向]** confidence calibration 黃金線:以 XBRL certified 與否當標籤,校準 confidence 對應實際正確率。

- **`_looks_like_reference_stub` 的下一步**:與其擴充 regex(脆弱),不如用 XBRL 反向驗證——「這個 item 該有數字但 span 裡沒有」比措辭偵測穩固。

**OCR path(掃描版 / 老 filing)**:1990 年代的 10-K 是掃描 PDF,沒有 HTML 結構。這裡 OCR 才是對的工具(不是 LLM 猜)。方向:偵測到掃描 PDF → 標 `unsupported`(現狀)或走 OCR pipeline(Tesseract / textract)→ 得到帶座標的文字層 → 同一套 heading/boundary 邏輯。OCR 的正確率與成本都遠優於「餵圖給 LLM 讀」。

**買 vs 建(data vendor)**:如果目標是「拿到乾淨的 10-K item 文字」,訂閱資料商(你提到的 massive 之類,或 Intrinio / S&P Capital IQ / Bloomberg)在**覆蓋率與維護成本**上會贏過自建 parser——尤其是 edge case 的長尾。自建的價值在:(a) 可控、可審計、無授權限制的 source-exact span;(b) 資料商沒有的 item-level boundary evidence 與 confidence。**實務決策**:核心財報數字買(XBRL 免費、深度數據訂閱),item-level 結構化文字自建(可驗證性是賣點)。這個 trade-off 本身應寫進 `cost_latency_report.md` 的 scalability 段。→ 如果團隊要走這條,我需要知道預算與授權立場(見文末問題)。

## 4. Browser Agent:實務場景與 adaptation(已實作,含 killer demo + eval)

現有設計(受控 action space、task contract verifier、selector memory、failure taxonomy)對應的真實場景:

- **監控型爬蟲**(法遵、價格、政府公告):真實痛點不是「點得到」,是「網站改版後靜默壞掉沒人知道」。selector memory + DOM fingerprint + 對抗式 mock site 正是為此設計——UI 一變,repair 有 evidence,不是靜默回傳舊資料。
- **RPA / 表單自動化**:企業內部系統。這裡「可逆、無登入、無金流」的邊界不是保守,是**責任邊界**——由 code-enforced capability guard(`packages/browser_agent/capability.py`:`screen_task` / `screen_action`)把 login/purchase/checkout/submit 擋在外,task 回 `refused`。這是能不能上 production 的關鍵,且已是程式強制,非文件宣示。
- **Agent 評測基建**:更大的機會是把這套 verifier + evidence + 對抗式 eval 抽出來,當成「別人的 browser agent 的評測平台」。市面上 browser agent 很多,能證明它何時失敗的很少。

**Killer demo 的意義**(mock site v1→v2、selector 故意失效、agent 用 accessibility tree 找候選、小步驗證、verifier pass、記憶更新):它證明的不是「能點網站」,是「網站變了我能自己修並拿出證據」。這是 production 可靠性的核心,也是 autonomous agent 最不會主動做的。

## 5. Harness engineering:本專案用到的前沿作法

「駕馭工程 / harness engineering」在這個專案的具體體現:

1. **對抗式稽核 harness**(已用):不是叫一個 agent 說「看起來對嗎」,而是 fan-out audit → 每個 anomaly 交獨立 verifier「盡力反駁」→ 多數決。這把「AI 自我感覺良好」換成「AI 互相證偽」。12 個 anomaly 被反駁層擋掉(它們其實是誠實行為),說明反駁層真的在工作。
2. **受控 action space / 受控輸出**:LLM 不輸出任意 code,只輸出 schema 驗證過的 action / decision。錯誤面積可控、可重播、可評估。
3. **證據鏈優於自述**:每個 pass 都要有 evidence chain,verifier 判不了就標 unknown。lack of evidence 結構上不能升級成 success。
4. **確定性優先,LLM 只在不確定時升級**:SEC 主路徑 0 個 LLM call(sweep LLM 成本 $0),LLM 只當 boundary 裁判;Browser 已知任務走 Script Mode 不動 LLM。成本與 hallucination 同時歸零。

**下一個前沿**:把 XBRL cross-check(§3)接進對抗式稽核,讓 verifier 不只靠 LLM 判斷,而有一條結構化事實線——**AI 驗證 + 結構化 ground truth 的混合**,比純 LLM-judge 或純規則都強。

## 6. 實務應用場景與適配(主管問:更多應用 / 會遇到什麼場景 / 如何優化)

### SEC Extractor 的真實應用

| 場景 | 會遇到什麼 | 現有作品如何適配 / 優化 |
|---|---|---|
| **投研 / 量化前處理** | 要把數千份 10-K 的 Item 1A/7/8 結構化餵下游模型;wrapper filing(Intel/Citi/GE)佔比不低 | 已有:source-exact span + XBRL 認證 + page-anchor 還原。優化:批次化(process pool)、把 XBRL 反向定位自動化 |
| **法遵 / 揭露監控** | 逐年比對某公司 Risk Factors / Cybersecurity(1C)變化 | item-level boundary + sha256 讓 diff 精準到段落;topic oracle 防止比錯段 |
| **審計 / 盡職調查** | 需要「這段話出自 filing 哪個 offset」的可稽核性 | provenance + char_range + evidence chain 正是為此;LLM 生成的摘要做不到 |
| **老 filing / 掃描檔** | 1990s 10-K 是掃描 PDF | 現狀 code-enforced `unsupported`;優化:OCR path(Tesseract,不是餵圖給 LLM)→ 同一套 boundary 邏輯 |

### Browser Agent 的真實應用

| 場景 | 會遇到什麼 | 現有作品如何適配 / 優化 |
|---|---|---|
| **監控型爬蟲**(價格/公告/法遵) | 痛點不是「點得到」,是**改版後靜默壞掉**沒人知道 | selector memory + DOM fingerprint + repair evidence:UI 一變就有 repair 紀錄,不是靜默回傳舊資料 |
| **RPA / 內部系統自動化** | login/金流/送出是紅線 | capability guard **程式攔截**,task 回 refused——上 production 的前提 |
| **未知網站 / 一次性任務** | 沒有預寫 script | Agent Mode(LLM 驅動)接手,但輸出受限 + verifier 把關 |
| **別人的 agent 的評測平台** | 市面 browser agent 多,能證明何時失敗的少 | 把 verifier + evidence + 對抗式 mock drift eval 抽出來當 SaaS——這可能是**比兩個 demo 更大的產品** |

**共同優化主線**:真實網站廣度(接 WebArena/WebVoyager 對標)、把 XBRL/topic 這種「獨立結構化 oracle」的思路推廣到更多 item / 更多網站驗證面。

## 6.5 從量化到使用情境(2026-07-10)

> 完整情境表(24 個具體情境,含程式碼佐證與 cheap fixes)在 `docs/usage_scenarios.md`。這裡收核心論點與下一波優先序。

### 兩個核心論點

**Browser Agent:人不是用 pass rate 信任 agent。** 人類(含評分者)用三個量化指標看不到的判準:(1) **結論與人眼是否一致**——silent false pass(preflight 自選 landmark 太早為真)、明明在播卻 FAIL(媒體任務)、誤殺 REFUSED(裸字 `post` 命中 guard),每次背離都是信任歸零事件,而它們在 eval 數字裡分別記成 pass、fail、refused,全部「正常」;(2) **失敗時系統知不知道自己為什麼失敗**——REFUSED+理由、unknown+trace 是誠實,raw `TimeoutError` 裸奔、新分頁追丟後自述「點了沒效果」是出糗,分界不在結局對錯,在自述與事實是否一致;(3) **成果有沒有交到人手上**——extract_text 的答案被丟棄(`agent.py` 只回傳 `__download__`)、截圖存了不顯示、下載檔只給 server 本機路徑,90% 工程投資花在 verdict 可信,deliverable 卻沒接到人面前,造成「pass rate 完美、使用者價值為零」的結構性盲區。最大的兩個一日內可修的信任洞:capability guard 的英文裸字誤殺與中文穿透——直接打穿 README 最引以為傲的「code-enforced 責任邊界」宣稱,是面試必問點。

**SEC Extractor:人用「錯誤的形狀」決定信不信。** 人靠兩件事建立信任:抽查一兩個自己熟的 item 看邊界對不對;丟一個刁鑽輸入(20-F、pre-2001、wrapper)看系統「知不知道自己不知道」。本系統的誠實內核(三態 status、XBRL/topic oracle、gap 保底)正中這兩點,但表達層仍是機器語彙(`filing_class=non_10k`、`conf 0.67`)。量化沒捕捉到的是錯誤的形狀:「誠實拒絕+說明原因+指出內容位置」與「靜默給錯」在 F1 上可能同分,對人卻是 A 級與 C 級的分水嶺。各族的一票否決各不同:律師要可獨立重驗的 offset 配方(sha256 對 normalized text 算,raw 下載卻是原始 HTML——斷鏈)、量化要無共享狀態的批次 API(全域 `_SEC_STATE` 併發下會串台)、基本面分析師要 stub 一鍵跳到正文(誠實但沒用=沒用)、評分者要系統對不支援輸入的第一句話。修這些多半不是改 pipeline,是把已存在的證據(warnings、gap offsets、filing_class、accession)翻譯成人話並接上連結。

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

## 7. 給評審的一頁總結

- 我沒有向你們要 API key(資安考量);SEC 走公開 EDGAR,Browser 的 Codex 由**你自己的 OAuth** 經 gateway 驅動,key 從不進 repo。
- 我沒有相信自己的 pass rate;我用對抗式稽核證偽它,抓到 15 個 silent failure 才修。
- **Intel/Citi 我不只誠實標示,還用 page-anchor 把正文真的抽回來了**(Item 1A 96K 字、Item 8 202K 字且 XBRL 認證)。
- status 可信不只靠 Item 8 XBRL——每個 item 都有獨立的 topic-consistency oracle。
- 「丟給 OpenClaw/Hermes 會怎樣」我直接做了(Agent Mode),證明差異在**用 LLM 但不信 LLM 自評**。
- 這套東西的真正產品可能不是兩個 demo,是底下那套「能證偽 AI 產出」的 harness。
