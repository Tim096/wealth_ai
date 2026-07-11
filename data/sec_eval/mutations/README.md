# Verifier mutation-harness fixtures (P0-4)

Small committed helpers for `tests/test_verifier_mutations.py` — the runtime
verifier mutation harness. The harness injects known corruptions into real
pipeline outputs and asserts the shipped verification layers (topic_check,
third-engine triangulation, heading-at-segment-start, boundary length band)
catch them.

Files:

- `toc_stub.txt` — a synthetic table-of-contents block (dotted leaders + page
  numbers). Used by the `toc_anchor` mutation class: a span replaced by this
  block simulates a TOC-anchored mis-extraction.
- `wrapper_financial_section.txt` — a synthetic bound Financial Section
  (~1,400 words: audit report, balance sheet, income statement, cash flows,
  notes). Used by the `wrapper_swallow` class: appended to a terminal item it
  simulates the JPM/XOM "wrapper 10-K" runaway span.

Mutation classes (closed): `truncate`, `misalign`, `toc_anchor`,
`wrapper_swallow`; (open): `jitter` (random +/-5..25% boundary jitter),
`cross_swap` (cross-item body swap).

Quantified gates (asserted in the tests, not just reported):
per-mutation-class detection recall >= 0.95; clean false-alarm rate <= 0.05
on unmutated bases AND on the recorded sweep3 verifier outputs
(`data/sec_eval/records/sweep3` + `data/sec_eval/triangulation`).

All fixture text here is synthetic (written for this repo) — no SEC filing
text is committed.
