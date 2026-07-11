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

### wealth-agent

| 變數 | 必要 | 值的來源(本地) | 說明 |
|---|---|---|---|
| `AGENT_LLM_MODE` | 是 | 本地預設 `gateway`(config/agent.toml);**Zeabur 上必須設 `direct`**(codex OAuth gateway 只存在本機,容器連不到) | `gateway`/`direct`/`mock` |
| `OPENAI_BASE_URL` | 是(direct) | 本地未設(走 gateway `http://127.0.0.1:8791/v1`);Zeabur 上填實際 OpenAI-compatible endpoint | |
| `OPENAI_API_KEY` | 是(direct) | 本地不存在(codex OAuth 免 key);Zeabur 上填你的 key,**只存 Zeabur variables** | |
| `OPENAI_MODEL` | 是(direct) | config/agent.toml 預設 `gpt-5.3-codex`(僅適用 gateway);Zeabur 上填 endpoint 支援的 model | |
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
| item 內文 | `GET /api/jobs/<id>/item?code=1A` | source-exact 全文 |
| 誠實拒絕 | `POST /api/extract` body `{"ticker":"TSM"}` | error job,`NotA10KFilerError`(20-F) |
| auth(若設 ACCESS_TOKEN) | `GET /api/jobs` 無 token | 401;帶 `X-Access-Token` → 200 |

### wealth-agent(`https://<prefix-agent>.zeabur.app`)

| 檢查 | URL / 動作 | 預期 |
|---|---|---|
| health | `GET /api/health` | 200,planner 顯示 LLM (direct) 且 `ready: true` |
| UI | `GET /` | 200 |
| mock task | 提交 `mock:v2` 任務 | status=pass,confidence=1.0,有 trace + screenshots |
| 真實網站 | 提交 Wikipedia 查詢任務 | pass,證明容器 egress + LLM 鏈路 |

## 部署 ID 記錄(首次部署後填入)

| 項目 | ID |
|---|---|
| Project ID | _(待填)_ |
| wealth-sec Service ID | _(待填)_ |
| wealth-agent Service ID | _(待填)_ |
| wealth-sec URL | _(待填)_ |
| wealth-agent URL | _(待填)_ |
