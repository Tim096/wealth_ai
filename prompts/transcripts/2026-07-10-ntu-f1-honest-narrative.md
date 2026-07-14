# NTU F1 誠實敘事 — 輸給 vendored engine 照寫

- **Session**: `3ae1f24f-695e-448f-94aa-7efb6c9d79ab`
- **日期**: 2026-07-10（原始輪次 row 584–648)
- **Record type**: Verbatim transcript excerpt with editorial context
- **Verbatim boundary**: Only the dated `row ...` sections below `---` are verbatim. The title, metadata, summary, and cross-references are editorial scaffolding.
- **Redaction**: Secrets are replaced with explicit `[REDACTED-...]` markers; omitted tool material is marked `[...elided...]` where applicable.
- **對應重建紀錄**: `prompts/eval_design/2026-07-10-ntu-f1-honest-narrative.md`、`prompts/rejected_prompts/2026-07-10-broad-furniture-strip-for-f1.md`、記憶 `task2-ntu-f1-honest-narrative`

> 在外部 NTU itemseg benchmark 上,我方 vendor 進來的 edgar_crawler(0.6332)raw macro-F1 贏過我們(0.5964)。這串節錄記錄 AI 如何拒絕掩蓋、如何裁決 agent 之間對 fp 對稱性的矛盾、如何區分「合法拿得到的 +0.028」與「追不到的 0.0088」,最終把 F1 線收束成「全場唯一自我審計系統」的誠實敘事。

---

### row 584 — assistant

Honest result: the overshoot guard is clean-corpus-safe but **missed all three acceptance gates** (interception 20.6% vs ≥50%, AUROC 0.63 vs ≥0.75, false-pass actually *worsened* 0.24→0.25). And the remeasure surfaced something more important that I need to call out plainly:

**On the NTU external benchmark, two of the engines we vendored beat us: edgar_crawler 0.6332 and datamule 0.6244 vs our 0.5964.** That is the opposite of "exceeding SOTA" on this metric, and I'm not going to bury it.

The root cause diagnosis also exposed a conflation in my own plan: the overshoot guard only touched **confidence capping** (verification), so it couldn't move **F1** (extraction) — and indeed F1 moved +0.0003. The two are different problems:
- The F1 gap = our *end boundaries run long* (capture-first philosophy + missed intermediate headings → span overshoots). That's an extraction fix in `boundary.py`, not a verifier fix.
- edgar_crawler's stricter regex cuts cleaner, so it wins raw F1 while having none of our verification.

First, close the provenance gap the agent flagged, then attack the real thing:

### row 602 — assistant

三線現況:

- **Task 2**:overshoot confidence guard 誠實地三閘門全 MISS(已記錄)。更關鍵的發現我要對你直說:**外部 NTU benchmark 上,我們 vendor 進來的 edgar_crawler(0.6332)和 datamule(0.6244)在 raw F1 贏過我們(0.5964)**。我判斷這不該掩蓋。已開診斷 workflow:先分辨這是「真缺陷(漏偵測中間 heading 導致 span 跑長)」還是「NTU 邊界慣例差異」,winnable 才修 extraction 端邊界,然後前景重測比 edgar_crawler,不論輸贏都把誠實對照表(我們 F1 / 他們 F1 / 我們獨有的驗證軸)寫進文件。設了硬停止條件,不無限調參。
- **Task 1**:m2w 20 題 serial 重跑由收尾 agent 盯著。
- **部署**:等你。

我的判斷:A++ 不等於每個數字都贏。題目明列「failure modes honestly surfaced」,誠實報告 vendored engine 在單點 F1 贏我們、並解釋我們用 precision 換 capture-first recall 且是唯一有 multi-oracle 驗證的系統——這個框架比硬湊一個贏的數字更接近 A 級。已存記憶。

### row 616 — assistant

讀完了,而且抓到一個 agent 之間的**矛盾必須由我裁決**:

- 第一診斷說 furniture-line 的 fp 對雙方「對稱、公平」;
- 第二(fix agent 的逐 item probe)說「edgar_crawler 出稿前把這些行剝掉所以 fp≈0,我們沒剝所以 fp 爆炸」——**不對稱**;
- 最終 decide agent 採信了第一個,結論「不改」。

決定性證據站在第二個那邊:**一個 315 字元的 span 竟產生 fp=100**。315 字元不可能有 100 行真實邊界錯誤——這只能是「span 內一行重複頁眉/TOC 回連,被 adapter 按全文出現次數每次各計一次 fp」。所以 decide agent 錯判了,它拿較弱的宏觀 claim 壓過了較硬的逐 item 證據。

這翻轉了結論:**F1 差距不是邊界問題(end-boundary fix 觸發 0 次、F1 動 0.0000 已證實),是我們沒有清掉 item text 裡的頁面 furniture 行**。而清掉重複頁眉/TOC 回連是**真實的產品改良**(下游要乾淨 item text)、是 edgar_crawler 本來就做的標準做法、不是為跑分修剪真實 span。這個贏是合法拿得到的。

開最後一個 F1 workflow,先用硬證據終結矛盾,再做 output 端 furniture 清理,前景重測。設硬停止:這次還贏不了就全面轉誠實敘事,不再調 F1。

### row 630 — assistant

裁決做得很嚴謹,兩個前置 agent 都只對一半——真相是混合的:adapter 確實按「每 gold-row 位置 × 全文 text 包含」爆計 fp(Agent-2 的機制判讀對),但只有**一個** furniture 類別真正不對稱:TOC 導航回連(edgar_crawler 剝、我們留);其餘重複 furniture 兩邊對稱、broad strip 會吃掉真實內容且兩邊都掉分(正確否決)。

結論我認同:**F1 不贏,誠實敘事線關閉**。TOC-strip 合法 +0.0280 到 0.6244,只追平 datamule、仍差 edgar_crawler 0.0088,殘差是真實的邊界 over-extraction 不是 metric 假象。

但有一件事 workflow 的 gate 邏輯漏掉了:**TOC-strip 本身是個該落地的真實產品特性**(乾淨 item text 對下游更好、雙層輸出=乾淨 text + 保留 offset、裁決已確認合法),它被 skip 只因為「不足以贏 race」——但落地它的理由不是贏 race,是它讓輸出更好且 +0.028 是實測改良。留著不做是錯的。派一個聚焦 agent 把它作為 feature 落地(精確鎖定 TOC 導航回連類,非 broad strip),前景重測讓 0.6244 從 projected 變 measured,更新文件:

### row 638 — assistant

三線現況:

- **Task 2**:F1 調查結案。誠實結論——**我們 raw F1 0.5964 不贏,合法 TOC-strip 後 0.6244(追平 datamule、仍差 edgar_crawler 0.0088),殘差是真實邊界 over-extraction 非 metric 假象**。F1 線關閉,站穩誠實敘事:我們是全場唯一自我審計的系統(自報 false-pass 100,附完整 AUROC/ECE/coverage/mutation-recall),edgar_crawler 的 0.6332 是無法自我審計的 silent 數字。我判斷 TOC-strip 該作為真實特性落地(乾淨 item text 對下游更好、+0.028 實測、雙層輸出保留 offset),已派 agent 落地並把數字從 projected 轉 measured。
- **Task 1**:m2w 20 題重跑進行中。
- **部署**:等你。

我對這條線的判斷:**追不到的 0.0088 不追了**,但追得到的合法 +0.028 要拿(那不是為跑分,是真實輸出品質)。這個分寸就是誠信與求勝的界線。等 TOC-strip 落地與 m2w 數字進來後,我做兩題最終文件整合。

### row 648 — assistant（節錄前半;後段「等你決定兩件事」清單已省略)

整體盤點(距測驗文件加入已 44 個 commit,測試從 303 → 666 個 test function):

**Task 2(SEC)— 技術實質完成**
12 個 P0 + 補強全落地。誠實數字:
- 外部 NTU benchmark macro-F1:我們 0.6245(TOC-strip 後)、edgar_crawler 0.6332、datamule 0.6244、edgartools 0.4386 → **raw F1 不贏**,但我們是唯一自我審計的系統(自報 false-pass 79、附 AUROC/ECE/coverage/mutation-recall 全套)
- Mutation harness 六類 recall 全 1.0;JPM/XOM wrapper 重組經 XBRL+CYD 雙 oracle 認證;triangulation 5 引擎 2-of-N
- 校準 AUROC 0.63(誠實揭露弱,殘差是真實邊界 over-extraction,已診斷)

[...後段部署待決事項與自主 backlog 清單省略...]
