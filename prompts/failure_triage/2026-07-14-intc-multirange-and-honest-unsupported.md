# INTC 多段頁碼截斷 + 污染頁碼圖的誠實降級 triage

> **Record type:** Derived decision record

## Trigger

使用者對已部署系統做複驗,回報兩個紅燈:Intel 早年 cross-reference-index 10-K(FY2019 `-20-`、FY2020 `-21-`)的 Item 7 只抽到 7,725 / 14,737 字(截斷),FY2019 Item 8 只有 1,454 字且 SEC XBRL 三項數字皆不在 span 內,卻仍以 `partial` 交付。要求:「不要只挑單一 range,改成 `source_ranges[]` 或明確標該年份 unsupported」。

## Scoring Criteria

- 失敗處理:診斷根因(不是加 retry),分兩個獨立機制修
- 最小變更:只動壞掉的案例,已驗證為綠的 Citi / INTC 最新年度必須 byte-identical
- 正確性驗證:不信任表面 partial,對真實 filing 實測字數 + 用獨立 oracle(XBRL)交叉確認
- 完整優先於分類:多段正文重組回完整 body;無法可信解析者誠實標記,不偽裝

## Prompt summary

(AI 自我指令)「先在真實 filing 上定位根因,不要猜。查 `page_map.resolve_page_ref` 為何對 INTC Item 7 回傳截斷 span;查 FY2019 Item 8 的 1,454 字 span 是什麼(印出 span text)。決定:(1) 多段 body 如何重組且不吃到別的 item;(2) 如何讓 XBRL 矛盾的 Item 8 不以 partial 交付;(3) 怎麼保證 Citi / INTC 最新年度不被動到。」

## AI Output Summary

根因為兩個獨立機制:

1. **多段截斷** — `resolve_page_ref` 取「最早起始」的單一 range。INTC Item 7 的 index 是「4-5, 18-39, 45-46; …」,最早的 4-5 只是 2 頁引言,真正 MD&A 在 18-39 被丟掉。
2. **污染頁碼圖** — `build_page_map` 的 LIS 鏈被一張五年財報數字表(遞增的儲存格數字)污染,FY2019 Item 8 的「65-111」解到財報索引頁(1,454 字),而非報表本身;`certify_item8` 原本只在 `status=='pass'` 才降級,故該 partial 從未被降級 → 假的 partial pass。

## Decision

- 新增 `ItemSegment.source_ranges[]`,`resolve_page_ranges` 逐段解析並串接;body 的 sha256 對串接計算,`text_of` / coverage / 記錄一致。
- **關鍵 gating(最小變更):** 只有當「最早單一 range」小於 `_MIN_SINGLE_RANGE_CHARS`(20K)時才啟用多段重組;否則走原本的單段路徑。→ Citi Item 7(8-36=86K)、INTC 最新年度等最早 range 已是實體正文者**完全不變**,只有最早 range 過小的壞案例(FY2019 7.7K / FY2020 14.7K)才改走多段。
- **誠實降級:** 每頁字數過低(`< _MIN_CHARS_PER_PAGE`,污染徵兆)→ `unsupported`;`certify_item8` 的降級門檻由 `pass` 擴到 `pass|partial`,XBRL 矛盾一律降 `unsupported`。絕不以截斷/錯誤 span 當 partial 交付。

## Reason

寧可誠實標 `unsupported`,不要給看起來像內容的假 partial(SPEC:畫面看起來完成 ≠ 成功)。用「最早 range 是否已是實體正文」當開關,而非「相對大小」或「跨 item 共享 range」的啟發式,是因為前者讓所有已驗證案例保持 byte-identical——修 bug 不該動到沒壞的東西。

## Resulting Change

- `packages/sec_core/items.py`:新增 `source_ranges` 欄位。
- `packages/sec_core/page_map.py`:新增 `PageResolution` + `resolve_page_ranges`(多段、合併相鄰、回報涵蓋頁數)。
- `packages/sec_core/cross_ref.py`:單段門檻 gating + 污染守衛 + 多段 emit。
- `packages/sec_core/pipeline.py`、`coverage.py`:`text_of` / partition 支援多段。
- `packages/sec_core/xbrl.py`:`certify_item8` 降級門檻擴到 `partial`。
- 測試:`tests/test_xbrl.py` 新增 partial→unsupported 回歸;既有 SEC 套件全綠。
- 實測(真實 EDGAR):FY2019 Item 7 7,725→**76,363**(5 段)、Item 8 →**unsupported**(XBRL contradicted);FY2020 Item 7 14,737→**127,871**、Item 8 152,016(XBRL certified 3/3);Citi 7=86,462 / 7A=207,375 / 8=576,936 與 INTC 最新年度皆**未變**。
- 前端 `apps/services/sec/static/index.html`:showcase 同步兩例(多段重組=做得好、污染圖降級=誠實的失敗處理)。
