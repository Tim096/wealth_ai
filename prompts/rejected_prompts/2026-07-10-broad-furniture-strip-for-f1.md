# Rejected: broad「duplicated=furniture」全 strip 收 F1 gap

## Trigger

NTU head-to-head 終判(18:40 對抗裁決)期間,AI 評估的一個方案:既然 per-item probe 證明重複頁眉/導覽行灌了大量 fp,把**所有**跨頁重複文字當 furniture 全部 strip 掉,一口氣收掉對 edgar_crawler 的 0.0368 F1 gap。

## Scoring Criteria

- 誠實邊界:metric hack vs 真產品特性的分界
- 正確性驗證:strip 規則必須可辯護、對所有引擎語義一致

## Prompt(被評估的設計)

「凡在同一 filing 內重複出現 ≥N 次的行視為 furniture,評分前全部移除,雙方對稱套用。」

## AI Output Summary(為何評估後拒絕)

實測重算後拒絕:

1. **吃掉真實內容**:重複 ≠ furniture——公司/子公司頁眉、逐頁重複的 `Net sales` 等財務行是合法內容。broad strip 實測**雙降**:ours 0.5964→0.57、edgar_crawler 0.6332→0.5905。分數形狀全變但誰都沒變準,是純 metric 破壞。
2. **不可辯護**:strip 規則若只為評分存在、不對應任何交付價值,就是 metric hack;面試官一問「這規則產品裡在哪」即穿幫。
3. **真正非對稱的只有一類**:per-item probe 拆帳證明只有 TOC 導覽 backlink 是 EC strip 我們留的非對稱項;其餘 recurring furniture 兩引擎逐筆相同(對稱),高-fp item 主體是真 boundary bleed。

## Human / PM Decision

拒絕 broad strip。改走**窄而合法**的路:TOC-navigation-backlink stripping 落成產品雙層輸出——`clean_slice()` delivery 層移除「整行 ∈ TOC 片語白名單 **且** 整行字元都在內部錨點內」的行;provenance 層(offsets/sha256/coverage)不動。它獨立於評分存在(可讀性、下游 diff),放進評分只是誠實把交付層算進去。

## Reason

- 錨點閘門讓規則精準:真正的 `TABLE OF CONTENTS` 章節標題(非錨點)保留、合法 recurring 財務內容永不被 strip。
- 即使合法 strip 之後 F1 仍輸 EC 0.0087——所以它是特性揭露,不是勝負宣稱。寧可輸著誠實,不要贏得可疑。

## 事後看(2026-07-10 landed 實測)

拒絕正確。窄版 strip 落地後實測 0.6245(比投影 0.6244 高 0.0001,來自錨點閘門更保守),`tests/test_toc_backlink_strip.py` 7 tests 證明真實 body 句子與 recurring 財務內容永不被 strip、provenance 不變;mutation harness recall 全六類維持 1.0。若當時採 broad strip:數字雙降、驗證層失真、且整條誠實敘事(見 `prompts/eval_design/2026-07-10-ntu-f1-honest-narrative.md`)失去立足點。

## Resulting Change

- 採用:`packages/sec_core/normalize.py::clean_slice` + `pipeline.py::clean_text_of`(commit `3c6ef01`);**不做** broad duplicated-strip
- 裁決記錄:`docs/research/giants_task2.md` 終判 18:40 / landed 兩節;artifact `data/sec_eval/scoring/head_to_head.json`
