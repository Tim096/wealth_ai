# m2w_heldout_20260711 — held-out 凍結子集單跑(反 overfitting 證據)

`runs/browser_eval/m2w_heldout_20260711/`(gitignored)的追蹤快照:20 題 Online-Mind2Web **與原 20 題零重疊**的新任務,選題規則確定性(見 `freeze_manifest.json`,任務檔 sha256 先凍結後開跑),**單一 launch、禁止迭代**。

結果:done 18 / harness_error 2(carmax、birkenstocks 均 site_unreachable);**pass 12 / fail 5 / unknown 1 → 66.7%**(gradable)。與迭代後合成 61.1% 並排為泛化證據,**不可混比**(單跑 vs 迭代合成)。

任務檔:`data/browser_eval/external/m2w_heldout_20260711.json`。逐題 trace 在 gitignored run dir。分析:`docs/eval_report.md`、`docs/research/giants_task1.md`。
