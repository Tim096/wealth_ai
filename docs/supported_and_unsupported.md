# Supported & Unsupported (誠實邊界)

> SPEC 1.1「誠實邊界」+ 主管回饋:好的作業會明確列出 unsupported class。這裡把 10-K 依**結構類別**分,並說明每一類的行為與可信度。

## SEC 10-K:filing class 與行為

pipeline 會先判定 filing class(`ExtractionResult.filing_class`),不同類走不同路徑:

pipeline 產生的**確切字串值**(非概念):

| Filing class(`ExtractionResult.filing_class`)| 說明 | item status(`ItemSegment.status`)| 可信度 |
|---|---|---|---|
| **standard** | 正文含可定址 Item N 章節(AAPL/MSFT/WMT/CAT/KO/NEM/MRNA/NVDA…) | `pass`/`incorporated_by_reference`/`reserved`/`missing`/`ambiguous`/`partial` | 高;Item 8 另經 XBRL 認證 |
| **cross_reference_index**(Intel/Citi/GE) | 主文件是交叉引用索引,正文在另外裝訂的 annual report | `incorporated_by_reference`(needs_review, provenance `cross_reference_pointer`)/`missing`/`reserved` | 誠實標為指標,**不偽裝成內容** |
| **non_10k** | 找不到任何 item heading(結構不符) | 全部 `missing` + 警告 | 誠實標為不支援 |
| **unsupported_scanned_or_binary** | 掃描 PDF / 非 HTML / binary(**code-enforced**:`%PDF` 開頭、含 NUL、或無 HTML tag) | 空(無 segments)+ 警告 | 明確拒絕,建議 OCR path |

> `ItemStatus` enum 亦定義 `unsupported`,但目前程式以 `filing_class` + `missing` 表達不支援,尚未在單一 item 上 emit `unsupported`——如實揭露此 doc/code 命名細節。

## Unstable / 邊界不穩定(SPEC 要求的第三類,誠實揭露 flaky 風險)

| Unstable 情形 | 風險 | 目前緩解 |
|---|---|---|
| cross-ref-index 偵測靠門檻 `_MIN_CLUSTERED_ITEMS=8`/`_CLUSTER_SPAN=8000`/`_MIN_PAGE_REF_RATIO=0.25`/`_MAX_INDEX_GAP=300`(`cross_ref.py`)| 罕見排版可能誤判 standard↔index | 群聚外有正文候選即排除;需更多 held-out 校準 |
| bare-index(Citi 無「Item」前綴)靠 canonical-title 相似度 ≥0.5 | 標題大幅改寫可能漏抓 | 有 page-ref 佐證;漏抓 fallback non_10k(仍不偽裝)|
| 10-K/A amendment | 尚未特別處理,走 standard | 列為 backlog |
| browser login/captcha 偵測是 substring heuristic | 措辭變體可能漏判 | capability guard intent 層另有攔截;列 unstable |

### 關鍵設計:cross-reference-index 不偽裝成功

主管點名的 corner case——INTC FY2019/FY2020 Item 14 被別的作業標成 extracted/ok。本 pipeline:

- **自動偵測**該類(item heading 群聚 + 頁碼指標,或群聚且行間距極小=無正文),不需硬編 Intel/Citi 白名單。
- Item 14 等標成 `incorporated_by_reference` / `needs_review`,warning 明講「body 不在可定址 Item 章節,指向年報第 X 頁」。
- 已驗證:INTC FY2019/FY2020/FY2025、Citi FY2025 全部正確歸類。

### 已知限制(誠實揭露)

- **cross-reference-index 的正文尚未還原**:目前誠實標為指標,但還沒「跟著指標進 annual-report exhibit 把正文接回來」。這是明確的下一步(`insights_and_directions.md` §2),刻意不出貨脆弱的猜測版——**錯的正文比誠實的指標更糟**。
- **掃描 PDF 老 filing**:標 `unsupported`;正確作法是 OCR path(非 LLM),見 insights §3。
- **token-level boundary IoU** 尚未對真實 filing 量化(合成 fixtures 有 status-level golden labels)。

## Browser Agent 支援範圍

見 [README](../README.md#支援範圍browser-agent)。核心:公開搜尋/導航/擷取/下載支援;登入、CAPTCHA、購買、送出正式表單、付費資料**不支援**(責任邊界,不是能力不足)。Phase 2 實作中。

## 如何確保 status 可信(主管最看重的問題)

四層防禦,不靠 AI 自述:

1. **三態判定**:缺證據 → `unknown`/`needs_review`,結構上不能升級成 pass(`eval_core/verdict.py`)。
2. **對抗式稽核**:56-agent workflow 證偽自報 pass rate,抓到 15 個 silent failure(`eval_report.md`)。
3. **XBRL 獨立 oracle**:Item 8 對照 SEC companyfacts 的營收/淨利/總資產——真財報 span 一定含這些數字,wrapper stub 不含。11 家全數,pipeline 分類與 XBRL 判定**零分歧**(`tools/certify.py`)。
4. **provenance + needs_review**:每個 item 標明來源(offset_exact_span / cross_reference_pointer / unresolved)與是否需人工複核。
