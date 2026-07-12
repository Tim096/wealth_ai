# External live tasks (P1-1)

`mind2web_subset.json` — a stratified ~20-task sample of
[Online-Mind2Web](https://huggingface.co/datasets/osunlp/Online-Mind2Web)
(OSU-NLP-Group, **CC-BY-4.0**, COLM 2025, arXiv:2504.01382), converted to our
task+contract format by `tools/import_mind2web.py`. Committed content is the
**task list only** (text + metadata, per-task attribution); the full dataset,
trajectories and screenshots are never committed. The dataset is HF-gated
(auto-approve): regenerate with `HF_TOKEN` set for the official file, or let
the importer fall back to an ungated CC-BY mirror (recorded in
`source.fetched_from`).

New imports intentionally leave `success_conditions` empty. Task-text-derived
strings are stored only as `advisory_landmarks`; a site name or generic verb is
not completion gold. The runner records the full trajectory and reports
`unknown` at the runtime-contract layer, while an independent WebJudge or human
review decides task completion. Existing dated subsets/runs retain their frozen
historical contracts so their provenance is not rewritten; their verifier pass
rates are landmark-hit diagnostics, not task-success rates.

Difficulty comes from the paper's rule (reference_length ≤5 easy / 6–10 medium
/ ≥11 hard) and plugs into the P1-15 step budget via the `difficulty` field.
`tools/naive_baseline.py` records the historical no-repair/no-vision shortcut
comparison. For newly imported independent-judge tasks, do not report a
verifier pass-rate baseline from `advisory_landmarks`.

## Live-task maintenance protocol

Mock-site tasks are deterministic and do not rot; **live tasks do** (redesigns,
dead URLs, new bot walls, retired features). Every entry therefore carries
`added`, `status` (`active` | `stale` | `replaced`), `replaced_by`, and
`update_history`. The rules:

1. **Staleness check (before any reported eval run, and at least monthly).**
   For each `active` task, load `website` and confirm the task is still
   *performable by a human*: page reachable (no hard CAPTCHA/login wall on the
   entry path), the feature the task names still exists. An agent failure is
   NEVER evidence of staleness — only a human/manual check or an unreachable
   site is. Record the check date in `update_history`
   (`{"date", "check": "ok" | "stale: <reason>"}`).
2. **Marking stale.** A task that fails the staleness check gets
   `status: "stale"` plus the reason in `update_history`. Stale tasks are
   excluded from success-rate denominators immediately (they still appear in
   the file — history is never deleted).
3. **Replacement rule.** A stale task is replaced by re-running
   `tools/import_mind2web.py` selection over the same upstream pool: the next
   unused task of the **same difficulty level** (and, where possible, a
   different domain than other active tasks) becomes a new entry; the stale
   entry gets `status: "replaced"` and `replaced_by: "<new task_id>"`. The new
   entry's `added` date starts its own history. Never edit a stale task's text
   to "fix" it — that silently changes the benchmark.
4. **Upstream updates.** Online-Mind2Web occasionally revises tasks (task_ids
   gain a suffix like `_110325`). On import, `source_task_id` is kept verbatim;
   when upstream replaces a task we treat ours as stale and follow rule 3.
5. **Comparability.** Any number reported from this layer must state the set
   version: the pair (`fetched_at`, count of `active` tasks) identifies it.
   Success rates from different versions are not directly comparable; the
   `update_history` chain is the audit trail.
