"""P0-12: LLM adjudicator tier wiring + cost accounting.

The deterministic pipeline never calls an LLM; adjudicate_ambiguous() is the
one opt-in escalation. These tests use a fake client (no network) to verify
the schema/evidence-quote gates and the per-filing cost accounting, plus the
sweep_metrics cost-column aggregation (including pre-P0-12 record back-compat).
"""

import json
import sys
from pathlib import Path

import pytest

from llm_core.openai_client import LLMResponse, OpenAIClient
from sec_core.pipeline import adjudicate_ambiguous, extract_from_html

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import sweep_metrics  # noqa: E402

# Two plausible non-TOC "Item 1" headings -> runner-up scores within the
# ambiguity margin -> status == ambiguous (the adjudicator's only trigger).
AMBIG_HTML = """<html><body>
<p>ANNUAL REPORT ON FORM 10-K</p>
<p><b>Item 1. Business</b></p>
<p>We are a diversified manufacturer of widgets. This overview summarizes the company.</p>
<p>Some intervening narrative that continues for a while to give the first candidate a body.
The company operates in three segments and sells worldwide.</p>
<p><b>Item 1. Business</b></p>
<p>General. The Registrant is a corporation organized under the laws of Delaware. Our
business consists of the design, manufacture and sale of widgets and related services.
Customers include industrial distributors. Competition is intense. Employees number 4,200.</p>
<p><b>Item 1A. Risk Factors</b></p>
<p>Our business faces risks and uncertainties, including risk factors related to competition,
supply chain disruption, and regulatory change that could adversely affect our results.</p>
<p><b>Item 2. Properties</b></p>
<p>We own our headquarters facility and lease manufacturing plants in several locations.</p>
<p><b>Item 3. Legal Proceedings</b></p>
<p>We are party to ordinary routine litigation incidental to the business.</p>
<p><b>Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations</b></p>
<p>The following discussion analyzes our results of operations and liquidity and capital resources.</p>
<p><b>Item 8. Financial Statements and Supplementary Data</b></p>
<p>The consolidated financial statements are included herein. Consolidated balance sheet data follows.</p>
<p>SIGNATURES</p>
</body></html>"""


class FakeClient:
    """OpenAIClient-shaped stub: returns a canned decision, accounts fake usage."""

    def __init__(self, decision: dict):
        self.decision = decision
        self.calls = 0

    def available(self) -> bool:
        return True

    def complete_json(self, system: str, user: str, image_path=None):
        self.calls += 1
        return self.decision, LLMResponse(
            text=json.dumps(self.decision), input_tokens=1000, output_tokens=50,
            cost_usd=0.00035, latency_ms=1234.0, model="fake-model", prompt_sha256="deadbeef",
        )


@pytest.fixture()
def ambig_result():
    result = extract_from_html(AMBIG_HTML, "ambig_fixture")
    assert result.segment("1").status == "ambiguous"
    return result


def test_deterministic_path_has_zero_llm_cost(ambig_result):
    assert ambig_result.llm_calls == 0
    assert ambig_result.llm_input_tokens == 0
    assert ambig_result.llm_output_tokens == 0
    assert ambig_result.llm_cost_usd == 0.0
    assert ambig_result.llm_call_records == []


def test_adjudication_accounts_cost_and_records_evidence(ambig_result):
    seg = ambig_result.segment("1")
    span_before = (seg.start_offset, seg.end_offset)
    # a quote guaranteed verbatim inside candidate A's context window
    quote = ambig_result.doc.slice(seg.start_offset, seg.start_offset + 40)
    client = FakeClient({"decision": "candidate_b", "confidence": 0.8,
                         "evidence_quote": quote, "reason": "candidate B has the body"})

    calls = adjudicate_ambiguous(ambig_result, client)

    assert calls == 1 and client.calls == 1
    assert ambig_result.llm_calls == 1
    assert ambig_result.llm_input_tokens == 1000
    assert ambig_result.llm_output_tokens == 50
    assert ambig_result.llm_cost_usd == pytest.approx(0.00035)
    rec = ambig_result.llm_call_records[0]
    assert rec.purpose == "boundary_adjudicator"
    assert rec.schema_valid is True
    assert rec.cost_usd == pytest.approx(0.00035)
    # the decision is evidence, never a silent span rewrite
    assert (seg.start_offset, seg.end_offset) == span_before
    assert seg.needs_review is True
    ev = next(e for e in seg.evidence if e.kind == "llm_adjudication")
    assert "decision=candidate_b" in ev.detail
    assert any("LLM adjudicator: candidate_b" in w for w in seg.warnings)


def test_confident_decision_without_quote_fails_schema_gate(ambig_result):
    client = FakeClient({"decision": "candidate_a", "confidence": 0.9,
                         "evidence_quote": "", "reason": "trust me"})
    adjudicate_ambiguous(ambig_result, client)
    assert ambig_result.llm_call_records[0].schema_valid is False
    ev = next(e for e in ambig_result.segment("1").evidence if e.kind == "llm_adjudication")
    assert "decision=unknown" in ev.detail


def test_non_verbatim_quote_is_downgraded_to_unknown(ambig_result):
    client = FakeClient({"decision": "candidate_a", "confidence": 0.9,
                         "evidence_quote": "this text appears nowhere in the filing",
                         "reason": "fabricated"})
    adjudicate_ambiguous(ambig_result, client)
    assert ambig_result.llm_call_records[0].schema_valid is True  # schema ok, quote gate failed
    ev = next(e for e in ambig_result.segment("1").evidence if e.kind == "llm_adjudication")
    assert "decision=unknown" in ev.detail
    assert "verbatim" in ev.detail


def test_no_client_configured_is_a_noop(ambig_result):
    calls = adjudicate_ambiguous(ambig_result, OpenAIClient(api_key=""))
    assert calls == 0
    assert ambig_result.llm_calls == 0
    assert any("no client configured" in w for w in ambig_result.warnings)


def test_env_flag_without_key_stays_deterministic(monkeypatch):
    monkeypatch.setenv("SEC_LLM_ADJUDICATE", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = extract_from_html(AMBIG_HTML, "ambig_envflag")
    assert result.llm_calls == 0
    assert any("no client configured" in w for w in result.warnings)


def _record(ticker: str, with_cost: bool) -> dict:
    rec = {
        "ticker": ticker, "form": "10-K", "report_date": "2025-12-31",
        "raw_chars": 1000, "latency_ms": 100.0, "candidates": 5, "toc_rejected": 1,
        "items": {"1": {"status": "pass", "confidence": 0.95, "toc_listed": True}},
    }
    if with_cost:
        rec.update({"llm_calls": 2, "llm_tokens": 2100, "llm_usd": 0.0007})
    return rec


def test_sweep_metrics_aggregates_cost_columns(tmp_path, monkeypatch, capsys):

    (tmp_path / "a.json").write_text(json.dumps(_record("AAA", with_cost=True)), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps(_record("BBB", with_cost=False)), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["sweep_metrics.py", str(tmp_path)])
    sweep_metrics.main()
    out = capsys.readouterr().out
    assert "llm cost: calls 2, tokens 2100, usd $0.0007" in out
    assert "pre-P0-12 records" in out  # back-compat note when old records present
    assert "| AAA | 10-K 2025-12-31 | 1,000 | 1 | 0 | 1 | 1/5 | 100 | 2 | $0.0007 |" in out
    assert "| BBB | 10-K 2025-12-31 | 1,000 | 1 | 0 | 1 | 1/5 | 100 | 0 | $0.0000 |" in out
