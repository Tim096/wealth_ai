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
| **non_10k_filer**(resolver 層,20-F/40-F 外國私人發行人:TSM/SONY/BABA)| 公司 EDGAR 紀錄中**零筆** 10-K/10-K/A → 不進 pipeline,`NotA10KFilerError`(`sec_core/resolver.py`)| —(未抽取,typed exception)| **明確拒絕 + 指出實際 form**:訊息列出該公司真正申報的 form 分布(如 TSM:20-F×26、6-K×1320)並明講「僅支援 10-K item 抽取」;live evidence:`data/sec_eval/rejection/foreign_filer_rejection.json` |

> `ItemStatus` enum 亦定義 `unsupported`,但目前程式以 `filing_class` + `missing` 表達不支援,尚未在單一 item 上 emit `unsupported`——如實揭露此 doc/code 命名細節。

## Format-era 支援表(2026-07-10 分層抽樣實測,T2-4)

按年代格式 × filing agent 分層抽樣,每個缺口層實跑 1–2 份(artifact:`data/sec_eval/stratification/stratification.json`;重跑:`SEC_EDGAR_USER_AGENT=<contact> .venv/Scripts/python tools/stratified_sample.py`):

| Era | 實測樣本 | 行為 | coverage | 支援 |
|---|---|---|---|---|
| **text_pre2001**(純文字 SGML)| AAPL FY1996、KO FY1997 | normalize 正常但 heading detector 0 candidate,22 item 全 missing;partition invariant 仍成立(整份=單一 unclassified block,零 silent drop)| 0.0 | **Unsupported**(見 FG-SEC-009)|
| html_2001_2008 | AAPL 2004(0001047469-04-035975)| 17 pass | 0.9824 | Supported |
| xbrl_2009_2018 | AAPL 2013(0001193125-13-416534)| 15 pass + 5 IBR | 0.9592 | Supported |
| ixbrl_2019plus | baseline 11 家 + Toppan 樣本 | 現行主路徑 | ≥0.91 | Supported |

**Filing-agent 驗證**:靠文件頭 generator comment 偵測(非 body 公司名,避免 Merrill Lynch 類誤判)。三家 agent 全過 pipeline、cov ≥0.91、無 agent-specific 破損:Workiva、DFIN(Donnelley)、Toppan Merrill(cov 0.9107)。生態系抽樣(efts 2025-02,n=40):Workiva 31 / unknown 8 / Toppan 1——Workiva 壟斷,baseline(10 Workiva + 1 DFIN)是合理抽樣,補 Toppan 後三家皆有實測。

**CAT 非標準 Item 1D 發現**(CYD oracle 抓到,T2-3):CAT 10-K 有非標準的「Item 1D. Information about our Executive Officers」;1D 不在 `VALID_CODES`,我方 Item 1C span 尾部把它吞入 → CYD containment 73.1%(coverage 仍 100%)。這是官方 oracle 抓到「span 跑長」的真訊號,列為 landmine 候選(非標準 item code)。Evidence:`data/sec_eval/cyd_groundtruth/cyd_agreement.json` records[CAT]。

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
- **pre-2001 純文字 SGML**:Unsupported(見上方 format-era 表與 FG-SEC-009);修法是 text-mode normalizer,非本波範圍。
- **boundary 精度已量化(2026-07-10)**:char-offset F1(建構性 gold,regression baseline;敏感度注入鎖在 `tests/test_scoring.py::test_sensitivity_injection_on_real_sweep3_aapl`,AAPL F1 1.0→0.9267)+ CYD 官方 iXBRL oracle(9/9 pass segment coverage 100%)。人工 token-level 標註(絕對正確率)仍列 backlog。見 `eval_report.md`「Eval 升級」段。

## Browser Agent 支援範圍

見 [README](../README.md#支援範圍browser-agent)。核心:公開搜尋/導航/擷取/下載支援;登入、CAPTCHA、購買、送出正式表單、付費資料**不支援**(責任邊界,不是能力不足)。Phase 2 實作中。

### 任務可驗證性分類(2026-07-10)

| 任務類型 | 行為 | verdict | 依據 |
|---|---|---|---|
| 有可機讀成功/禁止條件(搜尋、導航、下載、擷取)| preflight 導出條件 → verifier 對照 evidence | `pass` / `fail` | 主路徑 |
| **開放式 / 不可驗證任務**(如「隨便逛逛看有什麼有趣的」、成功條件無法事先機讀)| **支援執行**、照錄完整 trace + screenshots,verifier 因無可機讀證據回 unknown + 明講交人工審 trace | **`unknown`**(絕不 vacuous pass、絕不 crash)| FG-BROWSER-006(commit 2fec949);artifact `data/browser_eval/open_ended/open_ended_results.json`(3/3 honest_unknown,crashes 0)|
| 責任邊界(登入/購買/正式表單/付費)| capability guard code-enforced 攔截 | `refused` | `packages/browser_agent/capability.py` |

> 三態鐵律的落地:缺可機讀證據 → `unknown`(交人工),結構上不能升級成 pass。開放式任務「執行得了但無法自動判成功」是誠實 unknown,不是失敗、也不是不支援執行。

## 如何確保 status 可信(主管最看重的問題)

四層防禦,不靠 AI 自述:

1. **三態判定**:缺證據 → `unknown`/`needs_review`,結構上不能升級成 pass(`eval_core/verdict.py`)。
2. **對抗式稽核**:56-agent workflow 證偽自報 pass rate,抓到 15 個 silent failure(`eval_report.md`)。
3. **XBRL 獨立 oracle**:Item 8 對照 SEC companyfacts 的營收/淨利/總資產——真財報 span 一定含這些數字,wrapper stub 不含。11 家全數,pipeline 分類與 XBRL 判定**零分歧**(`tools/certify.py`)。
4. **provenance + needs_review**:每個 item 標明來源(offset_exact_span / cross_reference_pointer / unresolved)與是否需人工複核。
