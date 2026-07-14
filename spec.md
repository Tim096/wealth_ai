# spec.md — 這個專案在做什麼(由淺入深)

> 本文是給「從零開始的讀者」的分層說明書:第 1、2 節不需要任何技術背景,第 3 節逐項深入機制,第 4 節是不粉飾的量測數字,第 5 節讓你五分鐘親手驗證,第 6 節是深入閱讀地圖。
> 工程凍結規格是另一份文件 `docs/SPEC.md`,兩者用途不同:那份是「系統必須長什麼樣」,這份是「這個系統到底在做什麼、為什麼可信」。

---

## 1. 一句話 + 三段白話故事

**一句話:兩個 AI 工人(一個會操作瀏覽器、一個會拆解財報),加上一個從頭到尾不信任他們的檢查系統——這個專案賣的不是工人,是檢查系統。**

想像你有一個很聰明的實習生。你叫他去查資料、寫報告,他隔天交上來一份漂亮的成果,還拍胸脯說「都做完了」。問題是:你怎麼知道哪一頁能信?實習生最危險的不是做不出來——是做錯了還理直氣壯。主管真正需要的從來不是那份報告,而是「知道哪頁能信」的能力。

AI 就是這種實習生。它會操作網頁、會讀財報、會給答案,而且永遠自信。這個專案做了兩個這樣的 AI 工人:一個聽自然語言指令去操作瀏覽器(網頁改版了還能自己找到路),一個把上市公司幾百頁的年報拆成標準章節。但專案的重點不在工人多能幹,而在旁邊站著一個「不聽工人自述、只看物證」的檢查系統:工人說「做完了」不算數,檢查系統要親眼看到證據才蓋章;看不到證據就寫「不知道」,絕不因為工人講得好聽就放行。

為什麼「檢查」比「做出來」難且值錢?因為做錯了還說做對了(silent failure,無聲失敗)是 AI 最貴的錯誤形態——它不會報錯、不會當機,只會安靜地把錯的東西交到你手上。寫出一個 80 分的 AI 工人已經不稀缺;稀缺的是一套能證明「這 80 分裡哪些是真的 80 分」的制度。本專案的每一個設計,都是圍繞這件事。

## 2. 這個系統做什麼(給一般讀者)

**Task 1 — Browser Agent(瀏覽器代理人)**:你用一句中文或英文描述任務(例如「去搜尋框查 widget 然後打開第一筆結果」),它自己規劃步驟、點擊、輸入;網站改版(按鈕換了 id、彈出 cookie 視窗、多了誘餌按鈕)時,它會診斷失敗原因並自我修復,而不是死在原地。最後由獨立的 verifier 判定 pass / fail / unknown——不採信 agent 自己說的「我做完了」。

**Task 2 — SEC 10-K Extractor(財報抽取器)**:輸入一個美股代號(例如 `AAPL`),它去 SEC EDGAR 抓該公司的 10-K 年報,拆成標準的 Item 1–16 章節(含 1A、7A 等子項,共 23 個代號)。關鍵保證:**每個字都能指回原始文件的確切位置**——每段抽出的文字附帶字元起迄位置(offset)與內容指紋(sha256),LLM 從頭到尾不產生任何一個財報字,所以不可能「幻覺」出財報內容。

還有一條刻意畫下的邊界:登入、購買、結帳、送出表單這類不可逆動作,Task 1 **在程式碼層拒絕執行**(task 回 `refused`),不是文件上寫寫而已——寧可少做,不做「做了但你不知道後果」的事。指路:`packages/browser_agent/capability.py`。

兩個系統都公開部署,**你自己就能試**,不用安裝、不用帳號:

- Task 1:https://wealth-agent-ncku.zeabur.app (點「Self-repair / 自我修復(v2 介面漂移)」看免金鑰的自我修復示範)
- Task 2:https://wealth-sec-ncku.zeabur.app (輸入 `AAPL` 按「Extract / 開始抽取」,點任一 Item 看原文與驗證訊號)

## 3. 核心技術由淺入深

八項機制,共同主題只有一個:**每一層都假設上一層可能在騙你**。agent 可能謊報完成 → verifier 只看物證(3.1、3.2);verifier 可能壞掉 → mutation harness 故意弄壞資料測它(3.7);抽取結果可能看起來對其實錯 → 多個獨立 oracle 交叉驗(3.5);評測本身可能自己騙自己 → 凍結協議與對抗式稽核(3.6、3.8)。每項:生活比喻 → 機制 → 去哪裡看 code/artifact。

### 3.1 三態 verdict:pass / fail / unknown

**比喻**:海關查驗只有三種結果——放行、攔下、留檢。行李掃不出來不等於沒問題,只能留檢,不能直接放行。

**機制**:所有判定只允許三種狀態。規則寫死在共用層:每個成功條件逐一核對,任何一條被觀測到違反 → fail;沒有違反但至少一條「無法觀測」→ unknown,**永遠不會是 pass**。「缺證據」在結構上不可能升級成成功——這是對 silent failure 的結構性防禦,不是文件宣示。連「零條件」的輸入都會回 unknown 並明講「拒絕在沒有證據時宣稱成功」。

**指路**:`packages/eval_core/verdict.py`(`combine_checks`,全檔不到 70 行,建議直接讀)。

### 3.2 verifier 是唯一裁判,LLM 只能建議

**比喻**:運動員不能兼任裁判。跑者自己喊「我壓線了」不算,計時器說了算;旁邊的評論員(LLM)可以發表意見,但改不了成績。

**機制**:Task 1 的 verifier 是確定性程式碼:檢查 URL 是否包含指定片段、頁面是否真的出現指定文字(且會剔除「0 results for "xxx"」這種把查詢原句回顯的假命中)、下載檔是否真的存在且內容包含指定字串。agent 的自述完全不進判定;answer 型任務只認 agent 實際從頁面抽出的文字,沒抽到就是 fail。另有一個 LLM second judge,但它是 advisory-only:分歧只會標 needs_review,**從不改判**。

**指路**:`packages/browser_agent/verifier.py`(判定本體);`packages/browser_agent/second_judge.py`(檔案開頭明寫「the runtime verifier stays the SOLE judge」「it never changes a verdict」)。

### 3.3 selector 自我修復

**比喻**:常去的超市改裝了,貨架全搬位。死記「第三排左邊」的人會失敗;記得「我要找的是醬油」的人會重新找到。修復靠的是理解用途,不是死記位置。

**機制**:動作失敗時先「診斷」失敗類型(selector 找不到、被 modal 擋住、點了沒反應……),再套對應策略——是診斷驅動,不是盲目重試。修復時列舉頁面 accessibility tree 的候選元素,以 role / aria-label / placeholder / 文字 / 位置對「元素用途」(搜尋框、送出鈕、下載鈕……)評分選擇,並明確避開誘餌(decoy)元素;還有可行性 gate:如果沒有任何元素真的能執行該動作,誠實回報「no viable candidate」,而不是默默點錯的東西。Agent Mode 的 history 也保留 grounded target、輸入值與 intent；同頁狀態連續兩次 no-effect 後，第三次相同 action 會在 executor 前被擋下。三種不同 DOM shape 的確定性 mechanism probe 從 generic history `0/3` 提升到 grounded history `3/3`。

**指路**:`packages/browser_agent/repair.py`(`diagnose_failure`、`_PURPOSE_HINTS`、decoy 與 feasibility gate)；`packages/browser_agent/agent.py`(`action_history_entry`、`action_state_signature`)；`tools/action_history_cross_site_eval.py`。

### 3.4 source-exact 溯源:offset + sha256

**比喻**:嚴謹的圖書館員不幫你抄書(抄寫可能出錯或加油添醋),只告訴你「第 762158 到 771903 字元」,還附一枚指紋,讓你隨時驗證那段文字沒被動過。

**機制**:Task 2 每個抽出的 Item 都是原始文件的一段連續 span,以 `start_offset` / `end_offset` / `text_sha256` 定址;LLM 不產生 filing text,只有結構分析參與定界。status 同樣誠實分級:pass / partial / missing / incorporated_by_reference(原文只放了一個「請見他處」的指標時如實標示,不假裝抽到內容)/ reserved / unsupported。

**指路**:`packages/sec_core/items.py`(`ItemSegment` schema,檔案第一行即寫明「the LLM never generates filing text」)。

### 3.5 多重獨立 oracle

**比喻**:法庭不會只聽一位證人。多位互不認識的證人獨立作證且說法一致,才值得採信;有人翻供就送重審。

**機制**:Task 2 的每個抽取結果被多個獨立訊號源交叉檢驗——(a) **XBRL oracle**:Item 8 的營收/淨利/總資產對照 SEC 官方機器可讀數據,對不上就把 pass 翻成 needs_review,oracle 真正 gate 輸出、不只印警告;(b) **CYD oracle**:Item 1C 有 SEC 官方強制的 iXBRL 標記 span,可直接比對邊界(目前 11 家全 agree);(c) **topic 一致性**:span 內容與該 Item 的語意主題是否相符;(d) **2-of-N 引擎投票**:vendored 的獨立開源抽取引擎(edgartools / edgar-crawler / datamule)對同一份原始 HTML 各自解析後投票,分歧一律標 needs_review,不單方判自己贏。

**指路**:`packages/sec_core/xbrl.py` + `tools/certify.py`;`packages/sec_core/cyd.py` + `tools/certify_cyd.py`;`packages/sec_core/topic_check.py`;`packages/sec_core/third_engine.py`(`apply_triangulation`,2-of-N)。artifact:`data/sec_eval/certification/item8_certification.json`、`data/sec_eval/cyd_groundtruth/cyd_agreement.json`。

### 3.6 凍結協議:先凍題目,再跑分

**比喻**:先把考卷封進信封、公證,考完才拆封對答案。如果考完才決定「哪些題算數」,分數再高也沒意義。

**機制**:防的是「自己騙自己」(overfitting 到評測集)。兩處落地:(a) Task 2 的 offset gold 以寫死的協定半自動凍結,凍結後才當 regression 基準,且報告誠實標明它是「建構性結果」,不是絕對正確率;(b) Task 1 的 held-out 評測先以無人工挑題的規則選 20 題、把任務檔的 sha256 與「單跑、結果如實報、禁止改 agent 後重跑」的協定寫進 freeze manifest,然後才跑,跑出來多少報多少。

**指路**:`tools/freeze_offset_gold.py`(凍結協定寫死在程式裡);held-out 凍結協定與結果見 `docs/eval_report.md`「Browser held-out 凍結子集」節。

### 3.7 mutation harness:故意弄壞,測驗證器

**比喻**:要知道煙霧偵測器是不是裝飾品,唯一的方法是真的點根煙。從來沒響過的警報器,可能是因為沒失火,也可能是因為它壞了。

**機制**:對已知正確的抽取結果注入六類人工損毀——截斷(truncate)、錯位(misalign)、用目錄假冒內文(toc_anchor)、wrapper 吞噬(wrapper_swallow)、邊界抖動(jitter)、跨 Item 內文調包(cross_swap)——然後看驗證層會不會叫。目前六類 detection recall 全 1.0,對乾淨資料的誤報率 0.0056。這回答的是「驗證器本身可不可信」——沒有這一層,前面所有 oracle 都只是未經測試的警報器。

**指路**:`tests/test_verifier_mutations.py`(六類 mutation 的定義與門檻都在測試裡)。

### 3.8 對抗式稽核:一批 agent 專門證偽另一批的結論

**比喻**:天主教封聖曾設「魔鬼代言人」,唯一職責是找出候選人不該封聖的理由。能活過專職找碴的結論,才值得信。

**機制**:multi-agent workflow 把「找問題」與「盡力反駁問題」分成獨立角色；只有能落成 accession-level fixture、artifact 或 regression test 的 finding 才算成立。這避免 audit agent 的自信文字直接變成產品結論，也讓 reviewer 不必相信 agent 數量或會議紀錄，只需重跑具名案例與測試。

**指路**:`prompts/eval_design/2026-07-10-adversarial-audit-workflow.md`；`data/sec_eval/records/`；`tests/test_landmines.py`、`tests/test_refine.py`、`tests/test_cross_ref.py`。

## 4. 誠實的數字(不粉飾)

以下全部取自 `docs/eval_report.md`(canonical)與其引用的 artifact,包括我們輸掉的:

1. **外部人工標註 benchmark(NTU itemseg 30-slice head-to-head),我們輸了。** 四引擎同場對跑 macro-F1:edgar_crawler **0.6332** > **我們 0.6245** ≈ datamule 0.6244 > edgartools 0.4386。單軸 F1 我們沒有贏,輸 0.0087,追平 datamule——如實記錄,F1 tuning 已 CLOSED。artifact:`data/sec_eval/scoring/head_to_head.json`。
2. **官方 Online-Mind2Web 300 題全量,嚴格裁判只認 7.42%。** 我們的 runtime verifier(landmark 口徑,非任務成功率)給 95/283 = **33.57%**;但套官方 WebJudge 協定的獨立 LLM 裁判只認 21/283 = **7.42%**(abstain 70/283 = 24.73%,且已揭露其中 63 個 abstain 是 prompt 模板 artifact 造成的上界膨脹)。兩軸落差 26 個百分點,verifier pass 但 WebJudge failure 的最大分歧格有 56 題——照登。此數字因 judge model 與論文不同,**不可與官方 leaderboard(Browser Use ~97%)比較**,報告裡也明寫了。
3. **confidence 校準主 gate 沒過。** NTU human-labeled 層 AUROC = **0.6667**,未達 ≥0.75 gate(MISS,報告明令「不得引用為可接受」);ECE 0.1235 較前一波**轉差** +0.0102,原因(IBR cap 壓低 60 個 correct stub 的 confidence)照實寫。過的 gate 也如實列:needs_review 錯誤攔截 77/118 = 65.3%(gate ≥50% 首次 PASS)。artifact:`data/sec_eval/calibration/calibration.json`。
4. **false-pass 是自己量出來、自己公布的。** 現行營運 gate 下 false-pass 33/243 = **0.1358**,代價是 coverage 降到 0.4746(54+ 個 pointer stub 改走人工 review,審查負載上升是真實代價,列帳)。
5. **好看的數字附帶它的來歷,不是一開始就好看。** Task 1 impossible-task set(12 個不可能/應拒絕任務)現在 silent_failure_rate = **0.0**、honest_outcome_rate = **1.0**——但報告保留了修復前的 0.1:先量到一個真實的 silent failure(查詢回顯被當成頁面證據),修掉根因,再重量,measure → fix → remeasure 的完整閉環,「不是一開始就 cook 出的 0.0」是報告原話。verifier 本身也被 50 個 by-construction 損毀案例校準:sensitivity 1.0 / specificity 1.0(修復前 specificity 0.9583,唯一的 false positive 已修)。artifacts:`data/browser_eval/impossible/impossible_results.json`、`data/browser_eval/calibration/calibration_results.json`。

**為什麼照登輸的數字是核心主張而非弱點**:這個系統賣的東西就是「量測可信」。一個只公布贏的數字的系統,你無法知道它沒公布什麼;一個把輸的數字、量測口徑的坑、甚至自家裁判 prompt 的 bug 都寫進報告的系統,它公布的每個贏的數字才有重量。edgar_crawler 的 0.6332 是一個無法自我審計的數字——它贏了 F1,但它不知道自己哪些 pass 是假的;我們知道,因為假的 pass 是我們自己抓出來公布的。差異化不在單點跑分,在驗證軸:多 oracle、誠實棄權、mutation-tested 的驗證器。

## 5. 五分鐘自己驗證

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

## 6. 深入閱讀地圖

| 順序 | 文件 | 一句話定位 |
|---|---|---|
| 1 | `README.md` | 入口:部署網址、強弱案例對照表、reviewer evidence path |
| 2 | `docs/eval_report.md` | canonical 數字的唯一來源:每個 metric 附重跑指令與 artifact 路徑 |
| 3 | `docs/failure_gallery.md` | 逐條失敗事故報告(FG-* 編號):根因、修復、前後對照 |
| 4 | `prompts/README.md` | AI 協作的決策紀錄:關鍵 prompt、被否決的方案與否決理由 |
| 5 | `docs/SPEC.md` | 凍結的工程規格:系統「必須」滿足的契約,verdict/schema/協定的權威定義 |

補充兩份:`docs/supported_and_unsupported.md`(什麼能做、什麼誠實標不支援的完整矩陣)、`docs/insights_and_directions.md`(為什麼有些「還沒做」是刻意不做——例如錯的正文比誠實的指標更糟)。

讀完本文你應該能回答一個問題:**這個系統說「pass」的時候,你為什麼可以信?** 答案不在任何單一數字,而在第 3 節那條「每一層都不信任上一層」的鏈。
