# 交件前文件整理:整併、濃縮、hash 校正的 curation 決策

## Trigger

交件前全面 review:PM 指出 prompts 與文件層有三類問題——(1) 原始對話摘錄的口語 user turn 讓開發流程觀感失真;(2) `docs/research/` 兩份 140KB 工作筆記混雜跑分 log 與自誇語氣,不是 reviewer 該讀的形狀;(3) root TODO 帶自評分數,而評分是 reviewer 的事。另在執行中發現兩個計畫外缺陷:文件引用的 commit hash 全數為 2026-07-12 timestamp 校正前的舊值(clone 後不可解析),以及 NTU itemseg 資料集(CC BY-NC,使用中)缺 ATTRIBUTION 列項。

## Scoring Criteria

- 誠實邊界:刪減必須留痕(git history + 本紀錄),不得變成「洗 repo」
- 可驗證性:所有留下的引用(hash、節標題、路徑)必須在 clone 後可解析
- Prompt records 品質:重建紀錄與原始摘錄互補,不重複敘事

## Prompt(reconstructed from session records)

PM 指令(節錄大意):把整份 repo 的 prompt 與文件驗證一輪——對話式贅字看起來不專業的收斂掉,對 repo 沒幫助、讓開發流程顯得混亂的刪掉,拿分的東西盡量留;改動前先給計畫。PM 核准計畫後授權執行。

## AI Output Summary

1. **transcripts 整併(5→2)**:與重建紀錄重疊的 3 份摘錄,獨有內容併入對應紀錄後移除(對應表見 `prompts/transcripts/README.md`「整併紀錄」節);保留原始性最高的 verifier-paradox(哲學起點)與 heldout-freeze-protocol(凍結協議佐證)。原文全數留在 git history。
2. **giants 研究筆記原地濃縮**(task1 480→263 行、task2 631→269 行):去跑分 log 敘事與自我優越語氣,保留全部量測表、backlog ID、引用義務與被外部引用的節錨點(凍結 artifacts 以節名引用,錨點是硬契約);`external_benchmark_spike.md` 的授權判定與 adapter 度量併入 giants_task2 §4 後刪除。
3. **TODO 重定位**:自評分數與目標分數全移除,改為 known-limitations/experiments roadmap;LLM 決策表與「不做」清單原樣保留。
4. **計畫外修復**:(a) 40 個失效 commit hash 依 commit message 1:1 映射至校正後現行值(上游專案 pin、session id 不動;verbatim 摘錄凍結不改,README 揭露);(b) 補 NTU itemseg 的 ATTRIBUTION 列項;(c) transcripts README 移除部署密碼字面前綴,重跑脫敏複掃(0 hits)。

## Human / PM Decision

PM 逐項核准計畫(含 transcripts「留 1-2 份、其餘改寫」與內部筆記「濃縮改寫」兩個方向決定);執行與計畫外缺陷的處置由 AI 自主判斷。

## Reason

- 題目明說 prompts 資料夾「we will actually read them」:重複敘事與口語贅字稀釋高價值紀錄;但全部 polish 掉會失去原始佐證,故保留兩份 verbatim 錨點。
- 自評分數放在 repo 門面,reviewer 只會拿來對照扣分;把同一內容改寫成弱點→實驗的映射,資訊不變、立場正確。
- 失效 hash 對主打「可重驗」的 repo 是實質缺陷:每一條 Resulting Change 的 commit 引用都應該 `git show` 得出來。
- 所有刪除都可在 git history 還原,且本紀錄與 transcripts README 明文記載去向——curation 有紀錄,不是掩蓋。

## Resulting Change

- `prompts/transcripts/`(5→2 + README 重寫)、`prompts/eval_design/2026-07-10-ntu-f1-honest-narrative.md`、`prompts/failure_triage/2026-07-10-second-judge-live-abstain-chain.md`(整併補強)、新增 `prompts/failure_triage/2026-07-11-official300-resume-abort-deadlock.md`
- `docs/research/giants_task1.md`、`giants_task2.md`(濃縮)、刪除 `docs/research/external_benchmark_spike.md`、`docs/ATTRIBUTION.md`(NTU 列項)
- `TODO.md`、`README.md`、`docs/insights_and_directions.md`(重定位與措辭)
- 19 檔 hash 映射(commit `90bc8f5`);本輪各 phase 獨立 commit,不 amend、不 force-push
