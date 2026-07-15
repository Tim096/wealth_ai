# Roadmap — Known Limitations & Next Experiments

> **一句話:這不是功能願望清單,是我自己列的「我哪裡最容易被打臉」清單。**
>
> **本文拆成七段,先給你地圖:**
> ①**P0** — 五個最容易被質疑的主張,我打算交什麼證據?
> ②**V** — 驗證軸自我審計:我拿來量別人的那把尺,自己歪在哪?
> ③**P1** — 產品與可靠性還缺什麼?(Task 1 / Task 2 各一組)
> ④**P2** — Reviewer 要花多少力氣才能相信我?
> ⑤**LLM 決策** — 哪裡用 LLM、哪裡堅持不用,gate 是什麼?
> ⑥**執行順序** — 為什麼是這個順序?
> ⑦**Definition of Done + 不做** — 怎麼算做完?什麼我絕對不幹?

目標不是增加功能數量，而是把目前最容易被質疑的主張換成可獨立重驗的證據。完成與否不改變本文件對現狀弱點的誠實陳述。

**白話:一般的 roadmap 是許願池——列滿新功能,讓人以為現在已經很完整。這份相反:每一列都對著一個「現在就會被打臉的地方」。打勾的項目不會讓已公布的難看數字變好看;沒打勾的項目也不會因為寫進 roadmap 就算做過。未完成就是未完成。**

- 原則：先 freeze protocol，再跑 evaluation；歷史 artifacts 不覆寫；runtime verifier、LLM judge、human label 三者不得混成同一口徑。

**白話:考卷先封好、公證,才准開考(freeze protocol);考壞的成績單不許撕,只能加印新的一張(artifacts 不覆寫);三把不同的尺——程式自己量的、AI 裁判量的、真人量的——不許混在一起報成同一個數字。**

## P0 — 五個最容易被質疑的主張,我打算交什麼證據?

| 項目 | 成本 | 對應弱點 | 交付物與驗收門檻 |
|---|---:|---|---|
| 用修正版 WebJudge 重判 frozen 283 trajectories | M，1–2 天 | Task 1 evaluation credibility | 沿用原 trajectory，不重跑 agent；`283/283` 有 binary outcome；template-artifact 為 `0`；公布 success/failure、abstain、difficulty strata、verifier × judge confusion；隨機抽 30 題 blind human audit 並列 agreement。 |
| 建立新的 unseen real-site set | L，3–5 天 | Task 1 real-world generalization | 先提交 freeze manifest，再跑至少 50 題、10 個 domains、5 類 task；成功條件由獨立 reviewer 建立，不從 task text heuristic 衍生；報 task-success、environment failure、silent-failure、p50/p95 latency、cost/success 與 bootstrap CI。 |
| Live self-maintenance causal ablation | M，2 天 | Task 1 mechanism substance | 對同一組任務分別關閉 selector repair、overlay recovery、new-tab following、vision escalation、replay cache；每個元件必須有可重播 failure fixture 與前後差值，不能只展示 happy-path demo。 |
| Task 2 外部人工 span gold | L，3–5 天 | Task 2 correctness credibility | 從未參與調參的 filings 分層抽樣：modern HTML、wrapper、cross-file、legacy SGML；雙人標註 item start/end，分歧 adjudication；公布 macro P/R/F1、bootstrap CI、missing/hallucination 與 boundary error。 |
| Task 2 confidence recalibration | M，2–3 天 | confidence / failure handling | 僅使用新的 human gold；比較 raw confidence、isotonic、logistic calibration；目標 AUROC `>=0.75`、ECE `<=0.10`。若未達標，UI 改顯示 risk band，不宣稱 probability。 |

**這張表的術語,就地翻成人話:**

- **trajectory**:agent 當時實際跑過的完整操作軌跡紀錄。重判用舊軌跡、不重跑 agent,是為了不讓「換一次運氣」混進分數。
- **template-artifact 為 `0`**:上一波有 abstain 是被我自己的 prompt 模板害的(裁判棄權不是因為題目難,是因為我的模板寫壞)。這一輪要求這種假棄權必須歸零。
- **difficulty strata**:按題目難度分層報,不讓簡單題把平均拉高。
- **verifier × judge confusion**:把「我的程式判什麼」×「AI 裁判判什麼」排成一張對照格,分歧格數字要攤開。
- **blind human audit**:真人不知道機器判了什麼,獨立再判一次 30 題,然後看兩邊同意率。
- **freeze manifest**:先寫死「要跑哪些題、成功條件是什麼」再開跑——先封考卷,才准考。
- **bootstrap CI**:反覆重抽樣算出的信賴區間,白話就是「這個數字的誤差範圍有多寬」。
- **ablation**:一次拆掉一個零件,看分數掉多少;掉了才證明那個零件真的有用,而不是擺著好看。
- **span gold**:真人標好的「這個章節從哪個字到哪個字」標準答案。雙人標、分歧再仲裁(adjudication),避免一個人的偏見變成金標準。
- **AUROC / ECE**:AUROC = 信心分數能不能把「答對的」排在「答錯的」前面;ECE = 自稱的把握度與實際答對比例之間的平均落差。

**這一列必須講白:`目標 AUROC >=0.75`——這個目標到今天還沒達成。** 現況是 MISS,所以走的正是這一列自己寫下的退路:UI 改顯示 risk band(**白話:只說「高風險 / 中風險 / 低風險」這種分級,不謊稱一個看起來很精確的機率**),不宣稱 probability。

> **不是「我們的信心分數有 0.75 的水準」,是「沒到 0.75,所以我不准自己講機率」。**

## V — 驗證軸自我審計:我拿來量別人的那把尺,自己歪在哪?

**這一段的來歷要先講白:整個專案賣的就是「知道自己何時對、何時錯、何時證據不足」。那我對自己的驗證器,就該套同一把尺。** 2026-07-15 我把驗證軸上全部 24 條公式與檢驗逐條攤開重算(不是讀 code 推理,是實際執行),結果如下。**這一段全部未完成 —— 它是本文件裡最新、也最難看的一段。**

**先給結論,不埋在後面:**

> **驗證軸是分層的。判定核心(三態梯)是硬的、可證的、第一性原理站得住的;訊號層(confidence 八項、三道 overshoot 護欄、四種交叉檢驗)是軟的、手調的、大量未經校準的。而現在的敘事把兩者放在同一個「嚴謹」的框裡講 —— 核心撐得起那個框,訊號層撐不起。**

### V-0 先講站得住的(這不是自誇,是對照錨)

沒有對照,底下的負面清單會被讀成「整套都爛」。實際不是:

- **三態梯 `combine_checks`**(`packages/eval_core/verdict.py:40-65`):`fail > unknown > pass` 的短路優先梯,全檔零個魔術數字。第一性原理無懈可擊 —— 它把「否定」與「無知」分成兩種東西,並規定無知永不升級為成功。**這是整個專案唯一一條我攻不破的公式。**
- **`gate_then_average` 的 Extractor/Verifier 分離**(`packages/browser_agent/second_judge.py:262-280`):引用的 span 若不在快取證據裡,一律降級 abstain。幻覺證據結構上過不了。
- **`span_prf` 的漏抓計 0 分且留在分母**(`packages/sec_core/scoring.py:114`):多數人會把漏抓移出分母讓數字好看,這裡沒有。
- **`cost_metrics` 分母為零回 `None`**(`packages/browser_agent/cost_metrics.py:23-24`):不給假的 `0.0`。
- **`risk_band` 的存在本身**(`packages/sec_core/risk_band.py`):AUROC gate 沒過 → 降級成風險分級、不宣稱機率。我把它的推導逐位重算過,`273+124+115=512`、`231+94+69=394`,與 stratum 總數完全相符,並與 `risk_coverage` 曲線交叉驗證通過。**推導誠實,不是編的。**

### V-1 有真洞 — 依投報比排序,不依嚴重度

| 項目 | 成本 | 證據(實測,非推理) | 交付物與驗收門檻 |
|---|---:|---|---|
| **CYD 官方 oracle 只驗 recall,對主要病灶瞎眼** | S,半天 | `sec_core/cyd.py:222-225` 只 gate `coverage`;`containment` 在 L223 算出、round、寫進 `CydCheck`,**從不參與判定**。而 `boundary.py:238-241` 自陳主要失效模式是 boundary bleed(NTU fold 123/141):**recall≈1、precision 崩壞** —— 正是 CYD 判 `agree` 的狀態。 | gate 加入 `containment`(數字已算好);對 mutation harness 補「span 包含官方 1C 但長 N 倍」的 fixture,recall 必須為 1.0;重跑並公布 before/after 的 CYD verdict 分布。 |
| **`aggregate_verdict` 叫「2-of-N 投票」,實際是 OR 閘** | S,半天 | `sec_core/third_engine.py:292-299`:`if "agree" in verdicts: return "agree"`。**3 引擎、1 同意 2 反對 → 判 agree、零懲罰、不進 review。** docstring 說「a lone dissenting engine is outvoted」,實際是 **a lone AGREEING engine outvotes everyone**。且 N 越大越寬鬆 —— 加證據反而弱化檢驗,方向是反的。 | 改真多數決(`agree ≥ ⌈N/2⌉`)或改名為 `any_engine_agrees` 並在 docstring 標明其寬鬆語義;兩者擇一但必須先量 N=1/2/3 下的 verdict 分布差異,不得無實測直接換。 |
| **`robust_contains` tier 2/3 產生偽陽性** | M,1–2 天 | `browser_agent/text_match.py:63-70`。tier 2 是**純 bag-of-words,無相鄰性/順序約束**。實測四例全部 `True`:needle `"New York"` 對上 `"New products…York Street"`;`"Board Game"` 對上 `"Board of Directors…Game theory"`;tier 3 去空白後 `"in car"` 命中 `"Incarnation"`、`"the rap"` 命中 `"therapy"`。docstring 宣稱「never on partial overlap alone」字面為真、實質誤導。 | tier 2 加入視窗約束(所有 token 需落在同一段/N 字元內);tier 3 `_MIN_DESPACE_LEN` 從 5 提高並要求詞界對齊。**先建 ≥30 組真陽性 + ≥30 組上述形態的偽陽性 regression set,再改**;改後真陽性召回不得下降。 |
| **`tristate` 的漏抓警報是相關失效** | M,1–2 天 | `sec_core/scoring.py:35-36`:`missing` + `toc_listed` → `MISSING`(警報);`missing` + 非 `toc_listed` → `NULL`(合法缺席)。**裁判是 TOC,而 TOC 出自同一份你正在解析失敗的文件。** TOC 解析失敗 → 真漏抓被靜默重分類成合法 null → **警報正好在解析器最壞時啞掉**。 | 引入與 TOC 獨立的第二個 should-exist 來源(item 序列先驗 / XBRL / 引擎票);TOC 不可解析時 tri-state 必須回 `unsupported` 而非 `NULL`;公布「TOC 解析失敗」filing 的比例與其 MISSING 率變化。 |
| **`_download_ok` 8MB 截斷後回 `fail`** | S,半天 | `browser_agent/verifier.py:58,66`:只讀前 `_DOWNLOAD_SCAN_BYTES = 8_000_000`,讀不到 needle 即 `fail`。**只看了一部分卻斷言「它不存在」—— 違反本專案憲法(證據不足 → `unknown`)。** 附帶結構性後果:PDF 亂碼率必然 > 5% → **含內容 needle 的 PDF 任務結構上永不可能 pass**,而這未寫進 SPEC 6.4 支援邊界表。 | 截斷未命中改回 `unknown` 並在 reason 標明「只掃描前 N bytes」;PDF/二進位的內容不可判定寫入 SPEC 6.4 邊界表,或接上 text extraction 後再判。 |
| **size_bands 與 length_prior 對同一份證據雙罰** | S,半天 | `sec_core/pipeline.py:274` 與 `:283` 皆傳入同一個 `breakdowns`,兩者都可能 append `max_score=3.5` 的零分 component → 分母 `10+3.5+3.5=17` → 倍率 `10/17 = 0.588`。**「絕對字元數超標」與「佔全文比例超標」量的是同一件事:這段太長了。** 兩個近乎完全相關的訊號被當成兩個獨立證據各罰一次。 | 兩者擇一 append、或取 max、或明確論證兩者殘差獨立(需實測相關係數);公布 before/after 的 confidence 分布與 AUROC/ECE 變化。 |

**翻成人話,挑最刺的三個:**

- **CYD 那個**:SEC 強制 filer 用 XBRL 標記 Item 1C —— 這是全專案**唯一一個官方標準答案**。而我只檢查「官方標的內容有多少在我裡面」(recall),沒檢查「我裡面有多少是官方標的」(precision)。**所以我的 span 長 100 倍、把官方那段整個包進去、順便吞掉 Item 2 整章,照樣認證通過。** 而我自己的文件白紙黑字寫著:我 87% 的錯誤就長這樣。**唯一的官方裁判,對主要病灶免疫。修法是一行,而且那個數字早就算好躺在那裡沒人看。**
- **OR 閘那個**:我寫「三方交叉驗證」,聽起來很嚴謹。實際上程式是 `any()` —— 問三個獨立引擎,**只要有一個說我對,就算對**。而且引擎加越多,「碰巧有一個同意」的機率越高 → **這道檢驗越弱**。加證據應該讓檢驗更嚴,我這裡讓它更鬆。
- **TOC 那個**:「文件目錄說有這個 item、我卻沒抓到」才報警。**但目錄也是我從這份我正在解析失敗的文件裡解出來的。** 一份格式怪到讓我 TOC 解不出來的 filing,正是我最可能漏抓的 filing —— **而那時警報剛好啞了。這不是寫錯,是架構層的相依性沒被看見。**

> **不是「這六個是小 bug」,是「其中兩個讓我最引以為傲的檢驗,在最需要它的時候剛好失效」。**

### V-2 數學上不可能觸發的檢驗(寫了、跑了、報了 0 violations —— 而 0 是保證的)

- [ ] **SRAF 全文不變量對 boundary bleed 永不觸發**。`sec_core/size_bands.py:68` 設 `SRAF_TOLERANCE = 1.25`,檢驗 `sum_item_words / sraf_n_words ≤ 1.25`。但 `sraf_n_words` 是**整份提交檔**(主文件 + exhibits)字數,items 是主文件的**子集** —— 只要各 span 不重疊,`ratio ≤ 1.0` **恆成立**。實測 15 份全部符合:`max_ratio = 0.9856`,`violations = 0`。**要觸發得抓出比整份文件還多 25% 的字,那只有 span 大幅重疊才可能**(而程式用 `set` 只去重完全相同的 `(start,end)`,部分重疊會被算兩次)。**它只抓得到「你重複輸出了同一段」,完全抓不到「你的邊界越界了」。** 且 `violations: 0` **不是證據** —— 註解自陳 tolerance 來源是「max ratio observed, plus headroom」,**用觀測最大值定義門檻再回報同批資料零違反,是循環論證**。交付:改成能偵測 boundary bleed 的不變量(例如逐 item 對 SRAF 分項、或 span 重疊率獨立成檢);tolerance 必須用 held-out filing 標定,不得用觀測最大值 + 餘裕;若保留現行式,artifact 必須標註「此檢驗對 boundary bleed 不敏感」。
- [ ] **`topic_check` 特異度近乎零**。`sec_core/topic_check.py:21` 的訊號詞**不互斥**:Item 1A 的訊號是 `["risk","adversely","could","materially","harm","uncertain"]` —— **「could」和「risk」在 10-K 每一章都出現**。實測拿 100% 純 Item 7 散文餵進去:`check_topic('1A', <item-7 散文>) → consistent`,`matched=['risk','adversely','could']`。**它唯一抓得到的是「完全沒有風險語言的 span」,而真實失效模式是「span 溢出到隔壁財務散文」—— 隔壁散文照樣滿是 risk 和 could。它在最常見的錯誤上結構性無效。** 交付:改判別式訊號(每個 item 的 log-odds / TF-IDF 對比其他 item,而非裸子字串);驗收門檻為「拿 item X 的散文餵 item Y 的檢查,`consistent` 率 ≤ 0.1」;在達標前 `topic_check` 的 `consistent` **不得作為任何 confidence component 或 pass 依據**。(已做對的部分保留:`_BOILERPLATE` 正則正確分出 `None./Not applicable./Reserved`,不罰合法短答案。)

> **不是「這兩道檢驗通過了」,是「這兩道檢驗在數學上不可能不通過,所以它們的通過不含資訊」。**

### V-3 統計上撐不住現在的講法

- [ ] **risk band 講的是三段,資料只撐得起兩段。** 我算了 Wilson 95% CI:`low 42/273 = 0.1538 → [0.116, 0.201]`、`medium 30/124 = 0.2419 → [0.175, 0.324]`、`review 46/115 = 0.4000 → [0.315, 0.491]`。**low 與 medium 的 CI 重疊 —— 在 n=512 下這兩段統計上分不開**;只有 `review` 真的與 `low` 拉開。且三個數字**全是 in-sample**(切點與錯誤率出自同一批 512 個項目,無 held-out,是系統性樂觀的再代入估計),卻報到小數第 4 位。交付:`band_payload` 增加 `ci_low`/`ci_high`/`in_sample: true` 欄位並在 UI 同步顯示;在取得 held-out gold(見 P0「Task 2 外部人工 span gold」)前,**文件與 UI 不得把 low/medium 描述為兩個可區分的操作點**。
- [ ] **0.6 這條切點,正好落在信心分反轉的位置。** 實測 `ntu_human_labeled` 的 reliability bins:`[0.5,0.6)` n=71 **acc 0.6620**,`[0.6,0.7)` n=15 **acc 0.4667**。**剛好越過「過關線」的項目,比剛好沒越過的更容易是錯的。** band 層級的排序(0.1538 < 0.2419 < 0.4000)還單調,純粹是被 n=273 與 n=93 兩個大桶拉回來的。**0.6 是從部署閘門繼承來的,不是為了最大化區分度選的,而且局部是反向的。** 交付:`risk_band.py` docstring 明載此事(現在沒有);在 held-out gold 上重掃切點,若最佳切點 ≠ 0.6 則兩者並列公布,**不得只留好看的那個**。
- [ ] **`pseudo_gold_corpus_only` 的 AUROC = 0.3389,低於擲硬幣的 0.5 —— 這不是「弱」,是「反向」。** 實測其 reliability bins **正確率隨信心單調下降**:`[0.4,0.5)` n=26 acc **1.0000** → `[0.9,1.0)` n=158 acc **0.8038**。把分數取負號,AUROC 會變成 0.661。**數字有記帳**(`docs/eval_report.md:249`「aux stratum pseudo_gold AUROC 0.3459→0.3389」),**但只當流水帳記在護欄子句裡,沒有任何一句話說「低於 0.5 代表這一層的信心分是反的」。按本專案自己的 house style(負面結果拉到標題級),一個低於隨機的 AUROC 應該是標題,不是括號。** 交付:①`eval_report.md` 與 `risk_band.py` 以標題級揭露此事並寫明其含義;②檢驗那個可能的辯護 —— pseudo_gold 的標籤是「corpus teacher verdict == agree」,而 confidence 內含 `cross_detector_agreement` / `verifier_result` 等**我們自己的內部訊號**,反相關**可能**是在講「我們最有信心處正是教師因邊界問題最愛唱反調處」,即**教師的性質而非我們的性質**。**這個辯護在被寫出來並實測之前不算數** —— 帳面上就是兩層 stratum、一層 0.667、一層 0.339。
- [ ] **`span_prf` / macro-F1 在 item 層級對幻覺完全瞎眼。** `sec_core/scoring.py:101-119`:gold 為 null 而我們抓出內容 → 無 gold span → **排除在 F1 之外**,只記在 confusion counts。推論:**一個系統幻覺出 20 個 item、把 10 個真的抓完美,macro-F1 = 1.0。** docstring 誠實寫了,confusion counts 也另外帶著這資訊 —— **所以只要 F1 從不單獨被引用就沒問題**。但既有敘事是「vendored engines 的 raw F1 贏我們」。交付:**任何 F1 對照表旁必須同框出現 hallucination / omission 的 confusion counts**,否則就是拿一個對幻覺瞎眼的指標在比;`docs/eval_report.md` 與 README 的每一處 F1 引用逐一補上。

> **不是「我們的信心分數有鑑別力,只是弱了點」,是「一層 0.667、一層 0.339 —— 而 0.339 的意思是排反了,這件事我到今天還沒解釋」。**

### V-4 誠實但要改字(態度沒問題,文字在誤導)

- [ ] **`OVERSHOOT_COMPONENT_MAX = 3.5` 校準的那條「0.75 review 線」不存在。** `sec_core/confidence.py:18-24` 的註解**坦承這個數字是從目標倒解出來的**(要 `10/(10+x) < 0.75` → `x > 3.333` → 取 3.5)——**這個誠實我給滿分,不改**。但實際部署的線是 **0.6**(`risk_band.py:33`,`verifier_false_pass.gate = "needs_review == False and confidence >= 0.6"`),band 邊界是 0.6 / 0.9。實測 `band_for(0.7407) → "medium"` —— **0.74 不但沒低於某條 0.75 的線,它還高於實際的 0.6 過關門檻。真正擋下項目的是同時設的 `needs_review = True`,不是這個權重;3.5 在部署行為上幾乎是裝飾。** 交付:註解改指 0.6/0.9 的真實 band,或明講「本權重不負責 gating,gating 由 needs_review 承擔」。
- [ ] **「cap」是錯字,它不是上限,是固定倍率。** 加一個 `score=0, max=m` 的 component,**代數上完全等價於乘上 `base/(base+m)`**。實測倍率恆為 `10/13.5 = 0.7407`,與原分數無關:`1.00→0.7407`、`0.90→0.6667`、`0.80→0.5926`、`0.60→0.4444`。**「caps an otherwise-perfect item at 0.74」描述的是特例,讀者會當成通則。** 交付:`confidence.py` docstring 改述為「乘 0.7407 的相對折扣」並列出上表。
- [ ] **`"held-out measurement only, never parameters"` 這行字,跟它隔壁的欄位互相矛盾。** `data/sec_eval/calibration/topic_prior_attribution.json` 與 `length_prior_attribution.json` 的同一個 JSON 字串裡寫著這句免責,**而同一份檔案的 `verdicts` 就記著用 NTU AUROC 差值做的出貨/砍掉決定**(`margin: shipped … AUROC +0.0040` / `floor: KILLED … AUROC -0.0086`)。**標籤沒被當梯度參數擬合 —— 字面為真;但它們選了哪個版本上架 —— 這是 model selection on the measurement set,對「這個估計偏不偏」而言是同一件事。** 這是 V-4 這一類的**最嚴重案例**:態度誠實、數字誠實、**唯獨那行字會讓讀者以為 Definition of Done 第 4 條已達成**。完整證據與交付門檻見下方 Definition of Done 第 4 條;**交付:改寫該行為「labels were not fit as parameters, but variant selection was scored on them — this is not an unbiased held-out estimate」,並在取得真 held-out gold 前,所有引用該 artifact 的地方同步標註。**
- [ ] **同一件事用了三種懲罰代數,而且排序看起來是反的。** 「引擎不同意」`max_score=1.0`(`third_engine.py:371`)→ 倍率 **0.909**;「overshoot」`max_score=3.5` → 倍率 **0.741**。**「一個獨立實作說你抓錯了」是外部證據,「我自己量到這段比中位數長」是內部啟發式 —— 外部證據理應更重,這裡卻輕 3.5 倍,無任何註解說明。** 更糟:`third_engine.py:376` 同一訊號因一個 dict 查找是否命中,走**乘法(×0.909)或減法(`confidence - 0.15`)兩條完全不同的路**,而 `0.15` **無任何理由註解**。交付:統一為單一懲罰代數;三個權重的相對排序必須有實測支撐(各自對 AUROC 的邊際貢獻)或明載為未校準。

**另外三件小的,一併記帳(成本皆 S,不單獨立項):**

- `ConditionCheck.required`(`eval_core/verdict.py:21`)宣告了「True = 成功條件 / False = 禁止條件」,而 `combine_checks` 全程只看 `.observed`。我 grep 過 `packages/`、`apps/`、`tools/`:**零處讀取**。現在不出錯(建構時語義已反轉),但**這是一顆等人踩的地雷** —— 未來任何人照它分組會拿到相反結果。刪掉或接上。
- `_check_success` 的 `table_extracted` 未命中回 `unknown`(`verifier.py:89`),隔壁 `field_value_equals` 同情況回 `fail`(`:91`),**無註解解釋**。後果:帶 `table_extracted` 的任務**結構上永不可能被判 fail**,使 fail rate 系統性低報。
- `detect_false_success` 的分數空間實測**只有 10 個相異值**(32 種特徵組合塌縮),卻 `round(score, 6)`。**手設 5 權重、二值特徵的線性模型報到小數第 6 位是虛假精度**(模組自陳標註軌跡遠低於訓練所需的 ~60 條 —— 這個自覺是對的,不該被 6 位小數推翻)。改 2 位。

> **不是「這三條寫錯了」,是「這三條的態度全對、數字全誠實,只有文字在替它們吹牛 —— 而文字才是別人讀到的東西」。**

### V-5 這一段自己的邊界(不寫這條就變成我在雙標)

- **本次審計是單人、單次、白箱的**,沒有第二人獨立重跑。**它本身不是 held-out 證據,是一份自陳。**
- **審計只涵蓋驗證軸的 24 條公式/檢驗**,不涵蓋 extraction 主線、前端、部署。
- **所有實測數字出自 `2026-07-15` 當下的 working tree**,artifact 引用為 `data/sec_eval/calibration/calibration.json`、`data/sec_eval/size_bands/size_bands.json`、`data/sec_eval/calibration/length_prior.json`。**上述任何一條修好之後,這些數字都會變,而本段的舊數字不覆寫,只加印新的一版。**
- **V-1 到 V-4 全部未完成。列進 roadmap 不等於做過。**

> **不是「我審過了所以我很嚴謹」,是「我用同一把尺量了自己,量出 13 個問題,而且在修好之前它們就掛在這裡」。**

## P1 — 產品與可靠性還缺什麼?

**以下每一項都還沒做完(`[ ]` 就是還沒做),唯一打勾的那一項有日期、有 endpoint、有實測結果。**

### Task 1

- [ ] 將 answer-quality gate 從已知 skip-link 擴充為 evidence-based classifier；先收集至少 30 個 navigation residue 與 30 個合法短答案，再定規則，避免靠字串黑名單無限增生。
- [ ] 每個 answer 顯示來源 URL、selector、擷取時間與 evidence screenshot；答案與 evidence 不一致時回 `unknown`。
- [ ] Capability guard 增加中英文拒絕案例與 boundary tests，避免 `post` / `pay` 等裸字誤殺正常內容。〔**2026-07-15 實測:這一列低估了問題。不只誤殺,而是中文完全失效(fail-open)。** `packages/browser_agent/capability.py:18-20` 全部 regex 用 ASCII `\b` 詞界 + `re.I`,**CJK 永遠匹配不到**。我實跑 `screen_task()`:`登入我的銀行帳戶` → **allowed=True**、`購買第一個商品並結帳` → **allowed=True**、`幫我付款` → **allowed=True**;而 `Log in to my bank account` → 正確 refused。同時誤殺照舊:`Read the latest blog post about widgets` → refused(post_submit)、`Find the pay scale for engineers` → refused(purchase)、`Summarize the post-mortem report` → refused(post_submit)。**`capability.py:1-8` 宣稱「responsibility boundary 是寫在 code 裡、不只寫在文件裡」,README 宣稱「Login, CAPTCHA, purchases, posting… are refused by design」——而這個專案是 zh-TW 介面。對中文輸入,這條邊界目前是未強制執行的。** 這是 fail-open,不是 fail-closed,方向最壞。交付門檻升級:①先補 zh-TW 詞表並改用非 `\b` 依賴的邊界判定,②`tests/test_browser_agent.py:206-219` 現有 3 條英文斷言擴充為中英各 ≥10 條拒絕案例 + ≥10 條近似誤殺案例,③**在修好前,README 與 SPEC 6.4 的「refused by design」必須標註「僅英文輸入」**。〕
- [ ] 在兩個不同日期重跑 frozen live set，量化 website drift、pass@2 與 flakiness；不得把兩次最好結果拼成單一成功率。〔**2026-07-15 查核:三個 live suite 全部只有一次 run,日期都是 `2026-07-14`**(`data/browser_eval/live_{information_retrieval,mixed_interaction,attested_smoke}/results.json`);grep `pass_at_|flak|drift` 於三者皆零命中。唯一的 pass@k artifact(`data/browser_eval/passk/passk_results.json`)**不是 live set 且自陳無效**:Script Mode 確定性建構 → `pass@1 == pass@k`、`flaky_rate: 0.0` 是必然結果,自述「Non-trivial flakiness needs a live LLM planner」。**這一列零進度。**〕
- [ ] 對 live service 做 1/2/4/8 concurrent sessions 壓測，公布 queue wait、task latency、memory、timeout、LLM rate-limit 與 cost。〔**部分已達,但測錯對象**:`tools/scalability_bench.py` 的 1/2/4/8 掃描**真的跑過**(`runs/browser_eval/scalability/w{1,2,4,8}_rep{1,2}/`,2026-07-11,有 throughput / speedup_vs_w1 / avg_task_latency_ms 實數)。**但它 docstring 自陳「Deterministic, offline, $0: file:// mock sites, Script Mode, no LLM」—— 測的是離線 worker pool,不是 live service。** 六項要求裡只達成 task latency 一項:queue wait ✗(`apps/services/agent/` grep `queue_wait|queued_at` 零命中)、memory ✗(只有一次性 `ram_available_gb` 快照)、timeout ✗(只數 `watchdog_kills`)、LLM rate-limit ✗(路徑上根本沒有 LLM)、cost ✗(無 LLM 故 $0,只有計算時間模型)。且 `apps/services/agent/main.py:99,110` 的 HTTP 429 admission limit **從未被任何 bench 觸發過**。**離線 bench 的數字不得引用為 live service 的併發能力。**〕

**翻成人話:**第一項是「別再靠關鍵字黑名單擋爛答案,先收集夠多真實案例再定規則」——實測現在的「gate」就是 `agent.py:38` 一個**三個字串的集合**,沒有 classifier、沒有那 30+30 的資料集;第二項是「答案要附證據,對不上就認輸回 `unknown`」——實測 `answer` 目前是 `agent.py:402` 的**一個裸字串**,URL / selector / 時間 / 截圖四樣一樣都沒有(原料存在於 step trace,但從未綁到答案上);**第三項要重講,因為原本寫的比實情輕**——我以為問題是「防衛過度、誤殺正常內容」,實測發現**真正的問題是反過來的:中文輸入完全穿透**。`登入我的銀行帳戶`、`購買第一個商品並結帳`、`幫我付款` 三句,guard 全部放行。**一個宣稱「寫在 code 裡的責任邊界」,對它自己的介面語言不生效——而且是往「該擋沒擋」的方向壞,不是往「擋太兇」的方向壞。** 第四項的 **pass@2** 是「跑兩次至少過一次」,而**這一列自己寫死了不准把兩次最好的結果拼成一個成功率**——實測目前只跑過一次,零進度;第五項是同時開 1、2、4、8 個工作階段壓測,連帳單一起公布——**掃描真的跑了,但跑在離線 mock 上、沒有 LLM,所以六個要測的東西裡只測到一個。**

> **不是「capability guard 擋太兇要放寬」,是「它對中文根本沒在擋,而我到今天才實際跑過中文輸入」。**

### Task 2

- [x] ✅ **已完成(查核於 2026-07-15)**:Task 2 strong cases 與前端好壞並列 — `apps/services/sec/static/index.html:194-232` 三張卡並列(`task2StrongCase` AAPL Item 8「✓ 目前做得好(限定範圍)」/ `task2BodyCase` INTC·C 頁碼錨點正文 / `task2WeakCase`「⚠ 目前沒做好」),且 `:206` 就地自我設限「不代表整份 filing 全部正確」——履行本列「通過前只稱限定案例」的約束;`README.md:132-137` 好壞等寬並列表(`:130` 明寫「不是先鋪三頁優點再把缺點塞附錄」);可重跑 artifact `data/sec_eval/certification/item8_certification.json`(AAPL `3/3 XBRL headline figures found in the span`,`certified`),以 `tools/certify.py` 重生;渲染由 `tests/test_reviewer_tour.py:75-78`、`tests/test_dashboard_render.py:35` 把關。〔**未達的一角,照實記**:`apps/web/test-center/index.html` 這第三個前端**零 case 展示**——「前端優先明列」只在部署版 SEC UI 與 dashboard 成立,測試中心 UI 沒有。〕
- [ ] 實作**真正跨檔** exhibit / proxy-statement join：只接受 accession、filing manifest、document type 與 source link 可驗證的正文。〔**部分已達**:Intel/Citi 的**同檔**印刷頁碼錨點正文已由 `page_map` / `source_ranges[]` 從 `incorporated_by_reference` 轉為 source-addressable `partial` span(多段串接);仍未做的是另外**跨檔申報**的 proxy statement(Item 10–14)join,維持 pointer + review。〕
- [x] ✅ **已完成(2026-07-14)**:normalized text 可重現鏈 — `/api/jobs/{id}/normalized` 提供 normalized 全文 + `X-Normalized-Sha256` / `X-Normalization-Version` header;item payload 帶 `normalized_sha` / `source_ranges`,線上實測依 offsets 重算 SHA 為 MATCH。
- [ ] 移除全域 filing state 的併發串台風險；所有 item request 必須攜帶 accession，mismatch 明確失敗。〔**部分已達,而且未達的那半比本列原本寫的更難看**:①**部署服務已 job-scoped** —— `apps/services/sec/main.py:14` 自陳「job-scoped (no global mutable filing state)」,狀態存在每個 `Job` 裡(`jobs.py:44`),item 經 `job.state` 取得(`main.py:427`),`main.py`/`pipeline.py` 無模組級可變 filing state。②**但全域狀態仍然出貨** —— `tools/test_center.py:50` 還留著模組級 `_SEC_STATE = {"result": None, ...}`,而 `:202-203` 的 `sec_item_text()` 直接讀它、**且不取 `_SEC_LOCK`**(鎖只包住 `sec_extract`,是 last-writer-wins)。A 抽 AAPL、B 抽 MSFT,A 的 item request 會拿到 MSFT 的正文 —— **正是本列要消滅的串台,原封不動**。而 `啟動測試中心.bat` 就是跑這支,`apps/web/test-center/index.html` 也還在。③**accession 那半完全沒做** —— `main.py:422-423` 是 `def job_item(job_id: str, code: str = Query(default=""))`,**無 accession 參數、無 mismatch 檢查**。不透明的 uuid `job_id` 在結構上擋住了串台,但本列白紙黑字的要求(「必須攜帶 accession,mismatch 明確失敗」)未實作。**本列讀起來像「全域狀態已移除」——它從部署服務移除了,沒從 repo 移除。**〕
- [ ] 對 20-F、10-K/A、pre-2001 SGML、PDF/scanned filing 顯示具體 unsupported reason，不回模糊的「找不到」。〔**部分已達**:20-F 走 `NotA10KFilerError` 列出實際 form 分布;PDF/scanned/binary 標 `unsupported_scanned_or_binary` + 前端紅色未支援 banner(2026-07-15,payload `supported` + `coverage=null`,非假 100%)。仍待:10-K/A amendment 專門處理、pre-2001 SGML text-mode normalizer。**2026-07-15 查核補充,這兩項比「仍待」更難看:**①**10-K/A 是靜默丟棄,不是「未特別處理」** —— `resolver.py:152` 明明設了 `is_amendment`,`main.py:356` 卻用 `if not f.is_amendment` **直接從 picker 濾掉,不吐任何 reason**。`docs/usage_scenarios.md:169` 自己招了:「靜默過濾,picker 完全不見…docs 層誠實、UI 層靜默——自相矛盾」。**這正是本列要消滅的行為,卻發生在本列自己的範圍內。**②**pre-2001 SGML 根本沒有偵測** —— `packages/` grep `sgml` 零命中;實際行為是 0 個 heading candidate → `pipeline.py:335` 吐 `"no item heading candidates found — unsupported or non-10-K document"`。**這句話把兩個原因混在一起(「不支援」還是「根本不是 10-K」),而且從不說出「pre-2001 SGML」——正是本列開宗明義要禁止的模糊。**〕
- [ ] 加入 review workload 指標：coverage、false-pass risk、每 100 filings 預期人工審查量與每正確 item 成本。

**翻成人話,特別是那兩個「部分已達」——半套就要講成半套:**

- **跨檔 join**:年報常常寫「這段請見我們的股東會通知書」。同一個檔案裡靠印刷頁碼找回正文,我做到了(Intel/Citi);**跨到另一份申報文件去撈 proxy statement(Item 10–14),我還沒做**,現在照實維持 pointer + review。
- **unsupported reason**:20-F(外國公司年報)、PDF/掃描檔,現在會明講「不支援,原因是這個」,前端還會出現紅色未支援 banner——**而且 `coverage=null`,不假裝 100%**。**10-K/A(修正版年報)與 pre-2001 SGML 老格式,仍然沒做。**
- **併發串台**:目前的 filing 狀態是全域的,兩個人同時查有互相污染的風險。**這是已知的、還沒修的問題**;修法是所有 item request 都必須帶 accession(SEC 給每份申報的唯一編號),對不上就明確失敗,不猜。
- **review workload**:把「人工要審多少」變成可報的數字——每 100 份 filing 要多少人力、每個正確 item 花多少錢。誠實揭露的代價要列帳,不能只講風險降低。

> **不是「跨檔 join 做好了」,是「同檔的做好了,跨檔的還沒,所以我照實標 pointer」。**

## P2 — Reviewer 要花多少力氣才能相信我?

**目的只有一個:把「相信我」的成本從「讀完整個 repo」壓到「五分鐘」。2026-07-15 逐項查核後,一項已完成、兩項部分已達、兩項零進度 —— 原本寫「這一段全部未完成」是舊的,已更正。**

- [ ] 首頁加入 5 分鐘 reviewer path：一個 Task 1 repair pass、一個 honest unknown、一個 Task 2 modern pass、一個 wrapper/review 案例。〔**部分已達(3/4)**:導覽真的出貨了,但不在 `apps/web/`(那裡沒有),而在 `apps/services/agent/static/index.html:169-215` 與 `apps/services/sec/static/index.html:146-190`「🧭 5 分鐘審閱導覽 · Reviewer tour」,四站、跨服務互連、跑真動作而非錄影。**達成 3 站**:v2-drift repair pass ✓、honest UNKNOWN ✓、AAPL Task 2 pass ✓。**未達第 4 站**:本列要求的是 **wrapper/review 案例**,實際第 3 站放的是 capability refusal(登入+購買 → REFUSED);真正的 wrapper/needs_review 案例只以未納入導覽的 chip 存在(`sec/static/index.html:225-226` 的「Review INTC」「Review C」)。另記:導覽預設 `hidden`,且可經 localStorage 永久關閉(`sec/static/index.html:590`)。`README.md:147` 的「Reviewer evidence path」是**讀文件清單**,不是這 4 個 demo,不能當本列的達成證據。〕
- [ ] UI 顯示 `pipeline_rev`、contract source、model/provider、artifact link 與可複製的 reproduction command。〔**部分已達,但本列的重點那項是零**:contract source **DONE**(`agent/static/index.html:313-316` 渲染 `start_url_source` / `conditions_source`);model/provider **部分**(`agent/static/index.html:290` 有 mode+model banner,SEC 前端兩者皆無);artifact link **部分**(只有截圖 `:334,401`,無 eval artifact 連結);`pipeline_rev` **未顯示** —— 它只存在於 `apps/services/sec/main.py:335` 的 JSON,前端反而叫 reviewer 自己去 curl(`sec/static/index.html:231`:「部署版本可從 /api/health 的 build_sha／pipeline_rev」),agent 端則完全沒有;**reproduction command 零** —— 四個前端 grep `reproduc|repro_cmd|clipboard|navigator.clipboard` **命中數 0**。**而這正是本段白話自己說的「每個畫面都附你可以複製去自己重跑的指令」—— 全段最核心的那項,一個字都沒寫。**〕
- [x] ✅ **已完成(查核於 2026-07-15)**:raw exception → 人類可讀 failure reason + `unknown` 顯示最後截圖 — `apps/services/agent/static/index.html:348-361` 的 `const DIAG={...}` 把 14 個錯誤碼映射成白話 zh-TW,**未知碼明確 fallback 回原始碼(不猜)**;`:387-405` 的 `renderTriage()` 在 `unknown/fail/refused/error` 時渲染「🩺 診斷 / triage — 為何不是 PASS」+ missing evidence + **最後畫面 last screenshot**;分類來源 `packages/browser_core/failures.py:12-23`,並帶誠實旗標 `dispatched`(`:31-33`「Declared != dispatched」)。〔**保留一角**:本列的「下一步」是**隱含在 DIAG 字串裡**(例如「改用語意 / 無障礙樹重新定位」),不是獨立欄位。實質達成,但不是字面全達。〕
- [ ] 增加 deployment smoke workflow：兩個 health endpoints、deterministic demo、AAPL extraction、public asset cache、rollback check。〔**零進度,且 rollback 在 repo 裡不存在**:`.github/workflows/` **只有 `ci.yml`**,無 smoke workflow;五項要求全部 ✗;**`docs/deploy.md` 通篇沒有 rollback 章節**。現存的是手動、非 workflow:`tools/smoke_real_filing.py`(手動 EDGAR AAPL)與一份 build-SHA 存證的 2 題 live smoke(`data/browser_eval/live_attested_smoke/results.json`,`deployment_attested: true`,`passed: 2/2`),依 `README.md:169` 由人手動跑。**手動跑過 ≠ 有 workflow。**〕
- [ ] 建立 release checklist，要求 README 數字、eval report、artifacts、CI 與 live revision 完全一致。〔**零進度**:`find -iname "*release*"` 無檔案;字串「release checklist」全 repo 僅出現在本列自己。**而這一列現在有了實測的存在理由 —— 見下方 Definition of Done 第 6 條:repo 裡同時有四個不同的 revision 在流通。**〕

**翻成人話:**第一項刻意排了**一個 honest unknown**——展示櫃裡故意放一個「我不知道」,而不是四個成功案例;**這一站真的做到了**,而且導覽整體 4 站到了 3 站——只是第 4 站放錯東西(放了拒絕示範,不是本列要的 wrapper/review 案例)。第二項是每個畫面都附「你可以複製去自己重跑的指令」——**實測:零。四個前端一個 clipboard 都沒有。** 第三項是把程式的原始錯誤訊息翻成人看得懂的失敗原因——**這項做完了,而且做得比本列要求的更誠實:未知錯誤碼明確 fallback 回原始碼,不猜。** 第五項是防止「網頁上的數字」跟「報告裡的數字」對不起來——**實測現在有四個 revision 在流通,所以這一列從「預防」變成「已經發生了,要修」。**

> **不是「請相信我的結論」,是「這裡有指令,你自己跑一次」——而這句話目前是空頭支票:全段最核心的 reproduction command,四個前端一個都沒有。**

## LLM 決策 — 哪裡用 LLM、哪裡堅持不用?

| 區域 | 決策 | 理由與 gate |
|---|---|---|
| Task 1 planner | 使用 LLM | 自然語言分解與跨站 adaptation 確實需要；action 必須通過 capability screen，最終結果由獨立 verifier 決定。 |
| Task 1 verifier | 不使用 LLM 作唯一裁判 | 有機讀條件時 deterministic verifier 唯一裁決，LLM 不介入；零條件（開放式）任務在 verdict 時走 evidence-grounded LLM 評分（`second_judge.score_open_ended`，引文必須逐字存在於 evidence，ground 不了 → abstain → `unknown`，離線/無 key 維持 `unknown`，絕不捏造 pass）；LLM judge 對有條件任務仍只作離線 measurement，不改 runtime verdict。 |
| Task 1 vision escalation | 條件式使用 LLM | 僅在 DOM/a11y repair 卡住時啟用；必須量化增益、額外 latency、tokens 與 cost/success。 |
| Task 2 primary extraction | 不使用 LLM | 邊界、offset、hash、XBRL 與 filing metadata 可用 deterministic pipeline 重驗，成本與 reproducibility 更佳。 |
| Task 2 review fallback | 實驗後再決定 | 只針對 `needs_review` strata 做 A/B；必須在 untouched human gold 上降低 false-pass，且輸出 source span。未同時改善 risk 與 coverage就不採用。 |
| Frontend | 不使用 LLM | Common Requirement 3 是 presentation requirement；LLM 不會提高 UI 可驗證性。 |

**這張表的一句話總結:LLM 只准出現在「需要理解人話」的地方,不准出現在「需要蓋章」的地方。**

- **planner 用 LLM**:因為把一句人話拆成步驟、換個網站還能適應,確實只有 LLM 做得到。但它產生的每個動作都要先過 capability screen(能力篩檢),最後結果由獨立的 verifier 說了算。
- **verifier 不讓 LLM 當唯一裁判**:有機器可讀條件時,LLM 連碰都不能碰。只有「零條件」的開放式任務才走 LLM 評分,而且引文必須**逐字**存在於證據裡——ground 不了就棄權(abstain)回 `unknown`;離線或沒有 key 也維持 `unknown`。**絕不捏造 pass。**
- **Task 2 主抽取不用 LLM**:因為邊界、offset、hash、XBRL 都能用確定性流程重驗——**便宜、可重現,而且不會編**。
- **Task 2 review fallback 還沒決定**:這是「實驗後再決定」,不是「已經在用」。gate 寫死了:必須在**沒碰過的**人工金標準上降低 false-pass,且**未同時改善 risk 與 coverage 就不採用**——不准拿降低風險當藉口把 coverage 砍到見骨。

> **不是「這個系統用了很多 LLM」,是「這個系統把 LLM 關在它不會害人的地方」。**

## 執行順序 — 為什麼是這個順序?

**白話:先把尺校準,再量身高。順序反了,後面做什麼都是白做。**

0. **Ruler repair(V 段,2026-07-15 新增為第 0 步)**:先修驗證軸自己。優先序:①**V-1 的 CYD containment gate**(一行、數字已算好、修的是唯一官方 oracle 對主要病灶的盲點)→ ②**capability guard 中文 fail-open**(這是宣稱了但未強制的邊界,屬於誠實問題不是功能問題)→ ③**V-4 全部改字**(不需實驗,只需把文字改成與程式行為一致)→ ④V-1 其餘 + V-2 + V-3。
1. **Evidence repair**：重判 frozen 283、human audit、同步唯一 canonical metrics。
2. **Unseen evaluation**：freeze 新 Task 1 set 與 Task 2 human gold，禁止邊跑邊調參。
3. **Mechanism improvement**：只修新 evaluation 暴露的最大 failure buckets，逐項 ablation。
4. **Product hardening**：cross-file join、concurrency、evidence links、failure UX。
5. **Independent rescore**：reviewer 不看開發過程，只依 prompt、public repo、live frontend 與 frozen artifacts重新評分。

**為什麼 V 是第 0 步、插在「重判」前面?** 因為第 1、2 步要用尺去量,而 V 段的發現是**尺本身有 13 個問題**。拿一把已知歪掉的尺去重判 283 條軌跡、去量新的 unseen set,量出來的數字還是得重量一次。**尤其 V-4 那三條改字不需要任何實驗、不改任何行為、當天就能做完 —— 沒有理由排在後面。**

先修「尺」(0),再修「量測」(1、2),才修「機制」(3);機制修完才修「產品」(4);最後一步刻意把自己交出去——**reviewer 不看開發過程**,只看 prompt、公開 repo、線上前端與凍結的 artifact 重新評分。

> **不是「先把功能做完再來量」,是「先確定尺沒歪,才有資格談做完」——而 2026-07-15 之前,我一直以為尺是沒歪的那一個。**

## Definition of Done — 怎麼算做完?

**這七條全部未完成(`[ ]`)。它們是驗收條件,不是成績單。2026-07-15 逐條查核,七條的狀態沒有一條改變 —— 但其中兩條的「未完成」比原本以為的更硬,補記在後。**

- [ ] 所有 headline metrics 都有 tracked artifact、重現指令、分母與 failure accounting。〔**部分已達,卡在「所有」二字**:機制是真的 —— `data/claims_registry.json` 16 條 claim,每條帶 `artifact` + `rule` + `doc_evidence`,並由 `.github/workflows/ci.yml`(「Verify headline claims against tracked artifacts」→ `tools/verify_claims.py`)在 CI 把關;分母紀律確實落實(見下第 3 條)。**但未涵蓋**:cost/latency 數字、以及 eval-dashboard 自己的數字(`apps/web/eval-dashboard/data.json`:11 filings / 253 items / pass 70.36%)都不在 registry 裡。**更硬的一點**:撐起 5 條註冊 claim 的 NTU 資料集**本身不是 tracked artifact** —— `tools/fetch_ntu_itemseg.py:9-16` 明寫「NEVER committed to the repo」,gitignored。**一條「有 tracked artifact」的 claim,其資料來源不可追蹤。**〕
- [ ] Task 1 有可信的 task-success rate，不再使用 landmark hit 代替。〔**未達,而且是 repo 自己說的**:`data/claims_registry.json` 的 `task1_300run_verifier_landmark` 自我標註「landmark-hit axis = pass 95 of done 283 (**diagnostic axis, NOT task success rate**)」;另一軸 WebJudge 21/283 註冊為「advisory only」。`docs/eval_report.md:496` 補刀:「這批題的 success condition 多為單一 landmark,verifier 對其是弱 proxy」。**兩個軸,沒有一個是 task success rate。**〕
- [ ] Task 1 unseen set 無 silent success；environment failures 獨立列出但保留全分母口徑。〔**未達,因為 unseen set 不存在**(P0 那列仍開著)。**但分母紀律這半是真的,值得記**:`m2w_full300_20260711/webjudge_results.json` → `n_done: 283`、`n_harness_error: 17`、`env_blocked: 0`、`success_rate_full_denominator_300: 0.3167`,並註明「'refused' kept as its own bucket… counted in denominator」。**一份好會計,記在一個不是 unseen 的 set 上。**〕
- [ ] Task 2 至少一組未參與調參的人工 span gold 與 confidence calibration。〔**未達,而且這一條要講重話 —— 它是本次查核最該被看見的發現。** ①**NTU gold 沒有 held-out,它決定了出貨組態。** `data/sec_eval/calibration/topic_prior_attribution.json` 與 `length_prior_attribution.json` **同一個 JSON 字串裡**寫著「labels are held-out measurement only, never parameters」,**而同一份檔案的 `verdicts` 欄記著**:`"margin": "shipped — … NTU fires 10 (7 correct / 3 error), **AUROC +0.0040**, hi-conf errors -5"`、`"floor": "**KILLED** … **AUROC -0.0086**; removed from the codebase"`。**標籤確實沒被當成梯度參數擬合 —— 這句話字面為真。但它們決定了哪個變體出貨、哪個被砍。這就是 model selection on the measurement set。對「這是不是無偏估計」這個問題而言,這是一個沒有差別的區別。** `length_prior_attribution.json` 同理:「'two_sided_flat' is the shipped configuration」,選自在同一批 30 份 cached NTU filings 上評分的 4 變體 sweep。②**它不是 span gold。** NTU 是 line-level BIO(`calibration.json` 的 `definitions/correct_ntu` = 「line-level item F1 >= 0.5」)—— 一個衍生的二元標籤,不是人工 span offsets。③**真正的 span gold 是自標的,不是人工的。** `data/golden_labels/offsets/AAPL.json` 的 `labeling` 自陳「semi-automatic: pipeline offsets frozen only where the independent third engine… returned verdict=agree」—— **我自己的輸出,由一個姊妹引擎背書**,僅「human spot-checked before commit」;`tools/freeze_offset_gold.py:15-16` 承認「this tool only enforces the mechanical rules」;`docs/research/giants_task2.md:40` 承認「自家 gold 僅 5 份 self-frozen(F1 1.0 無誤差訊號可校準)」。④calibration 存在但兩個 gate 皆 MISS(`auroc 0.6667` < 0.75、`ece 0.1235` > 0.10,n=512)——**這一點 `docs/verifier_trust_card.md:15,25` 據實報 MISS 且拒絕引用為可接受,該給的分要給。** **總結:任何人讀到「held-out measurement only, never parameters」就停下來,會以為這條達成了。它沒有。這行字必須改。**〕
- [ ] 每項 LLM 使用都有 deterministic control、增益、latency、tokens、USD 與 stop rule。〔**未達**:`grep -rni "stop rule|stop_rule|停止規則"` 全 repo **只命中本列自己**。現存的 ablation 明確不含 LLM(`docs/eval_report.md:598`:「mock/script 確定性環境,$0、無 LLM」)—— **那就不是「某個 LLM 用途」的對照組**。vision escalation 預設未測(`eval_report.md:474`:「未設 AGENT_VISION=auto」)。tokens/USD 有 per-run(`agent/static/index.html:365-369` 的 `renderCostChip`),但沒有 per-LLM-use 的增益表。〕
- [ ] CI、README、eval report、public frontend 顯示同一 revision 與同一組數字。〔**未達,而且實測有四個 revision 同時在流通**:`git HEAD` = `aafcda1`;`README.md:52` + `live_mixed_interaction/results.json` = `f384843`;`live_information_retrieval/results.json` = `abc2e19`;`live_attested_smoke/results.json` = `d062c0e`。CI 不顯示 revision;`apps/web/eval-dashboard/` grep `build_sha|revision` 零命中;兩個服務前端都不渲染 `build_sha`。**per-artifact 的 `source_commit` 與 build-SHA 存證(`agent/main.py:69-73`)是好機器,只是從沒有人把靶對齊過。** 這條直接餵給 P2 的 release checklist。〕
- [ ] 獨立 review 的每一項扣分都能映射回一個可驗證的 experiment。〔**未達,且前提未發生**:獨立 rescore 還沒做(執行順序第 5 步),所以沒有扣分可映射。「獨立 review…扣分」全 repo 只出現在本列與執行順序第 5 步。〕

**翻成人話,挑四條最刺的:**

- 「不再使用 landmark hit 代替」——白話:現在報的 Task 1 數字是「有沒有踩到路標」,**不是真正的任務成功率**。這條沒打勾,代表這個弱點今天還在。而且**這句不是我謙虛,是 `claims_registry.json` 自己寫的**:「diagnostic axis, NOT task success rate」。
- 「保留全分母口徑」——白話:環境掛掉的題目可以另外列,但**不准從分母裡拿掉**。拿掉分母是把成功率灌水最常見的手法。**這半我做到了**(refused 留在分母、`success_rate_full_denominator_300: 0.3167`),只是做在一個不是 unseen 的 set 上——**好會計記在錯的帳本上,還是不算數。**
- 「未參與調參的人工 span gold」——**這條是四條裡最刺的,而且刺的是我自己。** 我在兩個 attribution 檔裡寫了「labels are held-out measurement only, never parameters」,**而同一個檔案的下一個欄位就記著我用 NTU 的 AUROC 差值決定了 margin 出貨(+0.0040)、floor 砍掉(−0.0086)。** 白話:**我沒有拿標準答案去「訓練」,但我拿標準答案去「挑哪個版本上架」——對「這個分數可不可信」來說,這兩件事一樣糟。** 而且那批 NTU 根本不是 span gold(是 line-level 的衍生二元標籤),我真正的 span gold 是**我自己的輸出給姊妹引擎背書後凍結的**,只有 5 份、F1 1.0、無誤差訊號。**這條沒打勾是對的,但光沒打勾不夠——那行「never parameters」必須改掉,因為它會讓人以為打勾了。**
- 「每一項扣分都能映射回一個可驗證的 experiment」——白話:別人挑我毛病,我不能用嘴反駁,只能用一個他能重跑的實驗回應。

> **不是「這七條還在努力中」,是「其中一條的達成假象,是我自己寫的一行字造成的 —— 而我今天才發現它跟隔壁欄位互相矛盾」。**

## 不做 — 什麼事我絕對不幹?

**這一段是我對自己的手銬。上面每一條「還沒做」都可以慢慢做;下面每一條,做了就是造假。**

- 不在看過 held-out 結果後修改成功條件。
- 不覆寫失敗的歷史 artifacts；新增版本並保留 before/after。
- 不把 LLM self-report、runtime landmark、WebJudge 與 human label 混成一個成功率。
- 不為提高數字排除 anti-bot、timeout、unsupported 或 abstain；同時報 gradable 與 all-task denominator。
- 不為追求表面分數重寫 failure gallery、刪除負面結果或宣稱與官方 leaderboard 可比。

**以下四條為 2026-07-15 驗證軸審計(V 段)後新增 —— 它們堵的是這次自己抓到的路:**

- **不把在同一批資料上切點、又在同一批資料上量錯誤率的數字,當成 held-out 估計引用。** 現行 risk band 的 0.1538 / 0.2419 / 0.4000 全是 in-sample;在取得未參與調參的 gold 前,一律標 `in_sample: true` 並附 CI。
- **不把「標籤沒被當梯度參數擬合」當成「標籤是 held-out」。** 用測量集挑變體就是 model selection on the measurement set。要嘛別挑,要嘛別叫它 held-out —— 不准兩個都要。
- **不把數學上不可能觸發的檢驗,其 `violations: 0` 當成證據。** 用觀測最大值 + 餘裕定義門檻、再回報同批資料零違反,是循環論證。門檻必須用 held-out 標定,否則 artifact 上要標明該檢驗的不敏感範圍。
- **不讓一個未實測過的 guard 出現在能力邊界的宣稱裡。** capability guard 對中文 fail-open 這件事,是我寫了「寫在 code 裡的責任邊界」卻從沒跑過中文輸入才發生的。**宣稱一道邊界存在之前,先跑它一次。**

**翻成人話,一條一句:**看過答案不准改題目;考壞的成績單不准撕,只能加印新的一張並保留前後對照;四把不同的尺不准混成一個數字;不准把「機器人被擋」「逾時」「不支援」「裁判棄權」這些難看的題目從分母偷偷拿掉——gradable 與 all-task 兩個分母都要報;不准為了好看重寫失敗紀錄、刪負面結果,或宣稱自己跟官方 leaderboard 可以比。

**新增那四條的白話:**用同一批人考試、又用同一批人算及格率,那個及格率不准當成「拿去考別人也會這樣」;「我沒拿答案訓練」跟「我拿答案挑要交哪一份」是同一件事,不准只承認前者;一個門檻設在「比我看過最糟的還糟 27%」的檢驗,它永遠不會響——那它的「零違反」不是證據,是廢話;最後一條最直接:**你說你擋得住,先當著我的面擋一次。**

> **這份 roadmap 的價值不在「我打算做什麼」,在「我已經先把自己作弊的路全部堵死了」——而這次新增的四條,堵的全是我自己已經走上去的路。**
