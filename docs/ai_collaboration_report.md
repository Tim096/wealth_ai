# AI Collaboration Report

> SPEC 14.3。本專案由使用者與 AI coding agent 協作完成；以下只把能由目前 code、Git objects、tests、artifacts 或明確 verbatim excerpt 支持的內容當成證據。

## Provenance limitation

`prompts/` 不是完整原始 chat transcript。只有明確標成 verbatim excerpt 的
區段可視為逐字證據；其餘 derived decision records 是依 code、tests、artifacts
與 Git blobs 整理的決策摘要，不引用成使用者或 AI 的逐字說法。
`tools/verify_prompt_provenance.py` 會核對 record type、原始 Git blob 與五份
verbatim body hash，讓摘錄正文可自動核對。

## AI 用在哪些地方

| 用途 | 說明 |
|---|---|
| 架構與 schema 設計 | packages/* 全部 pydantic schema、不變量的 code-level 強制 |
| 確定性 pipeline 實作 | SEC normalize/headings/toc/boundary/fetcher/resolver/main_doc(無 LLM) |
| 對抗式稽核 harness | multi-agent workflow 稽核真實 10-K 並找出可重現的 false-pass classes；成果以 accession-level fixtures、artifacts 與 regression tests 驗證。|
| 失敗診斷與修復 | JPM cross-ref stub、三大 silent-failure class |
| Eval 設計 | 分層 eval set、合成 fixtures + golden labels、held-out |
| 文件與 prompt log | 全部 docs/ 與 prompts/ |

## AI 沒有被允許做的事(硬邊界)

- **不向使用者索取 API key**(資安)。SEC 走公開 EDGAR;LLM 主路徑 $0。
- **LLM 不產生 filing text**:所有 item text 是 offset-exact source span;LLM 只在 ambiguous boundary 當裁判,且高信心裁決必須附 exact quote(schema validator 強制)。
- **LLM 不輸出任意 browser code**:只輸出 schema 驗證過的 action JSON。
- **缺證據不得標 success**:三態 verdict 結構上讓 unknown 不能升級成 pass。

## AI 建議被採納的例子

- 對抗式稽核 harness → 產生 accession-level regression fixtures 與 silent-failure tests。
- Python-first + repo-local `.venv` → 統一 browser、SEC 與 eval toolchain。

## AI 建議被拒絕 / 修正的例子

- **TypeScript-first stack** → 改採 Python-first。記錄於 `prompts/rejected_prompts/2026-07-10-typescript-first-stack.md`。
- **Broad furniture stripping** → 因兩側 F1 都下降而拒絕，改採窄版 TOC anchor gate。

## AI 如何對照評分標準工作

每個改動自問:對應哪個評分項?有 evidence 嗎?有 verifier 嗎?有 eval 嗎?有 failure case 嗎?會不會 silent failure?——三大 silent-failure class 的修復,就是「會不會 silent failure」這一問的直接產物:先用對抗式稽核逼出來,再修,再用新 test 鎖住,再誠實更新 metrics(pass rate 下降但正確性上升)。
