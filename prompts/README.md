# AI Collaboration Records

SPEC 第 10 節要求保存關鍵 AI 協作過程。這裡不是完整 chat archive，也不是每個檔案都宣稱是原始 prompt；它保存影響設計、實作、eval、修復與拒絕方案的高價值紀錄，並在每檔開頭標示 provenance。

## Provenance 類型

| 類型 | 數量 | 可以主張什麼 |
|---|---:|---|
| **Verbatim transcript excerpt** | 5 | `---` 後標明 row 的 user/assistant 文字逐字保留；秘密與過長工具內容只以明確 marker 遮蔽或截斷 |
| **Verbatim prompt artifact** | 1 | workflow 實際保存的 prompt template；不是人機對話 transcript |
| **Derived decision record** | 19 | 依 Git、code、artifacts、docs 或 session evidence 重建決策；`Prompt` 段是摘要，不是逐字引言 |

目前共 25 份紀錄。分類讓 reviewer 能分辨哪些字句可逐字核對、哪些是可由 code、artifacts 與 tests 驗證的設計紀錄。

## 目錄

| 目錄 | 一句話定位 |
|---|---|
| `project/` | 專案層級決策:SPEC 導入、stack 選擇與平台基礎 |
| `browser_agent/` | Task 1 agent 本體的設計決策:selector 修復、planner system prompt 演進 |
| `eval_design/` | 評測體系的設計決策:eval set、對抗式稽核、外部 benchmark、mutation harness、多引擎投票 |
| `failure_triage/` | 真實失敗的診斷紀錄:根因鏈、修復、重驗(不信任表面 pass) |
| `rejected_prompts/` | 被拒絕的設計:為什麼拒、拒了之後走哪條路、事後看對不對 |
| `transcripts/` | 5 份已脫敏的原始 AI 協作對話摘錄；verbatim body 由 provenance manifest 與 verifier 固定 |

> `sec_extractor/` 的 boundary/adjudicator 決策目前併在 `eval_design/` 與 `failure_triage/`(SEC 尚未觸發 LLM adjudicator);待 adjudicator 實際啟用再獨立成目錄。

## 索引(依日期)

### project/

| 檔案 | 一句話 |
|---|---|
| `2026-07-10-spec-ingestion-and-foundation.md` | SPEC 導入後第一階段建什麼、用什麼 stack 的奠基決策 |

### browser_agent/

| 檔案 | 一句話 |
|---|---|
| `2026-07-10-selector-repair-design.md` | selector 修復 + capability guard 的初始設計(確定性優先、LLM 是升級手段) |
| `2026-07-10-planner-system-prompt-v2.md` | planner system prompt v1→v2:實測失敗模式固化進 prompt |

### eval_design/

| 檔案 | 一句話 |
|---|---|
| `2026-07-10-real-filing-sweep.md` | 11 家公司分層真實樣本 sweep 設計 |
| `2026-07-10-adversarial-audit-workflow.md` | 對抗式稽核設計:11-company accession evidence、獨立 verifier 與 regression tests |
| `2026-07-10-xbrl-and-cross-ref.md` | cross-reference-index 處理 + XBRL 當獨立驗證基材 |
| `2026-07-10-reviewer-prompts-verbatim.md` | reviewer/auditor agent prompt 逐字保存(SPEC 10.1) |
| `2026-07-10-eval-upgrade-todo-from-web-research.md` | 兩個研究 agent 網查後的 11 項 eval 升級波(invariant + 校準裁判本身) |
| `2026-07-10-verifier-mutation-harness.md` | P0-4:對 runtime 驗證層注入六類腐蝕,recall/false-alarm 門檻用 assert 鎖死 |
| `2026-07-10-five-engine-2of-n-voting.md` | P0-7:第四/五仲裁票 + 2-of-N 投票;GPL 擋下 vendor 改 subprocess 隔離 |
| `2026-07-10-prompt-injection-adversarial-suite.md` | P1-14:注入對抗頁套件 + instruction/content separation,metric 以服從式 agent 自證 ASR=1.0 |
| `2026-07-10-ntu-f1-honest-narrative.md` | NTU head-to-head 終判:F1 輸 edgar_crawler 0.0087 照寫,敘事轉唯一可自我審計的驗證軸 |

### failure_triage/

| 檔案 | 一句話 |
|---|---|
| `2026-07-10-jpm-cross-ref-stub.md` | JPM Item 11 51 字元標 pass 的誤判診斷 → incorporated_by_reference 分類誕生 |
| `2026-07-10-browser-decoy-and-modal.md` | decoy button + cookie modal 導致修復選錯元素的 triage |
| `2026-07-10-second-judge-live-abstain-chain.md` | second judge live 18/18 abstain 的兩層根因(HOLE A 接線+證據餓死、gateway wrapper)與定向重驗 |
| `2026-07-11-official300-resume-abort-deadlock.md` | 官方全量 300 題死鎖:resume 不計 n_attempted 使 3 個死站永觸 abort;chunk agent 依鐵律 escalate、修 harness 不修題 |

### rejected_prompts/

| 檔案 | 一句話 |
|---|---|
| `2026-07-10-typescript-first-stack.md` | 拒 TS monorepo → Python-first;事後:pip 生態撐起全部關鍵能力 |
| `2026-07-10-browser-vision-model-repair.md` | 拒 vision 當修復主路徑;事後:vision 回歸為感知升級層,repair 維持零 LLM |
| `2026-07-10-sec-title-based-body-resolution.md` | 拒 title-based 正文猜測 → 誠實指標;事後:page-anchor + wrapper reassembly 補完正文 |
| `2026-07-10-broad-furniture-strip-for-f1.md` | 拒 broad duplicated-strip 刷 F1(實測雙降)→ 窄版錨點閘門 TOC-strip 落成產品特性,仍輸照寫 |

### transcripts/

| 檔案 | 一句話 |
|---|---|
| `2026-07-10-verifier-paradox.md` | verifier 不可能完美時，如何用不變量、棄權、交叉分歧與錯誤注入建立退出條件 |
| `2026-07-10-ntu-f1-honest-narrative.md` | 外部 F1 輸給 edgar_crawler 後，如何裁決相反診斷並停止追分 |
| `2026-07-10-second-judge-abstain-wrapper.md` | live second judge 全 abstain 的兩層根因與 gateway wrapper 修復 |
| `2026-07-11-heldout-freeze-protocol.md` | held-out 任務先凍結、後執行的原始協作過程 |
| `2026-07-11-official-300-resume-abort-deadlock.md` | 官方 300 題 run 被 resume/abort deadlock 卡住後的診斷、escalation 與修復 |

## 格式

Derived records 依 SPEC 10.2 使用 Trigger / Scoring Criteria / Prompt summary / AI Output Summary / Decision / Reason / Resulting Change；verbatim excerpts 保留原本輪次結構。

- 每檔先標 `Record type`。未標 verbatim 的 `Prompt` 段一律視為重建摘要，不是原始對話。
- Verbatim transcript 中只有 `---` 後標明 row 的段落屬逐字內容；檔名、標題、metadata 與開場摘要是 editorial context。
- 無法逐字重現時，不補寫 user/assistant 對話；改以 Git、code、artifact、doc 或 session evidence 重建 decision record。
- 命名:`YYYY-MM-DD-short-slug.md`。日期是整理時採用的事件標籤，不是 chronology proof；時序應以可解析 Git objects、artifacts 或 verbatim row metadata 交叉驗證。
