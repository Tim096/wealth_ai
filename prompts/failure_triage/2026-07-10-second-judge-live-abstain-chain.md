# Second-judge live 全 abstain 根因鏈:HOLE A 接線 + gateway wrapper unwrap

## Trigger

外部量測(Online-Mind2Web 20 題 live 子集)兩輪皆出現同一異常:advisory second judge **18/18 abstain**。第二輪已把 extractor 接上 LLM(每題 cost 0.00014–0.00042,LLM 確實被呼叫)仍全 abstain——「能力在、live 泛化不在」,6 個 open-ended unknown 一分未得。

## Scoring Criteria

- 失敗處理:診斷 → 根因分層 → 修復 → 定向重驗
- 正確性驗證:修復後的 pass 必須 evidence-grounded 且人工抽查
- 誠實邊界:證據不足仍 abstain,不引入假 pass;verifier 唯一裁判不動搖

## Prompt(reconstructed from session records)

AI 自我指令(triage pass):

> second judge 已武裝仍 18/18 abstain,不是 wiring 表層問題。逐層追:(1) open-ended 評分有沒有真的接到判決路徑?(2) 證據面是什麼、引文為何 quote 不到?(3) LLM 回包長什麼樣、extraction 為何全 malformed?每層修完只重跑受影響子集驗證。

## AI Output Summary

根因是**兩層疊加**,單修任何一層都不夠:

1. **HOLE A(評分未接線 + 證據被餓死)**:`run_agentic` 的最終 `verify_contract` 沒帶 `open_ended_extractor`——零條件契約直接判 blanket unknown,開放式評分只到 verifier 參數層、未到 agent loop。且證據被截在 ~4-5K 字(obs cap 5K / prompt cap 4K),引文根本無處可 quote,grounding demotion 一律降級 abstain。修復(`9a40ae2`):verdict-time 用 planner 自己的 LLM client 武裝 extractor(offline/mock → None,行為不變);證據面改餵最終頁 `inner_text` 12K + P0-5 逐步摘錄(bounded:last 10 / 2.5K)——引文必須真出現於證據才 grounded-satisfied,否則 abstain → honest unknown,永不幻覺 pass。
2. **Gateway wrapper(修完 HOLE A 仍全 abstain 的真兇)**:本機 codex gateway 以 `--output-schema` 把**每個** completion 硬套 planner action schema,judge/extractor 回包全變 `{"action":"done","value":"<real JSON>"}` → key-point extraction 與 micro-judgment 全數 "malformed" → abstain。修復(`6dbe095`):`_unwrap_gateway_action` 精確還原該形狀;unwrap 後 grounding demotion 照常裁決(wrapped 幻覺引文仍降級 abstain;真 planner action 的非 JSON value 維持 malformed-abstain)。+6 tests。
3. 同場發現姊妹洞 **HOLE B**(`e53c324`):productized runner 共用單一 page,一次 ERR_HTTP2 污染後續全部任務——改每題 fresh context+page。

**定向重驗**(只重跑上一輪 6 個 unknown,artifact `runs/browser_eval/m2w_abstain_fix2_20260710/`):3 pass / 2 fail / 1 abstain-unknown。TSLA 收盤價題 grounded pass(證據含 `Mar 17, 2023 … Close 180.13`,**人工抽查非幻覺**);證據不足者誠實 fail/abstain,零假 pass。合成後 11/18 = 61.1%(誠實標明:組成數字非單次全集跑,n 小屬方向指標)。

## Human / PM Decision

AI 自主 triage 與修復(總指揮授權);「composed 61% 必須標明組成、不得當單跑引用」為誠實紀律的自我約束,PM 未介入。

## Reason

- 「已武裝仍 abstain」證明表層歸因(wiring)錯誤——多層根因要逐層剝,每層修復配獨立證據。
- grounding demotion 在兩次修復中都**保留**:寧可 abstain 也不讓 LLM 引文未接地就給分,這是 second judge 不奪 verifier 裁判權的結構保證。
- 定向重跑(只跑受影響 6 題)控成本,但必須誠實標為組成數字。

## Resulting Change

- `packages/browser_agent/second_judge.py` `_unwrap_gateway_action`;`agent.py` verdict-time extractor 武裝 + 12K final-page evidence;`tools/run_external_eval.py` per-task fresh context
- Commits:`9a40ae2`(HOLE A)、`6dbe095`(wrapper unwrap)、`e53c324`(HOLE B)、`0eebeef`(6-unknown 重跑記錄)
- Artifacts:`runs/browser_eval/m2w_abstain_fix2_20260710/`、`docs/research/giants_task1.md`「追補:abstain-gap 修復後」節
