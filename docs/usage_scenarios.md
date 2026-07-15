# Usage Scenarios:人怎麼用、怎麼信、哪裡會斷

> 這份文件是 evaluation discipline 的一部分:pass rate / F1 / triangulation 之外,把「具體的人、具體的輸入、具體的期待」攤開,對照程式碼現況找落差。每個「現況」欄標注 **已驗**(讀 code 驗證過,附檔案:行號)或 **推理**(從程式結構推斷,未實跑)。嚴重度分三級:**breaks_trust**(結論與人眼背離、或宣稱與實作矛盾)> **friction**(能用但體驗斷裂)> **polish**(細節)。
>
> 讀者:評分者與面試官。這份文件本身就是主張——量化指標捕捉不到「信任如何建立、如何一次歸零」,所以要用情境補上。
>
> **文件定位:**這是開發期間的 scenario audit 與修復 ledger,保留當時發現、已修與未修案例,不是目前功能清單。最終 metrics 以 [`eval_report.md`](eval_report.md) 為準;目前支援邊界以 [`supported_and_unsupported.md`](supported_and_unsupported.md) 為準。

**先把上面那段翻成人話。**這份文件在做一件事:**我拿著我自己的程式碼,去找我自己的難看**。

- **pass rate / F1 / triangulation** = 三種打分數的方式 —— 白話:考卷分數。
- 這份文件的主張是:**分數看不見信任。**一個系統可以每題都 pass,而一個真人用三十秒就決定「這東西不能信」。
- 所以我不看分數,我看**具體的人拿具體的輸入撞上來,會撞出什麼**。
- 每一格「現況」我都標了 **已驗**(我真的去讀 code 對過,附檔案:行號)或 **推理**(我從程式結構推出來的,沒有實跑)—— **這兩者的差別我不模糊**。

嚴重度分三級,白話版:

| 等級 | 白話 |
|---|---|
| **breaks_trust** | 系統講的話跟事實不一樣 —— 信任一次歸零 |
| **friction** | 能用,但用起來會卡、會皺眉 |
| **polish** | 細節不夠漂亮 |

### 這份文件怎麼讀?

本份分兩半,各自一張情境表 + 一段「出糗 vs 誠實」的分界分析 + 一張修復帳本:

| 段落 | 一句話功能 |
|---|---|
| [Task 1:Browser Agent](#task-1browser-agent) | 瀏覽器 agent:人用什麼判準信它、它在哪裡會當著人的面出糗 |
| [Task 2:SEC 10-K Extractor](#task-2sec-10-k-extractor) | 財報擷取:誠實內核已經做好了,但誠實**表達**還會失敗 |

**這份文件的性質必須先講死:它是 ledger(帳本),不是型錄。**裡面有「待做」的欄位、有沒修完的洞。我不刪掉它們來讓自己好看 —— 一份只列成就的文件,讀者沒辦法用它來查我。

---

## Task 1:Browser Agent

### 核心洞察:人到底憑什麼信一個 agent?(不是 pass rate)

人類(含評分者)判斷這個系統可不可信,用的是三個量化指標完全看不到的判準:

1. **結論與人眼是否一致**。silent false pass(landmark 太早為真)、明明在播卻 FAIL(媒體任務)、誤殺 REFUSED(裸字 `post`)——每一次背離都是信任歸零事件,而它們在 eval 數字裡分別記成 pass、fail、refused,全部「正常」。
2. **失敗時系統知不知道自己為什麼失敗**。REFUSED + 理由、unknown + trace 是誠實;raw `TimeoutError` 裸奔、新分頁追丟後自述「點了沒效果」是出糗。分界不在結局對錯,在**自述與事實是否一致**。
3. **成果有沒有交到人手上**。`extract_text` 的答案被丟棄、截圖付了成本卻不顯示、下載檔只給 server 本機路徑——90% 工程投資花在 verdict 可信,deliverable(答案/畫面/檔案)卻沒接到人面前,造成「pass rate 完美、使用者價值為零」的結構性盲區。

**白話這三條:**

1. **系統說「過了」,我的眼睛說「沒有」** —— `silent false pass`(silent = 靜默、沒人發現;false pass = 明明沒做到卻判過)。這種錯在分數上長得跟成功一模一樣,這是它最可怕的地方。
2. **失敗不可恥,失敗時搞不清楚自己為什麼失敗才可恥。**`TimeoutError` 裸奔 = 系統把內部的髒話直接噴到使用者臉上。
3. **做到了但沒交出來,對人來說等於沒做。**90% 的工程投資花在「判定可不可信」,結果**答案/畫面/檔案沒有一個真的到人手上** —— 這就是「pass rate 完美、使用者價值為零」。

> **第三條是這份文件最貴的一句:pass rate 是我給自己打的分數,deliverable 才是使用者拿到的東西。兩者可以完全脫鉤。**

### 具體會撞成什麼樣?(情境表)

表中反覆出現的術語,先就地翻:**landmark** = 我拿來判斷「成功了」的路標;**needle** = 要在頁面上找的關鍵字;**preflight** = 動手前先想好「怎樣算成功」;**guard** = 擋下超出責任邊界任務的關卡;**verdict** = 最後判決(pass / fail / unknown 三態)。

| # | 誰 | 典型輸入 | 期待體驗 | 現況 | 落差 | 嚴重度 |
|---|---|---|---|---|---|---|
| 1 | 評分者,第一個 unseen 任務用日常英文 | "Find the latest blog post about AI safety" / 打開 Washington Post / "compare payment methods" | 系統開始搜尋、找到文章;至少不被拒絕 | **已驗**(capability.py:19-20):`post_submit` regex `\b(post\|publish\|submit …)\b` 裸字 `post`/`publish` 即命中;`pay(ment)?` 同理(line 19)→ 立即 REFUSED,理由「task requires a post_submit operation」 | 誤殺的 REFUSED 比 FAIL 更傷:顯得系統連任務在講什麼都沒讀懂。README 引以為傲的 code-enforced boundary 第一發就被打穿 | breaks_trust |
| 2 | 中文使用者/刻意測邊界的評分者 | 「幫我登入 PChome 帳號,把 PS5 加入購物車結帳」 | 與英文相同:立刻 REFUSED + 責任邊界理由 | **已驗**(capability.py:17-33):三個 guard regex 全英文,不含「登入/購買/結帳/密碼/信用卡」;planner prompt 明寫 "Tasks may be in any language"(planner.py:68)→ 中文任務放行,唯一防線剩 prompt 自律(planner.py:67) | 邊界語言不對稱=「不支援」只對英文成立;宣稱(code-enforced)與實作直接矛盾,refuse rate 用英文測完全看不到 | breaks_trust |
| 3 | 一般真人(已發生的真實案例) | 「搜尋 33 號遠征隊的歌曲 並 播放」/ 在 YouTube 播白噪音 | 影片點開、聲音出來;系統結論跟耳朵一致 | **已驗**(guard 無「播放」;preflight 條件空間僅 text_visible/url_contains/download_exists,planner.py:161-165)+ **推理**(具體背離走向):歌名 needle 在搜尋結果頁就可見 → 沒點開也 PASS;或渲染語言不同 → 在播卻 FAIL。純中文任務 derive_success 回 [](nl.py:34-61)→ 誠實 unknown 反而是最好結局 | 體驗式任務的 ground truth 是感官事實(「有沒有在播」),verifier 的觀測空間對它結構性失明;這族在真人輸入裡佔比極高 | breaks_trust |
| 4 | 一般真人 | 「台北明天會不會下雨」/「NVDA 現在股價多少」 | 跑完畫面上直接有答案 | **已修 P2 commit 3431335(answer channel)**:extract_text 成功結果 → `extracted['answer']`,存 `TaskRun.answer`、UI「📋 擷取內容」區塊顯示;verifier 新條件 `answer_matches`(沒抓到答案 → 誠實 fail,不再偽 pass)。offline eval 3/3、silent_failures 0 | (原缺口)「做到了但沒把答案交給我」對人等於沒做到——已由 answer channel 修復 | breaks_trust(已修) |
| 5 | 評分者 | 「查台北到高雄開車要多久」(Google Maps) | PASS 代表路線真的規劃出來;失敗就說失敗 | **已修 P1 commit 8437826(baseline-subtraction)**:verifier 在 t0(agent 動作前)以空 extracted 跑一次 `_check_success`,t0 即成立的條件視為 premature landmark 剔除;全剔除 → open-ended gate 回誠實 **unknown**,絕不 vacuous pass。planner `_task_echo` guard 另擋任務句自帶 token 條件。INTC repro pass→unknown(`tests/test_premature_landmark.py` 9 passed)| (原缺口)LLM 自選條件品質不可控導致 silent false pass——已由 baseline-subtraction 結構性攔截 | breaks_trust(已修) |
| 6 | 評分者 | 貼一個掛掉的 URL / 目標站 30 秒載不進來 | 一句人話:「目標網站載入逾時,已中止」 | **已驗**(test_center.py:496-497):catch-all → status='error'、verifier 欄塞 `TimeoutError: Timeout 30000ms exceeded…` 原始例外;UI 直接渲染(index.html:207-211)。三態設計之外多了未設計的第五態 'error' | 同樣是失敗,誠實=系統知道自己為什麼停;raw exception 裸奔=系統自己也不知道發生什麼事 | friction |
| 7 | 評分者(對照組:系統最強的一族) | 「下載 INTC 最新 10-K 並確認含 Risk Factors」 | 檔案到手、系統證明內容對 | **已驗**:這族設計最完整——_sec_start_url 確定性 EDGAR 起點(test_center.py:353-366)、download 三形態(planner.py:49)、download_exists 讀 bytes 驗 needle(verifier.py:19-41)。但 UI 只顯示 `📁 C:\…\downloads\…` 本機路徑(index.html:210) | 最強能力的最後一哩沒接到人手上:deployed 評分流程中檔案在 server 上,評分者拿不到 | friction |
| 8 | 評分者,連續丟多個任務 | 連續提交 3 個不同網站的任務 | 知道自己在排隊、排第幾 | **已驗**(test_center.py:305, 572):單一 Playwright worker thread + queue;第二個任務 status 停在 'queued',API 無 queue_position;worker 若死亡,任務永遠 queued | 無回饋的等待與死掉無法區分;評分者 30 秒內判定「壞了」 | friction |
| 9 | 評分者,沒跑過 codex login 就啟動 | 任何真實網站任務 | 系統擋住:「demo 模式,真實任務需先 codex login」 | **已驗**(test_center.py:397-403):backend 非 codex 時只在 _AGENT_INFO 放警告字串,submit 不被阻擋;mock 的 canned 動作在真網站=亂點 | 警告存在但不阻斷=誠實了但沒保護;環境問題被記成能力問題 | friction |
| 10 | 評分者/真人 | 「在 Hacker News 找今天排名 40 的貼文」/ 捲到頁尾找信箱 | agent 像人一樣往下捲 | **已修 P3 commit 1c8f103(scroll playbook)**:planner PLAYBOOK 加「OFF-SCREEN TARGETS」條——`keyboard keys="PageDown"/"End"` 捲動後下一輪重讀,首屏沒找到是捲動理由不是 give_up 理由(keyboard 本就過 capability guard)| (原缺口)缺 scroll 讓 agent 只會處理首屏——已由 PLAYBOOK 規則修復 | friction(已修) |
| 11 | 評分者/真人 | 新聞入口點外部報導(target=_blank 開新分頁) | agent 跟著到新分頁繼續 | **已修 P3 commit 1c8f103(new-tab follow)**:executor 在 click/mouse 後偵測 `context.pages` 成長(含 200ms recheck 吸收 popup 非同步)→ wait domcontentloaded → 切到最新頁,agent 同步 `observer.page` 並記「↪ 跟隨新分頁」。tests/test_auto_vision_and_tabs.py | (原缺口)失敗原因(內容在別分頁)與自述背離——已由跟隨邏輯修復 | friction(已修) |
| 12 | 一般真人 | 「把『今天天氣很好』翻成日文」/「100 美元是多少台幣」 | 得到譯文/數字 | **推理**(依 #4 已驗的 answer channel 缺失延伸):譯文無法預知 → preflight 只能亂猜 needle 或給 landmark → unknown 或偽陽性;即使 extract_text 抓到譯文也不回傳 | 「開放式 + deliverable 是文字」的交集:unknown 是最好結局但人拿不到東西 | friction |
| 13 | 一般真人,看步驟串流 | 任何任務,盯著步驟 feed | 每一步都是人話;失敗時第一句就能懂 | **已驗**:底子很好(🧠/💭/🧹/⬇️ 全中文人話,agent.py:437-509)。外洩三處:noop 顯示英文內部句(planner.py:264);verifier reason 是條件語法 `violated: text_visible:…`(verdict.py:44);unknown 的 confidence 0.40 是寫死常數(agent.py:523),兩位小數是偽精度 | 呈現層 95 分,但失敗時刻(人最需要解釋時)恰好是外洩最集中的地方 | polish |
| 14 | 真人+評分者 | 「找最熱門的財經 podcast」(無可驗證條件的開放式任務) | 跑完給我看最後畫面,我一秒自己判斷 | **已驗**:每步截圖都存在(agent.py:507 → runs/test_center/shots/),但 UI 完全無 img 元素(grep index.html 無 `<img`);開放式任務誠實走 unknown(test_center.py:466-474 明確設計),但 unknown+conf 0.40+純文字 trace 讀起來像「壞掉」 | 人類對開放式任務的驗證器是眼睛;系統付了截圖成本卻鎖在磁碟裡。unknown 的正確體驗是「邀請人裁決」,現在是「機器聳肩」 | friction |

**表裡最刺眼的三個,我挑出來白話講:**

- **#1 —— 我的 guard 把「找一篇 AI safety 的 blog post」當成「發文」拒絕了。**因為 regex(文字比對規則)裡有裸字 `post`。這比失敗更傷:失敗只是做不到,**誤殺是連題目在說什麼都沒讀懂**。而 README 正在誇口的 code-enforced boundary(用程式碼強制的責任邊界)—— 第一發就被自己打穿。
- **#2 —— 我的邊界只擋英文。**三個 guard regex 全英文,中文的「登入/購買/結帳」一路放行,唯一防線剩下 prompt 自律(拜託 LLM 自己乖一點)。這一條是**宣稱與實作直接矛盾**:我說「code-enforced」,實際上中文路徑是 prompt-enforced。更陰險的是:**用英文測 refuse rate,這個洞完全看不到。**
- **#3 —— 我對「有沒有在播」這件事結構性失明。**preflight 的條件空間只有 text_visible / url_contains / download_exists 三種,沒有一種看得見「聲音出來了沒」。歌名在搜尋結果頁就看得到 → 沒點開也 PASS。這族在真人輸入裡佔比極高。

### 「出糗 vs 誠實」分界分析:同樣沒完成,為什麼有的加分、有的歸零?

同樣是「任務沒完成」,人類把結局分成兩類,分界線是**系統的自述與事實是否一致**:

| | 誠實(信任加分) | 出糗(信任歸零) |
|---|---|---|
| 拒絕 | 「這需要登入,超出責任邊界」——理由與人眼一致 | 把「讀一篇 blog post」當「發文」拒絕(#1)——理由與任務無關 |
| 失敗 | 「CAPTCHA 擋住,已嘗試直接 goto 繞過,無路可走」 | `TimeoutError: Timeout 30000ms exceeded`(#6)——內部例外裸奔 |
| 不確定 | 「無可驗證條件,已執行完,請看最終畫面確認」 | unknown + conf 0.40 + 沒有畫面(#14)——聳肩且不給證據 |
| 成功 | PASS + 依據 + 截圖,人可自行核驗語義窄度 | PASS conf 1.00 但路線根本沒規劃(#5)——與人眼直接矛盾 |

本系統的架構(三態 verdict、capability guard、evidence chain)是為左欄設計的,但四個實作縫隙(#1 誤殺、#2 中文穿透、#5 條件品質、#6 error 裸奔)會讓它在評分者面前掉到右欄。**修的不是能力,是自述與事實的一致性。**

**白話這張表:**左右兩欄的**結局完全一樣**(都是沒完成),差別只在系統有沒有搞懂自己在幹嘛。左欄的系統像一個誠實的員工:「我卡住了,原因是 X,我試過 Y。」右欄的系統像一個慌張的員工:噴一句 `TimeoutError: Timeout 30000ms exceeded` 就跑了。

而最痛的自我攻擊是:**我的架構是為左欄設計的,但四個實作縫隙會讓它掉進右欄。**架構對、實作漏 —— 這比架構就錯更難發現,因為文件上看起來一切正常。

> **不是能力不夠,是嘴巴跟事實對不上 —— 修的不是能力,是自述與事實的一致性。**

### Historical cheap-fix ledger:那些洞後來怎麼了?(依信任槓桿排序)

> 狀態是本文件建立時的歷史快照;已落地的最終修復與重測數字請以 `eval_report.md` / `failure_gallery.md` 為準。

| # | 修什麼 | 作法 | 工時 | 狀態 |
|---|---|---|---|---|
| F1 | guard 誤殺(#1) | `post/publish` 改需接受詞的 pattern(`(post\|publish)\s+(a\|an\|the\|my\|this)?\s*(comment\|review\|reply\|…)`);pay/buy 同法收窄;加 3 個誤殺回歸測試(blog post / Washington Post / payment methods) | 半天 | 待做 |
| F2 | 中文穿透(#2) | 三個 regex 各加中文詞:intent 加 `登入\|購買\|下單\|結帳\|付款\|驗證碼`,value 加 `密碼\|信用卡\|安全碼`,target 加 `結帳\|立即購買\|付款`;加中文 refused 測試 | 一小時 | 待做 |
| F3 | 媒體任務失明(#3) | 加 `media_playing` 成功條件:page.evaluate 查 `document.querySelector('video,audio')?.paused === false && currentTime > 0`;preflight prompt 教播放類任務用它 | 一天 | 處理中(verifier 弱點範圍,與平行 workflow 同步) |
| F4 | 答案通道(#4, #12) | extract_text 輸出寫進 extracted dict 並存 `rec['answer']`,UI 在 verdict 旁顯示「擷取內容」 | 一天 | 完成(P2 commit 3431335:answer channel + verifier `answer_matches`;`tools/answer_channel_eval.py` 3/3、silent 0) |
| F5 | premature landmark(#5) | 根治難;先攤牌:UI 把 PASS 渲染成「通過,依據:頁面出現『高雄』」+ 最終截圖;preflight prompt 加規則「條件不得是任務句中已含的實體名單獨出現」 | 一天 | 完成(P1 commit 8437826:verifier baseline-subtraction 剔除 t0 即成立的 landmark → 誠實 unknown;planner `_task_echo` guard;`tests/test_premature_landmark.py` 9 passed) |
| F6 | 最終截圖進 UI(#14) | test_center 加 /shots/ 靜態 route,rec 記最後截圖檔名,verdict 區顯示縮圖;unknown 文案改「已執行完畢,無法機器驗證——請由最終畫面確認」 | 一天 | 待做 |
| F7 | error 人話映射(#6) | worker except 分支加映射:TimeoutError→「網站載入逾時」等;原始字串收進折疊區 | 半天 | 待做 |
| F8 | 下載檔最後一哩(#7) | 加 `/api/agent/download` route(照抄 /api/sec/raw pattern,test_center.py:543-548),📁 改下載連結 | 兩小時 | 待做 |
| F9 | queue 回饋(#8) | status API 帶 queue_position,UI 顯示「前面還有 N 個任務」 | 兩小時 | 待做 |
| F10 | mock 模式攔截(#9) | backend 非 codex 時 submit 需二次確認 | 兩小時 | 待做 |
| F11 | 捲動(#10) | 純 prompt 改動:PLAYBOOK 加「目標可能在視窗外時,keyboard keys="PageDown"/"End" 捲動後重看」 | 一小時 | 完成(P3:planner.py PLAYBOOK「OFF-SCREEN TARGETS」) |
| F12 | 新分頁跟隨(#11) | executor click 後檢查 page.context.pages,有新頁則切換並記一步「↪ 跟隨新分頁」 | 半天 | 完成(P3:executor `_follow_new_page` + agent 同步 observer,tests/test_auto_vision_and_tabs.py) |
| F13 | 呈現層外洩(#13) | UI 翻譯 `text_visible:X`→「頁面需出現『X』」;noop 訊息改中文;unknown 不顯示 confidence 數字 | 半天 | 待做 |

**這張帳本我不美化:十三條裡,有完成的、有處理中的、也有一整排「待做」。**F1、F2 這兩個 breaks_trust 等級的洞,狀態就是**待做** —— 我不會因為它們難看就把它們從表裡刪掉。

已經補上的三發,值得講的是它們**修法的形狀**:

- **F5(premature landmark)白話:**問題是 landmark(路標)太早就成立 —— 我要去高雄,結果「高雄」兩個字在出發前就印在螢幕上了,系統看到就喊到站。**解法是 baseline-subtraction:動手前先拍一張,凡是「還沒動手就已經成立」的條件,一律作廢。**全部作廢就誠實回 unknown,絕不 vacuous pass(空洞通過)。INTC 那個 repro 從 pass 變成 unknown —— **注意,這是分數變差、正確性變好。**
- **F4(answer channel)白話:**答案抓到了卻沒交給人。修完之後多了一條規矩:**沒抓到答案就誠實 fail,不再偽 pass。**offline eval 3/3、silent_failures 0。

> **F5 修完之後,一個原本 pass 的案例變成 unknown。這不是退步 —— 是我把一個假的成功換成一句誠實的「我不知道」。**

---

## Task 2:SEC 10-K Extractor

### 核心洞察:人拿什麼決定信不信?用「錯誤的形狀」

人類不是靠 F1/triangulation 決定信任,而是靠兩件事:(1) **抽查一兩個自己熟的 item**,看邊界對不對;(2) **丟一個刁鑽輸入**(20-F、pre-2001、wrapper 10-K),看系統「知不知道自己不知道」。本系統的誠實內核(三態 status、XBRL/topic oracle、gap 保底)正中這兩點,但表達層仍是機器語彙——`filing_class=non_10k`、`conf 0.67`、`incorporated_by_reference`——人類要自己翻譯成「哪裡可信、哪裡要人工看、內容實際在哪」。

量化數字沒捕捉到的是**錯誤的形狀**:同樣拿不到內容,「誠實拒絕+說明原因+指出內容位置」與「靜默給錯」在 F1 上可能同分,對人類卻是 A 級與 C 級的分水嶺。且各族使用者的一票否決各不同:**律師**要可獨立重驗的 offset 配方、**量化**要無共享狀態的批次確定性 API、**基本面分析師**要 stub 一鍵跳到正文(誠實但沒用=沒用)、**評分者**要系統對不支援輸入的第一句話。修這些多半不是改 pipeline,是把已存在的證據(warnings、gap offsets、filing_class、accession)翻譯成人話並接上連結——便宜、且直接命中信任。

**白話拆解。**一個真人拿到這套系統,他不會去讀我的 F1,他只做兩件事:

1. **抽查一個他自己熟的 item**,看邊界剪得對不對 —— 白話:他拿他知道答案的題目來考我。
2. **丟一個刁鑽的輸入**(20-F、pre-2001 老檔案、wrapper 10-K),看我**知不知道自己不知道**。

第二點才是分水嶺。這段話裡最重要的一句是:

> 同樣拿不到內容,「誠實拒絕+說明原因+指出內容位置」與「靜默給錯」在 **F1 上可能同分**,對人類卻是 **A 級與 C 級**的分水嶺。

**白話:分數是色盲的,人不是。**F1 只數對錯,不管你錯得多難看。我把這個叫**錯誤的形狀** —— 同樣拿不到內容、同樣在 F1 上同分,「我不知道,但內容在未分類區段」和「(自信地給你一段錯的)」是兩個世界。

還有一句我必須加粗:**誠實但沒用 = 沒用。**告訴使用者「內容不在這裡」而不告訴他「在哪裡」,他一樣拿不到東西。

### 具體會撞成什麼樣?(情境表)

術語先翻:**offset** = 第幾字到第幾字;**sha256** = 內容指紋;**accession** = SEC 給每份申報文件的唯一編號;**filing_class** = 這份文件被歸成哪一類;**gap** = 沒被歸進任何 item 的剩餘文字(保底不丟);**stub** = 只寫「詳見附件」的殘段;**IBR(incorporated_by_reference)** = 以引用方式併入 —— 白話:「這段正文我不寫在這,你去看另一份」。

| # | 誰 | 典型輸入 | 期待體驗 | 現況 | 落差 | 嚴重度 |
|---|---|---|---|---|---|---|
| 1 | 評分者(held-out) | ticker「TSM」(foreign private issuer) | 「TSM 申報 20-F 非 10-K;20-F item 結構不同(Item 3.D 才是 Risk Factors),誠實不支援」 | **已驗**(resolver.py:91 只收 10-K/10-K/A;test_center.py:154 error 只有「找不到 10-K」) | 拒絕的「原因」沒說出口:submissions JSON 裡明明有實際 form 清單(20-F/6-K),卻只說查無——把 A 級誠實邊界演成 C 級查無資料 | breaks_trust |
| 2 | 多位評分者同時測 deployed test-center | A 抽 AAPL、B 同時抽 JPM,A 接著點 Item 1A | A 看到 AAPL 的內容,或明確錯誤「狀態已被覆蓋,請重抽」 | **已驗**(test_center.py:51 單一全域 `_SEC_STATE`;sec_item_text 只查當前 state,無 accession 比對)→ B 覆蓋後 A 拿到 JPM 的文字,UI 標頭仍是 A 記憶中的 AAPL 語境 | source-exact 是賣點,共享全域狀態卻能讓人拿到「別家公司的 source-exact 文字」——最誠實的 pipeline 配上會說謊的 serving 層 | breaks_trust |
| 3 | 盡調律師/審計 | 抽 AAPL → 記下 offset+sha256 → 下載原始 10-K 想自己驗 | 一條可執行配方:拿下載檔跑一行指令重現 sha256 | **已驗**(boundary.py:302 sha256 對 normalized text 計算;/api/sec/raw 回原始 HTML bytes,test_center.py:157-175, 544)→ 律師拿 raw HTML 對 offset 切出 tag soup,sha 對不上 | 給了證據(sha256)也給了原料(raw),卻沒給從原料到證據的函數;律師會合理懷疑「normalize 動了幾個字?」——最核心賣點在最需要它的使用者手上斷鏈 | breaks_trust |
| 4 | 量化分析師(NLP 前處理) | 想要:tickers.txt + 年份範圍 → 每 filing 一份 JSON,可斷點續跑 | README/frontend 明示批次路徑:CLI 或 API、schema 固定、cache-first | **已驗**(eval_one.py 可產 per-filing JSON;EdgarFetcher 有 cache_dir;`_SEC_LOCK` 使 HTTP API 序列化)+ **推理**(README 定位):能力存在但被定位成 eval 工具,沒當產品批次入口文件化 | 從量化視角看到的只有單發互動 UI → 判定「這是 demo 不是工具」離開;評分者寫 script 測 20 家也撞序列化瓶頸 | friction |
| 5 | 基本面分析師 | 抽 NVDA FY2025 → 看 Item 1A → 想對照 FY2024 | 一鍵「與上一年度比對」:字數差、新增/刪除段落 | **已驗**(sec_filings 年份 picker 存在,test_center.py:124-138;無任何 diff 功能,切年份整份重抽覆蓋畫面) | 系統手上有 YoY diff 全部原料(boundary、sha256、offset、年份清單),insights_and_directions.md §6 自己點名這是真實應用,UI 一步沒接 | friction |
| 6 | 基本面分析師(wrapper 10-K) | 抽 JPM → 點 Item 7(MD&A) | 就算正文不在標準章節也要能一鍵到達——「誠實告訴我在哪」的下一句必須是「帶我去」 | **已驗**(classify_reference_stub / detect_appended_section_cut 存在於 sec_core;gap:a-b 未分類列有完整檢視,test_center.py:210-221)+ **推理**(JPM 具體型態):stub 檢視與 gap 列之間無任何連結,使用者不知兩者是同一件事 | 「誠實但沒用」的具體形狀:MD&A 文字其實已端上桌,卻放在標「未分類內容」的別桌;比 Intel page-anchor 容易卻沒做 | friction |
| 7 | 評分者(held-out) | 年份 picker 選 KO 1997(pre-2001 SGML) | 第一眼一句人話:「這是 1997 年的格式;6 個 item 抽到、9 個是誠實指標、8 個是該年代不存在的 item code」 | **已驗(2026-07-16 重測)**:格式已支援(text-mode normalize,`NORMALIZATION_VERSION` 1.1)—— KO FY1997 實際回 **6 pass / 9 IBR / 8 missing**、cov 0.2126、`filing_class=standard`,8 個 missing 全部 needs_review。**此列舊版寫的「22 列灰色 missing + coverage 0% + `filing_class=non_10k`」已不成立**(root cause 是 normalize bug,見 FG-SEC-009)+ **推理**(UI 第一印象仍未改) | 落差**縮小但沒消失,而且換了形狀**:現在的第一眼是 `cov 0.2126` —— 一個看起來很難看、實際上是「9 個 item 真的是 IBR stub」的數字。**低 coverage 與漏抽在 UI 上長得一模一樣**,而這次系統其實有話可說(era 不存在的 code、IBR 指標),只是沒說出口 | friction |
| 8 | 所有人(評分者第一眼尤甚) | 抽 CAT → 面對 22 列 status/conf/xbrl/topic 表格 | 表格上方一句總覽:「17 pass(Item 8 XBRL 認證)· 4 建議人工複核:Item 1C(…)、Item 3(…)」 | **已驗**(每列有 confidence 小數、needs_review、warnings 計數;無聚合總覽)——證據齊全但全是原子化欄位 | confidence 0.67 vs 0.96 的鑑別度是給機器校準用的,人類對 0.67 沒有行動含義;信任從總覽建立,不是從 22 個小數 | friction |
| 9 | 評分者(用自己選的 filing) | 貼 EDGAR Archives URL 到查詢框 | 系統認得 URL,解析 CIK+accession 直接抽 | **已驗**(test_center.py:147:`int(q) if q.isdigit() else cik_for_ticker(q)`)→ URL 進 cik_for_ticker 然後 LookupError | 題目明文 "we can submit or select filings"——select 有了,submit 的最低成本形式(貼 URL)不通;評分者第一步碰壁影響後面所有印象 | friction |
| 10 | 學術研究者 | 抽 MSFT 2013 → 需要引用格式與重現指令 | 一鍵複製 citation:ticker、accession、item、offsets、sha256、**pipeline 版本** | **已驗**(meta dict 無任何版本欄位,test_center.py:168-170;sweep2→sweep3 span 已實際漂移:pass 177→178) | 可重現性 90% 都做到了,版本戳記缺席——那正是學術引用的必要欄位,決定研究者敢不敢寫進 methodology | polish |
| 11 | 評分者/法遵(測 10-K/A) | 輸入剛發過 10-K/A 的 ticker,在 picker 找那份 amendment | picker 列出但標「10-K/A 未支援(僅含修訂部分)」 | **已驗**(test_center.py:137, 148:`not f.is_amendment` 靜默過濾,picker 完全不見;supported_and_unsupported.md 有誠實列出) | docs 層誠實、UI 層靜默——與整個專案「誠實邊界要 surface 到眼前」的主張自相矛盾;評分者第一假設是 bug 不是設計 | polish |
| 12 | 分析師/律師(讀 Item 8) | 抽 WMT → 點 Item 8 → 想核對 balance sheet | 表格至少可讀,分得出哪個數字屬於哪年哪列 | **已驗**(sec_viewer.py:242 誠實聲明「表格數字已保留(cell 以空白分隔)」)——數字都在(XBRL 也證明),但三欄年度糊成一行 | 對 NLP 下游無妨,對人類核對是障礙;誠實聲明做到了,可用性沒跟上 | polish |

**三個我要親自認的:**

- **#2 —— 我的 serving 層會說謊。**pipeline 每個字都是 source-exact(逐字取自原文),但 UI 背後只有一個全域 `_SEC_STATE`。A 抽 AAPL、B 同時抽 JPM,**A 會拿到 JPM 的文字,標頭卻還寫著 AAPL**。這是全文最諷刺的一條:**source-exact 是我的賣點,而共享全域狀態讓人拿到「別家公司的 source-exact 文字」。**單元件全對,組合說謊。
- **#3 —— 我最核心的賣點,在最需要它的人手上斷鏈。**我給了律師 sha256(證據),也給了 raw HTML(原料),**就是沒給從原料算到證據的那個函數**。因為 sha256 是對 normalized text 算的,律師拿 raw HTML 照 offset 剪,剪出來是 tag soup(一堆標籤爛泥),對不上。他會合理懷疑:「你的 normalize 到底動了幾個字?」—— 我沒有給他答案的辦法。
- **#10 —— 版本戳記缺席,而且我有證據證明它會咬人。**meta dict 裡沒有任何版本欄位,而 **sweep2→sweep3 的 span 已經實際漂移過:pass 177→178**。白話:同一個 ticker、同一份 filing,不同版本的 pipeline 剪出來的東西不一樣。**這不是假想風險,是已經發生過的事實。**

### 「出糗 vs 誠實」分界分析:Task 2 的風險不是說謊,那是什麼?

Task 2 的誠實內核比 Task 1 完整(三態 status、oracle、gap 保底都已是程式行為),它的風險不在「說謊」,在**誠實的表達失敗**——四種形狀:

1. **誠實但無理由**(#1 TSM):正確拒絕了,但沒說「為什麼」,人無法區分「正確拒絕」與「resolver 壞了」。誠實的價值=理由的可見度。
2. **誠實的 pipeline + 會說謊的 serving**(#2 全域狀態):pipeline 每個字都 source-exact,但併發下 serving 層把 A 公司的標頭配上 B 公司的內文——單元件全對,組合說謊。
3. **誠實但斷鏈**(#3 offset 配方):給了 sha256 也給了 raw,卻沒給連接兩者的函數;可稽核性宣稱在最專業的使用者手上驗不動。
4. **誠實但沒用**(#6 IBR stub、#7 pre-2001):「內容不在這裡」說了,「內容在哪、帶你去」沒接。**#7 在 2026-07-16 換了形狀但沒離開這一類**:pre-2001 現在抽得到了,可是第一眼變成 `cov 0.2126` —— 系統手上明明有話可說(9 個是 IBR 指標、8 個是該年代不存在的 code),UI 上還是一個難看的數字加一堆灰格。**誠實從 status 欄位搬到了更多 status 欄位,還是沒搬到人眼前。**

共同解法不是改 pipeline,是**把已存在的證據翻譯成人話並接上連結**——這也是為什麼下面多數 fix 以小時計。

**白話這四種形狀:**我做對了一件難事(誠實內核),然後在一件簡單事上摔了(把誠實講出來)。

| 形狀 | 白話一句 |
|---|---|
| 誠實但無理由 | 我拒絕了你,但我不說為什麼 —— 你分不出我是嚴謹還是壞掉 |
| 誠實 pipeline + 說謊 serving | 每個零件都對,組起來對人說謊 |
| 誠實但斷鏈 | 我給你證據,也給你原料,就是沒給你算式 |
| 誠實但沒用 | 我說「東西不在這」,然後就沒有然後了 |

**第一種形狀最值錢的一句是:誠實的價值 = 理由的可見度。**一個沒說出口的正確拒絕,在使用者眼裡跟 bug 長得一模一樣。

> **不是我的系統不誠實,是我的誠實沒有被翻成人話 —— 而沒被聽懂的誠實,在使用者那裡的效果等於不誠實。**

### Cheap fixes:這些洞怎麼補?(依信任槓桿排序)

| # | 修什麼 | 作法 | 工時 | 狀態 |
|---|---|---|---|---|
| S1 | 拒絕要有理由(#1) | annual_filings 空時,從已抓到的 submissions JSON 統計 form 分布,error 改「該公司申報 20-F/6-K(foreign private issuer),10-K item 結構不適用,誠實不支援」 | 半天 | 待做 |
| S2 | 併發串台(#2) | _items_payload 每列帶 accession;/api/sec/item 要求 accession 參數,與 `_SEC_STATE['meta']` 比對,不符回「filing 已被另一次抽取取代,請重抽」——約 20 行 | 半天 | 待做 |
| S3 | offset 驗證配方(#3) | 加 /api/sec/normalized 下載 `result.doc.text`;item 標頭附一行可執行配方(python one-liner 重現 sha256) | 一天 | 待做 |
| S4 | EDGAR URL 入口(#9) | sec_extract 開頭加 regex 匹配 `sec.gov/Archives/edgar/data/(\d+)/(accession)`,抽出 CIK+accession——約 10 行 | 兩小時 | 待做 |
| S5 | review_summary 總覽(#8) | server 端聚合 needs_review item + warnings[0] 人話化成字串陣列,前端一個 div | 半天 | 待做 |
| S6 | IBR stub → gap 連結(#6) | stub 檢視加一行「→ 本文件內對應區段:未分類內容 gap:a-b(N 字)」可點跳轉——切點 offset 已知,純 UI 接線 | 半天 | 待做 |
| S7 | 不支援格式的敘事 banner(#7) | renderSec 加 filing_class→人話映射 dict(non_10k+coverage 0→「格式不支援,已誠實退出,0 item 捏造;原文完整保留於未分類區段」) | 兩小時 | 待做 |
| S8 | 批次路徑文件化(#4) | README 加「批次使用」節:eval_one.py CLI 用法+輸出 schema+for-loop 範例;extract 回應補 `?include_text=1` | 半天 | 待做 |
| S9 | YoY diff(#5) | item 檢視加「對照上一年度」:抽前一 accession 同 item(cache-first),difflib 算新增/刪除段落數+前 5 段新增文字 | 一天 | 待做 |
| S10 | amendment 現身(#11) | sec_filings 不過濾 amendment,payload 加 is_amendment;picker 顯示 disabled +「10-K/A 未支援」 | 兩小時 | 待做 |
| S11 | pipeline_rev(#10) | meta 加 pipeline_rev(啟動時 `git rev-parse --short HEAD` 一次);item 檢視加「複製引用」按鈕 | 兩小時 | 待做 |
| S12 | 表格核對導引(#12) | item 檢視加提示「核對表格請下載原始 10-K 於瀏覽器開啟,Ctrl+F 本段前 20 字定位」——raw 下載鈕已存在,只缺這句 | 一小時 | 待做 |

**這張表的狀態欄,十二條全是「待做」。**我不粉飾:Task 2 的這批 cheap fix,一條都還沒落地。

值得注意的是**工時欄**:S2 約 20 行、S4 約 10 行、S12 只缺一句話 —— **這些洞不貴,它們只是還沒被修**。這正好呼應上面那句「共同解法不是改 pipeline,是把已存在的證據翻譯成人話並接上連結」。

> **這批洞便宜到用小時計 —— 但便宜不等於已修。我把它們列出來,是讓你能拿這張表回頭查我,不是讓你以為它們不存在。**
