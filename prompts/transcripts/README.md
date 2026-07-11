# transcripts/ — 原始 AI 協作對話摘錄(脫敏)

本目錄補上 `prompts/` 其他目錄缺的一塊:**原始對話證據**。使用者已明確授權把 `~/.claude` 的 session transcripts 脫敏後節錄進來。

## 重建決策紀錄 vs 原始摘錄(兩者關係)

| | `prompts/{project,browser_agent,eval_design,failure_triage,rejected_prompts}/` | `prompts/transcripts/`(本目錄) |
|---|---|---|
| 性質 | **重建**的決策紀錄 | **原始**對話逐字摘錄 |
| 來源 | 依 git history + docs 忠實重建,標 `reconstructed from session records` | 直接節錄 `~/.claude/projects/E--Side-Project-wealth/*.jsonl` 的 user/assistant 原文 |
| 格式 | SPEC 10.2 結構化欄位(Trigger / Scoring / Prompt / Decision / Reason / Change) | 保留原輪次、時間戳、原文 |
| 用途 | 讓面試官快速讀懂「為什麼這樣設計」 | 讓面試官核對「重建是否忠於原對話」——證據軸 |

面試官指出的 gap:重建紀錄雖完整,但缺原始對話當佐證。本目錄即為此補證。兩者互補——重建紀錄給結論與脈絡,原始摘錄給不可否認的證據。

## 索引

| 檔案 | 一句話 |
|---|---|
| `2026-07-10-verifier-paradox.md` | 專案哲學起點:使用者提「裁判要完美才能驗產品」悖論,AI 拆成不變量/棄權/交叉分歧/錯誤注入四出口 + 回歸終止 |
| `2026-07-10-ntu-f1-honest-narrative.md` | NTU benchmark 上 vendored edgar_crawler raw F1 贏我們,AI 拒絕掩蓋、裁決 agent 矛盾、收束成「唯一自我審計系統」敘事 |
| `2026-07-10-second-judge-abstain-wrapper.md` | second judge live 全 abstain 的兩層根因追殺;真根因是 codex gateway action-schema wrapper 未解開 |
| `2026-07-11-heldout-freeze-protocol.md` | held-out 新 20 題凍結協議(pre-registered + sha256 先凍後跑 + 禁迭代),66.7% 反 overfitting 證據 |
| `2026-07-11-official-300-resume-abort-deadlock.md` | 官方全量 300 題跑到 50 題死鎖,resume 不計 n_attempted 使 3 個死站永觸 abort;誠實診斷 → 修 harness → 續跑 |

## 節錄原則

- **不虛構、不改寫**:user/assistant 輪次保留原文(繁中/英混雜照原樣)。
- **節錄標明**:每檔頭部標 session id、日期、原始輪次範圍,並聲明 `verbatim excerpt, secrets redacted`。
- **工具輸出截斷**:過長的 tool_use 腳本 / tool_result 以 `[...tool input elided...]` / `[...tool output elided...]` 標記截斷,不影響敘事的原文段落保留完整。
- **總量**:5 檔共 ~32 KB(< 300 KB 上限)。

## 脫敏方法

寫入前每段文字都過以下 pattern 掃描與替換(替換為 `[REDACTED-<type>]`):

| 類別 | Pattern | 替換 |
|---|---|---|
| OpenRouter key | `sk-or-v1-[A-Za-z0-9]+` | `[REDACTED-openrouter-key]` |
| 通用 API key | `sk-[A-Za-z0-9-]{20,}` | `[REDACTED-api-key]` |
| GitHub token | `ghp_[A-Za-z0-9]+` | `[REDACTED-github-token]` |
| Bearer token | `Bearer [^\s]+` | `Bearer [REDACTED-token]` |
| 敏感 key=value | `(OPENAI_API_KEY\|PASSWORD\|ACCESS_TOKEN\|...)=值` | `<key>=[REDACTED-secret]` |
| Zeabur 密碼 | `8CBn2[A-Za-z0-9]+` | `[REDACTED-zeabur-password]` |
| Email local part | `[...]@gs.ncku.edu.tw` | `[REDACTED-email]@gs.ncku.edu.tw` |
| 40+ 高熵字串 | `\b[A-Za-z0-9+/_-]{40,}\b`(需 upper+lower+digit 混合) | `[REDACTED-highentropy]` |

**必查的具體秘密**(已確認遮蔽):
- 2026-07-11 session `6fd60c6f` row 609 使用者貼出的 OpenRouter key(`sk-or-v1-` 前綴那把)→ 已遮蔽為 `[REDACTED-openrouter-key]`。
- Zeabur PASSWORD(`8CBn2…` 開頭)→ 本目錄選錄的片段未觸及,pattern 已備。
- 一處 `$env:OPENAI_API_KEY='…'` 佔位值 → 遮蔽為 `[REDACTED-secret]`。

高熵規則刻意要求 upper+lower+digit 混合,避免誤傷 SHA 雜湊、commit UUID 與 session id(如 `6fd60c6f-...` 全小寫+數字,非秘密,保留)。

## 自查結果(寫入後複掃整個目錄)

用上述 pattern 對 `prompts/transcripts/*.md` 全量再掃一輪:

```
=== TOTAL HITS: 0 ===
files scanned: 5   total 32.2 KB
```

另用具體秘密字串(OpenRouter `sk-or-v1-` 前綴、Zeabur `8CBn2` 前綴、email local part、`ghp_`、金鑰起頭 hex)獨立 grep 複查:**0 個真實秘密**(唯一匹配為 `OPENAI_API_KEY='[REDACTED-secret]'` 佔位符本身)。
