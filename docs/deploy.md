# Zeabur 部署指南

兩個獨立 service,同一個 repo root 作為 build context。Docker 本地驗證已通過(2026-07-10,零修正)。

## 拓撲

```
Zeabur project(單一 project,兩個 service)
├── wealth-sec    ← Dockerfile.wealth-sec    (SEC 10-K Extractor API + eval dashboard)
└── wealth-agent  ← Dockerfile.wealth-agent  (Browser Agent frontend + API,內含 Playwright Chromium)
```

- 兩個 service 互不依賴,可獨立部署、獨立重啟。
- Zeabur 對同一 repo 的多 service 依 `Dockerfile.<service-name>` 命名慣例選 Dockerfile;根目錄的 `Dockerfile.wealth-sec` / `Dockerfile.wealth-agent` 與 `apps/services/{sec,agent}/Dockerfile` 內容一致(本地 Docker 驗證用後者,Zeabur 用前者;改動時兩邊同步)。
- 根目錄 `.dockerignore` 排除 `.venv`(461MB)、`data/raw_filings`(359MB)、`runs`;`data/mock_sites` 為 wealth-agent runtime 必需,**不可**排除。
- `PORT` 由 Zeabur 注入(8080),CMD 已處理 fallback,無需設定。

## 環境變數

**規則:值只放 Zeabur service variables,絕不進 repo、絕不寫進文件。** 下表只列名稱與本地來源。

### wealth-sec

| 變數 | 必要 | 值的來源(本地) | 說明 |
|---|---|---|---|
| `SEC_EDGAR_USER_AGENT` | 是 | 本地 PowerShell session 手動設定(`$env:SEC_EDGAR_USER_AGENT`,格式 `姓名 email`,見 README killer demos 段) | EDGAR 要求的 UA;`/api/health` 的 `sec_user_agent_configured` 會回報是否已設 |
| `ACCESS_TOKEN` | 否 | 部署時自訂(隨機字串),只存在 Zeabur | 設定後除 `/api/health` 外均需 `X-Access-Token` header 或 `?token=`;不設 = 公開(評測者免 auth) |
| `MAX_CONCURRENCY` | 否 | — | 抽取 worker 數,預設 2 |
| `PREWARM_TICKERS` | 否 | — | 容器啟動時背景預熱的 tickers,預設 `INTC,AAPL,MSFT`;設空字串停用 |

### wealth-agent

| 變數 | 必要 | 值的來源(本地) | 說明 |
|---|---|---|---|
| `AGENT_LLM_MODE` | 是 | 本地預設 `gateway`(config/agent.toml);**Zeabur 上必須設 `direct`**(codex OAuth gateway 只存在本機,容器連不到) | `gateway`/`direct`/`mock` |
| `OPENAI_BASE_URL` | 是(direct) | 本地未設(走 gateway `http://127.0.0.1:8791/v1`);Zeabur 上填實際 OpenAI-compatible endpoint | |
| `OPENAI_API_KEY` | 是(direct) | 本地不存在(codex OAuth 免 key);Zeabur 上填你的 key,**只存 Zeabur variables** | |
| `OPENAI_MODEL` | 是(direct) | config/agent.toml 預設 `gpt-5.3-codex`(僅適用 gateway);Zeabur 上填 endpoint 支援的 model | |
| `DEPLOY_COMMIT_SHA` | 是(attested eval) | 每次 deploy 前取 `git rev-parse HEAD` | `/api/health.build_sha`;runner 在送題前強制比對 |
| `ACCESS_TOKEN` | 否 | 同 wealth-sec | |
| `AGENT_QUEUE_LIMIT` | 否 | — | 任務佇列上限,預設 10 |

## 部署(zeabur CLI,一律 `npx zeabur@latest ... -i=false`)

前置:確認/建立 project(若無 project,用 zeabur-project-create skill 流程,勿直接跑 `project create`):

```bash
npx zeabur@latest project list -i=false --json
```

### 首次部署(repo root 執行;不帶 --service-id 會建新 service)

```bash
# wealth-sec
npx zeabur@latest deploy --project-id <project-id> --name wealth-sec --json -i=false

# wealth-agent(image 較大:Playwright Chromium ~1.2GB layer,build 較久屬正常)
npx zeabur@latest deploy --project-id <project-id> --name wealth-agent --json -i=false
```

回應含 `service_id`,**立刻記錄**到下方 ID 表(repo 的 `.gitignore` 排除 CLAUDE.md,故記在這裡)。

### 設定環境變數(create 首次 / update 改值;一律用 service ID)

```bash
npx zeabur@latest variable create --id <sec-service-id> \
  -k "SEC_EDGAR_USER_AGENT=<name email>" \
  -y -i=false

npx zeabur@latest variable create --id <agent-service-id> \
  -k "AGENT_LLM_MODE=direct" \
  -k "OPENAI_BASE_URL=<endpoint>" \
  -k "OPENAI_API_KEY=<key>" \
  -k "OPENAI_MODEL=<model>" \
  -y -i=false
```

改變數後 restart 才生效(或直接 redeploy)。

### 綁定公開網域

```bash
npx zeabur@latest domain create --id <sec-service-id>   -g --domain <prefix-sec>   -y -i=false
npx zeabur@latest domain create --id <agent-service-id> -g --domain <prefix-agent> -y -i=false
# -g = Zeabur 產生的 *.zeabur.app;--domain 只填 prefix(≥3 字元,不含點)
```

### Redeploy(更新既有 service;**必帶 --service-id,否則會建重複 service**)

```bash
npx zeabur@latest deploy --project-id <project-id> --service-id <sec-service-id>   --json -i=false
npx zeabur@latest deploy --project-id <project-id> --service-id <agent-service-id> --json -i=false
```

失敗時看 log:用 zeabur-deployment-logs skill(`npx zeabur@latest` 對應指令),port 問題查 zeabur-port-mismatch skill。

## 部署後 smoke test

### wealth-sec(`https://<prefix-sec>.zeabur.app`)

| 檢查 | URL / 動作 | 預期 |
|---|---|---|
| health | `GET /api/health` | 200,`sec_user_agent_configured: true` |
| dashboard | `GET /` 與 `GET /dashboard` | 200 HTML |
| 抽取 | `POST /api/extract` body `{"ticker":"AAPL"}` | job → done,23 items,coverage ≈ 0.89 |
| 抽取(重複查詢) | 同上再打一次 | **同一 response 直接 `status=done` + 完整 payload**(result memo cache hit,零輪詢;實測 ~0.6s,舊版需輪詢 1.6–2.8s)|
| item 內文 | `GET /api/jobs/<id>/item?code=1A` | source-exact 全文 |
| 誠實拒絕 | `POST /api/extract` body `{"ticker":"TSM"}` | error job,`NotA10KFilerError`(20-F) |
| auth(若設 ACCESS_TOKEN) | `GET /api/jobs` 無 token | 401;帶 `X-Access-Token` → 200 |

### wealth-agent(`https://<prefix-agent>.zeabur.app`)

| 檢查 | URL / 動作 | 預期 |
|---|---|---|
| health | `GET /api/health` | 200,planner 顯示 LLM (direct)、`ready: true`、`build_sha` 等於 deployed source HEAD |
| UI | `GET /` | 200 |
| mock task | 提交 `mock:v2` 任務 | status=pass,confidence=1.0,有 trace + screenshots |
| 真實網站 | 提交 Wikipedia 查詢任務 | pass,證明容器 egress + LLM 鏈路 |

## 部署 ID 記錄(2026-07-10 上線,Tencent Ashburn)

| 項目 | ID / URL |
|---|---|
| Server ID (Tencent Ashburn) | `6a50e77ae33921bfb5d0f994` |
| Project ID | `6a50ea01f04125ac9a347957` |
| Environment ID | `6a50ea01104975fcb46760b2` |
| wealth-sec Service ID | `6a50ea51f04125ac9a34798c` |
| wealth-agent Service ID | `6a50ea7ff04125ac9a34799b` |
| **wealth-sec URL** | **https://wealth-sec-ncku.zeabur.app** |
| **wealth-agent URL** | **https://wealth-agent-ncku.zeabur.app** |

### 效能(2026-07-10 redeploy 後實測)

- wealth-sec:JobStore result memo(done job 依 kind/label/accession 直接命中)+ `POST /api/extract` cache hit 內嵌完整 payload(零輪詢)+ GZipMiddleware + 啟動 prewarm(`PREWARM_TICKERS`)。AAPL warm repeat:**0.6s / 0 polls / gzip ~1.3KB**(redeploy 前 1.6–2.8s / 需輪詢)。
- 前端:poll 首查即刻、間隔 400ms(原 1500ms);loadYears 改背景執行(省最多 2.1s);find 輸入 debounce 300ms。

### 上線驗證(response-content 實測)

- **wealth-sec** — `GET /api/health` → `{"ok":true,"sec_user_agent_configured":true,"auth_required":false}`;`POST /api/extract {"ticker":"AAPL"}` → job `done`,**23 items**;`GET /` → 200(dashboard)。**完全可用,免 auth。**
- **wealth-agent** — 2026-07-11 起為 **direct 模式(OpenRouter `x-ai/grok-4.5`)**:`GET /api/health` → `{"ok":true,"ready":true,"mode":"direct","llm_ok":true,"model":"x-ai/grok-4.5"}`;live smoke test 實跑 Wikipedia 查詢任務(Eiffel Tower 完工年份)→ **status=pass**,`answer_matches:[0-9]{4}` 命中,容器 egress + OpenRouter + verifier 全鏈路驗證(task `t3738698837-0`)。key 只存 Zeabur variables,不進 repo。免 key 示範任務以 `GET /api/demo` 的即時列表為準並固定走 MockPlanner。歷史紀錄:2026-07-10 上線時為 mock 模式(repo 內無雲端 LLM 憑證)。

### wealth-agent:改用真實 LLM 需在 Zeabur dashboard 補的變數

`AGENT_LLM_MODE=mock` 已設。要讓 planner 走真實 OpenAI-compatible LLM,將其改為 `direct` 並補以下三個(值只放 Zeabur variables,勿進 repo):

| 變數 | 值 |
|---|---|
| `AGENT_LLM_MODE` | `direct`(把現有的 `mock` 改成 `direct`) |
| `OPENAI_BASE_URL` | 你的 OpenAI-compatible endpoint(如 `https://api.openai.com/v1`) |
| `OPENAI_API_KEY` | 你的 key |
| `OPENAI_MODEL` | endpoint 支援的 model 名 |

補完後 restart wealth-agent(`service restart --id 6a50ea7ff04125ac9a34799b -y -i=false`)即生效;`/api/health` 的 `mode` 會變 `direct`、planner 不再是 MockPlanner。

### OpenRouter(建議)

LLM client 走標準 OpenAI-compatible `/chat/completions` + Bearer key,OpenRouter 直接可用。Zeabur variables 設這 4 個(缺 key 時 `/api/health` 會回 `llm_env_required` 列出同樣 4 個變數,UI 顯示示範模式 banner):

| 變數 | 值 |
|---|---|
| `AGENT_LLM_MODE` | `direct` |
| `OPENAI_BASE_URL` | `https://openrouter.ai/api/v1` |
| `OPENAI_API_KEY` | OpenRouter key(`sk-or-v1-…`,只存 Zeabur variables,勿進 repo) |
| `OPENAI_MODEL` | OpenRouter model slug,如 `openai/gpt-4o-mini` |

注意:client 每次呼叫都帶 `response_format: {"type":"json_object"}`,vision 升級時附 base64 截圖 — 選支援 structured output(+vision 更佳)的模型。設定後 restart,`/api/health` 應顯示 `mode: "direct"` 與 `model`。

### 免 key 示範(示範任務)

未設任何 LLM 變數(或 `AGENT_LLM_MODE=mock`)時,UI 顯示「示範任務」區；preset 以 `GET /api/demo` 的即時列表為準，涵蓋基準搜尋、介面漂移自我修復、注入防禦、capability guard 與 honest-unknown 路徑，並以內建 mock 網站 + 確定性 MockPlanner 完整跑通(live 進度 / 軌跡 / 截圖與真實 run 相同)。API:`POST /api/demo/{id}` 派工。設了 key 之後示範按鈕仍固定走 MockPlanner(穩定展示、零 token 成本),自然語言任務才走 LLM。
