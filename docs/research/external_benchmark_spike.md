# P0-2 Spike:NTU itemseg 外部 benchmark 可行性(2026-07-10)

> 結論先講:**dataset 可取得(公開 HTTP,已實測下載 + 解檔 + 跑分)**;
> **公開 leaderboard 不存在**——backlog 原文「對照公開 leaderboard」的假設錯誤,
> 可對照的只有論文自報數字(見 §3 的度量不可直接互比 caveat)。
> 授權為 research-only 級(CC BY-NC 系),走 **download-script route**,資料永不入 repo。

## 1. 可得性(spike 實測,非文獻宣稱)

| 項目 | 實測值 |
|---|---|
| 論文 | arXiv 2502.08875(Lu/Chien/Yen/Chen,NTU + 北商大;accepted at Journal of Information Systems) |
| Dataset URL | `https://www.im.ntu.edu.tw/~lu/data/itemseg/itemseg10kdata.7z`(論文 footnote 1) |
| HTTP 狀態 | 200 OK(2026-07-10),`Content-Length: 148468503`,Last-Modified 2025-01-06 |
| sha256 | `769bc7da89cdd0c53f8182f74d294be23839607ad9e75735767be445d1efd727`(凍結於 tools/fetch_ntu_itemseg.py,重跑必驗) |
| 內容 | 3,737 份 10-K(2001–2019):`training_csv/` 3,364 + `test_csv/` 373 + `report_list.csv`(fold/uid/cik/date_filed/EDGAR link/SIC) |
| 標註格式 | 每檔一 CSV,欄位 `label,Content`:line-level BIO(`O` / `B<code>` / `I<code>`,code 即 item 碼如 `1A`、`9B`、`15`) |
| 程式碼 repo | `https://github.com/hsinmin/itemseg`(推論工具,BIO 輸出同格式) |

Backlog 修正:**無公開 leaderboard**(GitHub repo、paperswithcode、論文正文皆無)。
外部對標的形狀是「同一 test fold 上與論文自報數字並列」,不是排行榜提交。

## 2. 授權判定(three-tier rule)

- 論文本身:arXiv 頁 CC BY 4.0(只涵蓋論文文字)。
- 程式碼 repo `hsinmin/itemseg`:README 明載 **CC BY-NC 4.0**(non-commercial)。
- Dataset 壓縮檔內 **無任何 LICENSE/README**(3,741 entries 全列過);期刊版 Data Availability 卻寫 "Data available upon request",與 footnote 公開 URL 並存。
- 判定:授權訊號矛盾且最嚴格解讀為 non-commercial → **tier「unclear/research-only」→ download-script route**:
  - `tools/fetch_ntu_itemseg.py` fetch-on-demand 到 `data/raw_filings/external/ntu_itemseg/`(位於既有 gitignore 的 `data/raw_filings/` 之下,結構上不可能被 commit);
  - 不 vendor、不節錄 fixture(連小樣本都不入庫,因為逐行內容即標註資產本體);
  - 引用義務:任何使用其數字的文件引 arXiv 2502.08875。
- **待辦(檔案非本項所有)**:`docs/ATTRIBUTION.md` §4 需補一列——
  `NTU itemseg dataset(arXiv 2502.08875)| CC BY-NC 系 research-only(repo CC BY-NC 4.0;archive 無 LICENSE)| P0-2 外部 benchmark,fetch-on-demand 不入庫(tools/fetch_ntu_itemseg.py)`。

## 3. Adapter 度量(tools/head_to_head.py)

每個 engine 的統一介面是 `item_code -> text`。對 NTU 每一條非瑣碎 gold line
(alnum-normalized 後 ≥8 字元),測其是否為某 item 正規化全文的 substring:

- `tp(item)` = 該 item 的 gold lines 中被該 item 文字涵蓋者
- `fn(item)` = 該 item 的 gold lines 未被涵蓋者
- `fp(item)` = 非該 item(含 `O`)的 lines 卻被涵蓋者
- per-item P/R/F1;macro-F1 只平均「有 gold lines 的 item」(fp-only item 列出但不進 macro)

正規化 = lowercase + 只留 alnum,對 inscriptis(NTU 的 HTML→text)、我方 normalizer、
edgartools renderer 三種渲染差異穩健。

**不可互比 caveat(誠實記錄)**:論文自報數字(BERT4ItemSeg core-item macro-F1
0.9825、GPT4ItemSeg 0.9567)是 **per-line BIO 分類 F1**——模型直接對每行打標。
我們的 containment adapter 是把 span 輸出投影回行,是**下界**(engine 內文任何
渲染丟字都算 fn)。兩組數字同表並列時必須帶此註;宣稱「超越」只能在
**同一 adapter 下的 head-to-head 欄位間**成立(ours vs edgartools vs datamule),
不能跨到論文欄位。

## 4. Head-to-head 骨架現況

- 參賽 engine:`ours`(sec_core pipeline)、`edgartools`(5.42.0,重用
  third_engine.extract_items_edgartools,同 raw bytes 離線解析)、`datamule`
  (adapter 佔位,拋 EngineUnavailable;等 P0-7c 的 engine module 落地後接上,
  整合點:`tools/head_to_head.py:run_datamule`)。sec-parser 無 end-to-end item
  extractor,不參賽(如實註記,同 giants_task2.md §5.5)。
- 抽樣:test fold 按 date_filed 排序等距抽(era-stratified),**硬上限 30 份**
  (corpus-run bound;超過即 ValueError)。
- 取檔:sec_core.fetcher.EdgarFetcher(rate-limited + disk cache),需
  `SEC_EDGAR_USER_AGENT`。
- 姊妹交付物 B hook 已接:ours 每 item 記 `status/confidence/needs_review`,
  artifact 報 `verifier_false_pass` = line-F1 < 0.5 且 verifier 全綠
  (無 needs_review 且 confidence ≥ 0.6)的 item。

### 3 份 smoke(2026-07-10;只證管線通,樣本太小不構成任何排名宣稱)

| uid | filing | ours macro-F1 | edgartools macro-F1 |
|---|---|---|---|
| 7192675 | 2001 `.txt`(pre-2002 text format) | engine 失敗(no items) | engine 失敗(no items) |
| 9078974 | 2008 HTML(Kodiak) | 0.605(verifier_false_pass:['1']) | 0.1745 |
| 13204932 | 2012 HTML | 0.7597 | engine 失敗(no items) |

誠實註記:(a) 2001 `.txt` 兩邊全掛——NTU test fold 含 pre-2002 text filings,
正好命中 §2.1 的 pre-era 缺口,正式跑分前需 P0-1 的 form-era 處理或在報表中
分 era 欄;(b) uid 9078974 我方 item 1 F1 0.4731 但 verifier 全綠 → deliverable B
的 false-pass 訊號真的會亮,校準素材成立;(c) items 10–13 F1 ≈ 0.5 的型態
是 IBR(incorporated by reference)——gold 把 heading+pointer 行都算 item,
我方只留 stub,屬度量口徑差異,正式報告需註記。

## 5. 正式跑分(未跑,後續)

1. `tools/fetch_ntu_itemseg.py`(test split,~150 MB)
2. `SEC_EDGAR_USER_AGENT=... tools/head_to_head.py --slice 30 --engines ours,edgartools`
3. artifact `data/sec_eval/scoring/head_to_head.json` + markdown 表進 eval_report
4. datamule 接上後加 `--engines ...,datamule`

## 6. 本 spike 交付檔

- `tools/fetch_ntu_itemseg.py` — download-script(sha256 凍結)+ gold loaders
- `tools/head_to_head.py` — 同場競技 harness + line-level per-item F1 adapter + deliverable B hook
- `tests/test_external_benchmark.py` — loaders/度量/抽樣上限,離線 10 tests
- 依賴:`py7zr`(僅 fetch 時 lazy-import;建議入 dev deps,檔案非本項所有)
