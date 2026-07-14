# 敘事對齊 shipped behavior + 誠實顯示邊界(unsupported ≠ 100%)triage

> **Record type:** Derived decision record

## Trigger

多段頁碼還原(見 [`2026-07-14-intc-multirange-and-honest-unsupported`](2026-07-14-intc-multirange-and-honest-unsupported.md))上線後,使用者對部署系統再複驗,回報「剩下的問題看起來都是 print 顯示問題」:

1. **敘事落後實作** — 多處 doc / runtime warning 仍描述舊行為:`README.md:101/232` 說 Intel/Citi 正文未還原、只標指標;`docs/supported_and_unsupported.md:19` 說 pipeline「尚未在單一 item 上 emit `unsupported`」;`packages/sec_core/pipeline.py:328` runtime warning 說「body resolution is a documented next step」;`failure_gallery.md:321`、`architecture.md:74` 同類。實作其實**已經做到**——反向誇大(說做不到、其實做到了)也是不誠實。
2. **顯示邊界** — 上傳假 PDF → `filing_class=unsupported_scanned_or_binary`、0 items,但 `coverage_ratio` 對空文字回傳 `1.0`,前端渲染「本文覆蓋 100.0%」+ job `done`,看起來像 100% 成功。

## Scoring Criteria

- **完整優先於分類**:不只修被點名的 3 處,掃全 repo 找**同類但漏列**的字句(反例:只修 cited 的會漏掉 README:232 / failure_gallery:321 / architecture:74)。
- **誠實邊界**:unsupported 必須在**視覺**與 **machine-readable** 兩層都與「100% 成功」可區分(SPEC 1.1;畫面看起來完成 ≠ 成功)。
- **最小變更**:純函式 `coverage_ratio`(空=真空全覆蓋的數學約定,partition invariant 測試依賴)不動,誤導只在顯示層 → 只修顯示層。
- **不誤刪誠實限制**:AUROC 0.6667<0.75、外部 macro-F1 0.6245<edgar_crawler 等**仍為真**的限制不得被當成 stale 一併「修掉」。

## Prompt summary

(AI 自我指令)「開三個平行 finder 的 workflow 掃描,每個 finder 帶一份 **shipped-behavior ground truth 對照清單**與一份**仍為真、不得誤報的誠實限制清單**;分工:(a) docs/**、README,(b) 程式字串(warnings/print/docstring/comment),(c) 顯示邊界(coverage→payload→前端渲染鏈)。回傳 exact verbatim quote + line + why_stale + confidence,不要自作主張改字;人工裁決後由我最小改動落地。」

## AI Output Summary

3-finder workflow(`stale-claim-sweep`)回傳 **12 findings(8 high-confidence)**,三類:

- **敘事落後 shipped(6)**:README:101、README:232、supported_and_unsupported:19、failure_gallery:321、architecture:74、pipeline.py:328。共同根因是「cross-reference-index 正文已由**同檔**印刷頁碼錨點還原為 `partial`(多段 `source_ranges[]` 串接),僅跨檔 proxy statement Item 10–14 維持指標」與「item-level `unsupported` 現會 emit」兩件事尚未同步進敘事。
- **顯示邊界(5)**:`coverage_ratio` 空文=1.0 → `meta.coverage` → 前端 `本文覆蓋 100%`;payload 無 machine-readable supported 訊號;filing_class 中性 mono、0-item 表格空白。
- **誠實限制驗證(隱含)**:finder **正確未把** AUROC / macro-F1 當 stale——證明 ground-truth 對照有效隔離「已修」與「仍為限制」。

## Decision

- **敘事全部對齊 shipped**:cross-ref 正文=同檔頁碼錨點還原的 source-exact `partial`;弱點縮小為「頁邊界對齊 heuristic + XBRL 矛盾年度降 `unsupported` + 跨檔 proxy 未 join」。`unsupported` 現會在 item 級 emit(`xbrl.certify_item8` XBRL 矛盾降級、`cross_ref` 污染/TOC 頁守衛),與 filing 級不支援並存。
- **顯示邊界**:不改 `coverage_ratio`(純函式約定);改在 `_items_payload` 加 machine-readable `supported = filing_class ∈ {standard, cross_reference_index} ∧ items≠∅`,unsupported 時 `coverage=None`(移除 raw JSON 的誤導 1.0);前端據 `supported` gate 掉 coverage%、filing_class 上 `p-fail` pill、顯式「未支援」banner、0-item 不留空白表格改 empty-state row。
- **jobs strip 的 `✓` 不動**:job `status=done` 對「跑完無 error」是誠實的(finder 亦標 low-confidence);過度標記反成雜訊。

## Reason

程式快速演進時,最大的誠實風險往往不是 bug,而是**敘事落後實作**——把「找出所有與 shipped 行為矛盾的字句」交給帶對抗式 ground-truth 的平行掃描,變成**可重跑的完整性網**,而非人工挑幾處(實測補抓到 3 處 cited 清單外的漏列)。顯示邊界守則同一條:`unsupported` 必須在視覺與機器可讀兩層都與 100% 成功可區分,否則「0 items 卻 100% 覆蓋」就是畫面看起來完成的假成功。

## Resulting Change

- 敘事:`README.md`(101、232)、`docs/supported_and_unsupported.md`(19 + class 表 14)、`docs/failure_gallery.md`(321)、`docs/architecture.md`(74)、`packages/sec_core/pipeline.py`(cross-ref warning 重寫)。
- 顯示邊界:`apps/services/sec/main.py`(`_items_payload` 加 `supported`、unsupported 時 `coverage=None`);`apps/services/sec/static/index.html`(coverage% gate、filing_class p-fail pill、未支援 banner、empty-state row)。
- 測試:`tests/test_sec_service.py` 新增 `test_items_payload_flags_unsupported_filing_not_supported`(unsupported→`supported=False`、`coverage=None`)與 `..._standard_filing_supported`;SEC 套件 60/60 綠。
- `coverage_ratio` 與所有已驗證抽取案例 **byte-identical 未動**——修敘事與顯示不該動到數值管線。
