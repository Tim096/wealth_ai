# second judge live-abstain 根因追殺 — gateway wrapper unwrap

- **Session**: `3ae1f24f-695e-448f-94aa-7efb6c9d79ab`
- **日期**: 2026-07-10（原始輪次 row 879–1088)
- **Record type**: Verbatim transcript excerpt with editorial context
- **Verbatim boundary**: Only the dated `row ...` sections below `---` are verbatim. The title, metadata, summary, and cross-references are editorial scaffolding.
- **Redaction**: Secrets are replaced with explicit `[REDACTED-...]` markers; omitted tool material is marked `[...elided...]` where applicable.
- **對應重建紀錄**: `prompts/failure_triage/2026-07-10-second-judge-live-abstain-chain.md`

> open-ended scoring 明明實作了,但 live 上 second judge 18/18 全 abstain。這串節錄記錄兩層根因的追殺:HOLE A(判決路徑沒接線 + 證據餓死)先在 abstain-gap workflow 被鎖定,而真正的底層根因——codex gateway 回傳的 action-schema wrapper 沒被解開——是 verify agent 額外挖出來的;unwrap 之後 TSLA 那題才拿到 grounded pass,外部量測從 44% 收束到 61%。

---

### row 879 — assistant（abstain-gap workflow 啟動;HOLE A / HOLE B 診斷)

[tool_use: Workflow] 部分腳本節錄(diagnosis 段為原文):

```
name: 'task1-abstain-gap'
description: 'Wire open-ended scoring into verdict path + ground it on
  final-page evidence; fix runner page-bleed; targeted re-run of the 6 unknowns'

EVID = `Post bucket-fix m2w rerun (docs/research/giants_task1.md §rerun,
runs/browser_eval/m2w_rerun_20260710/): 8/18=44.4%. Two open holes:

HOLE A — open-ended scoring exists (second_judge.extract_key_points +
score_open_ended, verifier.verify_contract(open_ended_extractor=...)) but
(1) run_agentic NEVER passes open_ended_extractor at verdict time, so live
runs still blanket-unknown; (2) even when armed, the WebJudge grounding
demotion abstained 18/18 on live — key-point quotes can't ground because
the evidence store apparently lacks a final-page text snapshot to quote
from (P0-5 persisted obs excerpts exist per step; check what evidence
score_open_ended actually receives). unknown pool grew 3→6.

HOLE B — tools/run_external_eval.py has shared-page bleed: one hard
navigation failure (ERR_HTTP2) poisons the page and cascades 'interrupted
by another navigation' into subsequent tasks; the remeasure had to fall
back to a scratchpad isolated-context driver. Fix: fresh browser
context+page per task ...`
```
[...tool input elided...]

### row 889 — assistant（三線現況,兩個洞的白話版)

三線現況:

- **Task 1**:外部實測 **33% → 44.4%**(+11pt;桶2強韌比對是主功臣)。誠實記錄:桶1的開放式評分沒接進判決路徑且 live 上全棄權、桶3有一題回歸——已開聚焦 workflow 關這兩個洞(判決接線+最終頁證據接地、runner 隔離修 page-bleed),只重跑 6 題 unknown 驗證,省 token。
- **前端/效能/展示**:診斷+改造 workflow 跑著(慢的歸因、合併切換列、無 key 示範任務、OpenRouter 管線),完成會自動 redeploy。
- **部署**:兩網址活著;等你的 OpenRouter key(拿到後填 Zeabur Variables 或給我)。

兩個 workflow 檔案集不相交,可以同時跑。agent 端的改進落地後,我會在前端那波 redeploy 之後再補一次 redeploy 讓線上帶到最新機制。

### row 1081 — assistant（真根因揭露:gateway wrapper)

Task 1 abstain-gap 線收尾了。有意思:上一個 commit `49bcc6e` 顯示 verify agent 還額外找到並修了一個真根因(codex gateway 的 action-schema wrapper 沒解開),那才是 second judge live 全 abstain 的底層原因——修掉後 TSLA 那題才拿到 grounded pass。

現在把最新的 packages/browser_agent 改進(open-ended 評分、導航收斂、text_match、gateway wrapper 修復)redeploy 到線上 agent 服務,讓公開網址帶上最新機制:

### row 1088 — assistant（收束盤點)

agent 服務 redeploy 指令成功,背景等容器健康。

**現在的完整狀態盤點:**

**三線全部收斂:**
- **Task 1**:外部量測最終 **11/18 = 61%**(vs naive 20%),abstain-gap 關閉(TSLA 開放式任務 grounded pass、已抽查非幻覺),還意外修到 gateway wrapper 真根因。文件已 commit。
- **Task 2**:完整。線上 SEC 服務效能修好(重複查詢 0.6s、大 item 不再凍結)。
- **部署**:兩服務公開網址活著、前端合併、免 key 示範就緒;agent 服務正 redeploy 帶上最新機制。

**只剩你這一件(選配):** OpenRouter key —— 到 Zeabur dashboard → wealth-agent → Variables 填 4 個變數 restart,第一題就能跑任意真實任務。不填也能用示範按鈕展示。

---

### 根因鏈摘要（供對照)

| 層 | 症狀 | 根因 | 修法 | commit |
|---|---|---|---|---|
| HOLE A-1 | live 全 unknown | `run_agentic` 判決時未傳 `open_ended_extractor` | 判決路徑接線 | (abstain-gap workflow) |
| HOLE A-2 | 接線後仍 18/18 abstain | 證據 store 缺最終頁文字快照,key-point 無處接地 | final-page evidence grounding | (abstain-gap workflow) |
| **底層** | 接地後 live 仍全 abstain | **codex gateway 回傳 action-schema wrapper 未解開**,LLM 輸出被包一層 → 解析失敗 → 降級 abstain | unwrap wrapper in `second_judge` | `49bcc6e` |

驗證:TSLA 收盤價開放式任務在 unwrap 後拿到 grounded pass(引文 `Mar 17, 2023 … Close 180.13` 實際出現在頁面文本,非幻覺,已抽查)。
