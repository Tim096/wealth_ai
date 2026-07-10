# Codex OAuth → Gateway 設定(Task 1 預設)

Browser Agent 的 Agent Mode **預設走本地 gateway,由 Codex OAuth(你的 ChatGPT 訂閱)驅動**。設定分兩塊:一次性登入 + 啟動 gateway。本專案不儲存也不索取任何 key。

## 架構

```
browser_agent_live.py  ──OpenAI /v1/chat/completions──▶  codex_gateway.py  ──subprocess──▶  codex exec  ──OAuth──▶  ChatGPT/Codex
   (預設 base_url = http://127.0.0.1:8791/v1, config/agent.toml)
```

Codex 的 OAuth token 是 ChatGPT 範圍,**不能直接打 api.openai.com**;所以用 gateway 把它包成 OpenAI-compatible endpoint。

## 一次性設定

```powershell
# 1) 安裝 Codex CLI
npm i -g @openai/codex          # 或 brew install codex

# 2) 用 ChatGPT 帳號登入(開瀏覽器 OAuth,存 token 在本機)
codex login
#   驗證:codex exec "say hello" 應該有回應
```

## 每次使用(兩個終端機)

**終端機 A — 啟動 gateway:**
```powershell
.venv\Scripts\python tools\codex_gateway.py --model default
#   重要:ChatGPT OAuth 會拒絕明確的 codex-* model 名(gpt-5.3-codex / gpt-5-codex-mini
#   都會回 "model is not supported when using Codex with a ChatGPT account")。
#   用 --model default = 帳號預設(實測為 gpt-5.5)。明確 model 名只在用 API key 時有效。
#   看到 "listening on http://127.0.0.1:8791/v1" 即就緒
```

**終端機 B — 跑 agent(已預設指向 gateway,無需設任何 env):**

**互動模式(直接打自然語言,推薦):**
```powershell
.venv\Scripts\python tools\browser_agent_live.py         # 無參數 = 互動模式
# 然後照提示輸入:
#   任務 (自然語言) > 到 Wikipedia 搜尋 Reliability engineering 並打開那篇文章
#   起始 URL [目前頁面] > https://en.wikipedia.org/wiki/Main_Page
#   成功條件 (可留空自動推斷) > Reliability engineering
# 會開瀏覽器視窗執行,結束後可再輸入下一個任務,'quit' 離開。
```

**一次性模式(用參數):**
```powershell
.venv\Scripts\python tools\browser_agent_live.py --headed `
  --url "https://en.wikipedia.org/wiki/Main_Page" `
  --task "Search Wikipedia for 'Reliability engineering' and open the article" `
  --success "text_visible:Reliability engineering"
```
啟動時 agent 會先 preflight gateway;連不到會直接告訴你怎麼開。

## 先驗證整條路徑(不需 codex,證明 gateway↔agent 通)

```powershell
# 終端機 A:用 mock 後端(不呼叫 codex,回固定 JSON action)
.venv\Scripts\python tools\codex_gateway.py --backend mock
# 終端機 B:預設就走 gateway
.venv\Scripts\python tools\browser_agent_live.py     # 應輸出 STATUS: PASS(內建 mock 站)
```
這條路徑已在測試中驗證(`tests/test_codex_gateway.py` + e2e:mock gateway 驅動 agent → PASS)。把 `--backend mock` 換成預設的 `codex` 後端,同一條路徑改由真實 Codex 驅動。

## 三種後端

| gateway `--backend` | 用途 |
|---|---|
| `codex`(預設)| shell out `codex exec`,你的 Codex OAuth |
| `mock` | 固定 JSON action,驗證 gateway↔agent 不需 codex |
| `openai` | 轉發真實 OpenAI(需 `OPENAI_API_KEY`),做 A/B |

## 覆寫(env 永遠優先於 config/agent.toml)

```powershell
$env:OPENAI_BASE_URL = "http://127.0.0.1:9000/v1"   # 換 gateway 位址/埠
$env:OPENAI_MODEL    = "gpt-5-codex-mini"
$env:AGENT_LLM_MODE  = "direct"                      # 改成直連(需 OPENAI_API_KEY)
```

## 誠實邊界(我無法在此環境替你完成的部分)

- `codex login` 的 OAuth 需要**你本人在瀏覽器登入 ChatGPT**——我無法代做,也不該碰你的憑證。
- `codex exec` 的實際輸出格式依你安裝的 codex 版本;gateway 的 codex 後端依官方 non-interactive 文件實作(`--sandbox read-only --output-schema`),但**請用 `--backend mock` 先確認 gateway↔agent 通,再切 codex 後端跑一次確認你的 codex 版本相容**。gateway 的 HTTP/回應層已有測試覆蓋。
- 若 `codex exec` 回傳格式與預期不同,調整 `tools/codex_gateway.py::CodexBackend.complete` 的解析(已用 `_extract_json_object` 容錯抓第一個合法 JSON)。
