# Evidence snapshot: naive_baseline (trivial-pass reference line)

這是從 `runs/naive_baseline/`(被 `.gitignore` 的 `runs/` 規則排除,公開 clone 看不到)複製進 tracked 位置的證據快照。

- **原始路徑**:`runs/naive_baseline/results.json`
- **內容**:harness 寫出的 `results.json`(原檔逐 byte 複製,未修改)
- **數字**:trivial-pass 4/20 = **20%**(goto + first-match fill/click,無 repair/vision/planner;verifier 同真 agent)≈ 論文 22% naive-search 參考線
- **工具**:`tools/naive_baseline.py`
- **對應文件節**:`docs/supported_and_unsupported.md`(外部基準子集列)、`docs/research/giants_task1.md`(P1-1)
