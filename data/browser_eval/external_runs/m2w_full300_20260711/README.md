# m2w_full300_20260711 — 官方全量 300 題(進行中,誠實 partial)

Online-Mind2Web **全量 300 題、零排除**(login/購物類照收,capability guard refuse 也是數據),任務檔 sha256 凍結於 `freeze_manifest.json`。本快照為 2026-07-11 14:05 時點:**attempted 50 / done 46 / harness_error 4 / not_run 250**——run 因 harness resume-abort 交互 bug 中斷(3 個永久 unreachable 站在每次 resume 都成為前 3 個 attempted → 30% 熔斷誤觸發),詳見 `docs/research/giants_task1.md` 300 題節。

雙口徑(46 done):verifier **21/46 = 45.7%**;WebJudge 官方協定 advisory **9/46 = 19.6%**(judge 更嚴,decided-pair 一致 64.9%;judge model 非官方 o4-mini,不可與 leaderboard 直接比)。`webjudge_results.json` 含逐題 key-points 與混淆矩陣。

快照將於 run 補完後更新。逐題 trace 在 gitignored `runs/browser_eval/m2w_full300_20260711/`。
