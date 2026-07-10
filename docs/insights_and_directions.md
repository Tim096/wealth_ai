# Insights & Optimization Directions

> 這份文件不是功能清單,是思路。多數方向「有方向、不一定做出來」;做出來的部分會標明。目的:證明我知道這兩個任務在實務上會遇到什麼、現有作法的邊界在哪、往哪優化。

## 0. 一句話論點

**AI coding 把「寫出來」變便宜了,所以稀缺的不是產出,是驗證。** 這個專案的主體不是兩個 demo,是一套能證明自己何時對、何時錯、何時證據不足的 reliability 基礎設施。Browser Agent 與 SEC Extractor 只是拿來壓力測試它的兩個高難度負載。

這在本次開發中不是口號:我的 SEC pipeline 通過 3 家 smoke test 後自報 75.9% pass;接著我用 56 個 agent 的**對抗式稽核**跑 11 家真實 10-K,證明其中 15 個 pass 是 silent failure(reference stub 被當成內容、末項吞掉整本財報)。**稽核抓到了我自己的系統在說謊,然後我才修。** 這就是「demo 不可信,所以要做 eval」的實際演出。

## 1. 如果直接把這兩題丟給 autonomous coding agent(OpenClawn / Hermes 類)會怎樣?

會得到一個「跑得起來、自報完成度很高、但沒有人驗證過」的東西。具體:

- **SEC**:agent 會寫 regex 切 Item、跑幾家大公司(AAPL/MSFT)看起來很漂亮,然後宣稱完成。它不會自己去跑 JPM/XOM 這種 wrapper 10-K,更不會發現 Item 16 吞了 31 萬字還標 confidence 1.0——因為它沒有動機去**反駁自己**。這正是你們看到「很多作業 SEC 跑出來不完整但 AI 總結完成度很高」的結構性原因:autonomous agent 的 reward 是「產出看起來完成」,不是「產出被驗證為正確」。
- **Browser**:agent 會 happy-path 點一個網站成功,然後宣稱通用。不會設計 UI 變動的 mock site 來證明 selector 自修復,也不會區分「工具回傳成功」與「任務真的完成」。

**差異點不在會不會寫,而在會不會不相信自己。** 我的作法把「不相信自己」制度化:三態判定(缺證據永遠是 unknown,結構上不可能升級成 pass)、受控 action space、對抗式稽核 harness。這是人在 AI 之後的槓桿點。

## 2. SEC:wrapper 10-K 的 cross-reference resolution(最該做的下一步)

**現狀**:JPM/XOM 這類「wrapper 10-K」把 Item 7/8 寫成一句「見 Financial Section / annual report」,真正 MD&A 與財報以獨立區塊接在最後一個 item heading 之後。我目前**誠實地**標成 `incorporated_by_reference` 並警告內容在 appended section——不再是 silent failure,但也還沒把內容還原。

**方向**:第二遍 resolver。偵測到 reference stub 時,解析它指向的目標(page range / named section / Note N),到 appended section 或對應 anchor 把真正 span 接回該 item。這需要:
- page-anchor 對應(filing 內部 `<a href="#...">` 與頁碼 → offset)
- appended section 自身的 heading 偵測(它有自己的 mini-TOC)
- 把「Item 7 的內容其實在這段」建成一條 evidence,而非假裝原地就有

**為什麼重要**:Intel、Citi 都是這種結構。能正確處理 wrapper 10-K,是「跑得完整」與「跑一半」的分水嶺。

## 3. 驗證的正確基材:不是 LLM-as-judge,是結構化 ground truth

**主管的觀點我完全同意並想往前推一步:用 LLM 判斷財報對不對是壞主意(貴、不可重現、會 hallucinate)。** 我的 pipeline 已經不讓 LLM 產生或判斷 item 內容——它只做 offset-exact span 抽取,LLM 只在 ambiguous boundary 當裁判。但驗證還能更硬:

**SEC filing 自帶結構化 ground truth,大多數作業沒用到——這一條我已經實作了(`sec_core/xbrl.py`):**

- **Inline XBRL / `companyfacts` API**(`https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`):SEC 已把財報數字(Revenues、NetIncomeLoss、Assets…)結構化成機器可讀 fact。這是**免費、權威、非 LLM 的 cross-check**:
  - **[已實作]** 驗證 Item 8 抽對了——抽出的財報 span 必須含 XBRL 的營收/淨利/總資產(各種 scale);對不上就是 wrapper/boundary 的硬證據。實測 11 家:7 家 pass 全 `certified`、3 家 wrapper stub `contradicted`,**pipeline 與獨立 oracle 零分歧**(`tools/certify.py`)。
  - **[方向]** 反向定位:當 Item 8 被 XBRL contradicted,可全文搜尋這些數字出現在哪,自動指出真正財報位置 → 觸發 §2 的 wrapper resolution。
  - **[方向]** confidence calibration 黃金線:以 XBRL certified 與否當標籤,校準 confidence 對應實際正確率。

- **`_looks_like_reference_stub` 的下一步**:與其擴充 regex(脆弱),不如用 XBRL 反向驗證——「這個 item 該有數字但 span 裡沒有」比措辭偵測穩固。

**OCR path(掃描版 / 老 filing)**:1990 年代的 10-K 是掃描 PDF,沒有 HTML 結構。這裡 OCR 才是對的工具(不是 LLM 猜)。方向:偵測到掃描 PDF → 標 `unsupported`(現狀)或走 OCR pipeline(Tesseract / textract)→ 得到帶座標的文字層 → 同一套 heading/boundary 邏輯。OCR 的正確率與成本都遠優於「餵圖給 LLM 讀」。

**買 vs 建(data vendor)**:如果目標是「拿到乾淨的 10-K item 文字」,訂閱資料商(你提到的 massive 之類,或 Intrinio / S&P Capital IQ / Bloomberg)在**覆蓋率與維護成本**上會贏過自建 parser——尤其是 edge case 的長尾。自建的價值在:(a) 可控、可審計、無授權限制的 source-exact span;(b) 資料商沒有的 item-level boundary evidence 與 confidence。**實務決策**:核心財報數字買(XBRL 免費、深度數據訂閱),item-level 結構化文字自建(可驗證性是賣點)。這個 trade-off 本身應寫進 `cost_latency_report.md` 的 scalability 段。→ 如果團隊要走這條,我需要知道預算與授權立場(見文末問題)。

## 4. Browser Agent:實務場景與 adaptation(Phase 2 尚未實作,先講清楚方向)

現有設計(受控 action space、task contract verifier、selector memory、failure taxonomy)對應的真實場景:

- **監控型爬蟲**(法遵、價格、政府公告):真實痛點不是「點得到」,是「網站改版後靜默壞掉沒人知道」。selector memory + DOM fingerprint + 對抗式 mock site 正是為此設計——UI 一變,repair 有 evidence,不是靜默回傳舊資料。
- **RPA / 表單自動化**:企業內部系統。這裡「可逆、無登入、無金流」的邊界不是保守,是**責任邊界**——把不可逆操作擋在 capability router 外,是能不能上 production 的關鍵。
- **Agent 評測基建**:更大的機會是把這套 verifier + evidence + 對抗式 eval 抽出來,當成「別人的 browser agent 的評測平台」。市面上 browser agent 很多,能證明它何時失敗的很少。

**Killer demo 的意義**(mock site v1→v2、selector 故意失效、agent 用 accessibility tree 找候選、小步驗證、verifier pass、記憶更新):它證明的不是「能點網站」,是「網站變了我能自己修並拿出證據」。這是 production 可靠性的核心,也是 autonomous agent 最不會主動做的。

## 5. Harness engineering:本專案用到的前沿作法

「駕馭工程 / harness engineering」在這個專案的具體體現:

1. **對抗式稽核 harness**(已用):不是叫一個 agent 說「看起來對嗎」,而是 fan-out audit → 每個 anomaly 交獨立 verifier「盡力反駁」→ 多數決。這把「AI 自我感覺良好」換成「AI 互相證偽」。12 個 anomaly 被反駁層擋掉(它們其實是誠實行為),說明反駁層真的在工作。
2. **受控 action space / 受控輸出**:LLM 不輸出任意 code,只輸出 schema 驗證過的 action / decision。錯誤面積可控、可重播、可評估。
3. **證據鏈優於自述**:每個 pass 都要有 evidence chain,verifier 判不了就標 unknown。lack of evidence 結構上不能升級成 success。
4. **確定性優先,LLM 只在不確定時升級**:SEC 主路徑 0 個 LLM call(sweep LLM 成本 $0),LLM 只當 boundary 裁判;Browser 已知任務走 Script Mode 不動 LLM。成本與 hallucination 同時歸零。

**下一個前沿**:把 XBRL cross-check(§3)接進對抗式稽核,讓 verifier 不只靠 LLM 判斷,而有一條結構化事實線——**AI 驗證 + 結構化 ground truth 的混合**,比純 LLM-judge 或純規則都強。

## 6. 給評審的一頁總結

- 我沒有向你們要 API key(資安考量);SEC 走公開 EDGAR + 明確 user-agent + rate limit + cache,LLM 目前 $0。
- 我沒有相信自己的 pass rate;我用對抗式稽核證偽它,抓到 15 個 silent failure 才修。
- 我知道 wrapper 10-K(Intel/Citi 類)是分水嶺,已誠實標示並給出還原方向。
- 我知道驗證財報的正確基材是 XBRL / OCR / 結構化資料,不是 LLM-as-judge。
- 我知道這套東西的真正產品可能不是兩個 demo,是底下那套「能證偽 AI 產出」的 harness。
