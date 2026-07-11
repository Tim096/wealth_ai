# 官方全量 300 題 — resume-abort 死鎖的誠實處置

- **Session**: `6fd60c6f-4f09-4322-8120-604e8a5a60bf`
- **日期**: 2026-07-11（原始輪次 row 609–948)
- **性質**: verbatim excerpt, secrets redacted（原文逐字節錄,秘密已遮蔽;過長的 workflow 腳本與 task-notification 以 `[...tool output elided...]` / `[...tool input elided...]` 截斷)
- **對應重建紀錄**: `docs/eval_report.md`（300 題官方全量節)、`data/browser_eval/external_runs/m2w_full300_20260711/README.md`

> 官方 Online-Mind2Web 全量 300 題(無排除)跑到第 50 題就死鎖。根因:3 個永久連不上的站(carmax×2、united)在 `--resume` 後,因 resumed done rows 不計入 `n_attempted`,永遠是每次 launch 的「前 3 個 attempted」→ `should_abort(3,3)` 每次必觸發,第 4 題永遠跑不到。chunk agent 依鐵律不改 code、誠實停下 escalate;orchestrator 判定這是 harness 的 resume 語意 bug 並修復。此檔完整呈現:授權 → 死鎖診斷 → 根因 → 修法 → 續跑 → 連帶的 CI flake 修復。

---

### row 609 — user（授權 wave-4;OpenRouter key 已遮蔽)

```
1 and 2 都要做 然後候選也都要做 不要再問我
[REDACTED-openrouter-key] (use x-ai/grok-4.5)
```

> 使用者在此貼出真實 OpenRouter key 授權 wealth-agent 走真實 LLM。原始明文金鑰已於入庫前脫敏為 `[REDACTED-openrouter-key]`。

### row 640 — assistant（wave-4 workflow 啟動,節錄)

[tool_use: Workflow]

```
name: 'wave4-full-bench'
description: 'Wave 4: full official Online-Mind2Web 300-task benchmark +
  WebJudge advisory scoring + AI-collab transcripts (redacted) + AUROC
  content-axis signal'

任務:準備官方 Online-Mind2Web **全量 300 題**任務檔——這次是官方口徑,
**不做任何排除**(login/購物類照收;我方 capability guard 遇到會誠實 refuse,
那就是結果的一部分)。
```
[...tool input elided...]

### row 790 — user（wave-4 完成通知;死鎖診斷為 chunk agent 原文回報,節錄自 `lastChunk.notes`)

```
Chunk 6 無法推進:--resume --limit 300 兩次 launch 皆立即 abort(exit 2),
死鎖確定性重現。機制:run dir 目前 done=46/error=4(共 50 份 summary,
not_run=250,遠低於前 5 chunks 應累積的 ~240);檔案順序 idx 5
(m2w-92a3d4236f16, carmax medium)、idx 18 (m2w-bfa2de159be6, united hard)、
idx 26 (m2w-0b51b4fa0295, carmax hard) 為持久性 site_unreachable error;
resume 復用 done 不計 n_attempted,故每次 launch 首 3 個 attempted 必為這 3 題
→ should_abort(3,3) 觸發(tools/eval_worker.py:45-46 ERROR_ABORT_MIN=3,
RATE=0.30),n_attempted 永遠到不了第 4 題。實測 https://www.carmax.com/ 與
https://www.united.com/ 本機 curl 皆 timeout(http_code=000),非暫時性。
run_external_eval.py 無 CLI 參數可調 abort 門檻或跳過 error 題;依鐵律不修
code、不介入個別失敗,故停止並回報。... 解鎖需 orchestrator 決策之一:
(a) 提高/參數化 ERROR_ABORT_MIN 或 RATE;(b) resume 時將持久 error 題列入
可跳過;(c) 將 3 題標 status!=active 於任務檔(但檔已凍結 sha256)。gateway 全程 200。
```
[...tool output elided:雙口徑 verifier/WebJudge partial 數字、confusion matrix、license 見 webjudge_results.json...]

### row 793 — assistant（決策:這是 harness resume 語意 bug)

Wave-4 結果:AUROC 內容軸**首次打下攔截 gate(65.3% PASS)**;WebJudge 官方協定落地(MIT,雙口徑);但 **300 題只跑了 50 題就死鎖**——3 個永久連不上的站(carmax×2、united)在 resume 後永遠是「本次前 3 個 attempted」→ 30% abort 熔斷必觸發。chunk agent 依鐵律不改 code、誠實停下來 escalate。我來決策:這是 harness 的 resume 語意 bug(前次已 attempted 的 error 不該重新計為本次頭三筆),修 harness 後續跑。先讀 verify findings。

### row 853 — assistant（修法:resumed done row 計入 n_attempted)

[tool_use: Edit] `tools/run_external_eval.py`,新增(原文):

```python
                if resume:
                    prior = load_done_summary(entry["task_id"], out_root=run_dir)
                    if prior:
                        row = prior["row"]
                        row["harness_status"] = "done"
                        row["resumed"] = True
                        rows.append(row)
                        # A resumed done row is a successful attempt of this run:
                        # without this, tasks with persistent env errors become the
                        # first N attempts of every relaunch and the abort guard
                        # deadlocks the run (observed: 3 unreachable sites froze the
                        # full-300 sweep at 46 done).
                        n_attempted += 1
                        continue
```

### row 879 — assistant（commit message,原文)

```
fix(eval): resume counts prior done rows as attempts -- unfreezes abort-guard deadlock on persistent-error tasks

Root cause of the full-300 freeze at 46 done: resumed done tasks were
skipped without incrementing n_attempted, so 3 permanently unreachable
sites (carmax x2, united -- curl-verified dead) were always the first 3
attempts of every relaunch and should_abort(3,3) tripped before any new
task could run. A resumed done row is a successful attempt of this run;
counting it keeps the guard meaningful (a genuinely broken environment
still trips on fresh errors) while letting chunked resumes make
progress. Applied to both serial harnesses (run_external_eval.py,
browser_eval.py script pass); the worker-pool path prefilters resumed
tasks upstream and is unchanged. pytest 788 passed.

Claude-Session: 6fd60c6f-4f09-4322-8120-604e8a5a60bf
```

### row 883 — assistant（wave-4b 續跑 300 題,節錄)

[tool_use: Workflow]

```
name: 'wave4b-finish-300'
description: 'Finish the official 300-task run after the resume-abort fix,
  extend WebJudge coverage, land final dual-axis numbers, verify'

背景:full-300 run 先前因 resume-abort 死鎖停在 done=46;commit 0613aac 已修
(resumed done 計入 n_attempted),你的 launch 不會再因 3 個永久壞站
(carmax×2、united)熔斷——它們每次會被重試、逾時、記 error,這是預期行為,
不要介入。
LIMITS = [100, 150, 200, 250, 300, 300]  // 累積式 --limit + 同一 --out --resume
```
[...tool input elided...]

### row 943 — assistant（連帶修復:單一 error 永不熔斷,消除 CI order-dependent flake)

[tool_use: PowerShell] commit message(原文):

```
fix(eval): single harness error can never trip the abort guard -- kills order-dependent CI flake

CI run 29142969480 failed test_pool_captures_worker_task_error_without_
killing: with 3 tasks and 1 intentional error, should_abort(1,3) = 33%
> 30% tripped ONLY when the error was accounted third -- result-arrival
order decided the verdict (fast local runs accounted it first and
passed; the slow CI runner accounted it last and aborted). The guard
docstring already promised a single early error cannot kill the run;
n_error >= 2 makes that promise order-independent. All existing
threshold assertions unchanged and still pass; new (1,3) assertion
locks the boundary. pytest 788 passed.

Claude-Session: 6fd60c6f-4f09-4322-8120-604e8a5a60bf
```

### row 948 — assistant（狀態更新)

狀態更新:

- **CI 紅→綠**:上一輪 CI 失敗不是 wave-4 改壞,是**既有競態 flaky test**——pool guard「1 個錯誤 / 3 題」是否熔斷取決於錯誤第幾個到帳(本機快所以一直過,CI 慢跑才炸)。已修語意:單一錯誤永不熔斷(`n_error >= 2`,guard docstring 本來就承諾這件事),新增邊界斷言,788 tests 全綠,CI 復綠(run 29143148577)。
- **Wave-4b 執行中**(預估 ~5 小時):harness resume 死鎖修復後續跑 300 題官方全量(46→300)、WebJudge 續評、最終雙口徑落文件、對抗驗證。完成後我 commit+push。
- **已 push**:topic prior(攔截 gate 首次 PASS 65.3%)、WebJudge 工具 + MIT attribution、300 題凍結任務檔與 partial 證據快照、兩個 harness 修復。

Transcript 入庫仍等你指名(一句「把 ~/.claude 的 session transcripts 脫敏後節錄進 repo 的 prompts/transcripts/」)。
