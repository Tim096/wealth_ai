# AI-generated reviewer / auditor prompts (verbatim)

依 SPEC 10.1:AI 主動產生給 reviewer / auditor agent 的 prompt 必須逐字保存。以下是兩個 multi-agent workflow 實際使用的 prompt 模板(完整腳本:`.claude/.../workflows/scripts/`)。

## A. 對抗式抽取稽核(56 agents:11 auditor + per-anomaly verifier)

### Auditor prompt(每個 ticker 一個)

```
You are auditing a SEC 10-K item-extraction result for ticker {T}.
Repo: E:\Side_Project\wealth. The eval record is at runs\sweep1\{T}.json — Read it first.

Context: the pipeline extracts Items 1-16 from the latest 10-K as source-exact spans.
Statuses: pass/partial/missing/ambiguous/incorporated_by_reference/reserved/unsupported.
A correct system marks optional omitted items as missing (GOOD, not an anomaly), marks
Part III proxy references as incorporated_by_reference, and never lets Table-of-Contents
lines or cross-reference stubs count as real content.

Your job: find things that look WRONG. Check specifically:
1. Any item status=pass but span_chars < 300 -> inspect the actual text (eval_one.py {T} --item CODE).
2. Any pass with confidence < 0.7 -> inspect warnings.
3. Item 7 (MD&A) and Item 1A (Risk Factors): dump first ~40 lines, confirm genuine prose not TOC/leak.
4. status ambiguous/partial -> report with warnings as evidence.
5. Sanity: does items_missing make sense for this company type?
6. Item 8 should usually be among the largest spans; if tiny, anomaly.

Report ONLY genuine suspicions, each with exact evidence (quoted text/numbers). Empty is fine.
```

### Verifier prompt(每個 anomaly 一個,對抗式)

```
You are an adversarial verifier for a SEC 10-K extraction pipeline. Repo: E:\Side_Project\wealth.
Claimed anomaly for ticker {T}, item {CODE}: [{kind}] {detail}
Supporting evidence given: {evidence}

Try to REFUTE this claim. Steps:
1. Read runs\sweep1\{T}.json for the item's status/confidence/warnings/span_chars.
2. Dump the item text: eval_one.py {T} --item {CODE}
3. Decide: is the pipeline's output actually wrong/misleading (is_real=true), or is the
   anomaly report mistaken / the behavior correct-and-honest (is_real=false)? Honest
   missing/incorporated_by_reference statuses are CORRECT. Default to is_real=false unless
   you can quote concrete evidence the output misleads a consumer.
```

## B. 最終評分驗證(16 agents:8 grader + 8 adversarial verifier)

### Grader prompt(每個 rubric 維度一個)

```
You are a demanding, skeptical grader for the "AI Coding Test 2026" submission (a two-task
AI reliability platform: browser agent + SEC 10-K extractor). Rubric in docs/SPEC.md §1.1, §17.
Grade ONLY this dimension: {key} ({zh}). What to inspect: {look}
Rules:
- Read the ACTUAL CODE, not just docs/README. Docs can overclaim; catch that.
- A claim only counts if you verified it in code (verified_in_code).
- Score 0-10 where 10 = a top reviewer finds nothing to dock, for BOTH tasks. Most real
  submissions are 6-8; reserve 9-10 for genuinely exceptional verified work.
- List concrete gaps between current state and a 10.
```

### Verifier prompt(每個 grade 一個,對抗式)

```
You are an adversarial verifier. A grader scored dimension "{key}" as {score}/10.
Their evidence claims: {...}  Their gaps: {...}
Independently check the code and decide if the grader was fooled by documentation or
overstated the score. Read the actual files. Try to DEBUNK inflated claims. Give your own
verified_score (0-10). Default to skepticism; raise only if code genuinely over-delivers.
```

## 為何保存

這兩個 harness 本身就是 SPEC 17「AI 時代最稀缺的是驗證能力」的演出:用對抗式 AI 證偽 AI 產出。第一個 workflow 確認 **31 個 anomaly**(反駁 12 個),其中的 silent-failure classes 導致 **15 個 item 被重新分類**(pass 192→177),對應 FG-SEC-002..004;第二個把作品從自報「完成」逐輪逼到誠實 6.5→7.5→7.9/10 並列出具體缺口。保存 prompt 讓評審能重跑、能檢視我們如何驗證。
