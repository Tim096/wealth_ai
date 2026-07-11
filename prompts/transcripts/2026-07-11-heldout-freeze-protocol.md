# Held-out 凍結協議 — 反 overfitting 的最強證據

- **Session**: `6fd60c6f-4f09-4322-8120-604e8a5a60bf`
- **日期**: 2026-07-11（原始輪次 row 410–592)
- **性質**: verbatim excerpt, secrets redacted（原文逐字節錄,秘密已遮蔽;過長的 workflow 腳本以 `[...tool input elided...]` 截斷)
- **對應重建紀錄**: `docs/eval_report.md`（held-out 節)、`docs/research/giants_task1.md`、記憶 `codex-interviewer-grade-and-gaps`

> 面試官給 Task 1 評測可信度 6.5(最弱維度)。回應是打「held-out 新 20 題」:與迭代過的原 20 題零重疊、選題規則 pre-registered、sha256 先凍結後開跑、禁止看結果後迭代。結果 66.7% 高於迭代後的 61.1%——這是「沒有 overfit 到自建題」的最強證據。凍結協議(freeze-before-run + 確定性選題規則)是這串節錄的核心。

---

### row 410 — assistant（決策:開 wave-3 打最弱維度)

收到,自行判斷。決策:① 先 push 三個 post-tag commits(push 授權已成立,tag 樹已公開);② 嘗試 redeploy wealth-sec 帶上 dashboard 10/1;③ 開下一波打面試官最弱維度「Task 1 評測可信度 6.5」——核心是**held-out 新 20 題**(反 overfitting 的最強證據)+ 元件 ablation,Task 2 線做 GS/JPM wrapper span 收斂(CYD 官方 offsets 已在手)。

### row 433 — assistant（wave-3 workflow;held-out 凍結規則為原文)

[tool_use: Workflow] 部分腳本節錄(held-out agent 指令為原文):

```
name: 'wave3-credibility'
description: 'Wave 3: held-out fresh M2W 20-task run (anti-overfitting
  evidence) + component ablation + SEC wrapper span resolution vs CYD oracle'

你擁有:data/browser_eval/external_tasks*(新增 task 檔,勿改既有 20 題定義)、
runs/browser_eval/m2w_heldout_20260711/**(新 run dir)。禁改 docs。
任務:Online-Mind2Web **held-out 新 20 題**單跑——這是反 overfitting 的證據,
規則絕對:選題凍結後跑一次,結果原樣回報,禁止看結果後修 agent/verifier 再重跑。
步驟:
1. 讀 tools/import_mind2web.py ... 取得既有 task_id 清單。
2. 匯入 20 題**不重疊**的新題(官方 schema 欄位保留;難度分佈盡量貼近官方
   easy/medium/hard 比例;選題規則寫下來:確定性規則如「排除既有後按 dataset
   順序取前 20」,不得挑軟柿子)。凍結:先把任務檔與選題規則寫進 run dir 的
   manifest,再開跑。
3. 前景跑 tools/run_external_eval.py --tasks <新任務檔>
   --out runs/browser_eval/m2w_heldout_20260711(gateway 模式;second judge
   武裝:先設 $env:OPENAI_API_KEY='[REDACTED-secret]'; ...);單一 launch;
   逾時/env-error 照 harness 分類,不重跑已 done 的題(中斷才可 --resume)。
4. 回報:pass/fail/unknown/env_blocked 分佈、可評分成功率、... 與「迭代過的原
   20 題 61.1% 合成值」並排時必須標明本組是 held-out 單跑不可迭代。
```
[...tool input elided...]

### row 473 — assistant（wave-3 完成)

Wave-3 全部完成(7 agents,0 錯誤)。重點:held-out 新 20 題單跑 **66.7%**(高於迭代後的 61.1%——反 overfitting 最強證據)、ablation 證明 verifier 是最大差異元件(self-report 判準 10 個 false success)、CYD oracle 修到 **11/0**。讀完整輸出拿 verify findings,再決定 commit。

### row 566 — assistant（held-out commit message,原文;pre-registered + sha256 凍結)

[tool_use: PowerShell] commit message(原文):

```
data(eval): held-out frozen M2W 20-task single run -- 12/18 = 66.7% gradable

Anti-overfitting evidence: 20 fresh Online-Mind2Web tasks, zero overlap
with the iterated original 20, deterministic pre-registered selection
(same candidate universe + filters, official level distribution 5/10/5,
first-N by source_task_id, per-domain cap 2) frozen by sha256 in
freeze_manifest.json BEFORE the run. Single launch, no iteration, no
rerun of done tasks. Result: done 18 (2 site_unreachable env errors),
pass 12 / fail 5 / unknown 1 -> 66.7%, vs iterated composite 61.1% on
the original set (side-by-side evidence, not same-denominator).
Second judge advisory: yes 5 / no 5 / abstain 8, 2 hard conflicts,
never altered a verdict. Cost $0.0364 total. Selection rule and run
adversarially verified (task-set replay, timestamps, arithmetic).

Claude-Session: 6fd60c6f-4f09-4322-8120-604e8a5a60bf
```

> 註:前一輪 commit(row 562)的 session trailer 打錯一碼(`...60bf` 誤植 `...66bf`),本輪 `--amend` 修正——連 commit trailer 的一碼錯字都在意,是「數字不粉飾」原則的延伸。

### row 592 — assistant（wave-3 三線總結)

Wave-3 完成、已 push、CI 綠(含 integration lane)。三線總結:

- **Task 1(評測可信度,面試官最弱維度)**:① **Held-out 新 20 題單跑 66.7%**(12/18)——選題規則 pre-registered、sha256 先凍結後開跑、與原 20 題零重疊、禁止迭代;高於迭代後的 61.1%,是「沒有 overfit 到自建題」的最強證據(文件全處明標兩數不可混比)。② **元件 ablation 落地**(P1-10,13 配置 × 174 確定性 runs,$0):最大單元件是 selector repair(關掉 −3);決定性的軸是 verifier 本身——AgentOccam 式 self-report 判準崩到 4/18 + **10 個 false success**;反直覺結果照錄(selector memory 在版本交錯 suite 上淨零)。
- **Task 2**:CYD 官方 oracle **10/1 → 11/0**——page-top section anchoring 通用規則(無 ticker 特例、kill-switch 驗證可還原)修好 GS 1C(containment 0%→85.6%)與 JPM 1C(33.3%→70.5%,終點與官方逐位一致);F1/calibration 零連帶(四引擎逐位不變)。+9 tests,全綠(quick lane 772)。
- **品質關**:三線各自對抗驗證,4 個 minor findings 全數修掉才 commit(end-to-end 時間高估 35→21 min、子計數 2→3、CYD flag 翻轉補歸因、runs/ gitignored 證據補追蹤快照到 `data/browser_eval/external_runs/`)。

下一波候選(需要時我再開):官方 300 題 WebJudge 完整基準、AI 協作原始 transcript 入庫、AUROC 內容軸訊號(長度軸已實測見底)。
