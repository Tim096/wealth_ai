# Attribution & License Stance

> 站在巨人的肩膀上——但守住授權界線。研究(`docs/prior_art.md`)調查後的明確立場:
> **copyleft(GPL/AGPL)專案只借「想法」,不抄「程式碼」;permissive(MIT/Apache)專案才可 vendor / 改寫程式碼並保留出處。** 抄 GPL/AGPL 程式碼會讓整個 repo 被 copyleft 傳染,這對交付作品是不可接受的風險。

## 已納入的借鑑(clean-room 重寫,非複製貼上)

| 來源 | 授權 | 我們借了什麼 | 落地位置 |
|---|---|---|---|
| [EmergenceAI/Agent-E](https://github.com/EmergenceAI/Agent-E) | **MIT** | `mmid` DOM-distillation 概念:observe 時對每個互動元素蓋一個穩定 id,repair 後用該 id 精準定位「剛剛看到的那個元素」,而非重建可能不唯一的 CSS selector | `packages/browser_agent/observer.py`:observe 時蓋 `data-aid`;`repair.py`:action 用 `[data-aid=N]`(精準),memory 存 durable semantic selector(可跨 reload) |
| [nlpaueb/edgar-crawler](https://github.com/nlpaueb/edgar-crawler) | **GPLv3 → 僅借想法** | 「item boundary = 到下一個有效 item heading」與 TOC false-positive 需過濾短假 heading 的**觀念**。我們的多 detector + 加權 TOC filter 是**獨立重寫**,未參考其原始碼 | `sec_core/{headings,toc,boundary}.py`(clean-room) |

## 第四/第五仲裁票(P0-7;engines 只投票,不產文)

| 來源 | 授權 | 使用方式 | 落地位置 |
|---|---|---|---|
| [nlpaueb/edgar-crawler](https://github.com/nlpaueb/edgar-crawler) | **GPLv3**(P0-7a 前置:2026-07-10 於 `--depth 1` clone 實讀 LICENSE **再驗證**,commit `84a8d0c5dd7dd6769526e5ccec534c4e0880d56f`)→ **不 vendor、不 import、不 link** | **arms-length subprocess**:未修改的上游 CLI(`extract_items.py`)在本地 checkout(gitignored `data/raw_filings/external/edgar_crawler/`,pin 同上 commit)以獨立 process 執行,僅以檔案溝通——GPLv3 下的 mere aggregation,非衍生作品;checkout 不隨 repo 散布。其 README 要求學術引用 Loukas et al. 2021(EDGAR-CORPUS)。**Lineage 註記**:EDGAR-CORPUS 即此程式所建,edgar-crawler 票與 corpus teacher 票同血統,永不各算一票 | `sec_core/engines/edgar_crawler_vote.py` + `tools/triangulate.py`;subprocess 所需 permissive 依賴列於 pyproject `crawler-vote` extra |
| [john-friedman/datamule-python](https://github.com/john-friedman/datamule-python) | **MIT**(pip `datamule==5.0.1`;2026-07 調研 pin 上游 commit `122fc54` 2026-06-25,解析後端 = doc2dict 樣式驅動) | 第五票:`sec_core/engines/datamule_vote.py` 以 `Document.parse()` + `get_section(title_class="item")` 抽 item。**無公開 accuracy benchmark——當票不當 gold**;與我方 regex 驅動、edgartools、edgar-crawler 皆實作獨立 | `sec_core/engines/datamule_vote.py`;pyproject `sec` extra |
| [sec-api.io](https://sec-api.io) Extractor API | 商業 ToS:**cached responses 僅供內部 eval,不可再散布原文 payload**;free tier = **100 lifetime calls** | 外部仲裁票(P0-7b):`tools/arbitrate_secapi.py` cache-first(回應落盤才使用)、`--max-calls` 顯式預算、無 `SECAPI_KEY` 時僅產 ready-to-run 狀態文件(**絕不代辦註冊**);artifacts 只存 verdict/字數,payload 進 gitignored `data/sec_eval/arbitration/cache/` | `tools/arbitrate_secapi.py` + `data/sec_eval/arbitration/` |

## 明確未做的事(授權風險規避)

- **未** 複製 edgar-crawler(GPLv3)、Skyvern(AGPL)、py-sec-edgar(AGPL 商用)的任何程式碼。這些只用於「確認我們的方向 / 借觀念」。
- **未** 引入這些 repo 為執行期相依。

## 可安全深化的 permissive 依賴(roadmap)

- [dgunning/edgartools](https://github.com/dgunning/edgartools)(MIT):可作 EDGAR fetch / XBRL 標準化的參考或選配依賴。
- [jadchaar/sec-edgar-downloader](https://github.com/jadchaar/sec-edgar-downloader)(MIT):fetch 層可替換。
- Benchmark:WebArena / WebVoyager(研究用授權,跑評測 OK,勿把其網站資產當產品碼發佈)。

## 差異化(研究確認為 novel,無 prior art 可 defer)

三態 `unknown` 一級公民、a11y self-repair 綁定驗證迴圈、source-exact spans、**XBRL 認證 Item 8 span**——這些在調查的開源專案裡沒有直接對應物。詳見 `docs/prior_art.md`。
