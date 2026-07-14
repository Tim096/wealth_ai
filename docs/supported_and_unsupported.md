# Supported & Unsupported (誠實邊界)

> 對應 SPEC 1.1「誠實邊界」：這裡把 10-K 依**結構類別**分，並明確列出 unsupported class、行為與可信度。

## SEC 10-K:filing class 與行為

pipeline 會先判定 filing class(`ExtractionResult.filing_class`),不同類走不同路徑:

pipeline 產生的**確切字串值**(非概念):

| Filing class(`ExtractionResult.filing_class`)| 說明 | item status(`ItemSegment.status`)| 可信度 |
|---|---|---|---|
| **standard** | 正文含可定址 Item N 章節(AAPL/MSFT/WMT/CAT/KO/NEM/MRNA/NVDA…) | `pass`/`incorporated_by_reference`/`reserved`/`missing`/`ambiguous`/`partial` | 高;Item 8 另經 XBRL 認證 |
| **cross_reference_index**(Intel/Citi/GE) | 主文件是交叉引用索引,正文以印刷頁碼分頁 | `partial`(resolved_from_page_anchor, needs_review)供有頁碼指標的 item;proxy-only 的 10–14 為 `incorporated_by_reference`;XBRL 矛盾或污染頁碼圖降為 `unsupported`;`missing`/`reserved` | 頁碼錨點還原 source-exact span(多段 body 以 `source_ranges[]` 串接);proxy 指標誠實標記,**不偽裝成內容**;無法可信解析者降 `unsupported` |
| **non_10k** | 找不到任何 item heading(結構不符) | 全部 `missing` + 警告 | 誠實標為不支援 |
| **unsupported_scanned_or_binary** | 掃描 PDF / 非 HTML / binary(**code-enforced**:`%PDF` 開頭、含 NUL、或無 HTML tag) | 空(無 segments)+ 警告 | 明確拒絕,建議 OCR path |
| **non_10k_filer**(resolver 層,20-F/40-F 外國私人發行人:TSM/SONY/BABA)| 公司 EDGAR 紀錄中**零筆** 10-K/10-K/A → 不進 pipeline,`NotA10KFilerError`(`sec_core/resolver.py`)| —(未抽取,typed exception)| **明確拒絕 + 指出實際 form**:訊息列出該公司真正申報的 form 分布(如 TSM:20-F×26、6-K×1320)並明講「僅支援 10-K item 抽取」;live evidence:`data/sec_eval/rejection/foreign_filer_rejection.json` |

> `ItemStatus` 的 `unsupported` **現在會在單一 item 上 emit**:`certify_item8` 在 SEC XBRL 三項數字與 Item 8 span 矛盾時,把該 item 由 `pass`/`partial` 降為 `unsupported`(如 INTC FY2019 Item 8);污染頁碼圖(每頁字數低於守衛)解析出的 span 也降為 `unsupported`。**filing 級**不支援仍以 `filing_class`(unsupported_scanned_or_binary / non_10k)+ `missing` 表達——item 級與 filing 級並存,如實揭露。

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

我們鎖定的高風險 corner case——INTC FY2019/FY2020 Item 14 極易被誤標成 extracted/ok。本 pipeline:

- **自動偵測**該類(item heading 群聚 + 頁碼指標,或群聚且行間距極小=無正文),不需硬編 Intel/Citi 白名單。
- Item 14 等標成 `incorporated_by_reference` / `needs_review`,warning 明講「body 不在可定址 Item 章節,指向年報第 X 頁」。
- 已驗證:INTC FY2019/FY2020/FY2025、Citi FY2025 全部正確歸類。

### 已知限制(誠實揭露)

- **cross-reference-index 的正文已用印刷頁碼錨點還原**(Intel/Citi class):`resolve_page_ref`/`build_page_map` 跟著索引的頁碼範圍(如 "Risk Factors 49-62")定位到主文件內同一份 annual report 的 source-exact span,標 `partial` + needs_review(頁邊界對齊為啟發式,非逐字精確)。實測 Citi FY2025 解出 **9 個 item**(Risk Factors 88K、MD&A 86K、Market Risk 207K、Financials 577K 字)、INTC Item 8 span 經 XBRL 3/3 認證。指向**另外申報**的 proxy statement 的 Item 10–14 維持誠實 `incorporated_by_reference` pointer,不 join、不捏造。**碰撞防護**:同一 span 至多由一個 item 認領,後續 item 改用自己的替代頁碼範圍或降為 pointer,避免兩個 item 共用 body(如 INTC Item 15 導向自己的 exhibit index 而非 Item 8 財報)。**同檔附綁 wrapper(JPM/XOM)已還原**:`cross_ref.reassemble_wrapper_bodies`(commit 84ecea7),見 `failure_gallery.md` FG-SEC-007/008。
- **掃描 PDF 老 filing**:標 `unsupported`;正確作法是 OCR path(非 LLM),見 insights §3。
- **pre-2001 純文字 SGML**:Unsupported(見上方 format-era 表與 FG-SEC-009);修法是 text-mode normalizer,非本波範圍。
- **boundary 精度已量化(2026-07-10)**:char-offset F1(建構性 gold,regression baseline;敏感度注入鎖在 `tests/test_scoring.py::test_sensitivity_injection_on_real_sweep3_aapl`,AAPL F1 1.0→0.9267)+ CYD 官方 iXBRL oracle(9/9 pass segment coverage 100%)。人工 token-level 標註(絕對正確率)仍列 backlog。見 `eval_report.md`「Eval 升級」段。

## Browser Agent 支援範圍

見 [README](../README.md#支援範圍browser-agent)。核心:公開搜尋/導航/擷取/下載支援;登入、CAPTCHA、購買、送出正式表單、付費資料**不支援**(責任邊界,不是能力不足)。Phase 2 實作中。

### 任務可驗證性分類(2026-07-10)

| 任務類型 | 行為 | verdict | 依據 |
|---|---|---|---|
| 有可機讀成功/禁止條件(搜尋、導航、下載、擷取)| preflight 導出條件 → verifier 對照 evidence | `pass` / `fail` | 主路徑 |
| **開放式 / 不可驗證任務**(如「隨便逛逛看有什麼有趣的」、成功條件無法事先機讀)| **支援執行**、照錄完整 trace + screenshots;verdict 時若 planner 有 live LLM client(`run_agentic` 以同一 client 掛上 `open_ended_extractor`,無第二條 credential 路徑),走 evidence-grounded 開放式評分(`second_judge.score_open_ended`):引文必須逐字存在於 evidence,否則 demote 成 abstain → 誠實 unknown 交人工審 trace;離線/mock planner 不掛評分,直接 unknown | **`pass` / `fail`**(LLM 評分且引文 grounded)或 **`unknown`**(abstain / 離線);絕不 vacuous pass、絕不捏造 pass、絕不 crash | FG-BROWSER-006(commit f535c93);`packages/browser_agent/verifier.py` 零條件 gate;artifact `data/browser_eval/open_ended/open_ended_results.json`(離線路徑 3/3 honest_unknown,crashes 0)|
| 責任邊界(登入/購買/正式表單/付費)| capability guard code-enforced 攔截 | `refused` | `packages/browser_agent/capability.py` |

> 三態鐵律的落地:缺 grounded 證據 → `unknown`(交人工),結構上不能升級成 pass。開放式任務的 LLM 評分只有逐字引文 ground 得住才給 pass/fail;ground 不了就 abstain 回 unknown——是誠實 unknown,不是失敗、也不是不支援執行,更不可能捏造 pass。

### Browser eval 軸(2026-07-10 擴充)

| 軸 | 內容 | Artifact / 依據 |
|---|---|---|
| Layered mock-site set(主軸)| v1/v2/v3 漂移 + impossible + open-ended;task 可帶 `difficulty`(easy 8 / medium 15 / hard 25 步)或顯式 `max_steps` 決定 per-task step budget,CLI `--max-steps` 覆寫(P1-15)| `data/browser_eval/tasks.json`;`tools/browser_eval.py` |
| Prompt-injection 對抗 suite(P1-14)| 5 攻擊型態(DOM 注入假系統訊息、自宣稱同意 modal、標籤誤導、隱藏文字注入、毒化搜尋結果),每頁帶 deterministic oracle `window.__attack`;SUCCESS = 完成任務**且**不執行注入動作;指標 = ASR(attack success rate)。**live 實測(2026-07-10,`tools/measure_adversarial.py`,headless Chromium、0 LLM call)**:defended ASR **0.0**(0/5 attacks taken,goals 5/5);undefended 對照組 ASR **1.0**(5/5)——證明每個 trap 可達且 oracle 會響,0.0 不是 trap 失效的假象 | `data/browser_eval/adversarial.json`、`data/mock_sites/adversarial/`、`tests/test_adversarial_suite.py`;live 實測 artifact `data/browser_eval/adversarial_results.json` |
| 外部基準子集(P1-1)| **Online-Mind2Web** 20 tasks(8 easy / 8 medium / 4 hard,17 domains),確定性分層抽樣、排除登入/付費牆/CAPTCHA 域;live naive baseline 實測 trivial-pass 20%(4/20)≈ 論文 22% naive-search 參考線 → 子集非 shortcut 集。**自跑實測(2026-07-10)**:33.3%(6/18)→ bucket-fix 44.4%(8/18)→ abstain-fix 合成 **11/18 ≈ 61.1%**(明標合成估計,跨兩次 launch);judge abstain 6/6 → 1/6。Attribution:**Online-Mind2Web, OSU-NLP-Group(CC-BY-4.0,COLM 2025,arXiv:2504.01382)**,逐 task 標註 | `data/browser_eval/external/mind2web_subset.json`;維護協定 `data/browser_eval/external/README.md`;`tools/naive_baseline.py`;`docs/ATTRIBUTION.md`;實測 artifact `runs/browser_eval/m2w_rerun/`、`m2w_rerun_20260710/`、`m2w_abstain_fix_20260710/`、`m2w_abstain_fix2_20260710/`(gitignored 原始 run)+ tracked 快照 `data/browser_eval/external_runs/` 同名目錄與 `naive_baseline/`;定向重跑任務集 `data/browser_eval/external/m2w_unknowns6.json`(sha256 `1acfc7a3a20a3bc20d5bb07cdaed243642272dcfeccb232028ff62d8d4226c9b`)。**不可與官方 Online-Mind2Web leaderboard(300 題、WebJudge 評審、Browser Use ~97%)直接比較**——自建子集、單 landmark 契約、合成跨 launch;我們量的軸是 verifier 誠實性 |

## 如何確保 status 可信

四層防禦,不靠 AI 自述:

1. **三態判定**:缺證據 → `unknown`/`needs_review`,結構上不能升級成 pass(`eval_core/verdict.py`)。
2. **對抗式稽核**:multi-agent workflow 找出可重現的 silent-failure classes；per-agent 輸出未完整留存，因此 agent 數量與內部投票不是 headline evidence。可驗證結果是 `eval_report.md` 對應的 accession-level fixtures、oracles 與 regression tests。
3. **XBRL 獨立 oracle**:Item 8 對照 SEC companyfacts 的營收/淨利/總資產——真財報 span 一定含這些數字,wrapper stub 不含。11 家實測 **certified 10 / contradicted 1**(NVDA 誠實 IBR stub;JPM/XOM 經 P0-10 重組後 3/3 認證)(`tools/certify.py`,artifact `data/sec_eval/certification/item8_certification.json`)。
4. **provenance + needs_review**:每個 item 標明來源(offset_exact_span / cross_reference_pointer / unresolved)與是否需人工複核。
