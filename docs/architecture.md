# Architecture

> Status: shipped & deployed (last updated 2026-07-11; originally written in the 2026-07-10 foundation phase — outdated sections rewritten against the current tree). Anything not yet implemented is explicitly marked.

## The map first: what does this page answer?

Seven questions, in the order a stranger would ask them — what is this → what's in it → why Python → what can never break → where does the money go → how deterministic is the SEC path → what is actually done. Each section title is the question; the answer is inside.

1. [What is this repo, in one sentence?](#1-what-is-this-repo-in-one-sentence) — one platform, two apps.
2. [What are the layers?](#2-what-are-the-layers) — the tree, with an implementation status on every single line.
3. [Why Python?](#3-why-python) — one language decision, one reason.
4. [What can never break?](#4-what-can-never-break) — seven invariants, enforced in code, not in convention.
5. [When does the Browser Agent spend money?](#5-when-does-the-browser-agent-spend-money) — escalation economics, plus the honesty note on which repair rungs actually run where.
6. [How deterministic is the SEC pipeline?](#6-how-deterministic-is-the-sec-pipeline) — exactly one LLM call site, with a measured trigger rate.
7. [What is actually done — and what isn't?](#7-what-is-actually-done--and-what-isnt) — status, test counts, explicit boundaries.

---

## 1. What is this repo, in one sentence?

The repo is an **AI reliability platform** proven on two tasks:

1. **Browser Agent** — capability-aware browser automation with verifier-backed results and selector self-repair.
   Plain English: it drives a website, and something other than the model itself decides whether the job got done.
2. **SEC Extractor** — 10-K Item 1–16 structural extraction with source-exact spans and explainable confidence.
   Plain English: it cuts a company's annual report into its numbered chapters, and every chapter is addressed by where it lives in the original file — never by text the model wrote.

Both apps share the same reliability infrastructure. That sharing is the point: evidence, verification, eval, and cost accounting are platform concerns, not per-app afterthoughts.

> **The two apps are not the product — they are the load. The product is the thing underneath that can prove when it's right, when it's wrong, and when it simply doesn't know.**

---

## 2. What are the layers?

Every line below carries its own status tag — `implemented`, `active`, `configured`. Nothing is listed aspirationally.

```
apps/web/             (implemented) — eval-dashboard (self-contained HTML, real data);
                                      test center UI served by services (啟動測試中心.bat → http://127.0.0.1:8765)
services (deploy)     (implemented) — two containerized services on Zeabur: wealth-sec
                                      (SEC Extractor API + dashboard, Dockerfile.wealth-sec) and
                                      wealth-agent (Browser Agent + Playwright Chromium,
                                      Dockerfile.wealth-agent); see docs/deploy.md
packages/             (implemented, Python)
  observability_core  — EvidenceRecord schema, JSONL EvidenceStore, hashing
  eval_core           — three-state verdict combinator, layered EvalCase schema
  browser_core        — controlled action space, task contract, failure taxonomy, selector memory
  browser_agent       — executor/observer/verifier/repair/agent loop, capability guard,
                        LLM planner (Codex gateway), vision escalation, replay cache
  sec_core            — normalize/headings/toc/boundary/refine/cross_ref/xbrl/page_map/coverage,
                        ItemSegment schema, explainable ConfidenceBreakdown, LLM adjudicator I/O guard
  llm_core            — accounted LLM call records (cost / latency / schema validity)
tools/                (implemented) — eval runners & oracles (browser_eval, certify, certify_cyd,
                        triangulate, score_offsets, calibrate_verifier, degradation_curve,
                        impossible_tasks, head_to_head, run_external_eval, measure_adversarial, …)
data/                 (active)      — eval sets, mock sites, golden labels, committed eval artifacts
                                      (sec_eval/, browser_eval/, external_runs tracked snapshots)
prompts/              (active)      — every prompt that influenced design/code/eval/docs, with decisions
docs/                 (active)      — SPEC, this file, eval/cost/failure reports, research notes
.github/workflows/    (configured)  — ci.yml exists; **not yet executed** (first run happens on push)
```

Reading the tree in plain English, top to bottom: two web surfaces a human can click; two containers a stranger can deploy; six Python packages that do the work; one folder of eval runners that try to prove the work wrong; and three folders of receipts (`data/`, `prompts/`, `docs/`).

> **The `tools/` line is the tell. A repo that only ships features has no folder whose job is to attack them.**

---

## 3. Why Python?

Core pipelines are **Python 3.12 in a repo-local `.venv`**. The SPEC's TypeScript type definitions are implemented as pydantic models with identical field names, so a future TS/JS frontend consumes the same JSON shapes verbatim. The shipped web surfaces (eval dashboard, test center) are self-contained HTML served by the Python services.

Plain English: the SPEC was written in TypeScript types, the pipeline runs in Python — and I kept the field names identical on purpose, so nobody has to translate a schema by hand later. **The decision isn't "Python instead of TypeScript"; it's "one schema, two languages, zero drift."**

---

## 4. What can never break?

These are **invariants**, not guidelines. Plain English: a guideline is something a tired engineer forgets at 2am; an invariant is something the code refuses to let them do. The third column is where the refusal physically lives.

| Invariant | Plain English | Enforcement |
|---|---|---|
| Lack of evidence never upgrades to success | If I didn't observe it, I don't get to call it a win | `eval_core.combine_checks`: any unobserved condition → `unknown`, never `pass`; empty check list → `unknown` |
| LLM cannot emit arbitrary browser code | The model orders from a menu; it never gets to write the menu | `browser_core.BrowserAction` discriminated union rejects unknown action types at validation |
| Open-ended tasks are honest, not illegal input | "Go look around and tell me what's interesting" is a real request — it must neither crash the system nor earn a free pass | `BrowserTaskContract.success_conditions` allows an empty list (was min_length=1; relaxed in commit f535c93): empty success → forbidden checks still run (a violation still fails); when the planner has a live LLM client, the verdict then routes through evidence-grounded open-ended scoring (`verifier._score_open_ended` → `second_judge.score_open_ended`, armed in `run_agentic` with the planner's own client — no second credential path): a grounded yes/no becomes a real `pass`/`fail`, and any judgment whose quoted span is not verbatim in the evidence demotes to abstain → honest `unknown` (human review); offline/mock planners keep the unchanged `unknown`. Structurally blocks crash-on-honest-input, vacuous pass, and fabricated pass |
| Repair is diagnosis-driven | Fix what the diagnosis names; never retry blindly and hope | `FAILURE_TAXONOMY` maps each failure type to a specific strategy; `silent_failure_risk` is explicitly non-repairable → `unknown` |
| LLM never generates filing text | The model points at the filing; it never writes the filing | `ItemSegment` addresses text only by `start_offset`/`end_offset`/`text_sha256`; `AdjudicatorDecision` validator rejects confident decisions without an exact source quote |
| Confidence is explainable | Every confidence number can be taken apart back into named pieces | `ConfidenceBreakdown` is a sum of named, reasoned components — no free-floating score |
| Corrupt evidence fails loudly | A broken record stops the run; it never gets quietly skipped | `EvidenceStore` raises on malformed records instead of skipping them |

Look at row 3 closely, because it's the one that pays for the whole table. An open-ended task has three ways to embarrass a system: crash on it, rubber-stamp it, or invent a success story about it. The contract blocks all three structurally — and the escape hatch when the LLM judge can't quote its evidence verbatim isn't a softer pass, it's an abstain that lands on a human's desk.

> **Not "we're careful about evidence" — the combinator cannot spell `pass` without it.**

---

## 5. When does the Browser Agent spend money?

Script Mode (known site + known task, no LLM) → Agent Mode (unknown, LLM plans within the controlled action space) → Repair Mode (diagnosed failure, deterministic a11y-tree candidates verified in small steps). LLM spend is an escalation, not a default; vision (SoM screenshot) is a further stuck-only escalation (`AGENT_VISION` unset = auto).

Plain English: known job on a known site costs nothing; the model only gets called when the situation is genuinely unknown; and the screenshot-reading path — the most expensive rung — only comes out when the agent is stuck.

### The honesty note: which repair rungs actually run where?

This is the kind of detail a glossy architecture doc leaves out, so I'm putting it in the body, not a footnote.

Per-mode note — which repair rungs run where: the diagnose → repair cascade (`diagnose_failure` → per-failure-type strategy → hash rebind → a11y purpose scoring, counted in `TaskRun.repairs`) runs in Script Mode `run()` **and, since commit dfc3378, on the failure path of `run_agentic` — the deployed/eval Agent-Mode path — by reusing the same primitives rather than reimplementing them in parallel**. `run_agentic`'s other recovery rungs are unchanged: per-step overlay dismissal (`_dismiss_overlay`), replay-cache steps rebound by the same `rebind_by_hash` (`replay_cache.action_from_step`; a step that no longer resolves invalidates the cache entry), stagnation nudges, and vision escalation.

**What this paragraph used to say, and why that matters more than what it says now.** Until 2026-07-16 it read: the deployed Agent-Mode path reports `TaskRun.repairs` **always 0** — "not 'rarely repairs' — structurally zero, because it never enters the cascade at all. The famous repair ladder is a Script Mode feature; saying otherwise would be marketing."

That was **accurate**, and it was measured: `repairs` was hardcoded to 0 in `run_agentic`, selector memory was inert on the deployed path, and every memory key in the project was `mockshop::*` — the real web had taught it nothing. The task brief's literal ask, "adjust locator strategies dynamically", did not exist where a grader would click. Measured after wiring it in: `repairs` **0 (hardcoded) → 1 (real)**, selectors tried after a failure **1 → 2**, selector memory **never persisted → learned `news.ycombinator.com::agentic::result_link`**.

So the self-attack has moved up a level. This file disclosed the gap **precisely and voluntarily** — and the gap still shipped for weeks, because `README.md` listed the ladder as a Task 1 capability and pointed graders at the scripted demo. **A disclosure filed on the page nobody reads is an archive, not a disclosure.** See `failure_gallery.md` FG-BROWSER-010.

> **Not "the doc was wrong" — the doc was right, and being right in the wrong place bought nothing.**

---

## 6. How deterministic is the SEC pipeline?

Fetch → main-document detection → normalize with offset mapping → multi-detector heading candidates → TOC filter → boundary resolution → cross-reference/wrapper reassembly → verifier → confidence → independent oracles (XBRL Item 8 certification, CYD Item 1C span oracle, topic consistency, third-engine triangulation). The LLM appears exactly once, as a boundary adjudicator between existing candidates, and only when the deterministic pipeline says `ambiguous` (measured trigger rate on the 11-filing sweep: 0%).

Plain English: a fixed chain of deterministic steps, and the model is allowed to speak at exactly one of them — and only to pick between two boundaries the deterministic code already found. On the 11-filing sweep it never got to speak at all: **measured** trigger rate 0%, not an assumed one.

> **The LLM here is not the extractor. It's the tie-breaker who never had a tie to break.**

---

## 7. What is actually done — and what isn't?

Current status (2026-07-11).

### Done

- Implemented: everything in the Layers table above, including both task pipelines end-to-end, the eval system (verifier calibration, degradation curves, impossible/open-ended sets, pass@k, triangulation, offset F1, CYD/XBRL oracles, external NTU head-to-head, Online-Mind2Web live subset, prompt-injection adversarial suite) with committed artifacts under `data/`.
- Reports with real data: `eval_report.md`, `cost_latency_report.md`, `failure_gallery.md`, `supported_and_unsupported.md`.

### Tests — with the correction stated out loud

- Tests: **998 collected** — quick lane `-m "not integration"`: 945 passed / 53 integration deselected (integration lane includes real-browser and gateway e2e). Originally 16 tests in the foundation phase; this document previously understated the suite.

The anchor for "998" is the number this file used to imply. It started at 16 in the foundation phase, and **this document previously understated the suite** — I'm not quietly fixing that number, I'm naming the fact that the doc was wrong. The 2026-07-16 wave took the quick lane 853 → **945** (+92 across commits dfc3378 and aa1c039); re-derive with `.venv\Scripts\python -m pytest --collect-only -q` and `… -m "not integration"`.

### CI

- CI: `.github/workflows/ci.yml` — first run green on the `v1.0-submission` tag tree (run 29134525031: ruff clean + 743 selected → 742 passed / 1 skipped); the 20 length-prior tests added after the tag get verified on the next push.

The 20 length-prior tests landed after the tag, so that green run did **not** cover them. Stated plainly rather than rounded up to "CI is green."

### Not implemented — the explicit boundaries

- Not implemented / explicit boundaries: joining a **separately filed proxy statement** (cross-reference-index Items 10-14, and the Berkshire-class Part-level declaration — the same-file Intel/Citi/GE 10-K bodies ARE resolved via printed-page anchors into source-exact `partial` spans), era-aware item-schema mapping for pre-2001 filings, OCR path for scanned PDFs — see `supported_and_unsupported.md` and `insights_and_directions.md`.

Three boundaries — and the first one carries a distinction that's easy to over-claim in either direction, so the table splits it into two rows:

| Item | What this doc claims — and doesn't |
|---|---|
| Joining a **separately filed proxy statement** (cross-reference-index Items 10-14; Berkshire-class Part-level declarations) | Not implemented — the declaration sentence gets a source-exact span and `needs_review`; the body is never guessed |
| …but the **same-file** Intel/Citi/GE 10-K bodies | Resolved — via printed-page anchors, into source-exact `partial` spans |
| pre-2001 SGML text-mode normalizer | **Implemented** (commit dfc3378, `NORMALIZATION_VERSION` 1.1). The previous "not implemented" line rested on a root cause that measurement disproved — see `failure_gallery.md` FG-SEC-009 |
| era-aware item-schema mapping for pre-2001 filings | Not implemented — FY1996's `Item 14. Exhibits…` is semantically the modern Item 15; the span is handed to both codes with `needs_review` rather than guessed |
| OCR path for scanned PDFs | Not implemented |

Read rows 1 and 2 together. The **same-file** bodies **are** resolved. What isn't implemented is going out to fetch a *separately filed* proxy statement and stapling it on. Details of both live in `supported_and_unsupported.md` and `insights_and_directions.md`.

> **Not "we support Intel" and not "we can't do Intel" — we resolve what's in the file we were handed, and we point honestly at what isn't.**
