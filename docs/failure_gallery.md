# Failure Gallery

每個 failure 都是事故報告。Failure 不是扣分項,沒有 failure analysis 才是。

---

## FG-SEC-001: Cross-reference stub 被標 pass(silent failure)

| 欄位 | 內容 |
|---|---|
| Failure ID | FG-SEC-001 |
| App | sec_extractor |
| Input | JPM 10-K, accession 0001628280-26-008131 (FY2025) |
| Expected | Item 11 應反映「內容在別處」——不是完整正文 |
| Actual | Item 11 標 `pass`、confidence 0.96,但整個 body 只有 51 字元:`"Refer to Item 10."` |
| Status | fixed |
| Failure Type | silent_failure(錯了卻標成功)|
| Evidence | smoke run 輸出 + `r.text_of('11')` == `'Item 11. Executive Compensation.\nRefer to Item 10.\n'` |
| Root Cause | `_INCORPORATED_RE` 只匹配 "incorporated by reference" 字樣;JPM 用 "Refer to Item 10." 措辭,不含該片語,於是 stub 通過 verifier(heading 對、span 非空、順序對)拿到高 confidence |
| Repair Attempt | 新增 `_CROSS_REF_RE`(`refer to / see item N`):body < 600 字元且命中 cross-reference → `incorporated_by_reference` + warning |
| Why It Still Failed | (已修復)殘餘風險:非 Part III 的極短 cross-ref 措辭變體(如 "included in Item 8")尚未覆蓋,由 boundary_length_sanity confidence 分量部分攔截 |
| Next Fix | eval sweep 擴大公司樣本,收集更多 cross-ref 措辭變體 |
| Related Prompt | prompts/failure_triage/2026-07-10-jpm-cross-ref-stub.md |
| Related Commit | fix(sec): classify cross-reference stub bodies as incorporated_by_reference |

**附註(同次 smoke run 的正確行為驗證):** JPM 沒有 Item 16(選填項,raw HTML 0 hits)→ pipeline 標 `missing`,是正確的誠實判定,計入 missing item correctness。
