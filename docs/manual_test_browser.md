# 手動測試 Task 1(Browser Agent · Agent Mode)

Agent Mode 用 LLM(OpenAI/Codex)當大腦驅動瀏覽器。**你用自己的憑證跑,本專案不儲存也不索取 key。** 每個 action 都經 capability guard,最終由 verifier(不是 LLM)判 pass/fail/unknown。

## 前置

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev,browser]"
.venv\Scripts\python -m playwright install chromium
```

## 三種跑法

### A.(預設)Codex OAuth → gateway ★

**這是預設模式**(`config/agent.toml`,base_url `http://127.0.0.1:8791/v1`)。完整設定見 **[docs/setup_codex_gateway.md](setup_codex_gateway.md)**。摘要:

```powershell
# 一次性:codex login(ChatGPT OAuth)
# 終端機 A:啟動 gateway
.venv\Scripts\python tools\codex_gateway.py --model default
# 終端機 B:agent 已預設指向 gateway,不需設 env
.venv\Scripts\python tools\browser_agent_live.py --headed `
  --url "https://en.wikipedia.org/wiki/Main_Page" `
  --task "Search Wikipedia for 'Reliability engineering' and open the article" `
  --success "text_visible:Reliability engineering"
```
先用 `codex_gateway.py --backend mock` 可驗證整條路徑不需 codex(agent → gateway → JSON action → 執行 → verify)。

### B. 無 key、確定性(先確認裝好)

```powershell
.venv\Scripts\python tools\browser_agent_live.py --mock --query widget
```
用 MockPlanner 跑內建 mock 站(v2:UI 漂移 + cookie modal + decoy),應輸出 `STATUS: PASS`。

### C. 直連 OpenAI API key(A/B 用)

```powershell
$env:OPENAI_API_KEY = "sk-..."
$env:OPENAI_MODEL   = "gpt-5-codex-mini"
.venv\Scripts\python tools\browser_agent_live.py --direct --url "https://..." --task "..." --success "text_visible:..."
```

## 參數

| 參數 | 說明 |
|---|---|
| `--task` | 自然語言任務 |
| `--url` | 起始網址(預設內建 mock v2) |
| `--success "type:value"` | verifier 成功條件,可重複。type: `url_contains` / `text_visible` |
| `--headed` | 顯示瀏覽器視窗(觀看過程) |
| `--mock` / `--query` | 用確定性 MockPlanner(免 key) |
| `--max-steps` | LLM 迴圈上限(預設 8) |

## 會看到什麼 / 如何判讀

- 逐步 trace:每個 `[agent] action -> ok/FAIL` 加 LLM 的理由。
- `STATUS: PASS/FAIL/UNKNOWN/REFUSED` + `confidence` + verifier 原因。
- **REFUSED**:任務涉及 login/purchase/checkout/submit → capability guard 擋下(誠實邊界,code-enforced)。試 `--task "Log into my account"` 會直接 refused。
- artifact:`runs/agent_live/run.json`(trace)、`runs/agent_live/evidence/*.jsonl`(EvidenceRecord)、`runs/agent_live/shots/*.png`(截圖)。

## 手動驗收劇本:INTC 營收(answer channel,live LLM)

> 真實案例回歸驗收。這條需要 codex gateway(live LLM),**不進 CI**;離線等價
> 驗證由 `tools/answer_channel_eval.py` + `tests/test_answer_channel.py` 覆蓋。

歷史 failure(修復前):任務「找到 intc 10-k 的財報 找到裡面的最新的營收數字給我」
→ preflight 給 `text_visible:intc`(任務句自帶 token)→ agent 只開了 EDGAR 搜尋頁
→ 條件命中 → **PASS conf 1.00,但答案從沒交付**。三重根因:premature landmark(P1
已修)、答案無交付通道、extract 結果被丟棄(P2 已修)。

步驟:

```powershell
# 終端機 A(一次性 codex login 後)
.venv\Scripts\python tools\codex_gateway.py --model default
# 終端機 B
.venv\Scripts\python tools\test_center.py
```

在測試中心「題目一」輸入:`找到 intc 10-k 的財報 找到裡面的最新的營收數字給我`,派工。

驗收判準(全部要成立):

1. 🧭 規畫列的成功條件是 `answer_matches:<regex>`(deliverable 的形狀,例如
   `[\$][0-9][0-9,\.]+\s*(billion|million)?`),**不是** `text_visible:intc`
   (task-echo guard 會擋;若 LLM 仍給出開場即真的條件,trace 會出現
   「🚫 條件在開場就成立(vacuous),已剔除」)。
2. agent 走到含營收數字的頁面後,倒數步驟出現 `extract_text`(feed 顯示
   「📋 擷取內容(N 字):…」)。
3. verdict 旁出現「📋 擷取內容」區塊,內容含營收數字 —— 答案真的交到手上。
4. PASS 的依據是 answer_matches 對擷取文字的比對;若 agent 沒做 extract 就
   done,verdict 是 **FAIL**(沒交付=沒完成),不是 PASS。

## 可靠性設計(為何這不是「LLM 亂點」)

1. LLM 只能回傳受控 action JSON,target 只能用 aid 選現有元素——不能寫 code、不能造 selector。
2. 每個 action 先過 `capability.screen_action`(拒憑證輸入 / 不可逆操作)。
3. 成敗由 verifier 依 task contract 判定,LLM 說 done 不算數;缺證據 → unknown。
4. 全程 EvidenceRecord + 截圖,可回放。

這正是 Agent Mode 相對「直接丟給 OpenClaw/Hermes」的差異:同樣用 LLM,但輸出空間受限、有 guard、有 verifier、有 evidence——見 `docs/insights_and_directions.md` §1。
