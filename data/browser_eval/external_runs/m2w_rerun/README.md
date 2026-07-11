# Evidence snapshot: m2w_rerun (baseline live run, 2026-07-10)

這是從 `runs/browser_eval/m2w_rerun/`(被 `.gitignore` 的 `runs/` 規則排除,公開 clone 看不到)複製進 tracked 位置的證據快照。

- **原始路徑**:`runs/browser_eval/m2w_rerun/`
- **內容**:20 個 `m2w-*/summary.json`(harness 逐題原子寫入的原始檔,未修改)+ `results.json`
- **results.json 注意**:此 run 的 harness 未寫出最終 results.json(run 中斷於彙總前)。這裡的 `results.json` 是用 `tools/aggregate_run.py` 從 20 個 summary.json **事後彙總**產生,檔內標注 `aggregated_post_hoc: true`,時間來源為各 summary.json 的 `written_at`(2026-07-10T09:00–09:25 UTC)。
- **彙總數字**:pass 6 / done 18 = **33.3%**(error 2 = site_unreachable,排除於分母)
- **對應文件節**:`docs/research/giants_task1.md`(P1-1 baseline 表格,"6/18 = 33.3%")、`docs/eval_report.md`(baseline 列)、`docs/supported_and_unsupported.md`(外部基準子集列)
- **任務集**:`data/browser_eval/external/mind2web_subset.json`
