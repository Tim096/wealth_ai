# AI Collaboration Records

SPEC 第 10 節要求保存關鍵 AI 協作過程。

**一句話:這不是聊天記錄的備份,是一疊標好出處的決策檔案。**

白話:reviewer(閱卷者)打開這個資料夾,真正想知道的只有一件事——「這些字,哪些是 AI 當場真的講過的、哪些是你事後整理的?」我沒有把兩者混在一起裝成同一種東西。每一份檔案開頭都自己表明身分。

本頁分四段:

1. **這裡放的是什麼、不是什麼** —— 先劃邊界,免得你以為看到的是完整存檔。
2. **哪些字可以逐字核對?** —— 三種 provenance(出處類型)各多少份、各自能主張到什麼程度。
3. **東西放在哪?** —— 目錄定位,加上依日期排的檔案索引。
4. **怎麼讀、怎麼驗?** —— 格式、命名,以及日期**不能**拿來當什麼用。

## 這裡放的是什麼、不是什麼?

問題是:AI 協作紀錄很容易變成兩種沒人要的東西——要嘛是幾十萬字的原始對話傾倒(沒人讀得完),要嘛是事後美化的小作文(沒人信)。

答案是:這裡不是完整 chat archive(完整對話存檔),也不是每個檔案都宣稱是原始 prompt(下給 AI 的指令);它保存影響設計、實作、eval(評測)、修復與拒絕方案的高價值紀錄,並在每檔開頭標示 provenance。

> **不是「我保存了全部」,是「我保存了會改變判斷的那些——而且逐份告訴你成色」。**

## 哪些字可以逐字核對?

白話:同樣叫「紀錄」,可信度差很多。逐字保留的,你可以拿去跟原文一個字一個字對;事後重建的,你只能拿去跟 code 和 artifacts(產物檔)對。我把成色分成三級分開標,不讓最弱的那級沾最強的那級的光。

### 三種 provenance 類型

| 類型 | 數量 | 可以主張什麼 |
|---|---:|---|
| **Verbatim transcript excerpt** | 5 | `---` 後標明 row 的 user/assistant 文字逐字保留;秘密與過長工具內容只以明確 marker 遮蔽或截斷 |
| **Verbatim prompt artifact** | 1 | workflow 實際保存的 prompt template;不是人機對話 transcript |
| **Derived decision record** | 21 | 依 Git、code、artifacts、docs 或 session evidence 重建決策;`Prompt` 段是摘要,不是逐字引言 |

翻成一般人能懂的版本:

- **Verbatim transcript excerpt**(逐字對話摘錄):AI 當場講的原話。`row` 是對話的一輪;`marker` 是我留下的遮蔽記號——**遮了就明說遮了**,不會靜悄悄刪掉一段當作沒發生。
- **Verbatim prompt artifact**(逐字 prompt 檔):workflow(自動化流程)跑的時候真的送出去的那段模板。它是機器的**輸入**,不是人跟機器的**對話**——這兩件事我不混為一談。
- **Derived decision record**(重建型決策紀錄):我事後依 Git、code、artifacts 重寫的。**它的 `Prompt` 段是我的摘要,不是 AI 的原話。** 這一點我寧可講死,也不要讓你誤讀成引言。

目前共 26 份紀錄。分類讓 reviewer 能分辨哪些字句可逐字核對、哪些是可由 code、artifacts 與 tests 驗證的設計紀錄。

> **不是「這 26 份都是原始對話」,是「5 份逐字對話加 1 份逐字 prompt 檔可以逐字對,其餘 21 份請拿 code 來對」。**

## 東西放在哪?

### 各目錄負責什麼?

| 目錄 | 一句話定位 |
|---|---|
| `project/` | 專案層級決策:SPEC 導入、stack 選擇與平台基礎 |
| `browser_agent/` | Task 1 agent 本體的設計決策:selector 修復、planner system prompt 演進 |
| `eval_design/` | 評測體系的設計決策:eval set、對抗式稽核、外部 benchmark、mutation harness、多引擎投票 |
| `failure_triage/` | 真實失敗的診斷紀錄:根因鏈、修復、重驗(不信任表面 pass) |
| `rejected_prompts/` | 被拒絕的設計:為什麼拒、拒了之後走哪條路、事後看對不對 |
| `transcripts/` | 5 份已脫敏的原始 AI 協作對話摘錄;verbatim body 由 provenance manifest 與 verifier 固定 |

> `sec_extractor/` 的 boundary/adjudicator 決策目前併在 `eval_design/` 與 `failure_triage/`(SEC 尚未觸發 LLM adjudicator);待 adjudicator 實際啟用再獨立成目錄。

白話補一句上面這個註記:**目錄結構跟著實際跑起來的東西走,不跟著我想像中的架構走。** adjudicator(仲裁者:意見分歧時出來裁決的那一層)在 SEC 這條線上還沒被觸發過,所以我不先開一個空目錄擺著好看。

## 索引(依日期)

### project/

| 檔案 | 一句話 |
|---|---|
| `2026-07-10-spec-ingestion-and-foundation.md` | SPEC 導入後第一階段建什麼、用什麼 stack 的奠基決策 |

### browser_agent/

白話:這一區是「瀏覽器 agent 自己怎麼認路」。`selector`(選擇器)就是「怎麼指認網頁上的那顆按鈕」;`planner system prompt` 是規劃者的長期人格設定檔。

| 檔案 | 一句話 |
|---|---|
| `2026-07-10-selector-repair-design.md` | selector 修復 + capability guard 的初始設計(確定性優先、LLM 是升級手段) |
| `2026-07-10-planner-system-prompt-v2.md` | planner system prompt v1→v2:實測失敗模式固化進 prompt |

### eval_design/

白話:這一區回答的是「我憑什麼相信自己的分數」。三個縮寫先翻:**XBRL** 是財報的機器可讀標記格式(同一份財報的另一種寫法,可以拿來互相對帳);**ASR** 是 attack success rate(攻擊成功率,愈高代表愈容易被騙);**F1** 是精確率與召回率的調和平均(抓得準與抓得全的綜合分)。

裡面有兩份特別想請你先看:`verifier-mutation-harness` 是**元層**動作——不只證明「我沒發現問題」,而是故意注入腐蝕、看警報響不響,把結論升級成「我**有能力**發現、而且沒發現」;`ntu-f1-honest-narrative` 則是我輸的那一份,結論照寫。

| 檔案 | 一句話 |
|---|---|
| `2026-07-10-real-filing-sweep.md` | 11 家公司分層真實樣本 sweep 設計 |
| `2026-07-10-adversarial-audit-workflow.md` | 對抗式稽核設計:11-company accession evidence、獨立 verifier 與 regression tests |
| `2026-07-10-xbrl-and-cross-ref.md` | cross-reference-index 處理 + XBRL 當獨立驗證基材 |
| `2026-07-10-reviewer-prompts-verbatim.md` | reviewer/auditor agent prompt 逐字保存(SPEC 10.1) |
| `2026-07-10-eval-upgrade-todo-from-web-research.md` | 兩個研究 agent 網查後的 11 項 eval 升級波(invariant + 校準裁判本身) |
| `2026-07-10-verifier-mutation-harness.md` | P0-4:對 runtime 驗證層注入六類腐蝕,recall/false-alarm 門檻用 assert 鎖死 |
| `2026-07-10-five-engine-2of-n-voting.md` | P0-7:第四/五仲裁票 + 2-of-N 投票;GPL 擋下 vendor 改 subprocess 隔離 |
| `2026-07-10-prompt-injection-adversarial-suite.md` | P1-14:注入對抗頁套件 + instruction/content separation,metric 以服從式 agent 自證 ASR=1.0 |
| `2026-07-10-ntu-f1-honest-narrative.md` | NTU head-to-head 終判:F1 輸 edgar_crawler 0.0087 照寫,敘事轉唯一可自我審計的驗證軸 |

### failure_triage/

白話:這一區收的是**真的壞掉過**的紀錄——不是「我們遇到一點小挑戰」,是根因、修法、重驗。核心紀律一句話:**表面 pass 不算 pass。**

| 檔案 | 一句話 |
|---|---|
| `2026-07-10-jpm-cross-ref-stub.md` | JPM Item 11 51 字元標 pass 的誤判診斷 → incorporated_by_reference 分類誕生 |
| `2026-07-10-browser-decoy-and-modal.md` | decoy button + cookie modal 導致修復選錯元素的 triage |
| `2026-07-10-second-judge-live-abstain-chain.md` | second judge live 18/18 abstain 的兩層根因(HOLE A 接線+證據餓死、gateway wrapper)與定向重驗 |
| `2026-07-11-official300-resume-abort-deadlock.md` | 官方全量 300 題死鎖:resume 不計 n_attempted 使 3 個死站永觸 abort;chunk agent 依鐵律 escalate、修 harness 不修題 |
| `2026-07-15-stale-claim-sweep-and-display-boundary.md` | 多段還原上線後:3-finder workflow 掃全 repo 找敘事落後 shipped 的字句(補抓 cited 外 3 處)+ unsupported ≠ 100% 的誠實顯示邊界 |

### rejected_prompts/

白話:被拒絕的方案值錢在哪?**在事後回頭看我拒對了沒有。** 每份都寫「為什麼拒 → 走了哪條路 → 事後長怎樣」,包含事後證明我得繞回去補的部分。

| 檔案 | 一句話 |
|---|---|
| `2026-07-10-typescript-first-stack.md` | 拒 TS monorepo → Python-first;事後:pip 生態撐起全部關鍵能力 |
| `2026-07-10-browser-vision-model-repair.md` | 拒 vision 當修復主路徑;事後:vision 回歸為感知升級層,repair 維持零 LLM |
| `2026-07-10-sec-title-based-body-resolution.md` | 拒 title-based 正文猜測 → 誠實指標;事後:page-anchor + wrapper reassembly 補完正文 |
| `2026-07-10-broad-furniture-strip-for-f1.md` | 拒 broad duplicated-strip 刷 F1(實測雙降)→ 窄版錨點閘門 TOC-strip 落成產品特性,仍輸照寫 |

### transcripts/

白話:這五份是**可以逐字對**的那一批。`---` 之後的內容,雜湊值(把一段文字壓成一串指紋碼)被 manifest 與 verifier 鎖死——我事後想偷改一個字,verifier 會叫。

| 檔案 | 一句話 |
|---|---|
| `2026-07-10-verifier-paradox.md` | verifier 不可能完美時，如何用不變量、棄權、交叉分歧與錯誤注入建立退出條件 |
| `2026-07-10-ntu-f1-honest-narrative.md` | 外部 F1 輸給 edgar_crawler 後，如何裁決相反診斷並停止追分 |
| `2026-07-10-second-judge-abstain-wrapper.md` | live second judge 全 abstain 的兩層根因與 gateway wrapper 修復 |
| `2026-07-11-heldout-freeze-protocol.md` | held-out 任務先凍結、後執行的原始協作過程 |
| `2026-07-11-official-300-resume-abort-deadlock.md` | 官方 300 題 run 被 resume/abort deadlock 卡住後的診斷、escalation 與修復 |

## 怎麼讀、怎麼驗?

Derived records 依 SPEC 10.2 使用 Trigger / Scoring Criteria / Prompt summary / AI Output Summary / Decision / Reason / Resulting Change；verbatim excerpts 保留原本輪次結構。

四條讀法規則,每一條都是為了讓你**少信我一點**:

- 每檔先標 `Record type`。未標 verbatim 的 `Prompt` 段一律視為重建摘要，不是原始對話。
- Verbatim transcript 中只有 `---` 後標明 row 的段落屬逐字內容；檔名、標題、metadata 與開場摘要是 editorial context。
  - 白話:連逐字檔裡面,我都再切一刀——**標題和開場是我寫的,不算原話。**
- 無法逐字重現時，不補寫 user/assistant 對話；改以 Git、code、artifact、doc 或 session evidence 重建 decision record。
  - 白話:記不得原話,就**不編**。寧可降級成「重建紀錄」,也不要生一段像模像樣的假對話。
- 命名:`YYYY-MM-DD-short-slug.md`。日期是整理時採用的事件標籤，不是 chronology proof；時序應以可解析 Git objects、artifacts 或 verbatim row metadata 交叉驗證。

### 這裡最大的限制是什麼?——檔名上的日期不是證據

這條我拉到標題級,不塞附錄:

> **檔名日期是整理時採用的事件標籤,不是 chronology proof(時序證據)。**
> 白話:**別拿檔名當時間戳來信。** 想確認事情的先後,請去對可解析的 Git objects、artifacts,或 verbatim row 的 metadata——那些我改不動,檔名我改得動。

| 限制 | 這削弱了什麼 / 還能宣稱什麼 |
|---|---|
| 檔名日期只是事件標籤 | 削弱:不能用檔名證明「誰先誰後」。還能宣稱:時序可由 Git objects、artifacts、verbatim row metadata 交叉驗證 |
| 21 份是重建型紀錄 | 削弱:`Prompt` 段不能當逐字引言核對。還能宣稱:決策內容可由 code、artifacts 與 tests 驗證 |
| 5 份逐字摘錄含遮蔽 | 削弱:秘密與過長工具內容不在檔內。還能宣稱:遮蔽處都有明確 marker,不是無聲刪除 |

> **這疊紀錄的價值不在於它證明我做對了,而在於它讓你有辦法抓到我做錯了。**
