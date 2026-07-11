# wealth-sec — Task 2 public frontend + API

FastAPI wrapper over `packages/sec_core` (read-only import, never patched).
Graders operate everything from the browser at `/`; the prebuilt static eval
dashboard is served at `/dashboard`.

- 選 filing:ticker/CIK + 年度(accession)挑選,列表為即時 EDGAR 查詢(容器內
  `data/raw_filings` cache 為空、每 instance 自暖,不假設暖 cache)。
- 上傳 filing:`POST /api/upload`(test_center 移除的 `_ingest_html` 以正式
  route 重新啟用),離線抽取、不連 EDGAR。
- 長時抽取走背景 job(ThreadPoolExecutor,`MAX_CONCURRENCY` 預設 2)+ GET 輪詢,
  不長掛 HTTP 請求。
- 每 item 回 status / confidence / provenance / needs_review + topic oracle +
  Item 8 XBRL 認證;未分類 gap 與獨立 exhibit 一併列出(完整優先於分類)。
- 失敗可檢視:error job 保留 exception + traceback(`GET /api/jobs`、
  `GET /api/jobs/{id}`);誠實拒絕(如 TSM 為 20-F 申報者)原文呈現。
- 原始檔 byte-for-byte 下載(`/api/jobs/{id}/raw`)供獨立驗證。

## Endpoints

| Method | Path | 說明 |
|---|---|---|
| GET | `/` | 操作 UI(單檔,adapted 自 test-center SEC panel) |
| GET | `/dashboard` | 靜態 eval dashboard(`apps/web/eval-dashboard/index.html`) |
| GET | `/api/health` | 健康檢查 + `SEC_EDGAR_USER_AGENT` 是否已設 |
| GET | `/api/filings?query=INTC` | 該公司全部 10-K(最新在前);非 10-K 申報者回誠實拒絕 |
| POST | `/api/extract` `{"ticker":"AAPL","accession":""}` | 排背景抽取 job,回 `job_id`(`query` 亦可) |
| POST | `/api/upload` (multipart `file`) | 離線抽取上傳的 10-K HTML,同步回完整 items + `job_id` |
| GET | `/api/jobs` | 近期 jobs(含失敗案例) |
| GET | `/api/jobs/{id}` | job 狀態;done 時併入 `meta/items/gaps/exhibits`,error 時含 `error/trace` |
| GET | `/api/jobs/{id}/item?code=1A` | source-exact 原文(亦支援 `gap:<a>-<b>`、`ex:<n>`) |
| GET | `/api/jobs/{id}/find?q=...` | 全文搜尋(items + gaps + exhibits) |
| GET | `/api/jobs/{id}/raw` | 原始 filing byte-for-byte 下載 |

## Env vars

| Name | Required | 說明 |
|---|---|---|
| `SEC_EDGAR_USER_AGENT` | yes | SEC fair-access 要求的真實聯絡字串,例:`wealth-sec p76091014@gs.ncku.edu.tw`。未設時抽取 job 會以明確錯誤失敗,`/api/health` 回報 `sec_user_agent_configured:false` |
| `PORT` | no | Zeabur 注入(8080);本機 fallback 8080 |
| `ACCESS_TOKEN` | no | 預設不設 → 完全開放。設了之後 `/api/*`(health 除外)需 `X-Access-Token` header 或 `?token=`;UI 支援 `/?token=...` |
| `MAX_CONCURRENCY` | no | 同時抽取 job 數,預設 2(每 job 自有 fetcher,各自 0.5s/req 限速) |

## Local build / run / smoke

```sh
cd E:/Side_Project/wealth

# build — tar-pipe the context to exclude .venv/data/runs (no .dockerignore in repo)
tar --exclude=.venv --exclude=data --exclude=runs --exclude=.git \
    --exclude=node_modules -cf - . \
  | docker build -t wealth-sec -f apps/services/sec/Dockerfile -

# run
docker run --rm -p 8080:8080 \
  -e SEC_EDGAR_USER_AGENT="wealth-sec p76091014@gs.ncku.edu.tw" \
  wealth-sec

# smoke
curl -sf http://localhost:8080/api/health
JOB=$(curl -sf -X POST http://localhost:8080/api/extract \
  -H 'Content-Type: application/json' -d '{"ticker":"AAPL"}' | jq -r .job_id)
# poll until status=done (first run fetches live from EDGAR, ~30–90 s)
curl -s http://localhost:8080/api/jobs/$JOB | jq '{status, items: (.items|length? // 0)}'
curl -sf http://localhost:8080/dashboard | head -c 200
curl -sf -X POST http://localhost:8080/api/upload \
  -F "file=@data/raw_filings/<some>.bin;filename=fixture.htm;type=text/html" | jq .meta
```

Zeabur:以 repo root 為 build context、`apps/services/sec/Dockerfile` 部署,
變數只設 `SEC_EDGAR_USER_AGENT`。`data/raw_filings/`、`runs/` 已在 `.gitignore`,
git-based 上傳不會帶進 image。
