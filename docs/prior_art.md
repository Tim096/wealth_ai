# Prior Art & Positioning

> 由兩個 research agent(web search)彙整,2026-07-10。目的:誠實對照既有開源、標明我們能借鑑什麼、以及我們的差異化在哪(哪些是 novel、有無 prior art 可 defer)。

## Task 1 — Browser Agent

| 專案 | 授權 | 我們能借鑑 | 與我們(verification-first)的關係 |
|---|---|---|---|
| [browser-use](https://github.com/browser-use/browser-use) | MIT | 成熟 action space、DOM index 標註;最大宗 prior art | 成功判定多靠 LLM 自評——正是我們三態契約要超越的 |
| [Stagehand](https://github.com/browserbase/stagehand) | MIT | **self-healing + action caching**,與我們 selector memory 幾乎同構;observe() 預檢 | 偏可維護/可快取,我們偏可驗證 |
| [Agent-E](https://github.com/EmergenceAI/Agent-E) | MIT | **與我們最同源**:a11y-tree DOM distillation、注入穩定 id、LLM 限定 skills(非任意 code)——我們 action-JSON + a11y 定位的學術背書(arXiv 2407.13032) | 缺三態契約驗證與 failure taxonomy |
| [Skyvern](https://github.com/Skyvern-AI/skyvern) | **AGPL-3.0** | 視覺定位抗版面漂移的思路(對照我們 v1→v2 drift) | 哲學互補;**勿複製程式碼(copyleft)** |
| [Healenium](https://github.com/healenium/healenium) | Apache-2.0 | selector self-healing 既有領域先例(ML 找最近 locator、持久化) | 純測試域、無 LLM、無任務語意驗證 |

**該跑的 benchmark(建立可信度):** [WebArena](https://github.com/web-arena-x/webarena)(**outcome-based 驗證,與我們 verifier 同哲學**,最該對標)、[WebVoyager](https://github.com/MinorJerry/WebVoyager);經 [BrowserGym/AgentLab](https://github.com/ServiceNow/BrowserGym) 接入最快。

**我們的差異化(綜合研究結論):** 沒有任一專案把 **unknown 當一級公民**;a11y-tree self-repair + persistent memory + **綁定三態驗證迴圈**的組合是我們獨有。v1→v2 adversarial drift eval 是現有 benchmark 缺的角度。

## Task 2 — SEC 10-K Extractor

| 專案 | 授權 | 我們能借鑑 | 與我們(source-exact + XBRL-certified)的關係 |
|---|---|---|---|
| [nlpaueb/edgar-crawler](https://github.com/nlpaueb/edgar-crawler) | **GPLv3** | **最接近的 prior art**:item regex、TOC false-positive filter、next-item boundary、`get_last_item_section()` fallback(WWW 2025 paper)。當作我們超越的 baseline 引用 | regex-only(vs 我們多 detector)、無 offset/sha256、**無 XBRL 驗證**;其 missing-item「抓剩餘文字」正是我們 wrapper handling 修掉的 naive 行為。**copyleft,借思路勿抄 code** |
| [dgunning/edgartools](https://github.com/dgunning/edgartools) | MIT | best-in-class **EDGAR fetch/cache/no-key** + XBRL 標準化財報。可當 fetch/XBRL 依賴或對照 | 用 XBRL *產生報表*,不是*驗證某段文字含報數字*——我們的 novel 之處 |
| [sec-api.io](https://github.com/janlukasschroeder/sec-api-python) | 商用(閉源) | item 變體覆蓋(10-K/A、10-KT)、競品準確度對標 | server-side 閉源,無法借;無 source-exact provenance |
| [alphanome-ai/sec-parser](https://github.com/alphanome-ai/sec-parser) | MIT(停維護) | HTML→semantic tree 當 heading 訊號補強 | 不做 Item 1–16 boundary、無 TOC、無 XBRL |
| [sec-edgar-downloader](https://github.com/jadchaar/sec-edgar-downloader) | MIT | 乾淨 downloader + fair-access user-agent 範式 | 純下載,互補 |

**Eval 資料集:** EDGAR-CORPUS(crawler 自產,**非 gold label,循環論證**,只能壓力測);KPI-EDGAR(81 份人工標註,但標的是 KPI 關係非 item boundary);**無公開 gold-labeled item-boundary dataset**——手標 ~50 份(含 wrapper)會是可引用貢獻,也是我們的 eval set。

**兩個 research agent 的關鍵結論(我們的 novel 之處,無 prior art 可 defer):**
1. **Cross-reference / wrapper 10-K(Intel/Citi/GE)是真正的 open gap。** 沒有任一 repo 解得好;edgar-crawler 的 `get_last_item_section()` 反而會靜默誤標。我們的 `cross_reference_index` 偵測 + 三態 status 在開源界看似 novel。
2. **XBRL 當 span 內容的獨立 oracle 也大致 novel。** 既有專案用 XBRL 產報表,沒人用 companyfacts 去*認證 Item 8 span 真的含申報數字*。我們「XBRL as adversarial validator of a text span」framing 可主張為新。

## 對本專案的行動項

- **可安全依賴/借鑑(MIT/Apache):** edgartools(fetch/XBRL 參考)、Agent-E(a11y 技術 + 論文引用)、Stagehand(action caching 對照)。
- **借思路勿抄 code(copyleft):** edgar-crawler(GPLv3)、Skyvern(AGPL)、py-sec-edgar(AGPL 商用)。
- **對外可信度:** 把 WebArena / WebVoyager 列為 browser agent 的 roadmap benchmark;SEC 端主打「source-exact + XBRL 認證 + wrapper 處理」三個 novel 點。
- 我們目前的實作與上述結論一致:差異化站得住腳,且我們已經做出別人沒做的 XBRL 認證與 wrapper 分類。
