"""Advisory second judge (P0-8, WebJudge → Agent-as-a-Judge lineage).

Per-condition binary micro-judgments + deterministic aggregation — NEVER a
"grade the whole trajectory in one LLM call" WebJudge-style task-level review.
The citation chain says the decomposition itself is the accuracy gain:
WebJudge o4-mini 85.7% human agreement (arXiv:2504.01382) → Mind2Web 2
Agent-as-a-Judge 99.03% leaf-level (arXiv:2506.21506,
`mind2web2/verification_tree.py`). Mechanisms adopted from Mind2Web 2:

  1. gate-then-average aggregation instead of a flat AND: critical conditions
     gate (fail one → fail, excluded from the average), non-critical average
     into partial credit, sequential chains short-circuit — a more informative
     partial-completion signal than spec-pass-rate;
  2. Extractor/Verifier separation: the extractor (LLM or offline) only quotes
     a VERBATIM span and proposes a judgment; a deterministic verifier stage
     demotes any "satisfied" whose quoted span is not actually present in the
     cached evidence to abstain ("not supported") — hallucinated evidence can
     never pass;
  3. stub-pass smoke test: the full pipeline runs once with every verification
     stubbed to satisfied, catching runtime errors in the judge itself before
     any real judgment is trusted;
  4. evidence pre-caching: judgments are made ONLY from a snapshot (url +
     visible text) persisted BEFORE judging — replayable and auditable.

Project law: the runtime verifier stays the SOLE judge (same contract as
false_success.py). This module is opt-in tooling (`browser_eval --second-judge`);
its output is a per-condition diff vs the primary verifier plus an adjudication
artifact — a disagreement flags needs_review (the SEC track's triangulate.py
disagree pattern), it never changes a verdict. Judgments carry an EXPLICIT
abstain state; LLM calls go through llm_core.openai_client (temperature 0).
The offline fallback extractor is a deliberately independent naive reading
(quote the matching line, no query-echo masking): divergence from the primary
on e.g. zero-result echo lines is adjudication signal, not a bug — a second
judge that copies the primary's logic would produce zero information.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from observability_core import sha256_text

# how much cached visible text an LLM extractor prompt carries
_EVIDENCE_TEXT_CAP = 4000

# extractor proposal states (LLM output contract) / final judgment verdicts
_PROPOSALS = ("satisfied", "not_satisfied", "cannot_tell")
VERDICTS = ("yes", "no", "abstain", "skipped")

# per-condition verdict → the primary verifier's status axis, for the diff
_TO_PRIMARY = {"yes": "pass", "no": "fail", "abstain": "unknown"}

_SYSTEM = (
    "You are the EXTRACTOR stage of a web-task judge. You receive ONE "
    "machine-checkable condition and a cached snapshot of the final page "
    "(URL + visible text). Quote the single most relevant VERBATIM span from "
    "the snapshot that bears on the condition — copy it exactly, never invent "
    "or paraphrase; if nothing in the snapshot bears on the condition, "
    "extracted must be null. Then give a binary micro-judgment on THIS "
    "condition only. Respond with JSON only: "
    '{"extracted": string|null, "judgment": "satisfied"|"not_satisfied"|'
    '"cannot_tell", "reason": string}'
)


class SecondJudgeSmokeError(RuntimeError):
    """The stub-pass smoke run did not come out all-yes: the judge pipeline
    itself is broken (or the cached evidence is empty) — its real judgments
    must not be trusted."""


@dataclass
class MicroJudgment:
    """One binary micro-judgment for one contract condition."""
    condition: str              # 'type:value' key, same shape as the verifier's
    verdict: str                # yes | no | abstain | skipped
    extracted: str | None       # verbatim span the judgment rests on (or None)
    reason: str
    source: str                 # llm | offline | stub
    cost_usd: float = 0.0

    def as_dict(self) -> dict:
        return {"condition": self.condition, "verdict": self.verdict,
                "extracted": self.extracted, "reason": self.reason,
                "source": self.source, "cost_usd": round(self.cost_usd, 6)}


# --- evidence pre-caching (mechanism 4) ---

def cache_evidence(url: str, visible_text: str, path: Path) -> dict:
    """Persist the snapshot the judge will rule on BEFORE any judging, so every
    judgment is replayable against the exact bytes it saw. Returns the dict."""
    ev = {"url": url, "visible_text": visible_text,
          "sha256": sha256_text(f"{url}|{visible_text}"),
          "cached_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ev, indent=2, ensure_ascii=False), encoding="utf-8")
    return ev


def load_evidence(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# --- extractors (stage 1 of the Extractor/Verifier split) ---

class StubExtractor:
    """Every verification stubbed to satisfied — the Mind2Web 2 stub-pass
    smoke test that catches runtime errors in the pipeline itself."""
    source = "stub"

    def extract(self, cond_type: str, value: str, evidence: dict) -> dict:
        span = evidence.get("url") or (evidence.get("visible_text") or "").strip()[:80]
        return {"extracted": span, "judgment": "satisfied",
                "reason": "stub-pass smoke test: verification stubbed to satisfied"}


class OfflineExtractor:
    """Deterministic no-LLM fallback: a deliberately independent naive reading.
    text_visible quotes the first line containing the needle (NO query-echo
    masking — diverging from the primary there is the adjudication signal);
    url_contains reads the cached url; anything else is an honest cannot_tell."""
    source = "offline"

    def extract(self, cond_type: str, value: str, evidence: dict) -> dict:
        if cond_type == "url_contains":
            url = evidence.get("url", "")
            if value in url:
                return {"extracted": url, "judgment": "satisfied",
                        "reason": f"cached url contains {value!r}"}
            return {"extracted": None, "judgment": "not_satisfied",
                    "reason": f"cached url does not contain {value!r}"}
        if cond_type == "text_visible":
            needle = value.casefold()
            for line in (evidence.get("visible_text") or "").splitlines():
                if needle in line.casefold():
                    return {"extracted": line.strip(), "judgment": "satisfied",
                            "reason": f"line containing {value!r} found in cached text"}
            return {"extracted": None, "judgment": "not_satisfied",
                    "reason": f"{value!r} not found in cached text"}
        return {"extracted": None, "judgment": "cannot_tell",
                "reason": f"condition type {cond_type!r} is not judgeable offline "
                          "from a cached page snapshot"}


class LLMExtractor:
    """LLM extractor over llm_core.openai_client (temperature 0 there). A
    malformed / non-contract response is normalized to cannot_tell — the
    explicit abstain state, never a silent zero (the WebCanvas eval() +
    silently-score-0 anti-pattern)."""
    source = "llm"

    def __init__(self, client=None) -> None:
        if client is None:
            from llm_core.openai_client import OpenAIClient
            client = OpenAIClient()
        self.client = client

    def extract(self, cond_type: str, value: str, evidence: dict) -> dict:
        user = (f"Condition: {cond_type}: {value}\n\n"
                f"Cached page snapshot\nURL: {evidence.get('url', '')}\n"
                f"Visible text:\n{(evidence.get('visible_text') or '')[:_EVIDENCE_TEXT_CAP]}")
        parsed, resp = self.client.complete_json(_SYSTEM, user)
        out = {"extracted": None, "judgment": "cannot_tell",
               "reason": "malformed judge output", "cost_usd": resp.cost_usd}
        if isinstance(parsed, dict) and not parsed.get("_parse_error") \
                and parsed.get("judgment") in _PROPOSALS:
            out["extracted"] = parsed.get("extracted") or None
            out["judgment"] = parsed["judgment"]
            out["reason"] = str(parsed.get("reason", ""))
        return out


# --- deterministic verifier stage (stage 2) + per-condition judging ---

def _norm(s: str) -> str:
    return " ".join(s.split()).casefold()


def judge_condition(cond_type: str, value: str, evidence: dict,
                    extractor) -> MicroJudgment:
    """One micro-judgment: extractor proposes (span + judgment), then the
    deterministic verifier stage rules. A 'satisfied' whose quoted span is not
    verbatim in the cached evidence is DEMOTED to abstain ('not supported') —
    hallucinated evidence can never pass. Extractor errors are abstains too."""
    key = f"{cond_type}:{value}"
    try:
        out = extractor.extract(cond_type, value, evidence)
    except Exception as e:  # noqa: BLE001 — a judge crash must not kill the eval
        return MicroJudgment(key, "abstain", None,
                             f"extractor error: {type(e).__name__}: {e}", extractor.source)
    extracted = out.get("extracted") or None
    reason = out.get("reason", "")
    cost = float(out.get("cost_usd", 0.0))
    judgment = out.get("judgment")
    if judgment == "satisfied":
        hay = _norm(f"{evidence.get('url', '')}\n{evidence.get('visible_text', '')}")
        if not extracted or _norm(extracted) not in hay:
            return MicroJudgment(key, "abstain", extracted,
                                 "not supported: extracted span absent from cached "
                                 "evidence — hallucinated evidence cannot pass",
                                 extractor.source, cost)
        return MicroJudgment(key, "yes", extracted, reason, extractor.source, cost)
    if judgment == "not_satisfied":
        return MicroJudgment(key, "no", extracted, reason, extractor.source, cost)
    return MicroJudgment(key, "abstain", extracted,
                         reason or "cannot tell", extractor.source, cost)


def gate_then_average(judgments: list[MicroJudgment],
                      critical: set[str] | None = None) -> dict:
    """Deterministic gate-then-average aggregation (Mind2Web 2, replacing the
    flat AND): conditions in `critical` are gates — any 'no' fails the whole
    task and gates never enter the average; the rest average into a [0,1]
    partial-credit score ('skipped' counts 0, abstains are excluded from the
    mean but block a full 'yes'). Verdict axis: yes | no | partial | abstain."""
    critical = critical or set()
    if not judgments:
        return {"verdict": "abstain", "score": None, "gate_failed": [],
                "gate_abstained": [], "n_gates": 0, "n_averaged": 0,
                "n_abstain": 0, "reason": "no conditions to judge"}
    gates = [j for j in judgments if j.condition in critical]
    rest = [j for j in judgments if j.condition not in critical]
    gate_failed = [j.condition for j in gates if j.verdict in ("no", "skipped")]
    gate_abstained = [j.condition for j in gates if j.verdict == "abstain"]
    base = {"gate_failed": gate_failed, "gate_abstained": gate_abstained,
            "n_gates": len(gates), "n_abstain": sum(j.verdict == "abstain" for j in rest)}
    if gate_failed:
        return {"verdict": "no", "score": 0.0, "n_averaged": 0,
                "reason": f"gate failed: {', '.join(gate_failed)}", **base}
    if gate_abstained:
        return {"verdict": "abstain", "score": None, "n_averaged": 0,
                "reason": f"gate abstained: {', '.join(gate_abstained)}", **base}
    judged = [j for j in rest if j.verdict in ("yes", "no", "skipped")]
    if not judged:
        # gates all passed but nothing else was judgeable
        if rest:
            return {"verdict": "abstain", "score": None, "n_averaged": 0,
                    "reason": "every non-gate condition abstained", **base}
        return {"verdict": "yes", "score": 1.0, "n_averaged": 0,
                "reason": "all gates satisfied; no non-critical conditions", **base}
    score = sum(j.verdict == "yes" for j in judged) / len(judged)
    if score == 1.0 and base["n_abstain"] == 0:
        verdict = "yes"
    elif score == 0.0 and base["n_abstain"] == 0:
        verdict = "no"
    else:
        verdict = "partial"
    return {"verdict": verdict, "score": round(score, 3), "n_averaged": len(judged),
            "reason": f"{sum(j.verdict == 'yes' for j in judged)}/{len(judged)} "
                      "non-gate conditions satisfied", **base}


def judge_task(conditions, evidence: dict, extractor,
               critical: set[str] | None = None, sequential: bool = False) -> dict:
    """Judge every success condition (objects with .type/.value) against the
    cached evidence and aggregate. sequential=True short-circuits: after the
    first 'no', later conditions are marked 'skipped' without an extractor
    call (a step whose predecessor failed cannot have been reached)."""
    judgments: list[MicroJudgment] = []
    short_circuited = False
    for c in conditions:
        key = f"{c.type}:{c.value}"
        if short_circuited:
            judgments.append(MicroJudgment(
                key, "skipped", None,
                "short-circuited: an earlier condition in the sequential chain failed",
                extractor.source))
            continue
        j = judge_condition(c.type, c.value, evidence, extractor)
        judgments.append(j)
        if sequential and j.verdict == "no":
            short_circuited = True
    return {"judgments": judgments,
            "aggregate": gate_then_average(judgments, critical)}


def judge_open_ended(natural_language_task: str, expected_outcome: str,
                     evidence: dict, extractor) -> dict:
    """Score channel for the open-ended unknown bucket: a contract with ZERO
    machine-checkable conditions gets one micro-judgment against its
    expected_outcome. Advisory only — the primary's honest `unknown` stands;
    this just attaches a score (yes=1.0 / no=0.0 / abstain=None). The offline
    extractor abstains here (semantics are not judgeable offline)."""
    j = judge_condition("expected_outcome", expected_outcome, evidence, extractor)
    j.reason = f"open-ended task {natural_language_task!r}: {j.reason}"
    score = {"yes": 1.0, "no": 0.0}.get(j.verdict)
    return {"judgment": j, "score": score}


def diff_with_primary(judgments: list[MicroJudgment],
                      primary: dict[str, str]) -> list[dict]:
    """Per-condition diff vs the primary verifier's statuses (same 'type:value'
    keys, e.g. from check_conditions on the same cached snapshot). agree=None
    when no comparison is possible (skipped, or the primary never checked the
    key); a False flags needs_review — the triangulate.py disagree pattern."""
    rows = []
    for j in judgments:
        p = primary.get(j.condition)
        mapped = _TO_PRIMARY.get(j.verdict)
        agree = None if (mapped is None or p is None) else mapped == p
        rows.append({"condition": j.condition, "primary": p, "second": j.verdict,
                     "agree": agree, "needs_review": agree is False,
                     "extracted": j.extracted, "reason": j.reason})
    return rows


def smoke_test(conditions, evidence: dict) -> dict:
    """Stub-pass smoke test (Mind2Web 2): run the FULL pipeline — judging,
    aggregation, diff — with every verification stubbed to satisfied, to catch
    runtime errors in the judge itself. Raises SecondJudgeSmokeError if the
    stubbed run is not all-yes (pipeline logic or evidence is broken)."""
    result = judge_task(conditions, evidence, StubExtractor())
    diff_with_primary(result["judgments"],
                      {j.condition: "pass" for j in result["judgments"]})
    bad = [j.condition for j in result["judgments"] if j.verdict != "yes"]
    if bad:
        raise SecondJudgeSmokeError(
            f"stub-pass smoke test failed for: {', '.join(bad)} — "
            "the judge pipeline (or its cached evidence) is broken")
    return result
