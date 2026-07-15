# 手動測試 Task 1(Browser Agent · Agent Mode)

**一句話**:你打一句人話的任務,LLM 當大腦、真的去開瀏覽器點,最後由一個**不是
LLM 的裁判**(verifier)判它到底有沒有做到。

Agent Mode 用 LLM(OpenAI/Codex)當大腦驅動瀏覽器。**你用自己的憑證跑,本專案不
儲存也不索取 key。** 每個 action 都經 capability guard,最終由 verifier(不是 LLM)
判 pass/fail/unknown。

白話三個關鍵詞:

- **capability guard** = 動作的門神。LLM 想做的每一步,先送去問「這步准不准做」。
- **verifier** = 裁判。LLM 說「我做完了」不算數,裁判照契約檢查證據才算數。
- **pass / fail / unknown** = 過 / 沒過 / **我判不出來**。第三種存在,是因為「判不
  出來」比「猜一個過」誠實。

這份分六段:**前置** → **三種跑法** → **參數** → **會看到什麼/怎麼判讀** →
**一條真實 failure 的驗收劇本** → **為什麼這不是「LLM 亂點」**。

## 前置:先把環境裝起來

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev,browser]"
.venv\Scripts\python -m playwright install chromium
```

## 三種跑法怎麼選?

三條路的差別只在「大腦從哪來」:A 用你的 ChatGPT 訂閱,B 完全不用大腦,C 用你的
API key。**第一次跑建議先跑 B 確認裝好,再回頭跑 A。**

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

白話:mock 後端就是一個「假大腦」,回固定答案。**先證明水管是通的,再打開水龍頭** ——
路徑通了才去懷疑模型,而不是一次改兩個變數然後猜是哪裡壞。

### B. 無 key、確定性(先確認裝好)

```powershell
.venv\Scripts\python tools\browser_agent_live.py --mock --query widget
```
用 MockPlanner 跑內建 mock 站(v2:UI 漂移 + cookie modal + decoy),應輸出 `STATUS: PASS`。

白話:mock 站 v2 不是一個乖乖的靜態網頁 —— 它會**漂移 UI**(元素換位置)、**跳
cookie 彈窗**、**放誘餌**(decoy,長得像正確答案但不是)。這三樣就是拿來絆倒 agent
的。**不是「在理想網頁上跑得動」,是「在故意刁難的網頁上跑得動」。**

### C. 直連 OpenAI API key(A/B 用)

```powershell
$env:OPENAI_API_KEY = "sk-..."
$env:OPENAI_MODEL   = "gpt-5-codex-mini"
.venv\Scripts\python tools\browser_agent_live.py --direct --url "https://..." --task "..." --success "text_visible:..."
```

## 參數有哪些?

| 參數 | 說明 |
|---|---|
| `--task` | 自然語言任務 |
| `--url` | 起始網址(預設內建 mock v2) |
| `--success "type:value"` | verifier 成功條件,可重複。type: `url_contains` / `text_visible` |
| `--headed` | 顯示瀏覽器視窗(觀看過程) |
| `--mock` / `--query` | 用確定性 MockPlanner(免 key) |
| `--max-steps` | LLM 迴圈上限(預設 8) |

`--success` 是這張表裡最重要的一個:**它是你跟系統簽的契約**,裁判只認它。
`--max-steps`(預設 8)則是煞車 —— 不給上限,一個迷路的 agent 會永遠點下去。

## 會看到什麼 / 如何判讀

- 逐步 trace:每個 `[agent] action -> ok/FAIL` 加 LLM 的理由。
- `STATUS: PASS/FAIL/UNKNOWN/REFUSED` + `confidence` + verifier 原因。
- **REFUSED**:任務涉及 login/purchase/checkout/submit → capability guard 擋下(誠實邊界,code-enforced)。試 `--task "Log into my account"` 會直接 refused。
- artifact:`runs/agent_live/run.json`(trace)、`runs/agent_live/evidence/*.jsonl`(EvidenceRecord)、`runs/agent_live/shots/*.png`(截圖)。

四個 STATUS 的白話:

| 你看到 | 意思 |
|---|---|
| `PASS` | 裁判在證據裡找到你要的東西 |
| `FAIL` | 裁判找過了,沒有 |
| `UNKNOWN` | 裁判沒有足夠證據下判斷 —— 我寧可說不知道,也不猜一個 |
| `REFUSED` | 這件事我**設計上就不做**(登入/購買/結帳/送出) |

**REFUSED 不是做不到,是不准做**,而且是 code-enforced —— 寫死在程式裡的門神,
不是寫在 prompt 裡求模型自律。你可以自己試:`--task "Log into my account"` 會直接
refused。這是這套系統唯一一個「我主動把能力關掉」的地方。

## 手動驗收劇本:INTC 營收(answer channel,live LLM)

> 真實案例回歸驗收。這條需要 codex gateway(live LLM),**不進 CI**;離線等價
> 驗證由 `tools/answer_channel_eval.py` + `tests/test_answer_channel.py` 覆蓋。

**先講這條為什麼存在 —— 因為我真的被騙過一次。**

歷史 failure(修復前):任務「找到 intc 10-k 的財報 找到裡面的最新的營收數字給我」
→ preflight 給 `text_visible:intc`(任務句自帶 token)→ agent 只開了 EDGAR 搜尋頁
→ 條件命中 → **PASS conf 1.00,但答案從沒交付**。三重根因:premature landmark(P1
已修)、答案無交付通道、extract 結果被丟棄(P2 已修)。

翻成一般人能懂的版本:任務句裡本來就有「intc」這幾個字,系統就拿「畫面上看得到
intc」當成功條件 —— 於是 agent 只要打開搜尋頁,「intc」就出現了,**條件成立,滿分
通過,而使用者要的營收數字一個都沒拿到。**這是最惡劣的一種假通過:不是系統壞了,
是**成績單自己出題給自己考**。

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

這四條的白話:①換掉自己出題的成績單(`answer_matches` 認的是「答案長得像不像一
個金額」,不是「畫面上有沒有出現任務句裡的字」);②③證明答案真的被抓出來、真的
被端到你面前;④最狠的一條 —— **沒交付=沒完成,判 FAIL 不判 PASS。**

> 修好一個 bug 不算數,把「這個 bug 再犯就會被抓到」寫成一條可重跑的劇本才算數。

## 可靠性設計(為何這不是「LLM 亂點」)

1. LLM 只能回傳受控 action JSON,target 只能用 aid 選現有元素——不能寫 code、不能造 selector。
2. 每個 action 先過 `capability.screen_action`(拒憑證輸入 / 不可逆操作)。
3. 成敗由 verifier 依 task contract 判定,LLM 說 done 不算數;缺證據 → unknown。
4. 全程 EvidenceRecord + 截圖,可回放。

四道防線的白話,一句一道:①**它只能點,不能寫程式** —— 輸出空間被關進一個 JSON
的籠子,target 只能從畫面上已經存在的元素(aid)裡挑,連 selector 都不准自己造;
②**每一步都要過門神**,拒絕憑證輸入與不可逆操作;③**裁判不是它自己**,契約說了算,
缺證據就 unknown;④**全程留證**,可以整條回放。

這正是 Agent Mode 相對「直接丟給 OpenClaw/Hermes」的差異:同樣用 LLM,但輸出空間受限、有 guard、有 verifier、有 evidence——見 `docs/insights_and_directions.md` §1。

> 不是「我的模型比較聰明」,是**同樣一顆模型,我把它能亂來的空間關掉、把裁判權從
> 它手上拿走**。
