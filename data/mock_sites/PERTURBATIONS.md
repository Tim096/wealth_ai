# Mutation Site 擾動 Taxonomy(T1-2)

三軸擾動 × 輕/中/重強度的 mock site 生成矩陣,加一個 clean reference,共 10 個 cell。
依據:StressWeb(arxiv 2604.16385)的 perception / action / execution 三軸 × 強度分檔 + clean reference 設計;
WebArena「乾淨環境系統性高估 robustness」缺陷(arxiv 2407.01502)。

- 生成器:`tools/gen_mutation_sites.py`(參數化 template + 擾動注入;生成物 commit 在 `data/mock_sites/mutations/<cell>/index.html`,`manifest.json` 為機器可讀對照表)
- 量測:`tools/degradation_curve.py` → `data/browser_eval/artifacts/degradation_curve.json`
- 重生指令:`.venv/Scripts/python tools/gen_mutation_sites.py`
- 重跑指令:`.venv/Scripts/python tools/degradation_curve.py`

## 矩陣

| Cell | 軸 | 強度 | 注入手法 | 原則上可恢復? |
|---|---|---|---|---|
| `clean` | — | 0 | 無(v1 相同結構的 clean reference,fallback selector 直接命中) | n/a |
| `perception-light` | perception | 1 | id 改名(`#search-box`→`#qf`、`#search-btn`→`#find-btn`)、按鈕換字(Search→Find) | 是(aria-label/文字仍在,a11y repair 可尋回) |
| `perception-medium` | perception | 2 | + input 無 id、按鈕 icon 化(🔍)、decoy Search 按鈕、版面搬位(前置雜訊) | 是(語意屬性仍在,decoy 可由啟發式排除) |
| `perception-heavy` | perception | 3 | + cookie modal 蓋目標、submit 換 `div role=button + onclick`、真搜尋框無 aria/generic placeholder、前置 Promo code 誘餌欄位、隱藏 ghost input | 是(靠表單鄰近性/視覺 grounding 可辨識;純 a11y 字面比對會掉入誘餌欄位) |
| `action-light` | action | 1 | id 改名 + submit 按鈕零語意屬性(僅文字 "Go") | 是 |
| `action-medium` | action | 2 | 過期 snapshot:首次 input 事件後整組表單節點被「重建」(新 id、舊節點 detach,data-aid 失效;值保留) | 是(重觀察後 repair 可尋回新節點) |
| `action-heavy` | action | 3 | a11y tree 缺漏:submit 是無 role 的 `<span onclick>`,不進 `_ENUMERATE_JS` 枚舉結果 | 是(表單內單一 input,按 Enter 可 implicit submit;a11y-tree-only 的 agent 看不到該控制項) |
| `execution-light` | execution | 1 | 結果延遲渲染 250ms(模擬 XHR 延遲,落在 agent settle 窗內) | n/a(非破壞性) |
| `execution-medium` | execution | 2 | mid-task 移除元素:填入查詢後 `#search-btn` 被同步換成 `#resubmit`(不同 id)+ 250ms 結果延遲 | 是(repair 於 a11y tree 尋回替代按鈕 = 可量測的 mid-task recovery) |
| `execution-heavy` | execution | 3 | + 確定性 500:第一次 submit 回 "Server error (500). Please retry.",不渲染結果;第二次起成功 | 是(重試一次即成功;Script Mode 無 retry loop → 誠實 fail) |

## Determinism 政策

- **無 `Math.random`**:「隨機 500」實作為 attempt-counter 確定性故障排程(第 1 次必失敗、之後必成功),每次重跑逐位元重播。
- **事件錨定優先於計時器**:需要「可恢復」的變異(重建/換鈕)掛在 `input` 事件(`setTimeout(fn, 0)`),不靠長計時器賽跑;純延遲類(250ms XHR)才用時間,且刻意落在/落出 agent 的 400ms settle 窗。
- 每個 (cell, query) run 用 fresh selector memory,run 間互不污染。

## 量測定義(degradation_curve.json)

- **success**:最終 `verify_contract` 對完整 contract(`text_visible "results for"` + 完整商品名,forbidden captcha)判 pass。完整商品名(如 "Widget Pro 3000")避免 query-echo 假陽性(見 T1-3 FG 素材)。
- **checkpoint(mid-task)**:fill 階段結束時,query 是否已在「真的搜尋框」內。真搜尋框由站內 `data-sb` ground-truth 標記(agent 的 observer 不枚舉此屬性,對 agent 不可見);由 runner 收集欄位值餵給 `verify_contract`(`field_value_equals`)——與最終裁決同一套三態 verifier 機制。
- **fault_encountered**:trace 中出現任何 repair-mode step(含 modal 排除)。
- **recovery(mid-task recovery)**:fault_encountered 且最終 success。
- **degradation curve**:每軸 [clean, light, medium, heavy] 的 success_rate / checkpoint_rate / recovery_rate / avg_repairs;checkpoint 與 success 的落差可定位失敗發生在輸入階段(perception)或下游(action/execution)。

## Held-out 紀律

本矩陣只從 v1 型 clean template 衍生;held-out 站(`v3_heldout`)不被生成器讀取、不作為任何 cell 的基底,亦未用於調試擾動參數(有 test 鎖:生成器原始碼不得出現 held-out 站的引用)。
