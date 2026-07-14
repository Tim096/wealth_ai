# NTU head-to-head 終判:F1 輸了照寫,敘事轉驗證軸

> **Record type:** Derived decision record

## Trigger

P0-2 姊妹交付物 A(同場競技表)實測完成:NTU 30-slice、4 引擎同一 gold set 跑 `tools/head_to_head.py`。raw macro-F1 **我們輸**——ours 0.5964 < datamule 0.6244 < edgar_crawler 0.6332。「超越最佳公開實作」的單軸主張在此刻被自己的量測證偽,必須決定敘事怎麼寫。

## Scoring Criteria

- 誠實邊界:輸的數字不粉飾(A++ 敘事的可信度基礎)
- 評估紀律:外部 benchmark、對手引擎同場、artifact 可重算
- 正確性驗證:錯誤裁決要更正並留痕

## Prompt summary

對抗式 interpreter 任務：

> 對 post-fix 的 head-to-head artifact 做對抗式重算:每個 macro-F1 由 per-filing 逐筆重算,不引用 tool 輸出;結論先講、輸的照寫。若 F1 收不掉,判定 F1 line 是否 CLOSED、敘事轉往哪一軸。

## AI Output Summary

三段終判(全記於 `docs/research/giants_task2.md`):

1. **18:05**:end-boundary fix(`3ba717b`)上線但 rescan cut 在 30-slice 上觸發 0 次,per-item delta 全 0——修法落地但量測無效,照錄。raw 輸 EC 0.0368。當時判 furniture-fp「對雙方對稱、公平」。
2. **18:40 錯誤更正**:兩個前置 agent 結論相反(第一診斷判 furniture-fp「對雙方對稱、公平」;fix agent 的逐 item probe 判「非對稱」),decide agent 原採信前者;推翻它的決定性證據是**一個 315 字元的 span 產生 fp=100**——315 字元不可能有 100 行真實邊界錯誤,只能是 span 內一行重複頁眉/TOC 回連被 adapter 按全文出現次數逐次計 fp(scorer 重複計數),較硬的逐 item 證據壓過較弱的宏觀 claim。拆帳終判:`Table of Contents` 導覽 backlink 一類是非對稱的(EC 會 strip、我們留著),但高-fp item 多數是真 boundary bleed 非 scorer artifact。合法 TOC-strip 投影 0.6244:追平 datamule(非贏)、仍輸 EC 0.0088。broad「duplicated=furniture」全 strip 判**非法**不採(見 `prompts/rejected_prompts/2026-07-10-broad-furniture-strip-for-f1.md`)。**F1 line: CLOSED**,不再 tune。
3. **landed**:TOC-backlink strip 落成產品雙層輸出(`normalize.py::clean_slice` delivery 層 + provenance 層 offsets/sha256 不動),`head_to_head.py` 重跑實測 **0.6245**(vs 投影 0.6244,差異來自錨點閘門更保守,如實記錄)——**仍輸 EC 0.0087、追平 datamule**。

最終敘事:我們用 precision 換 capture-first recall(bleed 是這筆 trade 的帳單),換來全場唯一自我審計的系統——false-pass 100 筆(strip 後 79)是我們自己量出來自己公布的;edgar_crawler 的 0.6332 是一個無法自我審計的數字。單軸 F1 輸 0.0087;「敢不敢把輸出直接餵下游」這一軸,對面三家沒有參賽資格。

## Decision

確認剩餘差距是真實 extraction gap 後，停止調 F1；輸的數字照寫，後續比較轉向 reliability 與 verifiability evidence。

## Reason

- 假的「每個數字都贏」一戳就破;真的「單軸輸 0.0087 + 唯一驗證層」經得起面試官重算(artifact 齊)。
- 18:05→18:40 的錯誤更正本身就是產品主張的示範:錯誤會被自己的機制抓到並公開修正。
- F1 殘餘 0.0088 是 heading-undetectable cascade 的真實 bleed,繼續 tune 的 counterfactual ceiling 只有 +0.0026,不值得。
- 分寸線:**追不到的 0.0088 不追,追得到的合法 +0.028 要拿**——TOC-strip 落地的理由不是贏 race,是真實輸出品質改良(乾淨 item text + 保留 offset 雙層輸出);這就是誠信與求勝的界線。

## Resulting Change

- `docs/research/giants_task2.md` 終判三節(18:05 / 18:40 / landed)+ 錯誤更正記帳
- `packages/sec_core/normalize.py` `clean_slice` / `_is_toc_backlink_line`、`pipeline.py` `clean_text_of`(雙層輸出)
- `tests/test_toc_backlink_strip.py`(7 tests);mutation harness recall 全六類維持 1.0
- Commits:`3ba717b`(end-boundary fix)、`6de5912`(fresh artifact)、`9ff78b9`(honest verdict)、`df954c8`(final F1 verdict + 對稱錯誤更正)、`3c6ef01`(TOC-strip 落地)
- Artifact:`data/sec_eval/scoring/head_to_head.json`(30 filings、4 engines,cache-first 可重跑)
