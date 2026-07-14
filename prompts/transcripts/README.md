# transcripts/ — 原始 AI 協作對話摘錄（脫敏）

本目錄保存 5 份從原始 session transcript 擷取並脫敏的片段。這些摘錄不是完整 session；每份檔案以 `---` 明確標示 verbatim boundary，正文 hash 記錄於 `prompts/provenance_manifest.json`。

## 設計紀錄 vs 原始摘錄

| | `prompts/{project,browser_agent,eval_design,failure_triage,rejected_prompts}/` | `prompts/transcripts/`(本目錄) |
|---|---|---|
| 性質 | **Derived decision record** | **Verbatim transcript excerpt** |
| 來源 | 依 Git、code、artifacts、docs 或 session evidence 整理 | 從 session transcript 擷取並脫敏的 user/assistant 原文 |
| 格式 | SPEC 10.2 結構化欄位(Trigger / Scoring / Prompt / Decision / Reason / Change) | 保留原輪次、時間戳、原文 |
| 用途 | 讓面試官快速讀懂「為什麼這樣設計」 | 讓面試官核對「重建是否忠於原對話」——證據軸 |

兩者用途不同：derived record 讓 reviewer 快速理解決策，verbatim excerpt 讓 reviewer 檢查當時的語氣、分歧與修正過程。不得拿 derived record 冒充原始對話。

每份 transcript 中，只有 `---` 後標明 `row ...` 的區段屬 verbatim。標題、metadata、開場摘要與 cross-reference 是後加的 editorial context。摘錄凍結於節錄當下；內文的 commit hash 與量測數字不隨後續文件更新。

## 索引

| 檔案 | 一句話 |
|---|---|
| `2026-07-10-verifier-paradox.md` | 專案哲學起點:使用者提「裁判要完美才能驗產品」悖論,AI 拆成不變量/棄權/交叉分歧/錯誤注入四出口 + 回歸終止 |
| `2026-07-10-ntu-f1-honest-narrative.md` | 外部 F1 輸給 vendored engine 後，AI 如何承認結果、裁決相反診斷並停止追分 |
| `2026-07-10-second-judge-abstain-wrapper.md` | second judge live 全 abstain 的 wiring、evidence starvation 與 gateway wrapper 根因鏈 |
| `2026-07-11-heldout-freeze-protocol.md` | held-out 新 20 題凍結協議(pre-registered + sha256 先凍後跑 + 禁迭代),66.7% 反 overfitting 證據 |
| `2026-07-11-official-300-resume-abort-deadlock.md` | 官方全量 run 卡在 resume/abort deadlock 時，chunk agent 的停止、escalation 與 harness 修復 |

## 節錄原則

- **不虛構、不改寫**:user/assistant 輪次保留原文(繁中/英混雜照原樣)。
- **節錄標明**:每檔頭部標 session id、日期、原始輪次範圍與 verbatim boundary。
- **工具輸出截斷**:過長的 tool_use 腳本 / tool_result 以 `[...tool input elided...]` / `[...tool output elided...]` 標記截斷,不影響敘事的原文段落保留完整。
- **總量**:5 檔共約 33.4 KB(< 300 KB 上限)。

## 脫敏方法

寫入前每段文字都過以下 pattern 掃描與替換(替換為 `[REDACTED-<type>]`):

| 類別 | Pattern | 替換 |
|---|---|---|
| OpenRouter key | `sk-or-v1-[A-Za-z0-9]+` | `[REDACTED-openrouter-key]` |
| 通用 API key | `sk-[A-Za-z0-9-]{20,}` | `[REDACTED-api-key]` |
| GitHub token | `ghp_[A-Za-z0-9]+` | `[REDACTED-github-token]` |
| Bearer token | `Bearer [^\s]+` | `Bearer [REDACTED-token]` |
| 敏感 key=value | `(OPENAI_API_KEY\|PASSWORD\|ACCESS_TOKEN\|...)=值` | `<key>=[REDACTED-secret]` |
| 部署密碼 | 已知密碼字面值(具體前綴不記載於本文件) | `[REDACTED-zeabur-password]` |
| Email local part | `[...]@gs.ncku.edu.tw` | `[REDACTED-email]@gs.ncku.edu.tw` |
| 40+ 高熵字串 | `\b[A-Za-z0-9+/_-]{40,}\b`(需 upper+lower+digit 混合) | `[REDACTED-highentropy]` |

session 中曾出現的具體秘密(OpenRouter key、Zeabur 服務密碼、`OPENAI_API_KEY` 佔位值)均已確認遮蔽或未被選錄;其字面值與前綴一律不記載於本文件。

高熵規則刻意要求 upper+lower+digit 混合,避免誤傷 SHA 雜湊、commit UUID 與 session id(全小寫+數字,非秘密,保留)。

## 自查結果（2026-07-14）

用上述 pattern 對 `prompts/transcripts/*.md` 全量再掃一輪:

```
candidate hits: 1
confirmed secrets: 0
files scanned: 5   total ~33.4 KB
```

唯一 candidate 是 `data/browser_eval/external_runs/m2w_full300_20260711/README`：它因含大小寫、數字、slash 且超過 40 字元而觸發 high-entropy heuristic，人工判定為 repository path。其他 API-key、GitHub-token、Bearer、secret-assignment 與 NCKU email patterns 為 0 hits，因此確認為 **0 個真實秘密**。
