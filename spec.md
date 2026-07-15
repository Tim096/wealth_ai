# spec.md — 這個專案在做什麼(由淺入深)

> **這份文件分六段,先給你地圖:**
> 第 1 段 — 我到底在賣什麼?(零技術背景,三段白話故事)
> 第 2 段 — 這兩個系統實際會做什麼?(零技術背景,含我刻意畫下的邊界)
> 第 3 段 — 憑什麼說它可信?(八項機制,每項:生活比喻 → 機制 → code/artifact 指路)
> 第 4 段 — 我輸在哪裡?(不粉飾的量測數字,包含我輸掉的)
> 第 5 段 — 怎麼五分鐘自己驗?(可貼上就跑的指令)
> 第 6 段 — 想再深入,從哪讀起?(閱讀順序表)
>
> **這份不是工程規格。** 工程凍結規格是另一份文件 `docs/SPEC.md`,兩者用途不同:那份是「系統必須長什麼樣」,這份是「這個系統到底在做什麼、為什麼可信」。

---

## 1. 我到底在賣什麼?

**一句話:兩個 AI 工人(一個會操作瀏覽器、一個會拆解財報),加上一個從頭到尾不信任他們的檢查系統——這個專案賣的不是工人,是檢查系統。**

### 1.1 先講一個實習生的故事(全篇母題)

想像你有一個很聰明的實習生。你叫他去查資料、寫報告,他隔天交上來一份漂亮的成果,還拍胸脯說「都做完了」。問題是:你怎麼知道哪一頁能信?實習生最危險的不是做不出來——是做錯了還理直氣壯。主管真正需要的從來不是那份報告,而是「知道哪頁能信」的能力。

**這個實習生就是本篇的母題,後面每一個比喻都會繞回他。**

### 1.2 所以我做了什麼?

AI 就是這種實習生。它會操作網頁、會讀財報、會給答案,而且永遠自信。這個專案做了兩個這樣的 AI 工人:一個聽自然語言指令去操作瀏覽器(網頁改版了還能自己找到路),一個把上市公司幾百頁的年報拆成標準章節。但專案的重點不在工人多能幹,而在旁邊站著一個「不聽工人自述、只看物證」的檢查系統:工人說「做完了」不算數,檢查系統要親眼看到證據才蓋章;看不到證據就寫「不知道」,絕不因為工人講得好聽就放行。

### 1.3 為什麼「檢查」比「做出來」難、而且值錢?

因為做錯了還說做對了(silent failure,**白話:無聲失敗——它不報錯、不當機,只會安靜地把錯的東西交到你手上**)是 AI 最貴的錯誤形態。寫出一個 80 分的 AI 工人已經不稀缺;稀缺的是一套能證明「這 80 分裡哪些是真的 80 分」的制度。本專案的每一個設計,都是圍繞這件事。

> **不是「我做了一個很強的 AI」,是「我做了一套能證明 AI 哪裡不強的制度」。**

## 2. 這兩個系統實際會做什麼?

**Task 1 — Browser Agent(瀏覽器代理人)**:你用一句中文或英文描述任務(例如「去搜尋框查 widget 然後打開第一筆結果」),它自己規劃步驟、點擊、輸入;網站改版(按鈕換了 id、彈出 cookie 視窗、多了誘餌按鈕)時,它會診斷失敗原因並自我修復,而不是死在原地。最後由獨立的 verifier(**白話:驗證器,一段只看證據、不聽自述的判定程式**)判定 pass / fail / unknown——不採信 agent 自己說的「我做完了」。

**Task 2 — SEC 10-K Extractor(財報抽取器)**:輸入一個美股代號(例如 `AAPL`),它去 SEC EDGAR 抓該公司的 10-K 年報,拆成標準的 Item 1–16 章節(含 1A、7A 等子項,共 23 個代號)。關鍵保證:**每個字都能指回原始文件的確切位置**——每段抽出的文字附帶字元起迄位置(offset,**白話:這段文字從原文第幾個字開始、第幾個字結束**)與內容指紋(sha256,**白話:一段文字算出來的固定長度亂碼,原文動一個字就會整個變掉**),LLM 從頭到尾不產生任何一個財報字,所以不可能「幻覺」出財報內容。

### 2.1 我刻意不做什麼?

還有一條刻意畫下的邊界:登入、購買、結帳、送出表單這類不可逆動作,Task 1 **在程式碼層拒絕執行**(task 回 `refused`),不是文件上寫寫而已——寧可少做,不做「做了但你不知道後果」的事。指路:`packages/browser_agent/capability.py`。

### 2.2 你自己就能試

兩個系統都公開部署,**你自己就能試**,不用安裝、不用帳號:

- Task 1:https://wealth-agent-ncku.zeabur.app (點「Self-repair / 自我修復(v2 介面漂移)」看免金鑰的自我修復示範)
- Task 2:https://wealth-sec-ncku.zeabur.app (輸入 `AAPL` 按「Extract / 開始抽取」,點任一 Item 看原文與驗證訊號)

> **邊界不是文件上的一句承諾,是一行會回 `refused` 的程式碼。**

## 3. 憑什麼說它可信?

八項機制,共同主題只有一個:**每一層都假設上一層可能在騙你**。這條不信任鏈長這樣:

- agent 可能謊報完成 → verifier 只看物證(3.1、3.2)
- verifier 可能壞掉 → mutation harness 故意弄壞資料測它(3.7)
- 抽取結果可能看起來對其實錯 → 多個獨立 oracle 交叉驗(3.5)
- 評測本身可能自己騙自己 → 凍結協議與對抗式稽核(3.6、3.8)

每項的講法固定三拍:**生活比喻 → 機制 → 去哪裡看 code/artifact**。

### 3.1 為什麼「不知道」必須是一個合法答案?

**比喻**:海關查驗只有三種結果——放行、攔下、留檢。行李掃不出來不等於沒問題,只能留檢,不能直接放行。

**機制**:所有判定只允許三種狀態。規則寫死在共用層:每個成功條件逐一核對,任何一條被觀測到違反 → fail;沒有違反但至少一條「無法觀測」→ unknown,**永遠不會是 pass**。「缺證據」在結構上不可能升級成成功——這是對 silent failure 的結構性防禦,不是文件宣示。連「零條件」的輸入都會回 unknown 並明講「拒絕在沒有證據時宣稱成功」。

**指路**:`packages/eval_core/verdict.py`(`combine_checks`,全檔不到 70 行,建議直接讀)。

> **不是「盡量不要誤判 pass」,是「pass 這條路在結構上走不通」。**

### 3.2 誰有資格說「過了」?

**比喻**:運動員不能兼任裁判。跑者自己喊「我壓線了」不算,計時器說了算;旁邊的評論員(LLM)可以發表意見,但改不了成績。回到那個實習生——他的自我評價,一個字都不進成績單。

**機制**:Task 1 的 verifier 是確定性程式碼:檢查 URL 是否包含指定片段、頁面是否真的出現指定文字(且會剔除「0 results for "xxx"」這種把查詢原句回顯的假命中)、下載檔是否真的存在且內容包含指定字串。agent 的自述完全不進判定;answer 型任務只認 agent 實際從頁面抽出的文字,沒抽到就是 fail。另有一個 LLM second judge,但它是 advisory-only(**白話:只能提意見,不能改判**):分歧只會標 needs_review,**從不改判**。

**指路**:`packages/browser_agent/verifier.py`(判定本體);`packages/browser_agent/second_judge.py`(檔案開頭明寫「the runtime verifier stays the SOLE judge」「it never changes a verdict」)。

> **不是「LLM 說了算」,是「LLM 連投票權都沒有,只有發言權」。**

### 3.3 網站改版了,它為什麼還找得到路?

**比喻**:常去的超市改裝了,貨架全搬位。死記「第三排左邊」的人會失敗;記得「我要找的是醬油」的人會重新找到。修復靠的是理解用途,不是死記位置。

**機制**:動作失敗時先「診斷」失敗類型(selector 找不到、被 modal 擋住、點了沒反應……),再套對應策略——是診斷驅動,不是盲目重試。修復時列舉頁面 accessibility tree(**白話:瀏覽器給輔助工具看的頁面結構樹,寫著每個元件是什麼、叫什麼**)的候選元素,以 role / aria-label / placeholder / 文字 / 位置對「元素用途」(搜尋框、送出鈕、下載鈕……)評分選擇,並明確避開誘餌(decoy)元素;還有可行性 gate:如果沒有任何元素真的能執行該動作,誠實回報「no viable candidate」,而不是默默點錯的東西。Agent Mode 的 history 也保留 grounded target、輸入值與 intent；同頁狀態連續兩次 no-effect 後,第三次相同 action 會在 executor 前被擋下。

**對照錨**:三種不同 DOM shape 的確定性 mechanism probe 從 generic history `0/3` 提升到 grounded history `3/3`。白話:同一組探針,舊做法三個全掛,新做法三個全過——差別在「記得用途」而不是「記得位置」。

**指路**:`packages/browser_agent/repair.py`(`diagnose_failure`、`_PURPOSE_HINTS`、decoy 與 feasibility gate)；`packages/browser_agent/agent.py`(`action_history_entry`、`action_state_signature`)；`tools/action_history_cross_site_eval.py`。

> **不是「重試更多次」,是「先搞清楚為什麼掛,再決定重試什麼」。**

### 3.4 財報的字,憑什麼保證不是 AI 編的?

**比喻**:嚴謹的圖書館員不幫你抄書(抄寫可能出錯或加油添醋),只告訴你「第 762158 到 771903 字元」,還附一枚指紋,讓你隨時驗證那段文字沒被動過。

**機制**:Task 2 每個抽出的 Item 都是原始文件的一段連續 span(**白話:原文裡一段從頭到尾連著的文字**),以 `start_offset` / `end_offset` / `text_sha256` 定址;LLM 不產生 filing text,只有結構分析參與定界。status 同樣誠實分級:pass / partial / missing / incorporated_by_reference(原文只放了一個「請見他處」的指標時如實標示,不假裝抽到內容)/ reserved / unsupported。

**指路**:`packages/sec_core/items.py`(`ItemSegment` schema,檔案第一行即寫明「the LLM never generates filing text」)。

> **不是「AI 抄得很準」,是「AI 一個字都不准抄——它只能指位置」。**

### 3.5 一個證人不夠,那幾個才夠?

**比喻**:法庭不會只聽一位證人。多位互不認識的證人獨立作證且說法一致,才值得採信;有人翻供就送重審。

**機制**:Task 2 的每個抽取結果被多個獨立訊號源(oracle,**白話:一個獨立的、不靠我的判斷來源,用來對答案**)交叉檢驗——

- (a) **XBRL oracle**(XBRL:**白話:SEC 官方要求公司同時交的一份機器可讀財務數據**):Item 8 的營收/淨利/總資產對照 SEC 官方機器可讀數據,對不上就把 pass 翻成 needs_review,oracle 真正 gate 輸出、不只印警告;
- (b) **CYD oracle**:Item 1C 有 SEC 官方強制的 iXBRL(**白話:直接嵌在網頁原文裡的機器標記**)標記 span,可直接比對邊界(目前 11 家全 agree);
- (c) **topic 一致性**:span 內容與該 Item 的語意主題是否相符;
- (d) **2-of-N 引擎投票**(**白話:找 N 個外部引擎各自解一次,至少兩個講同一句話才算數**):vendored 的獨立開源抽取引擎(edgartools / edgar-crawler / datamule)對同一份原始 HTML 各自解析後投票,分歧一律標 needs_review,不單方判自己贏。

**指路**:`packages/sec_core/xbrl.py` + `tools/certify.py`;`packages/sec_core/cyd.py` + `tools/certify_cyd.py`;`packages/sec_core/topic_check.py`;`packages/sec_core/third_engine.py`(`apply_triangulation`,2-of-N)。artifact:`data/sec_eval/certification/item8_certification.json`、`data/sec_eval/cyd_groundtruth/cyd_agreement.json`。

> **不是「我的引擎最準」,是「跟我意見不合的人有權把我的 pass 降級」。**

### 3.6 怎麼防止我自己騙自己?

**比喻**:先把考卷封進信封、公證,考完才拆封對答案。如果考完才決定「哪些題算數」,分數再高也沒意義。

**機制**:防的是「自己騙自己」(overfitting 到評測集,**白話:偷偷照著考古題改答案,分數變高但實力沒變**)。兩處落地:

- (a) Task 2 的 offset gold(**白話:人工訂好的正確答案位置**)以寫死的協定半自動凍結,凍結後才當 regression 基準,且報告誠實標明它是「建構性結果」,不是絕對正確率;
- (b) Task 1 的 held-out 評測(**白話:留一批考題不給自己看,最後才拆封**)先以無人工挑題的規則選 20 題、把任務檔的 sha256 與「單跑、結果如實報、禁止改 agent 後重跑」的協定寫進 freeze manifest,然後才跑,跑出來多少報多少。

**指路**:`tools/freeze_offset_gold.py`(凍結協定寫死在程式裡);held-out 凍結協定與結果見 `docs/eval_report.md`「Browser held-out 凍結子集」節。

> **不是「我沒有偷看答案」,是「我把信封封起來、還把封條寫進程式碼」。**

### 3.7 從沒響過的警報器,是沒失火還是壞了?

**比喻**:要知道煙霧偵測器是不是裝飾品,唯一的方法是真的點根煙。從來沒響過的警報器,可能是因為沒失火,也可能是因為它壞了。

**機制**:這一層做的是**驗證那個驗證器**。對已知正確的抽取結果注入六類人工損毀——截斷(truncate)、錯位(misalign)、用目錄假冒內文(toc_anchor)、wrapper 吞噬(wrapper_swallow)、邊界抖動(jitter)、跨 Item 內文調包(cross_swap)——然後看驗證層會不會叫。

**數字**:目前六類 detection recall 全 **1.0**(**白話:六種假損毀,一個都沒漏抓**),對乾淨資料的誤報率 **0.0056**(**白話:沒壞的東西被誤叫的比例,約千分之五**)。這回答的是「驗證器本身可不可信」——沒有這一層,前面所有 oracle 都只是未經測試的警報器。

**指路**:`tests/test_verifier_mutations.py`(六類 mutation 的定義與門檻都在測試裡)。

> **結論不是「我沒發現問題」,是「我有能力發現問題,而且沒發現」。**

### 3.8 誰來反駁我?

**比喻**:天主教封聖曾設「魔鬼代言人」,唯一職責是找出候選人不該封聖的理由。能活過專職找碴的結論,才值得信。

**機制**:multi-agent workflow 把「找問題」與「盡力反駁問題」分成獨立角色；只有能落成 accession-level fixture、artifact 或 regression test 的 finding 才算成立。這避免 audit agent 的自信文字直接變成產品結論,也讓 reviewer 不必相信 agent 數量或會議紀錄,只需重跑具名案例與測試。

**指路**:`prompts/eval_design/2026-07-10-adversarial-audit-workflow.md`；`data/sec_eval/records/`；`tests/test_landmines.py`、`tests/test_refine.py`、`tests/test_cross_ref.py`。

> **不是「一群 agent 開會說沒問題」,是「說了不算,要能落成一個你可以重跑的測試才算」。**

## 4. 我輸在哪裡?(誠實的數字,不粉飾)

**數字溯源**:以下全部取自 `docs/eval_report.md`(canonical,**白話:唯一權威來源**)與其引用的 artifact,**包括我們輸掉的**。

### 4.1 外部人工標註 benchmark:我們輸了

**外部人工標註 benchmark(NTU itemseg 30-slice head-to-head),我們輸了。** 四引擎同場對跑 macro-F1(**白話:F1 是「抓得準」與「抓得全」的綜合分;macro 是每個章節各算一次再平均,不讓大章節主導**):

edgar_crawler **0.6332** > **我們 0.6245** ≈ datamule **0.6244** > edgartools **0.4386**。

單軸 F1 我們沒有贏,輸 **0.0087**,追平 datamule——如實記錄,F1 tuning 已 CLOSED。artifact:`data/sec_eval/scoring/head_to_head.json`。

### 4.2 官方 Online-Mind2Web 300 題全量:嚴格裁判只認 7.42%

**官方 Online-Mind2Web 300 題全量,嚴格裁判只認 7.42%。** 我們的 runtime verifier(landmark 口徑,**白話:只認「有沒有踩到指定的路標」,不是任務成功率**)給 95/283 = **33.57%**;但套官方 WebJudge 協定的獨立 LLM 裁判只認 21/283 = **7.42%**(abstain 70/283 = **24.73%**,**白話:裁判自己棄權不判的比例**,且已揭露其中 **63** 個 abstain 是 prompt 模板 artifact 造成的上界膨脹)。

兩軸落差 **26** 個百分點,verifier pass 但 WebJudge failure 的最大分歧格有 **56** 題——照登。此數字因 judge model 與論文不同,**不可與官方 leaderboard(Browser Use ~97%)比較**,報告裡也明寫了。

### 4.3 confidence 校準主 gate:沒過

**confidence 校準主 gate 沒過。** NTU human-labeled 層 AUROC(**白話:信心分數能不能把「答對的」排在「答錯的」前面,愈接近 1 愈能分辨**)= **0.6667**,未達 **≥0.75** gate(**MISS,報告明令「不得引用為可接受」**);ECE(**白話:自稱的把握度和實際答對比例之間的平均落差,愈小愈誠實**)**0.1235** 較前一波**轉差** **+0.0102**,原因(IBR cap 壓低 **60** 個 correct stub 的 confidence)照實寫。

過的 gate 也如實列:needs_review 錯誤攔截 77/118 = **65.3%**(gate **≥50%** 首次 PASS)。artifact:`data/sec_eval/calibration/calibration.json`。

### 4.4 false-pass:自己量出來、自己公布的

**false-pass(白話:錯的東西被蓋成 pass)是自己量出來、自己公布的。** 現行營運 gate 下 false-pass 33/243 = **0.1358**,代價是 coverage(**白話:系統敢自動蓋章、不送人工的比例**)降到 **0.4746**(**54+** 個 pointer stub 改走人工 review,審查負載上升是真實代價,列帳)。

### 4.5 好看的數字,附帶它的來歷

**好看的數字附帶它的來歷,不是一開始就好看。** Task 1 impossible-task set(**12** 個不可能/應拒絕任務)現在 silent_failure_rate = **0.0**、honest_outcome_rate = **1.0**——但報告保留了修復前的 **0.1**:先量到一個真實的 silent failure(查詢回顯被當成頁面證據),修掉根因,再重量,**measure → fix → remeasure 的完整閉環**,「不是一開始就 cook 出的 0.0」是報告原話。

verifier 本身也被 **50** 個 by-construction 損毀案例校準:sensitivity(**白話:有問題抓得出來**)**1.0** / specificity(**白話:沒問題不亂叫**)**1.0**(修復前 specificity **0.9583**,唯一的 false positive 已修)。artifacts:`data/browser_eval/impossible/impossible_results.json`、`data/browser_eval/calibration/calibration_results.json`。

### 4.6 為什麼「照登輸的數字」是核心主張,而不是弱點?

這個系統賣的東西就是「量測可信」。一個只公布贏的數字的系統,你無法知道它沒公布什麼;一個把輸的數字、量測口徑的坑、甚至自家裁判 prompt 的 bug 都寫進報告的系統,它公布的每個贏的數字才有重量。

edgar_crawler 的 **0.6332** 是一個無法自我審計的數字——它贏了 F1,但它不知道自己哪些 pass 是假的;我們知道,因為假的 pass 是我們自己抓出來公布的。差異化不在單點跑分,在驗證軸:多 oracle、誠實棄權、mutation-tested 的驗證器。

> **不是「我贏了所以你該信我」,是「我輸在哪都寫給你看了,所以我說贏的地方才有重量」。**

## 5. 怎麼五分鐘自己驗?

```bash
# 1. 健康檢查(兩個服務,免金鑰)
curl https://wealth-sec-ncku.zeabur.app/api/health
curl https://wealth-agent-ncku.zeabur.app/api/health

# 2. 抽取 AAPL 10-K(回 cached 結果或 job_id;job 可用 GET /api/jobs/<job_id> 輪詢)
curl -X POST https://wealth-sec-ncku.zeabur.app/api/extract \
  -H "Content-Type: application/json" -d '{"ticker":"AAPL"}'

# 3. 觸發 Task 1 自我修復示範(deterministic、免金鑰;或直接開網頁按「自我修復(v2 介面漂移)」按鈕)
curl -X POST https://wealth-agent-ncku.zeabur.app/api/demo/demo-v2-drift
```

```powershell
# 4. 本機跑測試(先照 README「Run locally」裝好 .venv)
.venv\Scripts\python -m pytest -m "not integration"

# 5. 單獨跑「故意弄壞驗證器」的 mutation harness
.venv\Scripts\python -m pytest tests\test_verifier_mutations.py -q
```

6. 用瀏覽器開 eval dashboard 看全部評測證據:https://wealth-sec-ncku.zeabur.app/dashboard

## 6. 想再深入,從哪讀起?

| 順序 | 文件 | 一句話定位 |
|---|---|---|
| 1 | `README.md` | 入口:部署網址、強弱案例對照表、reviewer evidence path |
| 2 | `docs/eval_report.md` | canonical 數字的唯一來源:每個 metric 附重跑指令與 artifact 路徑 |
| 3 | `docs/failure_gallery.md` | 逐條失敗事故報告(FG-* 編號):根因、修復、前後對照 |
| 4 | `prompts/README.md` | AI 協作的決策紀錄:關鍵 prompt、被否決的方案與否決理由 |
| 5 | `docs/SPEC.md` | 凍結的工程規格:系統「必須」滿足的契約,verdict/schema/協定的權威定義 |

補充兩份:`docs/supported_and_unsupported.md`(什麼能做、什麼誠實標不支援的完整矩陣)、`docs/insights_and_directions.md`(為什麼有些「還沒做」是刻意不做——例如錯的正文比誠實的指標更糟)。

### 6.1 我能宣稱什麼、不能宣稱什麼(硬切兩欄)

以下每一列都只是把前面幾節的事實搬過來,沒有新主張:

| 我**能**宣稱 | 出處 |
|---|---|
| 每個抽出的財報字都能指回原文確切位置(offset + sha256),LLM 從頭到尾不產生任何一個財報字 | 2、3.4 |
| 缺證據時回 unknown,「缺證據」在結構上不可能升級成 pass | 3.1 |
| 驗證器本身被測過:六類人工損毀 detection recall 全 1.0,乾淨資料誤報率 0.0056 | 3.7 |
| Task 1 impossible-task set 上 silent_failure_rate = 0.0、honest_outcome_rate = 1.0,且是 measure → fix → remeasure 得到的,不是一開始就 cook 出的 | 4.5 |
| 不可逆動作在程式碼層回 `refused`,不是文件宣示 | 2.1 |

| 我**不能**宣稱 | 出處 |
|---|---|
| 不能宣稱單軸抽取品質第一:NTU itemseg 30-slice head-to-head macro-F1 我們 0.6245,輸 edgar_crawler 0.6332(差 0.0087) | 4.1 |
| 不能與官方 Online-Mind2Web leaderboard(Browser Use ~97%)比較:judge model 與論文不同 | 4.2 |
| 不能宣稱 confidence 可當機率用:AUROC 0.6667 未達 ≥0.75 gate,MISS,報告明令「不得引用為可接受」;ECE 0.1235 較前一波轉差 +0.0102 | 4.3 |
| 不能宣稱沒有 false-pass:現行營運 gate 下 33/243 = 0.1358,且 coverage 只有 0.4746 | 4.4 |

讀完本文你應該能回答一個問題:**這個系統說「pass」的時候,你為什麼可以信?** 答案不在任何單一數字,而在第 3 節那條「每一層都不信任上一層」的鏈。
