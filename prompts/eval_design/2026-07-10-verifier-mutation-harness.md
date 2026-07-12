# Runtime verifier mutation harness(P0-4):門檻用 assert,不是報數字

## Trigger

giants 研究完整性批判(`docs/research/giants_task2.md` §5.3)指出兩個洞:(1) 既有 mutation test 只覆蓋 scorer,runtime 驗證訊號本身(confidence / needs_review / triangulation / topic_check / size band)從未被 mutation 測試——「驗證器自己被驗證」缺口;(2) 無量化門檻的 harness 只是存在性證明,不可引用。

## Scoring Criteria

- 正確性驗證:who-judges-the-judge 閉環
- 評估紀律:量化門檻(recall ≥ 0.95、false-alarm ≤ 0.05)寫死為 gate
- silent-failure prevention:注入的腐蝕必須被 shipped 驗證層抓到

## Prompt(reconstructed from session records)

workflow 派工指令(基於 P0-4 條目):

> 對 pipeline 輸出注入已知腐蝕(截斷、item 錯位、TOC-anchored 短 span、吞入財報 wrapper)+ 開放類 mutation(邊界抖動、跨 item 換文),斷言 runtime 驗證層必須抓到。門檻:per-class detection recall ≥ 0.95、乾淨輸出 false-alarm ≤ 0.05——低於門檻 = harness fail,不是報數字就算過。

## AI Output Summary

- **六類腐蝕**:truncate / misalign / toc_anchor / wrapper_swallow(封閉類)+ jitter / cross_swap(開放類)。
- **兩個 corrupt-base family**:offline alpha/beta fixture 抽取(全 detector 路徑)+ sweep3 proxy documents——由真實 per-item 字數/headings/文件序重建結構(真實 size 分布下測結構 detector,**不 commit 任何 filing 原文**)。
- **Gates asserted, not reported**:per-class recall ≥ 0.95 → 實測 **1.0000 全六類**(n=13..567);clean false-alarm ≤ 0.05 → fixture 0.0000(n=18)、proxy 0.0000(n=171)、recorded sweep3 runtime 輸出 0.0393(7/178,全部是 pre-P0-5 的 item-16 engine-blind disagrees,保守上界)。
- Fixtures:`data/sec_eval/mutations/`(合成 TOC stub + 合成 Financial Section wrapper,約 1.4K 字,零 SEC 原文)。

## Human / PM Decision

AI 依 workflow 授權自主實作;門檻數字直接採批判 pass 提出的 0.95/0.05,無放寬。

## Reason

- 無 ground truth 系統的可信度上限 = 驗證機制的可信度(2026-07-10 eval 升級波的第一性原理);mutation harness 是驗證機制自己的 regression。
- 門檻進 assert 意味著未來任何降低驗證層靈敏度的改動會直接紅燈,而非默默滑落。
- proxy-document 設計解決「要真實 size 分布但不能 commit SEC 原文」的兩難。

## Resulting Change

- `tests/test_verifier_mutations.py`(quantified gates)+ `data/sec_eval/mutations/` fixtures
- Commit:`034b0dc` feat(sec): P0-4 runtime verifier mutation harness with quantified gates
- 後續消費:TOC-strip 落地時以「mutation recall 全六類維持 1.0」作為不破壞驗證層的證據(`3c6ef01`);head-to-head 誠實敘事的可審計配套之一
