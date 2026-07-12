# 第四/第五仲裁票 + 2-of-N 投票(P0-7):GPL 擋下 vendor,改 arms-length subprocess

## Trigger

giants 研究(`docs/research/giants_task2.md` P0-7)確立 triangulation 需要血統獨立的仲裁票:既有 3-engine 的 12 個 disagree 無仲裁者,一律 needs_review 扣自己分,其中 8 個實為 edgartools 的 item 10-16 rescue bug(對方錯、我方被扣)。計畫三票:(a) vendor edgar-crawler regex core、(b) sec-api.io free-tier 仲裁協定、(c) datamule 第五票。

## Scoring Criteria

- 正確性驗證:多 oracle 血統獨立,disagree 有裁決機制
- 工程權衡:license 合規(MEMORY 既定 license 三檔規則)
- 誠實邊界:外部引擎當票不當 gold

## Prompt(reconstructed from session records)

workflow 派工指令(基於 P0-7 條目):

> 接入 edgar-crawler 為第四 engine、datamule 為第五票,apply_triangulation 擴為 2-of-N 投票;sec-api.io free-tier 做 cache-first 仲裁協定。vendor 前必查 LICENSE;外部引擎 agree 只能加信心,不可當 gold。

## AI Output Summary

1. **License 實查改變了實作形態**:edgar-crawler LICENSE 於 depth-1 clone @ `84a8d0c` 重驗為 **GPLv3** → **不 vendor**(避免 GPL 傳染 repo)。改為 arms-length subprocess adapter(`sec_core/engines/edgar_crawler_vote.py`)驅動未修改的 upstream CLI,checkout 釘 commit 且 gitignored 不入庫。
2. **datamule==5.0.1**(MIT,doc2dict 後端)pip 安裝為第五票(`engines/datamule_vote.py`)——樣式驅動路線,與我方 regex 驅動實作獨立。
3. **2-of-N 語義**:任一 corroborating engine 同意即確認我方 span;只有 uncorroborated disagree(無任何引擎站在我方)才扣 confidence。sweep 實測:原 11 個 disagreement → 全數轉 outvoted-agree;殘餘 uncorroborated class 是全引擎共同的 run-to-EOF 盲區(誠實記錄為 shared blindness,非我方獨有)。
4. **sec-api.io 協定**:`tools/arbitrate_secapi.py` cache-first + `--max-calls` 預算;無帳號時 no-key mode 輸出 ready-to-run state doc——**不代 user 註冊帳號**,100 lifetime calls 是 user 的決策。

## Human / PM Decision

採納。license 三檔規則(PM 既定):MIT/BSD 可 vendor 附聲明、GPL 系 subprocess 隔離或重實作、無 license 不入 repo——本案是該規則第一次實際攔下一個 vendor 計畫。sec-api 註冊留給 PM 決定,AI 只準備好協定。

## Reason

- 血統獨立是仲裁票的價值來源:regex(我方)/ style-driven(datamule)/ upstream regex(EC)/ anchor(edgartools)四條實作路線互不共享偏誤。
- 2-of-N 讓「對方 bug 扣我方分」的結構性冤枉消失,同時保留 uncorroborated disagree 的誠實扣分。
- GPL 不 vendor 是不可妥協的合規邊界;subprocess 隔離犧牲少量效能換乾淨的 license 邊界。

## Resulting Change

- `packages/sec_core/engines/edgar_crawler_vote.py`、`engines/datamule_vote.py`;`apply_triangulation` 2-of-N 擴充
- `tools/arbitrate_secapi.py` + `data/sec_eval/arbitration/`
- Commit:`4a59c13` feat(sec): P0-7 fourth-fifth-arbitration-votes
- 後續消費:4-engine head-to-head(`7aff8e2` adapters;見 `2026-07-10-ntu-f1-honest-narrative.md`)
