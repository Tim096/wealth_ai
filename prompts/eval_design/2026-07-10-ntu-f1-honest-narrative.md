# NTU head-to-head 終判:F1 輸了照寫,敘事轉驗證軸

## Trigger

P0-2 姊妹交付物 A(同場競技表)實測完成:NTU 30-slice、4 引擎同一 gold set 跑 `tools/head_to_head.py`。raw macro-F1 **我們輸**——ours 0.5964 < datamule 0.6244 < edgar_crawler 0.6332。「超越最佳公開實作」的單軸主張在此刻被自己的量測證偽,必須決定敘事怎麼寫。

## Scoring Criteria

- 誠實邊界:輸的數字不粉飾(A++ 敘事的可信度基礎)
- 評估紀律:外部 benchmark、對手引擎同場、artifact 可重算
- 正確性驗證:錯誤裁決要更正並留痕

## Prompt(reconstructed from session records)

AI 自我指令(adversarial interpreter pass,總指揮授權範圍內):

> 對 post-fix 的 head-to-head artifact 做對抗式重算:每個 macro-F1 由 per-filing 逐筆重算,不引用 tool 輸出;結論先講、輸的照寫。若 F1 收不掉,判定 F1 line 是否 CLOSED、敘事轉往哪一軸。

## AI Output Summary

三段終判(全記於 `docs/research/giants_task2.md`):

1. **18:05**:end-boundary fix(`a72ec43`)上線但 rescan cut 在 30-slice 上觸發 0 次,per-item delta 全 0——修法落地但量測無效,照錄。raw 輸 EC 0.0368。當時判 furniture-fp「對雙方對稱、公平」。
2. **18:40 錯誤更正**:per-item probe 拆帳證明 18:05 的「對稱」判斷**錯誤**——`Table of Contents` 導覽 backlink 一類是非對稱的(EC 會 strip、我們留著),但高-fp item 多數是真 boundary bleed 非 scorer artifact。合法 TOC-strip 投影 0.6244:追平 datamule(非贏)、仍輸 EC 0.0088。broad「duplicated=furniture」全 strip 判**非法**不採(見 `prompts/rejected_prompts/2026-07-10-broad-furniture-strip-for-f1.md`)。**F1 line: CLOSED**,不再 tune。
3. **landed**:TOC-backlink strip 落成產品雙層輸出(`normalize.py::clean_slice` delivery 層 + provenance 層 offsets/sha256 不動),`head_to_head.py` 重跑實測 **0.6245**(vs 投影 0.6244,差異來自錨點閘門更保守,如實記錄)——**仍輸 EC 0.0087、追平 datamule**。

最終敘事:我們用 precision 換 capture-first recall(bleed 是這筆 trade 的帳單),換來全場唯一自我審計的系統——false-pass 100 筆(strip 後 79)是我們自己量出來自己公布的;edgar_crawler 的 0.6332 是一個無法自我審計的數字。單軸 F1 輸 0.0087;「敢不敢把輸出直接餵下游」這一軸,對面三家沒有參賽資格。

## Human / PM Decision

PM 鐵律「誠實優先:數字不粉飾,輸的照寫」+ 既定總目標(外部老師當弱老師、不追單點跑分)授權下,AI 裁決:F1 line CLOSED、敘事全面轉可靠性/可驗證性差異化。PM 事後確認此為 Task 2 的正式敘事方向。

## Reason

- 假的「每個數字都贏」一戳就破;真的「單軸輸 0.0087 + 唯一驗證層」經得起面試官重算(artifact 齊)。
- 18:05→18:40 的錯誤更正本身就是產品主張的示範:錯誤會被自己的機制抓到並公開修正。
- F1 殘餘 0.0088 是 heading-undetectable cascade 的真實 bleed,繼續 tune 的 counterfactual ceiling 只有 +0.0026,不值得。

## Resulting Change

- `docs/research/giants_task2.md` 終判三節(18:05 / 18:40 / landed)+ 錯誤更正記帳
- `packages/sec_core/normalize.py` `clean_slice` / `_is_toc_backlink_line`、`pipeline.py` `clean_text_of`(雙層輸出)
- `tests/test_toc_backlink_strip.py`(7 tests);mutation harness recall 全六類維持 1.0
- Commits:`a72ec43`(end-boundary fix)、`e6db247`(fresh artifact)、`7b46be5`(honest verdict)、`5bb103f`(final F1 verdict + 對稱錯誤更正)、`eed20b6`(TOC-strip 落地)
- Artifact:`data/sec_eval/scoring/head_to_head.json`(30 filings、4 engines,cache-first 可重跑)
