# wealth-sec — Task 2 public frontend + API

**一句話**:給我一個公司代號,我把它整份 10-K 年報抓下來、切成一段一段、每段都
附上「這段原文在哪、我有多確定」,而且原始檔可以整份下載回去自己對。

這份 README 分四段:**這服務在做什麼** → **有哪些 endpoint** → **要設哪些環境變數**
→ **本機怎麼 build / run / 冒煙測**。第一次跑的人請照順序讀,下面的指令可以直接貼。

## 這服務在做什麼?

FastAPI wrapper over `packages/sec_core`(read-only import, never patched)。
白話:這個資料夾是門市,`packages/sec_core` 是引擎室 —— 門市不改引擎,只是把它
接到瀏覽器上。

Graders operate everything from the browser at `/`;the prebuilt static eval
dashboard is served at `/dashboard`。**不是「請你 clone 下來自己跑」,是打開網頁就能操作。**

拆成六件事:

- 選 filing:ticker/CIK + 年度(accession)挑選,列表為即時 EDGAR 查詢(容器內
  `data/raw_filings` cache 為空、每 instance 自暖,不假設暖 cache)。
  白話:新開的容器裡沒有預先塞好的資料,第一次查誰就當場去 SEC 抓誰 —— 我不靠
  「事先準備好的樣本」讓 demo 好看。
- 上傳 filing:`POST /api/upload`(test_center 移除的 `_ingest_html` 以正式
  route 重新啟用),離線抽取、不連 EDGAR。
  白話:你可以拿你自己的 10-K HTML 檔丟進來,完全不碰網路 —— 這條路徑排除了
  「他是不是只對某幾家公司調好了」的懷疑。
- 長時抽取走背景 job(ThreadPoolExecutor,`MAX_CONCURRENCY` 預設 2)+ GET 輪詢,
  不長掛 HTTP 請求。
  白話:抽一份年報不是瞬間的事,與其讓瀏覽器空轉到 timeout,不如先給你一張號碼牌
  (`job_id`),你自己回來查進度。
- 每 item 回 status / confidence / provenance / needs_review + topic oracle +
  Item 8 XBRL 認證;未分類 gap 與獨立 exhibit 一併列出(完整優先於分類)。
  白話:provenance = 這段文字在原始檔的哪個位置;needs_review = 我自己標記
  「這段我沒把握,請人看一眼」。**不是分類不到就丟掉 —— 分不出來的段落(gap)
  照樣列給你看。完整優先於分類。**
- 失敗可檢視:error job 保留 exception + traceback(`GET /api/jobs`、
  `GET /api/jobs/{id}`);誠實拒絕(如 TSM 為 20-F 申報者)原文呈現。
  白話:壞掉的 job 不會被藏起來,連 Python 的錯誤堆疊都留著給你看。TSM 這種
  「它根本不申報 10-K、它報的是 20-F」的案子,我直接說做不到,**不硬湊一個
  看起來有結果的結果。**
- 原始檔 byte-for-byte 下載(`/api/jobs/{id}/raw`)供獨立驗證。
  白話:byte-for-byte = 一個位元組都不差。你可以把原始檔拉回去,自己用任何工具
  重算一遍,不必相信我的抽取。

> 不是「相信我的分類」,是「原始檔給你、位置給你、沒把握的地方我先舉手」。

## 有哪些 endpoint?

三類看:**打開來看**(`/`、`/dashboard`、`/api/health`)、**派工**
(`/api/filings`、`/api/extract`、`/api/upload`)、**驗貨**(`/api/jobs` 那一族)。

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
| GET | `/api/jobs/{id}/normalized` | **offset 與 sha256 真正指向的那份 normalized 文字**;帶 `X-Normalized-Sha256` 與 `X-Normalization-Version` header |

三個值得單獨拎出來講的設計:

- `GET /api/jobs` **含失敗案例**。白話:失敗的 job 跟成功的 job 排在同一張清單裡。
  一個只列得出成功案例的系統,你沒辦法知道它失敗率多高。
- `source-exact` 原文 = 我回給你的字,是從原始檔裡照抄出來的,不是模型改寫過的
  摘要。**不是「模型說這段在講風險」,是「原始檔第幾個位元組到第幾個位元組,你自己看」。**
- `GET /api/jobs/{id}/normalized` 是**讓上一條真的驗得動**的那一塊。raw HTML 跟
  offset 指向的字串**不是同一個字串** —— 拿 raw 照 offset 剪,剪出來是 tag soup,
  sha 對不上。所以驗證配方是:下載這個檔 → 取 `text[start:end]`(多段 item 就把
  `source_ranges` 每段切出來接起來)→ 對 utf-8 bytes 算 sha256 → 等於該 item 的
  `normalized_sha`。**offset 是 Python str / code-point 索引,要切解碼後的文字,不要
  byte-slice。**

### `normalization_version`:offset 只在同一個 normalizer 版本下有效

`normalized_sha` / `offsets` / `source_ranges` **只對產生它們的那一版 normalizer 成立**,
所以每個回傳都掛著版本:`/api/jobs/{id}`(job meta 與 item 的 `normalization_version`
欄位)、`/api/jobs/{id}/item`、以及 `/api/jobs/{id}/normalized` 的
`X-Normalization-Version` header。

**現行值:`NORMALIZATION_VERSION` = `1.1`**(`packages/sec_core/normalize.py`)。

| 版本 | 變更 | 對 offset 的影響 |
|---|---|---|
| 1.0 | — | — |
| **1.1** | 新增 text mode(`looks_like_plain_text`):純文字 / SGML filing 保留行結構 —— pre-2001 的結構**全部在那些 `\n` 裡**,舊版把它們當空白吃掉 | **HTML 時代逐位不變**(text 與 `norm_to_raw` 皆 byte-identical);**純文字 filing 的 normalized text 與 offset 會改變**,1.0 時期存下來的 pre-2001 offset/sha 不可跨版沿用 |

**為什麼要把這件事寫在 API 契約裡,而不是 changelog?** 因為 offset 是這個服務的**產品本身**。
一個拿著 1.0 時期 offset 的使用者,在 1.1 上重驗 pre-2001 filing 會對不上 sha ——
**這時候他該看到的是「版本不同」,不是「你的資料錯了」。** 版本欄位就是為了讓這句話
講得出口。緣由(1.0 的行為是 bug 不是時代邊界)見 `docs/failure_gallery.md` FG-SEC-009。

## 要設哪些環境變數?

只有一個是必填。其他三個不設也能跑。

| Name | Required | 說明 |
|---|---|---|
| `SEC_EDGAR_USER_AGENT` | yes | SEC fair-access 要求的真實聯絡字串,例:`wealth-sec Your Name research@example.com`。未設時抽取 job 會以明確錯誤失敗,`/api/health` 回報 `sec_user_agent_configured:false` |
| `PORT` | no | Zeabur 注入(8080);本機 fallback 8080 |
| `ACCESS_TOKEN` | no | 預設不設 → 完全開放。設了之後 `/api/*`(health 除外)需 `X-Access-Token` header 或 `?token=`;UI 支援 `/?token=...` |
| `MAX_CONCURRENCY` | no | 同時抽取 job 數,預設 2(每 job 自有 fetcher,各自 0.5s/req 限速) |

每個設定的來歷,一個都不是拍腦袋:

- `SEC_EDGAR_USER_AGENT` —— **這是 SEC 的規矩,不是我的偏好**。SEC 要求爬他們的
  資料時附上真實聯絡方式。沒設的時候我讓 job **以明確錯誤失敗**,而不是偷偷帶一
  個假的 UA 混過去。`/api/health` 會誠實回報 `sec_user_agent_configured:false`。
- `MAX_CONCURRENCY` 預設 2 + 每 job `0.5s/req` —— 用速度換合規:同時開太多 job、
  打太快,就是在濫用 SEC 的免費服務。
- `ACCESS_TOKEN` 預設不設 → 完全開放 —— 用「任何人都能打」換「評審不必跟我要密碼」。

## 本機怎麼 build / run / 冒煙測?

照順序跑。build → run → smoke 三段,smoke 那段是在證明整條鏈是通的:健康檢查 →
派工 → 輪詢 → dashboard → 離線上傳。

```sh
cd E:/Side_Project/wealth

# build — tar-pipe the context to exclude .venv/data/runs (no .dockerignore in repo)
tar --exclude=.venv --exclude=data --exclude=runs --exclude=.git \
    --exclude=node_modules -cf - . \
  | docker build -t wealth-sec -f apps/services/sec/Dockerfile -

# run
docker run --rm -p 8080:8080 \
  -e SEC_EDGAR_USER_AGENT="wealth-sec Your Name research@example.com" \
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

第一次跑會慢 —— `~30–90 s`,因為 first run fetches live from EDGAR。這不是效能
問題,是前面說的「不假設暖 cache」的代價:**我用第一次的等待,換掉「demo 其實
是預先準備好的」這個懷疑。**

build 那行為什麼要 tar-pipe?註解已經寫了:`no .dockerignore in repo`。白話:repo
裡沒有 `.dockerignore`,不手動排除的話 `.venv/data/runs` 會整包被送進 build
context,又大又慢。

## 怎麼部署?

Zeabur:以 repo root 為 build context、`apps/services/sec/Dockerfile` 部署,
變數只設 `SEC_EDGAR_USER_AGENT`。`data/raw_filings/`、`runs/` 已在 `.gitignore`,
git-based 上傳不會帶進 image。

> 部署面只有一個變數要設 —— 不是我簡化了說明,是這個服務真的只需要這一個。
