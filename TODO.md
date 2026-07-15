# Roadmap — Known Limitations & Next Experiments

> **一句話:這不是功能願望清單,是我自己列的「我哪裡最容易被打臉」清單。**
>
> **本文拆成六段,先給你地圖:**
> ①**P0** — 五個最容易被質疑的主張,我打算交什麼證據?
> ②**P1** — 產品與可靠性還缺什麼?(Task 1 / Task 2 各一組)
> ③**P2** — Reviewer 要花多少力氣才能相信我?
> ④**LLM 決策** — 哪裡用 LLM、哪裡堅持不用,gate 是什麼?
> ⑤**執行順序** — 為什麼是這個順序?
> ⑥**Definition of Done + 不做** — 怎麼算做完?什麼我絕對不幹?

目標不是增加功能數量，而是把目前最容易被質疑的主張換成可獨立重驗的證據。完成與否不改變本文件對現狀弱點的誠實陳述。

**白話:一般的 roadmap 是許願池——列滿新功能,讓人以為現在已經很完整。這份相反:每一列都對著一個「現在就會被打臉的地方」。打勾的項目不會讓已公布的難看數字變好看;沒打勾的項目也不會因為寫進 roadmap 就算做過。未完成就是未完成。**

- 原則：先 freeze protocol，再跑 evaluation；歷史 artifacts 不覆寫；runtime verifier、LLM judge、human label 三者不得混成同一口徑。

**白話:考卷先封好、公證,才准開考(freeze protocol);考壞的成績單不許撕,只能加印新的一張(artifacts 不覆寫);三把不同的尺——程式自己量的、AI 裁判量的、真人量的——不許混在一起報成同一個數字。**

## P0 — 五個最容易被質疑的主張,我打算交什麼證據?

| 項目 | 成本 | 對應弱點 | 交付物與驗收門檻 |
|---|---:|---|---|
| 用修正版 WebJudge 重判 frozen 283 trajectories | M，1–2 天 | Task 1 evaluation credibility | 沿用原 trajectory，不重跑 agent；`283/283` 有 binary outcome；template-artifact 為 `0`；公布 success/failure、abstain、difficulty strata、verifier × judge confusion；隨機抽 30 題 blind human audit 並列 agreement。 |
| 建立新的 unseen real-site set | L，3–5 天 | Task 1 real-world generalization | 先提交 freeze manifest，再跑至少 50 題、10 個 domains、5 類 task；成功條件由獨立 reviewer 建立，不從 task text heuristic 衍生；報 task-success、environment failure、silent-failure、p50/p95 latency、cost/success 與 bootstrap CI。 |
| Live self-maintenance causal ablation | M，2 天 | Task 1 mechanism substance | 對同一組任務分別關閉 selector repair、overlay recovery、new-tab following、vision escalation、replay cache；每個元件必須有可重播 failure fixture 與前後差值，不能只展示 happy-path demo。 |
| Task 2 外部人工 span gold | L，3–5 天 | Task 2 correctness credibility | 從未參與調參的 filings 分層抽樣：modern HTML、wrapper、cross-file、legacy SGML；雙人標註 item start/end，分歧 adjudication；公布 macro P/R/F1、bootstrap CI、missing/hallucination 與 boundary error。 |
| Task 2 confidence recalibration | M，2–3 天 | confidence / failure handling | 僅使用新的 human gold；比較 raw confidence、isotonic、logistic calibration；目標 AUROC `>=0.75`、ECE `<=0.10`。若未達標，UI 改顯示 risk band，不宣稱 probability。 |

**這張表的術語,就地翻成人話:**

- **trajectory**:agent 當時實際跑過的完整操作軌跡紀錄。重判用舊軌跡、不重跑 agent,是為了不讓「換一次運氣」混進分數。
- **template-artifact 為 `0`**:上一波有 abstain 是被我自己的 prompt 模板害的(裁判棄權不是因為題目難,是因為我的模板寫壞)。這一輪要求這種假棄權必須歸零。
- **difficulty strata**:按題目難度分層報,不讓簡單題把平均拉高。
- **verifier × judge confusion**:把「我的程式判什麼」×「AI 裁判判什麼」排成一張對照格,分歧格數字要攤開。
- **blind human audit**:真人不知道機器判了什麼,獨立再判一次 30 題,然後看兩邊同意率。
- **freeze manifest**:先寫死「要跑哪些題、成功條件是什麼」再開跑——先封考卷,才准考。
- **bootstrap CI**:反覆重抽樣算出的信賴區間,白話就是「這個數字的誤差範圍有多寬」。
- **ablation**:一次拆掉一個零件,看分數掉多少;掉了才證明那個零件真的有用,而不是擺著好看。
- **span gold**:真人標好的「這個章節從哪個字到哪個字」標準答案。雙人標、分歧再仲裁(adjudication),避免一個人的偏見變成金標準。
- **AUROC / ECE**:AUROC = 信心分數能不能把「答對的」排在「答錯的」前面;ECE = 自稱的把握度與實際答對比例之間的平均落差。

**這一列必須講白:`目標 AUROC >=0.75`——這個目標到今天還沒達成。** 現況是 MISS,所以走的正是這一列自己寫下的退路:UI 改顯示 risk band(**白話:只說「高風險 / 中風險 / 低風險」這種分級,不謊稱一個看起來很精確的機率**),不宣稱 probability。

> **不是「我們的信心分數有 0.75 的水準」,是「沒到 0.75,所以我不准自己講機率」。**

## P1 — 產品與可靠性還缺什麼?

**以下每一項都還沒做完(`[ ]` 就是還沒做),唯一打勾的那一項有日期、有 endpoint、有實測結果。**

### Task 1

- [ ] 將 answer-quality gate 從已知 skip-link 擴充為 evidence-based classifier；先收集至少 30 個 navigation residue 與 30 個合法短答案，再定規則，避免靠字串黑名單無限增生。
- [ ] 每個 answer 顯示來源 URL、selector、擷取時間與 evidence screenshot；答案與 evidence 不一致時回 `unknown`。
- [ ] Capability guard 增加中英文拒絕案例與 boundary tests，避免 `post` / `pay` 等裸字誤殺正常內容。
- [ ] 在兩個不同日期重跑 frozen live set，量化 website drift、pass@2 與 flakiness；不得把兩次最好結果拼成單一成功率。
- [ ] 對 live service 做 1/2/4/8 concurrent sessions 壓測，公布 queue wait、task latency、memory、timeout、LLM rate-limit 與 cost。

**翻成人話:**第一項是「別再靠關鍵字黑名單擋爛答案,先收集夠多真實案例再定規則」;第二項是「答案要附證據,對不上就認輸回 `unknown`」;第三項是防自己過度防衛——看到 `post` / `pay` 這種裸字就誤殺正常內容;第四項的 **pass@2** 是「跑兩次至少過一次」,而**這一列自己寫死了不准把兩次最好的結果拼成一個成功率**;第五項是同時開 1、2、4、8 個工作階段壓測,連帳單一起公布。

### Task 2

- [ ] 建立並以獨立證據與可重跑 artifact 驗證真正具代表性的 Task 2 strong cases；前端優先明列目前做得好與目前沒做好的案例及證據，README 同步，通過前只稱限定案例或候選，不宣稱整體 strong case。
- [ ] 實作**真正跨檔** exhibit / proxy-statement join：只接受 accession、filing manifest、document type 與 source link 可驗證的正文。〔**部分已達**:Intel/Citi 的**同檔**印刷頁碼錨點正文已由 `page_map` / `source_ranges[]` 從 `incorporated_by_reference` 轉為 source-addressable `partial` span(多段串接);仍未做的是另外**跨檔申報**的 proxy statement(Item 10–14)join,維持 pointer + review。〕
- [x] ✅ **已完成(2026-07-14)**:normalized text 可重現鏈 — `/api/jobs/{id}/normalized` 提供 normalized 全文 + `X-Normalized-Sha256` / `X-Normalization-Version` header;item payload 帶 `normalized_sha` / `source_ranges`,線上實測依 offsets 重算 SHA 為 MATCH。
- [ ] 移除全域 filing state 的併發串台風險；所有 item request 必須攜帶 accession，mismatch 明確失敗。
- [ ] 對 20-F、10-K/A、pre-2001 SGML、PDF/scanned filing 顯示具體 unsupported reason，不回模糊的「找不到」。〔**部分已達**:20-F 走 `NotA10KFilerError` 列出實際 form 分布;PDF/scanned/binary 標 `unsupported_scanned_or_binary` + 前端紅色未支援 banner(2026-07-15,payload `supported` + `coverage=null`,非假 100%)。仍待:10-K/A amendment 專門處理、pre-2001 SGML text-mode normalizer。〕
- [ ] 加入 review workload 指標：coverage、false-pass risk、每 100 filings 預期人工審查量與每正確 item 成本。

**翻成人話,特別是那兩個「部分已達」——半套就要講成半套:**

- **跨檔 join**:年報常常寫「這段請見我們的股東會通知書」。同一個檔案裡靠印刷頁碼找回正文,我做到了(Intel/Citi);**跨到另一份申報文件去撈 proxy statement(Item 10–14),我還沒做**,現在照實維持 pointer + review。
- **unsupported reason**:20-F(外國公司年報)、PDF/掃描檔,現在會明講「不支援,原因是這個」,前端還會出現紅色未支援 banner——**而且 `coverage=null`,不假裝 100%**。**10-K/A(修正版年報)與 pre-2001 SGML 老格式,仍然沒做。**
- **併發串台**:目前的 filing 狀態是全域的,兩個人同時查有互相污染的風險。**這是已知的、還沒修的問題**;修法是所有 item request 都必須帶 accession(SEC 給每份申報的唯一編號),對不上就明確失敗,不猜。
- **review workload**:把「人工要審多少」變成可報的數字——每 100 份 filing 要多少人力、每個正確 item 花多少錢。誠實揭露的代價要列帳,不能只講風險降低。

> **不是「跨檔 join 做好了」,是「同檔的做好了,跨檔的還沒,所以我照實標 pointer」。**

## P2 — Reviewer 要花多少力氣才能相信我?

**這一段全部未完成。目的只有一個:把「相信我」的成本從「讀完整個 repo」壓到「五分鐘」。**

- [ ] 首頁加入 5 分鐘 reviewer path：一個 Task 1 repair pass、一個 honest unknown、一個 Task 2 modern pass、一個 wrapper/review 案例。
- [ ] UI 顯示 `pipeline_rev`、contract source、model/provider、artifact link 與可複製的 reproduction command。
- [ ] 將 raw exception 映射成人類可理解的 failure reason，並在 `unknown` 顯示最後 screenshot 與下一步。
- [ ] 增加 deployment smoke workflow：兩個 health endpoints、deterministic demo、AAPL extraction、public asset cache、rollback check。
- [ ] 建立 release checklist，要求 README 數字、eval report、artifacts、CI 與 live revision 完全一致。

**翻成人話:**第一項刻意排了**一個 honest unknown**——展示櫃裡故意放一個「我不知道」,而不是四個成功案例;第二項是每個畫面都附「你可以複製去自己重跑的指令」;第三項是把程式的原始錯誤訊息翻成人看得懂的失敗原因;第五項是防止「網頁上的數字」跟「報告裡的數字」對不起來。

> **不是「請相信我的結論」,是「這裡有指令,你自己跑一次」。**

## LLM 決策 — 哪裡用 LLM、哪裡堅持不用?

| 區域 | 決策 | 理由與 gate |
|---|---|---|
| Task 1 planner | 使用 LLM | 自然語言分解與跨站 adaptation 確實需要；action 必須通過 capability screen，最終結果由獨立 verifier 決定。 |
| Task 1 verifier | 不使用 LLM 作唯一裁判 | 有機讀條件時 deterministic verifier 唯一裁決，LLM 不介入；零條件（開放式）任務在 verdict 時走 evidence-grounded LLM 評分（`second_judge.score_open_ended`，引文必須逐字存在於 evidence，ground 不了 → abstain → `unknown`，離線/無 key 維持 `unknown`，絕不捏造 pass）；LLM judge 對有條件任務仍只作離線 measurement，不改 runtime verdict。 |
| Task 1 vision escalation | 條件式使用 LLM | 僅在 DOM/a11y repair 卡住時啟用；必須量化增益、額外 latency、tokens 與 cost/success。 |
| Task 2 primary extraction | 不使用 LLM | 邊界、offset、hash、XBRL 與 filing metadata 可用 deterministic pipeline 重驗，成本與 reproducibility 更佳。 |
| Task 2 review fallback | 實驗後再決定 | 只針對 `needs_review` strata 做 A/B；必須在 untouched human gold 上降低 false-pass，且輸出 source span。未同時改善 risk 與 coverage就不採用。 |
| Frontend | 不使用 LLM | Common Requirement 3 是 presentation requirement；LLM 不會提高 UI 可驗證性。 |

**這張表的一句話總結:LLM 只准出現在「需要理解人話」的地方,不准出現在「需要蓋章」的地方。**

- **planner 用 LLM**:因為把一句人話拆成步驟、換個網站還能適應,確實只有 LLM 做得到。但它產生的每個動作都要先過 capability screen(能力篩檢),最後結果由獨立的 verifier 說了算。
- **verifier 不讓 LLM 當唯一裁判**:有機器可讀條件時,LLM 連碰都不能碰。只有「零條件」的開放式任務才走 LLM 評分,而且引文必須**逐字**存在於證據裡——ground 不了就棄權(abstain)回 `unknown`;離線或沒有 key 也維持 `unknown`。**絕不捏造 pass。**
- **Task 2 主抽取不用 LLM**:因為邊界、offset、hash、XBRL 都能用確定性流程重驗——**便宜、可重現,而且不會編**。
- **Task 2 review fallback 還沒決定**:這是「實驗後再決定」,不是「已經在用」。gate 寫死了:必須在**沒碰過的**人工金標準上降低 false-pass,且**未同時改善 risk 與 coverage 就不採用**——不准拿降低風險當藉口把 coverage 砍到見骨。

> **不是「這個系統用了很多 LLM」,是「這個系統把 LLM 關在它不會害人的地方」。**

## 執行順序 — 為什麼是這個順序?

**白話:先把尺校準,再量身高。順序反了,後面做什麼都是白做。**

1. **Evidence repair**：重判 frozen 283、human audit、同步唯一 canonical metrics。
2. **Unseen evaluation**：freeze 新 Task 1 set 與 Task 2 human gold，禁止邊跑邊調參。
3. **Mechanism improvement**：只修新 evaluation 暴露的最大 failure buckets，逐項 ablation。
4. **Product hardening**：cross-file join、concurrency、evidence links、failure UX。
5. **Independent rescore**：reviewer 不看開發過程，只依 prompt、public repo、live frontend 與 frozen artifacts重新評分。

先修「量測」(1、2),才修「機制」(3);機制修完才修「產品」(4);最後一步刻意把自己交出去——**reviewer 不看開發過程**,只看 prompt、公開 repo、線上前端與凍結的 artifact 重新評分。

> **不是「先把功能做完再來量」,是「先確定尺沒歪,才有資格談做完」。**

## Definition of Done — 怎麼算做完?

**這七條全部未完成(`[ ]`)。它們是驗收條件,不是成績單。**

- [ ] 所有 headline metrics 都有 tracked artifact、重現指令、分母與 failure accounting。
- [ ] Task 1 有可信的 task-success rate，不再使用 landmark hit 代替。
- [ ] Task 1 unseen set 無 silent success；environment failures 獨立列出但保留全分母口徑。
- [ ] Task 2 至少一組未參與調參的人工 span gold 與 confidence calibration。
- [ ] 每項 LLM 使用都有 deterministic control、增益、latency、tokens、USD 與 stop rule。
- [ ] CI、README、eval report、public frontend 顯示同一 revision 與同一組數字。
- [ ] 獨立 review 的每一項扣分都能映射回一個可驗證的 experiment。

**翻成人話,挑三條最刺的:**

- 「不再使用 landmark hit 代替」——白話:現在報的 Task 1 數字是「有沒有踩到路標」,**不是真正的任務成功率**。這條沒打勾,代表這個弱點今天還在。
- 「保留全分母口徑」——白話:環境掛掉的題目可以另外列,但**不准從分母裡拿掉**。拿掉分母是把成功率灌水最常見的手法。
- 「每一項扣分都能映射回一個可驗證的 experiment」——白話:別人挑我毛病,我不能用嘴反駁,只能用一個他能重跑的實驗回應。

## 不做 — 什麼事我絕對不幹?

**這一段是我對自己的手銬。上面每一條「還沒做」都可以慢慢做;下面每一條,做了就是造假。**

- 不在看過 held-out 結果後修改成功條件。
- 不覆寫失敗的歷史 artifacts；新增版本並保留 before/after。
- 不把 LLM self-report、runtime landmark、WebJudge 與 human label 混成一個成功率。
- 不為提高數字排除 anti-bot、timeout、unsupported 或 abstain；同時報 gradable 與 all-task denominator。
- 不為追求表面分數重寫 failure gallery、刪除負面結果或宣稱與官方 leaderboard 可比。

**翻成人話,一條一句:**看過答案不准改題目;考壞的成績單不准撕,只能加印新的一張並保留前後對照;四把不同的尺不准混成一個數字;不准把「機器人被擋」「逾時」「不支援」「裁判棄權」這些難看的題目從分母偷偷拿掉——gradable 與 all-task 兩個分母都要報;不准為了好看重寫失敗紀錄、刪負面結果,或宣稱自己跟官方 leaderboard 可以比。

> **這份 roadmap 的價值不在「我打算做什麼」,在「我已經先把自己作弊的路全部堵死了」。**
