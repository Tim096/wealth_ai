# Prompt Logs

依 SPEC 第 10 節:任何影響設計、程式、eval、文件、修復的 prompt 都必須記錄——不論來自使用者還是 AI 自主產生。

## 目錄

| 目錄 | 一句話定位 |
|---|---|
| `project/` | 專案層級決策:SPEC 導入、stack 選擇、commit 粒度等流程鐵律 |
| `browser_agent/` | Task 1 agent 本體的設計決策:selector 修復、planner system prompt 演進 |
| `eval_design/` | 評測體系的設計決策:eval set、對抗式稽核、外部 benchmark、mutation harness、多引擎投票 |
| `failure_triage/` | 真實失敗的診斷紀錄:根因鏈、修復、重驗(不信任表面 pass) |
| `rejected_prompts/` | 被拒絕的設計:為什麼拒、拒了之後走哪條路、事後看對不對 |
| `transcripts/` | 原始 AI 協作對話逐字摘錄(脫敏):重建決策紀錄的證據軸,補面試官指出的「缺原始對話」gap |

> `sec_extractor/` 的 boundary/adjudicator 決策目前併在 `eval_design/` 與 `failure_triage/`(SEC 尚未觸發 LLM adjudicator);待 adjudicator 實際啟用再獨立成目錄。

## 索引(依日期)

### project/

| 檔案 | 一句話 |
|---|---|
| `2026-07-10-spec-ingestion-and-foundation.md` | SPEC 導入後第一階段建什麼、用什麼 stack 的奠基決策 |
| `2026-07-10-commit-granularity-directive.md` | PM 指令:每次錯誤/嘗試/階段都獨立 commit,history 反映真實開發過程 |

### browser_agent/

| 檔案 | 一句話 |
|---|---|
| `2026-07-10-selector-repair-design.md` | selector 修復 + capability guard 的初始設計(確定性優先、LLM 是升級手段) |
| `2026-07-10-planner-system-prompt-v2.md` | planner system prompt v1→v2:實測失敗模式固化進 prompt |

### eval_design/

| 檔案 | 一句話 |
|---|---|
| `2026-07-10-real-filing-sweep.md` | 11 家公司分層真實樣本 sweep 設計 |
| `2026-07-10-adversarial-audit-workflow.md` | 56-agent 對抗式稽核:確認與證偽由不同 agent 做 |
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

### rejected_prompts/

| 檔案 | 一句話 |
|---|---|
| `2026-07-10-typescript-first-stack.md` | 拒 TS monorepo → Python-first;事後:pip 生態撐起全部關鍵能力 |
| `2026-07-10-browser-vision-model-repair.md` | 拒 vision 當修復主路徑;事後:vision 回歸為感知升級層,repair 維持零 LLM |
| `2026-07-10-sec-title-based-body-resolution.md` | 拒 title-based 正文猜測 → 誠實指標;事後:page-anchor + wrapper reassembly 補完正文 |
| `2026-07-10-broad-furniture-strip-for-f1.md` | 拒 broad duplicated-strip 刷 F1(實測雙降)→ 窄版錨點閘門 TOC-strip 落成產品特性,仍輸照寫 |

## 格式

每個檔案依 SPEC 10.2:Trigger / Scoring Criteria / Prompt / AI Output Summary / Human-PM Decision / Reason / Resulting Change。

- Prompt 原文無法逐字重現時,依 git history 與 docs 忠實重建並標注 `reconstructed from session records`。
- 命名:`YYYY-MM-DD-short-slug.md`(日期 = 實際決策日)。
