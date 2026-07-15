# Attribution & License Stance

> 站在巨人的肩膀上——但守住授權界線。研究(`docs/prior_art.md`)調查後的明確立場:
> **copyleft(GPL/AGPL)專案只借「想法」,不抄「程式碼」;permissive(MIT/Apache)專案才可 vendor / 改寫程式碼並保留出處。** 抄 GPL/AGPL 程式碼會讓整個 repo 被 copyleft 傳染,這對交付作品是不可接受的風險。

**翻成一般人能懂的版本:** 開源軟體的授權大致分兩種脾氣。**permissive(寬鬆型,如 MIT/Apache)**像是「隨你用,記得寫我名字」;**copyleft(傳染型,如 GPL/AGPL)**像是「你用我的碼,你的碼也得跟著開源」。所以我對這兩種的處理方式不對稱:寬鬆型我可以直接把程式碼搬進來(vendor)再改;傳染型我**只讀觀念、不碰程式碼**——因為一旦碰了,傳染會蔓延到整個 repo,整份交付品的授權就毀了。

一句話總結我的立場:**不是「開源的都能拿」,是「拿什麼、怎麼拿,由對方的授權說了算」。**

本頁分六段:

1. **我借了什麼觀念?** —— clean-room 重寫的兩個來源。
2. **投票的引擎從哪來?** —— 第四/第五仲裁票,以及 GPL 怎麼把我逼去用 subprocess。
3. **我刻意沒做什麼?** —— 授權風險規避的負面清單。
4. **外部評測資料從哪來?** —— 資料集授權與「只 commit 子集」的紀律。
5. **外部評審怎麼借?** —— WebJudge 的逐字沿用與四項偏離揭露。
6. **哪些還能安全深化、哪些是我自己的?** —— roadmap 與差異化。

## 我借了什麼觀念?(clean-room 重寫,非複製貼上)

白話:**clean-room(無塵室)重寫**的意思是——我讀懂它的**想法**,然後把原始碼關掉,自己重寫一遍。想法不受著作權保護,程式碼才受。

| 來源 | 授權 | 我們借了什麼 | 落地位置 |
|---|---|---|---|
| [EmergenceAI/Agent-E](https://github.com/EmergenceAI/Agent-E) | **MIT** | `mmid` DOM-distillation 概念:observe 時對每個互動元素蓋一個穩定 id,repair 後用該 id 精準定位「剛剛看到的那個元素」,而非重建可能不唯一的 CSS selector | `packages/browser_agent/observer.py`:observe 時蓋 `data-aid`;`repair.py`:action 用 `[data-aid=N]`(精準),memory 存 durable semantic selector(可跨 reload) |
| [nlpaueb/edgar-crawler](https://github.com/nlpaueb/edgar-crawler) | **GPLv3 → 僅借想法** | 「item boundary = 到下一個有效 item heading」與 TOC false-positive 需過濾短假 heading 的**觀念**。我們的多 detector + 加權 TOC filter 是**獨立重寫**,未參考其原始碼 | `sec_core/{headings,toc,boundary}.py`(clean-room) |

翻成人話,這兩件事各是什麼:

- **Agent-E 的 `mmid` / DOM-distillation**(DOM 蒸餾):`DOM` 是網頁的骨架結構。做法像是**逛超市時先在每個看中的商品上貼一張自己的標籤**——等一下要回頭拿,直接找標籤,而不是憑「第三排左邊那個」這種描述重新找一次(描述可能撞號、可能失效)。它是 **MIT**,所以我本來可以直接抄碼,但我採用的是概念落地成自己的 `data-aid`。
- **edgar-crawler 的 item boundary 觀念**:`item boundary` 是「這一章從哪裡開始、到哪裡結束」;`TOC` 是目錄頁;`TOC false-positive`(目錄誤判)指的是——目錄頁上也印著章節的標題,程式很容易把**目錄裡那一行標題**誤認成**正文的開頭**。它是 **GPLv3**(傳染型),所以我只拿這個觀念,**沒讀它的原始碼**,自己重寫。

> **不是「我沒抄」這麼便宜,是「MIT 那份我大可抄卻仍重寫,GPLv3 那份我連看都不看原始碼」。**

## 投票的引擎從哪來?(第四/第五仲裁票;P0-7;engines 只投票,不產文)

白話:**仲裁票**的意思是——遇到「這一章的正文到底到哪為止」有爭議時,我不自己說了算,而是找幾個獨立實作的程式各投一票。關鍵紀律寫在標題裡:**engines 只投票,不產文**——外部引擎的輸出**不會變成我交付的內容**,只用來表態同不同意。

| 來源 | 授權 | 使用方式 | 落地位置 |
|---|---|---|---|
| [nlpaueb/edgar-crawler](https://github.com/nlpaueb/edgar-crawler) | **GPLv3**(P0-7a 前置:2026-07-10 於 `--depth 1` clone 實讀 LICENSE **再驗證**,commit `84a8d0c5dd7dd6769526e5ccec534c4e0880d56f`)→ **不 vendor、不 import、不 link** | **arms-length subprocess**:未修改的上游 CLI(`extract_items.py`)在本地 checkout(gitignored `data/raw_filings/external/edgar_crawler/`,pin 同上 commit)以獨立 process 執行,僅以檔案溝通——GPLv3 下的 mere aggregation,非衍生作品;checkout 不隨 repo 散布。其 README 要求學術引用 Loukas et al. 2021(EDGAR-CORPUS)。**Lineage 註記**:EDGAR-CORPUS 即此程式所建,edgar-crawler 票與 corpus teacher 票同血統,永不各算一票 | `sec_core/engines/edgar_crawler_vote.py` + `tools/triangulate.py`;subprocess 所需 permissive 依賴列於 pyproject `crawler-vote` extra |
| [john-friedman/datamule-python](https://github.com/john-friedman/datamule-python) | **MIT**(pip `datamule==5.0.1`;2026-07 調研 pin 上游 commit `122fc54` 2026-06-25,解析後端 = doc2dict 樣式驅動) | 第五票:`sec_core/engines/datamule_vote.py` 以 `Document.parse()` + `get_section(title_class="item")` 抽 item。**無公開 accuracy benchmark——當票不當 gold**;與我方 regex 驅動、edgartools、edgar-crawler 皆實作獨立 | `sec_core/engines/datamule_vote.py`;pyproject `sec` extra |
| [sec-api.io](https://sec-api.io) Extractor API | 商業 ToS:**cached responses 僅供內部 eval,不可再散布原文 payload**;free tier = **100 lifetime calls** | 外部仲裁票(P0-7b):`tools/arbitrate_secapi.py` cache-first(回應落盤才使用)、`--max-calls` 顯式預算、無 `SECAPI_KEY` 時僅產 ready-to-run 狀態文件(**絕不代辦註冊**);artifacts 只存 verdict/字數,payload 進 gitignored `data/sec_eval/arbitration/cache/` | `tools/arbitrate_secapi.py` + `data/sec_eval/arbitration/` |

### 這三票各自的「為什麼」是什麼?

**第一票:edgar-crawler——GPL 把我逼到 subprocess。**

問題是:我想要 edgar-crawler 這一票,但它是 GPLv3。把它 `import` 進來,我整個 repo 就被傳染。

答案是 **arms-length subprocess(一臂之遙的子行程)**。白話:我**不把它請進屋裡**,而是讓它在門外當一個完全獨立的程式跑,兩邊只靠**丟檔案**溝通——不 vendor(不搬碼)、不 import(不引入)、不 link(不連結)。GPLv3 對這種形態的稱呼是 **mere aggregation(單純聚合)**,不算衍生作品。而且那份 checkout 是 gitignored 的,**不隨 repo 散布**。

自我攻擊:「你會不會只是查了網路上寫 GPLv3 就算數?」——所以有 P0-7a 前置:2026-07-10 於 `--depth 1` clone **實讀 LICENSE 再驗證**,並 pin 死 commit `84a8d0c5dd7dd6769526e5ccec534c4e0880d56f`。**授權判定不靠印象,靠實讀檔案。**

再自我攻擊一次,這次攻擊的是**票數的誠實性**:「你有五票,是不是就等於五個獨立意見?」不是。**Lineage 註記**講死了——EDGAR-CORPUS 即此程式所建,edgar-crawler 票與 corpus teacher 票**同血統,永不各算一票**。白話:這兩票是**同一個爸爸生的**,讓它們各投一票等於同一個人投兩次,票數會虛胖。我寧可少一票,也不要一個假的多數。另外它的 README 要求學術引用 Loukas et al. 2021(EDGAR-CORPUS),照引。

**第二票:datamule——MIT,但我主動貼上「不是 gold」的標籤。**

它是 **MIT**,授權上我想怎麼用都行。但授權寬鬆不等於**準確**。**無公開 accuracy benchmark(沒有公開的準確度基準)——當票不當 gold**。白話:**沒人量過它多準,那它就沒資格當標準答案,只能當一張票。** 它的價值在於**實作獨立**:與我方 regex 驅動、edgartools、edgar-crawler 皆實作獨立——投票要有意義,投票者就得是各自想出來的,不能互相抄。

**第三票:sec-api.io——商業 ToS 下的三道自我約束。**

它是商業服務,規矩最緊:**cached responses 僅供內部 eval,不可再散布原文 payload**;free tier = **100 lifetime calls**。白話:「lifetime calls」是**一輩子只有 100 次**,不是每月 100 次——用完就沒了。所以設計上有三道閘:① cache-first,回應落盤才使用(同一題不重複燒額度);② `--max-calls` 顯式預算(想燒也得先講明白燒幾次);③ 沒有 `SECAPI_KEY` 時只產 ready-to-run 狀態文件,**絕不代辦註冊**。artifacts 只存 verdict/字數,payload 進 gitignored `data/sec_eval/arbitration/cache/`——**我留判決,不留人家的原文。**

> **不是「我湊滿了五個引擎」,是「每一票的授權、血統與可信度都寫在臉上——包括那票根本不准當標準答案」。**

## 我刻意沒做什麼?(授權風險規避)

白話:這一節是**負面清單**。技術文件通常只寫「我做了什麼」,但授權這件事,**沒做什麼才是重點**。

- **未** 複製 edgar-crawler(GPLv3)、Skyvern(AGPL)、py-sec-edgar(AGPL 商用)的任何程式碼。這些只用於「確認我們的方向 / 借觀念」。
- **未** 引入這些 repo 為執行期相依。

翻成人話:上面這三個專案我都讀過、也都覺得有東西可學,但它們全是 copyleft(傳染型)。所以它們的角色只有兩個——**幫我確認方向沒走歪、借我一個觀念**。**一行碼都沒進來,執行的時候也不依賴它們。**

## 外部評測資料從哪來?(P1-1)

白話:自己出題自己考,考幾分都沒有說服力。所以我去搬外部的題目來考自己——但**別人的題目也是別人的財產**,搬之前得先看授權。

| 來源 | 授權 | 使用方式 | 落地位置 |
|---|---|---|---|
| [osunlp/Online-Mind2Web](https://huggingface.co/datasets/osunlp/Online-Mind2Web)(OSU-NLP-Group,COLM 2025,arXiv:2504.01382) | **CC-BY-4.0**(2026-07-10 驗證:HF dataset card `license:cc-by-4.0` + GitHub README "Licensing Information";HF gate = auto click-through,無 CC-BY 以外附加條款)→ tier 1 署名即可 | `tools/import_mind2web.py` 分層抽 ~20 題(easy/medium/hard,排除 login/paywall/CAPTCHA 站),**只 commit 任務文字+metadata 子集**,每筆帶 attribution 與 `source_task_id`;完整資料集、軌跡、截圖一律不 commit。無 HF_TOKEN 時 fallback 到 ungated CC-BY mirror(hud-evals/Online-Mind2Web,來源記入 `source.fetched_from`)。live 任務失效維護協議見 `data/browser_eval/external/README.md` | `data/browser_eval/external/mind2web_subset.json`;shortcut 對照 `tools/naive_baseline.py` |
| [hsinmin/itemseg](https://github.com/hsinmin/itemseg)(NTU itemseg,arXiv:2502.08875)| repo README 明載 **CC BY-NC 4.0**;dataset 壓縮檔無 LICENSE、期刊版寫 "upon request" → 訊號矛盾取最嚴格解讀,**tier「unclear/research-only」** | Task 2 外部 benchmark 弱老師(一票,絕不當 gold):`tools/fetch_ntu_itemseg.py` fetch-on-demand(sha256 凍結 `769bc7da…`,重跑必驗)至 gitignored `data/raw_filings/external/ntu_itemseg/`;**不 vendor、不節錄 fixture**(逐行內容即標註資產本體);引用其論文。授權判定全文與 adapter 度量見 `docs/research/giants_task2.md` §4 | `tools/fetch_ntu_itemseg.py`、`tools/head_to_head.py`;artifact `data/sec_eval/scoring/head_to_head.json`(僅 verdict/計數,無原文)|

### Online-Mind2Web:授權乾淨,紀律仍然照上

**CC-BY-4.0** 白話就是「**你隨便用,寫我名字就好**」——授權上最乾淨的一種。而且不是查來的,是 2026-07-10 實際驗證過:HF dataset card 寫 `license:cc-by-4.0`、GitHub README 有 "Licensing Information",而且 **HF gate = auto click-through,無 CC-BY 以外附加條款**(白話:那道「請按同意」的門只是形式,背後沒有偷藏額外條件)。結論是 **tier 1 署名即可**。

即使如此,我還是只 **commit 任務文字+metadata 子集**——完整資料集、軌跡、截圖一律不 commit。為什麼授權都允許了還要克制?因為**重現只需要題目,不需要把人家整個資料集複製一份到我的 repo**。每筆都帶 attribution 與 `source_task_id`,你可以順著編號回去對原始出處。

一個工程細節值得講:無 HF_TOKEN 時 fallback 到 ungated CC-BY mirror(hud-evals/Online-Mind2Web),而且**來源記入 `source.fetched_from`**——白話:**我從哪個門進去拿的,檔案裡寫著。** 抽樣是分層的 ~20 題(easy/medium/hard),並排除 login/paywall/CAPTCHA 站;live 任務失效維護協議見 `data/browser_eval/external/README.md`。對照錨則是 `tools/naive_baseline.py` 的 shortcut。

### NTU itemseg:訊號矛盾時,我往最嚴格的那邊倒

這一份最值得講,因為**授權訊號是互相打架的**:

- repo README 明載 **CC BY-NC 4.0**(NC = non-commercial,不可商用);
- dataset 壓縮檔**無 LICENSE**;
- 期刊版寫 **"upon request"**(需索取)。

三個訊號指向三個不同結論。我的處理是:**訊號矛盾取最嚴格解讀**,判定 **tier「unclear/research-only」**(不清楚、僅供研究)。

> **不是「有一個訊號說可以,我就當可以」,是「訊號打架時,我按最嚴的那個辦」。**

落地的後果很具體:**不 vendor、不節錄 fixture**——理由是「**逐行內容即標註資產本體**」。白話:這份資料的價值**就是那些逐行標註**,所以我哪怕只截一小段當測試素材(fixture),截的都是它的**本體**,不是「引用一小段」那麼無辜。所以一行都不留在 repo 裡,改成 `tools/fetch_ntu_itemseg.py` fetch-on-demand(要用才抓),並用 sha256 凍結 `769bc7da…`、**重跑必驗**——白話:sha256 是內容指紋,凍結它是為了確保**我下次抓到的跟我當初量的是同一份東西**,免得對方悄悄改版讓我的數字失真。抓下來的東西進 gitignored `data/raw_filings/external/ntu_itemseg/`,並引用其論文。授權判定全文與 adapter 度量見 `docs/research/giants_task2.md` §4。

**誠實揭露(不軟化)**:它的定位寫死是 **Task 2 外部 benchmark 弱老師(一票,絕不當 gold)**。白話:**它是弱老師,不是標準答案。** 我不會因為它是台大出品、上了 arXiv 就讓它替我的系統打分定生死——它只投一票。artifact `data/sec_eval/scoring/head_to_head.json` 也只存 verdict/計數,**無原文**。

## 外部評審怎麼借?(WebJudge 官方自動評審;advisory 第二口徑)

白話:**advisory 第二口徑**的意思是——這是一個**參考用的第二意見**,不是判決。

| 來源 | 授權 | 使用方式 | 落地位置 |
|---|---|---|---|
| [OSU-NLP-Group/Online-Mind2Web](https://github.com/OSU-NLP-Group/Online-Mind2Web) `src/methods/webjudge_online_mind2web.py`(WebJudge,arXiv:2504.01382) | **MIT**(2026-07-11 於 GitHub 實讀 repo LICENSE 驗證;dataset 另為 CC-BY-4.0,見上節)→ 可改寫並保留出處 | 三階段協定(key-point 抽取 → 逐截圖 1-5 評分 → 軌跡總評)之 prompt 文字**逐字沿用**,僅將回應格式從自由文字改為 JSON(本機 codex gateway 之 action-schema 限制)。**與官方不可直接比數字**:judge model 為 gateway 帳號預設(gpt-5.5-class)非論文 o4-mini/WebJudge-7B;最終評審僅附 1 張最高分截圖(gateway 單圖限制);新增顯式 abstain(官方強制二元)。Advisory only,絕不改 runtime verifier 判決 | `tools/webjudge.py`;輸出 `runs/browser_eval/<run>/webjudge/webjudge_results.json`(deviations 全列於檔頭 docstring 與結果 JSON `deviations_from_official`) |

授權先講清楚:程式是 **MIT**,而且是 2026-07-11 **於 GitHub 實讀 repo LICENSE 驗證**的(dataset 另為 CC-BY-4.0,見上節)→ 可改寫並保留出處。**同一個專案,程式和資料的授權可以不一樣**——這就是為什麼要分開讀、分開記。

它做的事分三階段:key-point 抽取 → 逐截圖 1-5 評分 → 軌跡總評。白話:先問「這題要做到哪幾件事才算成功」,再一張截圖一張截圖給 1-5 分,最後看整條軌跡下總評。這些 prompt 文字我**逐字沿用**,只把回應格式從自由文字改成 JSON(因為本機 codex gateway 有 action-schema 限制)。

### 誠實揭露:我的 WebJudge 分數不能拿去跟論文比

這節最重要的一句話,我拉到標題級:**與官方不可直接比數字。** 我跟官方有四處偏離,每一處都會動到分數:

| 偏離 | 白話:這削弱了什麼 |
|---|---|
| judge model 為 gateway 帳號預設(gpt-5.5-class)非論文 o4-mini/WebJudge-7B | **改考官等於改考卷**。換了裁判,分數就不是同一把尺量出來的 |
| 最終評審僅附 1 張最高分截圖(gateway 單圖限制) | 裁判**只看到一張照片**就下總評,證據量比官方少 |
| 新增顯式 abstain(官方強制二元) | 官方**逼你二選一**,我允許裁判說「我不確定」——判決分布因此不可比 |
| 回應格式改為 JSON(action-schema 限制) | 格式受限於本機 gateway,不是原始自由文字 |

而且定位釘死:**Advisory only,絕不改 runtime verifier 判決。** 白話:**它只能在旁邊講話,不能改成績。** 我不讓一個「跟官方不可比」的裁判去動我系統的真實判決——否則就是拿一把量錯的尺去改答案。

這些偏離不藏在附錄:deviations **全列於檔頭 docstring 與結果 JSON `deviations_from_official`**——白話:**連機器讀的輸出檔裡都寫著「我哪裡跟官方不一樣」**,想無視都無視不掉。

> **不是「我通過了官方評審」,是「我沿用了官方的問法,但換了裁判、少給證據、多開一條棄權路——所以這個分數只配當參考」。**

## 哪些還能安全深化?(permissive 依賴 roadmap)

白話:這一節是「**未來可以放心踩的石頭**」——都是寬鬆授權,不會傳染。

- [dgunning/edgartools](https://github.com/dgunning/edgartools)(MIT):可作 EDGAR fetch / XBRL 標準化的參考或選配依賴。
- [jadchaar/sec-edgar-downloader](https://github.com/jadchaar/sec-edgar-downloader)(MIT):fetch 層可替換。
- Benchmark:WebArena / WebVoyager(研究用授權,跑評測 OK,勿把其網站資產當產品碼發佈)。

補一句白話:`XBRL` 是財報的機器可讀標記格式;最後一條的界線值得講明——**研究用授權讓我「拿來考自己」是 OK 的,但不代表我可以把人家的網站資產當成我的產品碼發出去。** 考試用和發佈用,是兩件事。

## 哪些是我自己的?(差異化:研究確認為 novel,無 prior art 可 defer)

三態 `unknown` 一級公民、a11y self-repair 綁定驗證迴圈、source-exact spans、**XBRL 認證 Item 8 span**——這些在調查的開源專案裡沒有直接對應物。詳見 `docs/prior_art.md`。

翻成人話,這四件是:

- **三態 `unknown` 一級公民**:答案不是只有「有/沒有」兩種,**「我不知道」是第三種正式答案**,不是失敗、不是空值——它在系統裡有正式身分。
- **a11y self-repair 綁定驗證迴圈**:`a11y` 是 accessibility(無障礙資訊)的縮寫。自我修復**綁死在驗證迴圈上**——修完不是自己說修好了,得過驗證那關。
- **source-exact spans**:`span` 是「原文的第幾個字到第幾個字」。**我指的是原文裡確切的那一段,不是我重新謄寫一份**——謄寫就有機會失真。
- **XBRL 認證 Item 8 span**:拿財報的機器可讀版本,回頭去**認證**我從人看的版本抓出來的那一段對不對——**兩種寫法互相對帳**。

**這裡的「novel(新穎)」只能主張到這個程度**:是「在調查的開源專案裡沒有直接對應物」,**不是「全世界首創」**。調查範圍就是 `docs/prior_art.md` 涵蓋的那些,超出範圍的我沒查、也就不宣稱。

> **授權這件事上,我唯一的招式是無聊的那招:每一份都實讀 LICENSE、訊號打架就從嚴、寧可少一票也不要一票髒。**
