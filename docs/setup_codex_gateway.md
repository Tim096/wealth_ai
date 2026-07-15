# Codex OAuth → Gateway 設定(Task 1 預設)

**一句話**:你的 ChatGPT 訂閱不能直接當 API 用,所以我在你電腦上開一個小翻譯官
(gateway),把 agent 講的「OpenAI API 話」翻成 codex 聽得懂的話。

Browser Agent 的 Agent Mode **預設走本地 gateway,由 Codex OAuth(你的 ChatGPT 訂閱)驅動**。設定分兩塊:一次性登入 + 啟動 gateway。本專案不儲存也不索取任何 key。

這份分六段:**架構** → **一次性設定** → **每次使用(兩個終端機)** → **先驗證整條
路徑** → **三種後端 / 覆寫 / 視覺通道** → **誠實邊界(我做不到的部分)**。

## 架構長怎樣?

```
browser_agent_live.py  ──OpenAI /v1/chat/completions──▶  codex_gateway.py  ──subprocess──▶  codex exec  ──OAuth──▶  ChatGPT/Codex
   (預設 base_url = http://127.0.0.1:8791/v1, config/agent.toml)
```

Codex 的 OAuth token 是 ChatGPT 範圍,**不能直接打 api.openai.com**;所以用 gateway 把它包成 OpenAI-compatible endpoint。

白話:OAuth token = 你登入 ChatGPT 拿到的通行證。這張通行證只能進 ChatGPT 那扇門,
**進不了 `api.openai.com` 那扇門**。gateway 做的事就是:agent 照 OpenAI 的標準格式
敲門,gateway 接下來,轉身用你的通行證去走 ChatGPT 那扇門,再把答案原路送回。

> 不是繞過任何授權,是**用你自己的訂閱、走 codex 官方的 CLI** —— gateway 只負責把
> 介面對上。

## 一次性設定(做一次就好)

```powershell
# 1) 安裝 Codex CLI
npm i -g @openai/codex          # 或 brew install codex

# 2) 用 ChatGPT 帳號登入(開瀏覽器 OAuth,存 token 在本機)
codex login
#   驗證:codex exec "say hello" 應該有回應
```

注意第二步最後那行:**先讓 `codex exec "say hello"` 有回應,再往下走。** 這是最便宜
的一次驗證 —— 如果連 codex 自己都不通,後面 gateway、agent 全都是白搭,而你會花
半小時懷疑錯地方。

## 每次使用(兩個終端機)

**終端機 A — 啟動 gateway:**
```powershell
.venv\Scripts\python tools\codex_gateway.py --model default
#   重要:ChatGPT OAuth 會拒絕明確的 codex-* model 名(gpt-5.3-codex / gpt-5-codex-mini
#   都會回 "model is not supported when using Codex with a ChatGPT account")。
#   用 --model default = 帳號預設(實測為 gpt-5.5)。明確 model 名只在用 API key 時有效。
#   看到 "listening on http://127.0.0.1:8791/v1" 即就緒
```

這個 `--model default` 是踩過坑換來的,值得白話講一次:你**不能**指名要哪個模型。
指名 `gpt-5.3-codex` 或 `gpt-5-codex-mini`,ChatGPT OAuth 會直接回你
`"model is not supported when using Codex with a ChatGPT account"`。所以只能用
`--model default`(帳號預設,實測為 gpt-5.5)。**明確 model 名不是壞了,是那條路只在
用 API key 時才開。**

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

白話:preflight = 起飛前檢查。agent 不會等你等半天才吐一個看不懂的 connection
error —— 它一開始就去敲 gateway,敲不到就直接告訴你該怎麼開。

## 先驗證整條路徑(不需 codex,證明 gateway↔agent 通)

```powershell
# 終端機 A:用 mock 後端(不呼叫 codex,回固定 JSON action)
.venv\Scripts\python tools\codex_gateway.py --backend mock
# 終端機 B:預設就走 gateway
.venv\Scripts\python tools\browser_agent_live.py     # 應輸出 STATUS: PASS(內建 mock 站)
```
這條路徑已在測試中驗證(`tests/test_codex_gateway.py` + e2e:mock gateway 驅動 agent → PASS)。把 `--backend mock` 換成預設的 `codex` 後端,同一條路徑改由真實 Codex 驅動。

**這一段是整份文件最值得先做的一件事。** 白話:mock 後端 = 假大腦,不呼叫 codex,
回固定的 JSON action。它把「水管通不通」和「大腦聰不聰明」拆成兩個獨立的問題 ——
先證明水管通,再打開水龍頭。**一次只改一個變數,壞掉的時候你才知道是誰壞的。**

## 三種後端各是幹嘛的?

| gateway `--backend` | 用途 |
|---|---|
| `codex`(預設)| shell out `codex exec`,你的 Codex OAuth |
| `mock` | 固定 JSON action,驗證 gateway↔agent 不需 codex |
| `openai` | 轉發真實 OpenAI(需 `OPENAI_API_KEY`),做 A/B |

一句話各一個:`codex` 是**真的跑**,`mock` 是**驗水管**,`openai` 是**找對照組** ——
同一條路徑換一顆大腦,才知道差的是模型還是我的系統。**孤立的一次成功不能宣稱什麼,
有對照才能。**

## 覆寫(env 永遠優先於 config/agent.toml)

```powershell
$env:OPENAI_BASE_URL = "http://127.0.0.1:9000/v1"   # 換 gateway 位址/埠
$env:OPENAI_MODEL    = "gpt-5-codex-mini"
$env:AGENT_LLM_MODE  = "direct"                      # 改成直連(需 OPENAI_API_KEY)
$env:AGENT_VISION    = "1"                            # 視覺:1=每步都送 SoM 截圖;0=全關;不設=卡住自動升級
```

規則只有一條、記住就好:**env 永遠贏過 config file。** 你不必去改 `config/agent.toml`,
臨時想換什麼,設 env 就蓋掉。

## 視覺通道(`AGENT_VISION`:1 / 0 / 不設=auto)

白話先講:預設情況下 agent 是「用讀的」—— 它讀網頁的結構,不看畫面。視覺通道就是
**給它一雙眼睛**,但這雙眼睛平常閉著,因為看圖要花錢(圖像 token)。

混合架構的「眼睛」:開啟後,agent 每步把畫面渲成 **Set-of-Marks 截圖**(每個可互動元素畫上編號框,編號=candidate 的 aid),隨 prompt 一起送給模型。gateway 的 codex 後端會用 `codex exec --image <som.png>` 把圖交給帳號預設的 **gpt-5.5(多模態)**,模型看圖挑元素;挑不到 aid 的自訂 widget 就讀框中心座標發 `mouse` 動作。座標來自真實 layout,不是幻覺;成敗仍由 verifier 判定,status 不受影響。需要 `--headed` 或有 `artifact_dir` 才會產生截圖。

**Set-of-Marks(SoM)** 翻成一般人能懂的版本:把網頁截圖拿來,在每個能點的東西上面
畫一個編號的框 —— 像考卷上的選擇題編號。模型不用描述「那個藍色的按鈕」,它只要報
一個號碼。編號就是 aid,agent 照號碼去點,**點的是真實存在的元素,不是模型幻想出來的**。

那「挑不到 aid 的自訂 widget」怎麼辦?讀框中心座標,發 `mouse` 動作直接點。這裡有
一句必須講清楚的話,原文已經寫了、我原樣保留:**座標來自真實 layout,不是幻覺;成敗
仍由 verifier 判定,status 不受影響。** 白話:就算讓模型看圖、讓它用座標點,**裁判權
還是沒有交給它** —— 眼睛換了,判分的人沒換。

> 不是「加了視覺所以更準」,是「加了視覺所以卡住時多一條路;準不準仍然由 verifier
> 說了算」。

三種模式:
- `AGENT_VISION=1`:每步都送截圖(圖像 token 花費最高)。
- 不設(預設,**auto**):平時走純文字;偵測到卡住(連續 3 步失敗/noop/give_up 被駁回,或頁面連續 3 步未變化)且 planner 支援多模態時,**自動切入視覺模式**,trace 記「🔍 切換視覺模式」,之後每步附截圖。mock/scripted planner 不會升級。
- `AGENT_VISION=0`:全關(backend 不支援圖像時由操作者明確宣告)。

auto 這條是一筆講得出價錢的交易:**用「卡住才睜眼」換掉「每步都付圖像 token」。**
觸發條件不是感覺,是寫死的:連續 3 步失敗/noop/give_up 被駁回,或頁面連續 3 步未
變化。而且它會在 trace 裡留一行「🔍 切換視覺模式」——**升級這件事本身也是可稽核的,
不是偷偷發生的**。

## 誠實邊界(我無法在此環境替你完成的部分)

**這節不藏在附錄,拉到跟其他節同一個層級。** 下面三件事是我做不到、或還沒替你驗過的:

- `codex login` 的 OAuth 需要**你本人在瀏覽器登入 ChatGPT**——我無法代做,也不該碰你的憑證。
- `codex exec` 的實際輸出格式依你安裝的 codex 版本;gateway 的 codex 後端依官方 non-interactive 文件實作(`--sandbox read-only --output-schema`),但**請用 `--backend mock` 先確認 gateway↔agent 通,再切 codex 後端跑一次確認你的 codex 版本相容**。gateway 的 HTTP/回應層已有測試覆蓋。
- 若 `codex exec` 回傳格式與預期不同,調整 `tools/codex_gateway.py::CodexBackend.complete` 的解析(已用 `_extract_json_object` 容錯抓第一個合法 JSON)。

第二點請讀仔細,我不想它被誤讀成比實際更強的宣稱:**已有測試覆蓋的是 gateway 的
HTTP/回應層,不是「你那一版 codex 一定相容」。** codex 後端是照官方 non-interactive
文件實作的(`--sandbox read-only --output-schema`),但你的 codex 版本輸出格式對不對
得上,**我沒替你測過,你得自己跑一次**。這就是為什麼上面那條「先 mock、再 codex」不
是客套話。
