# 官方全量 300 題 resume-abort 死鎖:harness resume 語意修復

## Trigger

官方 Online-Mind2Web 全量 300 題(無排除、任務檔凍結 sha256)跑到 done=46 即死鎖:`--resume --limit 300` 兩次 launch 皆立即 abort(exit 2),確定性重現。chunk agent 依「不改 code、不介入個別失敗」鐵律停止並 escalate,未自行 hack。

## Scoring Criteria

- 失敗處理:死鎖要診斷出機制,不靠重試矇混
- 評估紀律:凍結任務檔不得改動;修 harness 不修題
- 誠實邊界:永久壞站照跑照記 error,不排除、不粉飾

## Prompt(reconstructed from session records)

chunk agent 回報死鎖後,orchestrator 決策指令:

> 這是 harness 的 resume 語意 bug(前次已 attempted 的 error 不該重新計為本次頭三筆),修 harness 後續跑;3 個永久壞站每次重試、逾時、記 error 是預期行為,不要介入。

## AI Output Summary

死鎖機制(chunk agent 逐層診斷):任務檔序 idx 5/18/26(carmax medium、united hard、carmax hard)為持久性 `site_unreachable`(curl 實測 http_code=000,非暫時性);resume 復用 done rows 時**不計入 `n_attempted`**,故每次 relaunch 的前 3 個 attempted 必為這 3 題 → `should_abort(3,3)`(ERROR_ABORT_MIN=3、RATE=0.30)必觸發,永遠跑不到第 4 題。

修復(`548bd6d`):resumed done row 計入 `n_attempted`——它是本次 run 的一次成功 attempt;guard 對新鮮錯誤仍有效(真壞環境照樣熔斷),chunked resume 得以推進。兩條 serial harness 同步修;worker-pool 路徑上游已預濾 resumed tasks,不動。

連帶修復(CI order-dependent flake,`51ab5f0`):CI run 29142969480 揭露 pool guard「3 題 1 錯」是否熔斷取決於錯誤第幾個到帳——`should_abort(1,3)`=33%>30% 只在錯誤最後到帳時觸發,本機快跑一直過、CI 慢跑才炸。guard docstring 本來就承諾單一早期錯誤不殺 run;改 `n_error >= 2` 使承諾 order-independent,新增 (1,3) 邊界斷言。

續跑設計(wave-4b):累積式 `--limit`(100→150→…→300)+ 同一 `--out --resume`,3 個死站每輪照重試照記 error。最終 300 題全量完成,雙口徑(runtime verifier + WebJudge advisory)落 `docs/eval_report.md`。

## Human / PM Decision

PM 授權 wave-4 全量跑(官方口徑、不做任何排除);死鎖處置由 AI 自主決策——chunk agent 依鐵律 escalate、orchestrator 判定為 harness bug 並修復,PM 未介入個案。

## Reason

- chunk agent「不改 code、誠實停下」與 orchestrator「修 harness 不修題」的分工,是凍結協議下唯一不污染評測的解法:題目、成功條件、任務檔 sha256 全程不動。
- resumed done 計入 attempts 在語意上正確(guard 量測的是本次 run 的失敗密度),不是為續跑放水——新鮮錯誤照樣熔斷。
- CI flake 修復消除 order-dependence,讓 guard 行為與 docstring 承諾一致。

## Resulting Change

- `tools/run_external_eval.py` resume 計數(含 browser_eval.py script pass),commit `548bd6d`
- `tools/eval_worker.py` guard `n_error >= 2` + (1,3) 邊界斷言,commit `51ab5f0`
- Artifacts:`data/browser_eval/external_runs/m2w_full300_20260711/`;最終雙口徑見 `docs/eval_report.md`「Browser 300 題官方全量」節
