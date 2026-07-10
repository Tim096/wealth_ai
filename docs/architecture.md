# Architecture

> Status: foundation phase (2026-07-10). This document describes what exists now and what is planned; anything not yet implemented is explicitly marked.

## One platform, two apps

The repo is an **AI reliability platform** proven on two tasks:

1. **Browser Agent** — capability-aware browser automation with verifier-backed results and selector self-repair.
2. **SEC Extractor** — 10-K Item 1–16 structural extraction with source-exact spans and explainable confidence.

Both apps share the same reliability infrastructure. That sharing is the point: evidence, verification, eval, and cost accounting are platform concerns, not per-app afterthoughts.

## Layers

```
apps/web/*            (planned)  — Browser Agent UI, SEC Extractor UI, Eval Dashboard
services/*            (planned)  — browser-agent-api, sec-extractor-api, eval-runner, evidence-store API
packages/             (implemented, Python)
  observability_core  — EvidenceRecord schema, JSONL EvidenceStore, hashing
  eval_core           — three-state verdict combinator, layered EvalCase schema
  browser_core        — controlled action space, task contract, failure taxonomy, selector memory
  sec_core            — ItemSegment schema, explainable ConfidenceBreakdown, LLM adjudicator I/O guard
  llm_core            — accounted LLM call records (cost / latency / schema validity)
data/                 (planned)  — eval sets, mock sites, golden labels
prompts/              (active)   — every prompt that influenced design/code/eval/docs, with decisions
docs/                 (active)   — SPEC, this file, reports
```

## Language decision

Core pipelines are **Python 3.12 in a repo-local `.venv`** (PM directive, 2026-07-10). The SPEC's TypeScript type definitions are implemented as pydantic models with identical field names, so a future TS/JS frontend consumes the same JSON shapes verbatim. Frontend stack is decided when `apps/web/*` starts.

## Non-negotiable invariants (enforced in code, not convention)

| Invariant | Enforcement |
|---|---|
| Lack of evidence never upgrades to success | `eval_core.combine_checks`: any unobserved condition → `unknown`, never `pass`; empty check list → `unknown` |
| LLM cannot emit arbitrary browser code | `browser_core.BrowserAction` discriminated union rejects unknown action types at validation |
| Every task must be verifiable before it runs | `BrowserTaskContract.success_conditions` requires ≥1 condition |
| Repair is diagnosis-driven | `FAILURE_TAXONOMY` maps each failure type to a specific strategy; `silent_failure_risk` is explicitly non-repairable → `unknown` |
| LLM never generates filing text | `ItemSegment` addresses text only by `start_offset`/`end_offset`/`text_sha256`; `AdjudicatorDecision` validator rejects confident decisions without an exact source quote |
| Confidence is explainable | `ConfidenceBreakdown` is a sum of named, reasoned components — no free-floating score |
| Corrupt evidence fails loudly | `EvidenceStore` raises on malformed records instead of skipping them |

## Execution-mode economics (Browser Agent)

Script Mode (known site + known task, no LLM) → Agent Mode (unknown, LLM plans within the controlled action space) → Repair Mode (diagnosed failure, LLM proposes candidates that are verified in small steps). LLM spend is an escalation, not a default.

## SEC pipeline determinism

Fetch → main-document detection → normalize with offset mapping → multi-detector heading candidates → TOC filter → boundary resolution → verifier → confidence. The LLM appears exactly once, as a boundary adjudicator between existing candidates, and only when the deterministic pipeline says `ambiguous`.

## Current status

- Implemented: all `packages/*` schemas and invariants above, 16 passing tests (`.venv\Scripts\python -m pytest`).
- Not implemented yet: executors, fetchers, detectors, services, frontends, eval sets, dashboards. Reports (`eval_report.md`, `cost_latency_report.md`) will be created when there is real data to report — an empty report template would be theater.
