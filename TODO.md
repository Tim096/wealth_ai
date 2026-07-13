# Roadmap — Known Limitations & Next Experiments

目標不是增加功能數量，而是把目前最容易被質疑的主張換成可獨立重驗的證據。完成與否不改變本文件對現狀弱點的誠實陳述。

- 原則：先 freeze protocol，再跑 evaluation；歷史 artifacts 不覆寫；runtime verifier、LLM judge、human label 三者不得混成同一口徑。

## P0 — 主要已知弱點的直接補強

| 項目 | 成本 | 對應弱點 | 交付物與驗收門檻 |
|---|---:|---|---|
| 用修正版 WebJudge 重判 frozen 283 trajectories | M，1–2 天 | Task 1 evaluation credibility | 沿用原 trajectory，不重跑 agent；`283/283` 有 binary outcome；template-artifact 為 `0`；公布 success/failure、abstain、difficulty strata、verifier × judge confusion；隨機抽 30 題 blind human audit 並列 agreement。 |
| 建立新的 unseen real-site set | L，3–5 天 | Task 1 real-world generalization | 先提交 freeze manifest，再跑至少 50 題、10 個 domains、5 類 task；成功條件由獨立 reviewer 建立，不從 task text heuristic 衍生；報 task-success、environment failure、silent-failure、p50/p95 latency、cost/success 與 bootstrap CI。 |
| Live self-maintenance causal ablation | M，2 天 | Task 1 mechanism substance | 對同一組任務分別關閉 selector repair、overlay recovery、new-tab following、vision escalation、replay cache；每個元件必須有可重播 failure fixture 與前後差值，不能只展示 happy-path demo。 |
| Task 2 外部人工 span gold | L，3–5 天 | Task 2 correctness credibility | 從未參與調參的 filings 分層抽樣：modern HTML、wrapper、cross-file、legacy SGML；雙人標註 item start/end，分歧 adjudication；公布 macro P/R/F1、bootstrap CI、missing/hallucination 與 boundary error。 |
| Task 2 confidence recalibration | M，2–3 天 | confidence / failure handling | 僅使用新的 human gold；比較 raw confidence、isotonic、logistic calibration；目標 AUROC `>=0.75`、ECE `<=0.10`。若未達標，UI 改顯示 risk band，不宣稱 probability。 |

## P1 — 高價值產品與可靠性補強

### Task 1

- [ ] 將 answer-quality gate 從已知 skip-link 擴充為 evidence-based classifier；先收集至少 30 個 navigation residue 與 30 個合法短答案，再定規則，避免靠字串黑名單無限增生。
- [ ] 每個 answer 顯示來源 URL、selector、擷取時間與 evidence screenshot；答案與 evidence 不一致時回 `unknown`。
- [ ] Capability guard 增加中英文拒絕案例與 boundary tests，避免 `post` / `pay` 等裸字誤殺正常內容。
- [ ] 在兩個不同日期重跑 frozen live set，量化 website drift、pass@2 與 flakiness；不得把兩次最好結果拼成單一成功率。
- [ ] 對 live service 做 1/2/4/8 concurrent sessions 壓測，公布 queue wait、task latency、memory、timeout、LLM rate-limit 與 cost。

### Task 2

- [ ] 實作 cross-file exhibit join：只接受 accession、filing manifest、document type 與 source link 可驗證的正文；Intel/Citi 必須由既有 `incorporated_by_reference` 轉為 source-addressable span，否則維持 review。
- [ ] 修正 normalized text 的可重現鏈：提供 normalization version、raw SHA、normalized SHA 與一行驗證指令。
- [ ] 移除全域 filing state 的併發串台風險；所有 item request 必須攜帶 accession，mismatch 明確失敗。
- [ ] 對 20-F、10-K/A、pre-2001 SGML、PDF/scanned filing 顯示具體 unsupported reason，不回模糊的「找不到」。
- [ ] 加入 review workload 指標：coverage、false-pass risk、每 100 filings 預期人工審查量與每正確 item 成本。

## P2 — Reviewer experience 與可營運性

- [ ] 首頁加入 5 分鐘 reviewer path：一個 Task 1 repair pass、一個 honest unknown、一個 Task 2 modern pass、一個 wrapper/review 案例。
- [ ] UI 顯示 `pipeline_rev`、contract source、model/provider、artifact link 與可複製的 reproduction command。
- [ ] 將 raw exception 映射成人類可理解的 failure reason，並在 `unknown` 顯示最後 screenshot 與下一步。
- [ ] 增加 deployment smoke workflow：兩個 health endpoints、deterministic demo、AAPL extraction、public asset cache、rollback check。
- [ ] 建立 release checklist，要求 README 數字、eval report、artifacts、CI 與 live revision 完全一致。

## LLM 決策

| 區域 | 決策 | 理由與 gate |
|---|---|---|
| Task 1 planner | 使用 LLM | 自然語言分解與跨站 adaptation 確實需要；action 必須通過 capability screen，最終結果由獨立 verifier 決定。 |
| Task 1 verifier | 不使用 LLM 作唯一裁判 | 有機讀條件時 deterministic verifier 唯一裁決，LLM 不介入；零條件（開放式）任務在 verdict 時走 evidence-grounded LLM 評分（`second_judge.score_open_ended`，引文必須逐字存在於 evidence，ground 不了 → abstain → `unknown`，離線/無 key 維持 `unknown`，絕不捏造 pass）；LLM judge 對有條件任務仍只作離線 measurement，不改 runtime verdict。 |
| Task 1 vision escalation | 條件式使用 LLM | 僅在 DOM/a11y repair 卡住時啟用；必須量化增益、額外 latency、tokens 與 cost/success。 |
| Task 2 primary extraction | 不使用 LLM | 邊界、offset、hash、XBRL 與 filing metadata 可用 deterministic pipeline 重驗，成本與 reproducibility 更佳。 |
| Task 2 review fallback | 實驗後再決定 | 只針對 `needs_review` strata 做 A/B；必須在 untouched human gold 上降低 false-pass，且輸出 source span。未同時改善 risk 與 coverage就不採用。 |
| Frontend | 不使用 LLM | Common Requirement 3 是 presentation requirement；LLM 不會提高 UI 可驗證性。 |

## 執行順序

1. **Evidence repair**：重判 frozen 283、human audit、同步唯一 canonical metrics。
2. **Unseen evaluation**：freeze 新 Task 1 set 與 Task 2 human gold，禁止邊跑邊調參。
3. **Mechanism improvement**：只修新 evaluation 暴露的最大 failure buckets，逐項 ablation。
4. **Product hardening**：cross-file join、concurrency、evidence links、failure UX。
5. **Independent rescore**：reviewer 不看開發過程，只依 prompt、public repo、live frontend 與 frozen artifacts重新評分。

## Definition of Done

- [ ] 所有 headline metrics 都有 tracked artifact、重現指令、分母與 failure accounting。
- [ ] Task 1 有可信的 task-success rate，不再使用 landmark hit 代替。
- [ ] Task 1 unseen set 無 silent success；environment failures 獨立列出但保留全分母口徑。
- [ ] Task 2 至少一組未參與調參的人工 span gold 與 confidence calibration。
- [ ] 每項 LLM 使用都有 deterministic control、增益、latency、tokens、USD 與 stop rule。
- [ ] CI、README、eval report、public frontend 顯示同一 revision 與同一組數字。
- [ ] 獨立 review 的每一項扣分都能映射回一個可驗證的 experiment。

## 不做

- 不在看過 held-out 結果後修改成功條件。
- 不覆寫失敗的歷史 artifacts；新增版本並保留 before/after。
- 不把 LLM self-report、runtime landmark、WebJudge 與 human label 混成一個成功率。
- 不為提高數字排除 anti-bot、timeout、unsupported 或 abstain；同時報 gradable 與 all-task denominator。
- 不為追求表面分數重寫 failure gallery、刪除負面結果或宣稱與官方 leaderboard 可比。
