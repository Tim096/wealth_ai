# m2w_full300_20260711 — 官方全量 300 題(最終,無排除、雙口徑)

Online-Mind2Web **全量 300 題、零排除**(login/購物類照收,capability guard refuse 也是數據),任務檔 sha256 凍結於 `freeze_manifest.json`。本快照為 **最終 rollup**:**done 283 / harness error 17 / not_run 0**(error 全為環境:site_unreachable 17,其中 anti_bot 4)。

雙口徑(done 283):

- **verifier(唯一裁判)**:pass 95 / fail 158 / unknown 26 / refused 4 / env_blocked 0 → SR = **95/283 = 33.57%**(全分母 95/300 = 31.67%)。分層:easy 28/75 = 37.3%、medium 34/135 = 25.2%、hard 33/73 = 45.2%。來源:`webjudge_results.json → final_summary.verifier_axis_final`(逐 summary.json 重數,'refused' 獨立列出、留在分母)。
- **WebJudge 官方協定 advisory**:judged 283/283,success 21 / failure 192 / abstain 70 → SR = **21/283 = 7.42%**(abstain 留分母;全分母 21/300 = 7.0%);abstain_rate 24.73%。decided-pair 一致率 130/194 = 67.0%;最大分歧格 = verifier pass 但 WebJudge failure(56 題)。**誠實揭露**:63/70 abstain 是 judge 照抄 prompt envelope 範例字串 'success|failure'(模板 artifact,非真實不確定)→ abstain_rate 為受膨脹上界;7/70 為零證據軌跡。judge model 為 codex gateway gpt-5.5-class **非官方 o4-mini/WebJudge-7B**,不可與 leaderboard 直接比。

過程事件(measure-fix-remeasure):初跑在 3 題持久 site_unreachable 上觸發 resume-abort 死鎖(46/300 時記錄為誠實 partial)→ 根因 = `--resume` 不把先前 done 計入 attempts → fix `0613aac` → 補完至 300/300。judge 名目成本 $0.4714(實際經 codex gateway = $0)。

逐題 trace 與 per-task judge artifact 在 gitignored `runs/browser_eval/m2w_full300_20260711/`(`webjudge/per_task/*.json` 283 檔、`webjudge/judge_full_run.log`)。
