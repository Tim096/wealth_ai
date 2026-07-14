# Rejected: 用 vision LLM 定位元素做 selector 修復

> **Record type:** Derived decision record

## Trigger

設計 browser agent selector 修復時,AI 考慮的一個方案:UI 漂移時,截圖丟給 vision LLM(如 GPT-4V/Claude vision),讓它指出「搜尋框在哪」的座標,再點下去。這是 Skyvern 類的做法。

## Scoring Criteria

- 工程權衡:成本、延遲、可重現性、可驗證性
- 正確性驗證:修復是否可小步驗證

## Prompt summary

「selector 找不到時,screenshot → vision LLM → 回傳 bounding box → 點座標。」

## AI Output Summary(為何評估後拒絕)

拒絕當作**主要**修復路徑,理由:

1. **成本/延遲**:每次漂移一次 vision LLM call(~$0.01+、數百 ms–秒級),與我們「LLM 只在真正未知時升級」的原則衝突;a11y-tree 搜尋是確定性、<100ms、$0。
2. **不可重現**:vision 座標非決定性,eval 無法位元級重跑;a11y 候選 + 評分可重現。
3. **不可驗證**:座標點擊難以小步驗證「點到正確元素」;a11y 候選有 role/label/text 可解釋為何選它、為何避開 decoy。
4. **可觀測性差**:座標無語意,selector memory 存座標無意義;存 `input[name=query]` 才可跨 run 復用。

## Decision

拒絕為主要路徑。保留為**未來 fallback**:當 a11y 樹貧乏(canvas-heavy / 無語意 DOM)時,vision 定位是合理的最後手段(見 `docs/prior_art.md` Skyvern 條)。

## Reason

符合 SPEC 工程權衡與正確性驗證:確定性、可重現、可驗證優先;LLM(含 vision)是升級手段,不是預設。

## Resulting Change

- 採用 a11y-tree + purpose 評分修復(`packages/browser_agent/repair.py`),非 vision。
- vision fallback 記為 roadmap。

## 事後看(2026-07-10)

拒絕的**邊界**事後被驗證是對的:vision 後來確實回來了,但回在**感知升級**層(AGENT_VISION 三態 + heuristic 觸發,截圖只在 a11y 訊號不足時附進 planner call,`agent.py:216-224`),**不是**修復路徑——repair 至今維持確定性 a11y 評分、零 LLM 成本,giants 對照(`docs/research/giants_task1.md` §1.5)確認此設計在 cost 軸領先 SOTA(BU 的 use_vision='auto' 是同構等價)。「see+mouse+keyboard 混合、非取代;verifier 仍唯一裁判」正是當年拒絕理由(vision 當升級手段不當預設)的延伸,而非推翻。
