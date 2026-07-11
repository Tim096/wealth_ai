# Architecture

> Status: shipped & deployed (last updated 2026-07-11; originally written in the 2026-07-10 foundation phase — outdated sections rewritten against the current tree). Anything not yet implemented is explicitly marked.

## One platform, two apps

The repo is an **AI reliability platform** proven on two tasks:

1. **Browser Agent** — capability-aware browser automation with verifier-backed results and selector self-repair.
2. **SEC Extractor** — 10-K Item 1–16 structural extraction with source-exact spans and explainable confidence.

Both apps share the same reliability infrastructure. That sharing is the point: evidence, verification, eval, and cost accounting are platform concerns, not per-app afterthoughts.

## Layers

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

## Language decision

Core pipelines are **Python 3.12 in a repo-local `.venv`** (PM directive, 2026-07-10). The SPEC's TypeScript type definitions are implemented as pydantic models with identical field names, so a future TS/JS frontend consumes the same JSON shapes verbatim. The shipped web surfaces (eval dashboard, test center) are self-contained HTML served by the Python services.

## Non-negotiable invariants (enforced in code, not convention)

| Invariant | Enforcement |
|---|---|
| Lack of evidence never upgrades to success | `eval_core.combine_checks`: any unobserved condition → `unknown`, never `pass`; empty check list → `unknown` |
| LLM cannot emit arbitrary browser code | `browser_core.BrowserAction` discriminated union rejects unknown action types at validation |
| Open-ended tasks are honest, not illegal input | `BrowserTaskContract.success_conditions` allows an empty list (was min_length=1; relaxed in commit 2fec949): empty success → forbidden checks still run, then verdict short-circuits to `unknown` (human review), structurally blocking both crash-on-honest-input and vacuous pass |
| Repair is diagnosis-driven | `FAILURE_TAXONOMY` maps each failure type to a specific strategy; `silent_failure_risk` is explicitly non-repairable → `unknown` |
| LLM never generates filing text | `ItemSegment` addresses text only by `start_offset`/`end_offset`/`text_sha256`; `AdjudicatorDecision` validator rejects confident decisions without an exact source quote |
| Confidence is explainable | `ConfidenceBreakdown` is a sum of named, reasoned components — no free-floating score |
| Corrupt evidence fails loudly | `EvidenceStore` raises on malformed records instead of skipping them |

## Execution-mode economics (Browser Agent)

Script Mode (known site + known task, no LLM) → Agent Mode (unknown, LLM plans within the controlled action space) → Repair Mode (diagnosed failure, deterministic a11y-tree candidates verified in small steps). LLM spend is an escalation, not a default; vision (SoM screenshot) is a further stuck-only escalation (`AGENT_VISION` unset = auto).

## SEC pipeline determinism

Fetch → main-document detection → normalize with offset mapping → multi-detector heading candidates → TOC filter → boundary resolution → cross-reference/wrapper reassembly → verifier → confidence → independent oracles (XBRL Item 8 certification, CYD Item 1C span oracle, topic consistency, third-engine triangulation). The LLM appears exactly once, as a boundary adjudicator between existing candidates, and only when the deterministic pipeline says `ambiguous` (measured trigger rate on the 11-filing sweep: 0%).

## Current status (2026-07-11)

- Implemented: everything in the Layers table above, including both task pipelines end-to-end, the eval system (verifier calibration, degradation curves, impossible/open-ended sets, pass@k, triangulation, offset F1, CYD/XBRL oracles, external NTU head-to-head, Online-Mind2Web live subset, prompt-injection adversarial suite) with committed artifacts under `data/`.
- Tests: **813 collected** — quick lane `-m "not integration"`: 763 passed / 50 integration deselected (integration lane includes real-browser and gateway e2e). Originally 16 tests in the foundation phase; this document previously understated the suite.
- CI: `.github/workflows/ci.yml` — first run green on the `v1.0-submission` tag tree (run 29134525031: ruff clean + 743 selected → 742 passed / 1 skipped); the 20 length-prior tests added after the tag get verified on the next push.
- Reports with real data: `eval_report.md`, `cost_latency_report.md`, `failure_gallery.md`, `supported_and_unsupported.md`.
- Not implemented / explicit boundaries: cross-document exhibit body resolution (Intel/Citi class beyond same-file wrappers), pre-2001 SGML text-mode normalizer, OCR path for scanned PDFs — see `supported_and_unsupported.md` and `insights_and_directions.md`.
