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

verbatim 摘錄凍結於節錄當下:內文引用的 commit hash、量測數字以當時原文為準,不隨後續文件更新改寫(對應的現行值一律以重建紀錄與 `docs/` 為準)。

## 索引

| 檔案 | 一句話 |
|---|---|
| `2026-07-10-verifier-paradox.md` | 專案哲學起點:使用者提「裁判要完美才能驗產品」悖論,AI 拆成不變量/棄權/交叉分歧/錯誤注入四出口 + 回歸終止 |
| `2026-07-11-heldout-freeze-protocol.md` | held-out 新 20 題凍結協議(pre-registered + sha256 先凍後跑 + 禁迭代),66.7% 反 overfitting 證據 |

## 整併紀錄(2026-07-13)

原有 5 份摘錄中,3 份與既有重建紀錄高度重疊;為避免同一事件兩份敘事,已將其獨有內容併入對應重建紀錄後移除,原文完整保留於 git history(`git log --follow prompts/transcripts/<檔名>`):

| 原摘錄 | 獨有內容併入 |
|---|---|
| `2026-07-10-ntu-f1-honest-narrative.md` | `prompts/eval_design/2026-07-10-ntu-f1-honest-narrative.md`(315-char span fp=100 的 agent 矛盾裁決證據、誠信與求勝的分寸線) |
| `2026-07-10-second-judge-abstain-wrapper.md` | `prompts/failure_triage/2026-07-10-second-judge-live-abstain-chain.md`(根因鏈摘要表、wrapper 根因由獨立 verify agent 挖出) |
| `2026-07-11-official-300-resume-abort-deadlock.md` | `prompts/failure_triage/2026-07-11-official300-resume-abort-deadlock.md`(改寫為完整決策紀錄) |

保留的 2 份是原始性價值最高的:verifier-paradox 是專案哲學的起點對話(重建無法替代的思辨過程),heldout-freeze-protocol 是反 overfitting 協議「先凍結、後量測」順序的原始佐證。

## 節錄原則

- **不虛構、不改寫**:user/assistant 輪次保留原文(繁中/英混雜照原樣)。
- **節錄標明**:每檔頭部標 session id、日期、原始輪次範圍,並聲明 `verbatim excerpt, secrets redacted`。
- **工具輸出截斷**:過長的 tool_use 腳本 / tool_result 以 `[...tool input elided...]` / `[...tool output elided...]` 標記截斷,不影響敘事的原文段落保留完整。
- **總量**:2 檔共 ~12 KB(< 300 KB 上限)。

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

## 自查結果(2026-07-13 整併後複掃)

用上述 pattern 對 `prompts/transcripts/*.md` 全量再掃一輪:

```
=== TOTAL HITS: 0 ===
files scanned: 2   total ~12.0 KB
```

另用具體秘密字串(各 key 前綴、部署密碼、email local part)獨立 grep 複查:**0 個真實秘密**。
