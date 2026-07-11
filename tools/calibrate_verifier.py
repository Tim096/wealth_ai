"""Verifier calibration harness (T1-1, SPEC eval-upgrade).

Calibrates the JUDGE itself: feeds verify_contract() >=20 known-success and
>=20 programmatically-corrupted (contract, Observation, extracted) triples —
no browser, fully offline — and measures a confusion matrix (FP/FN rate),
then applies the Rogan-Gladen estimator to correct the apparent success rate
of the real eval run. Basis: judge AUROC 0.54-0.65 in production
(arxiv 2606.10315); verifier FP rate is the ceiling of eval credibility.

Two label layers, kept explicit:
  - calibration labels here are ground truth BY CONSTRUCTION (we build the
    corruption, so we know the truth) — strong labels;
  - the eval set's expect_status in data/browser_eval/tasks.json is
    hand-authored — weaker; Rogan-Gladen corrects the APPARENT rate measured
    against page state, it does not launder the hand labels.

Scope (honest): only condition types with an evidence surface are calibrated
(url_contains, text_visible, download_exists, answer_matches, and the
forbidden checks). answer_matches gained an evidence surface with the P2
answer channel (extract_text -> extracted['answer']), so it is IN scope:
answer present + regex match = pass, present + no match = fail, absent = fail.
table_extracted / screenshot_region_changed / field_value_equals return
unknown-or-need-extracted by design and would skew the matrix with structural
unknowns — excluded and declared in the output.

Usage: .venv/Scripts/python tools/calibrate_verifier.py
Writes data/browser_eval/calibration/{calibration_cases,calibration_results}.json
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from browser_agent.observer import Observation
from browser_agent.verifier import verify_contract
from browser_core import BrowserTaskContract

ROOT = Path(__file__).resolve().parents[1]
CAL_DIR = ROOT / "data" / "browser_eval" / "calibration"
EVAL_ARTIFACT = ROOT / "data" / "browser_eval" / "artifacts" / "eval_results.json"

# denominator below this is statistically meaningless -> verdict on the
# corrected rate is unknown, never a fabricated number
_MIN_DENOM = 0.10

_PRODUCTS = ["widget", "gizmo", "doohickey", "sprocket", "flange", "gadget"]
_SECTIONS = ["Risk Factors", "Management Discussion", "Legal Proceedings",
             "Controls and Procedures", "Executive Compensation", "Market Risk"]
_PAGES = ["pricing", "about", "contact", "faq", "terms", "privacy"]
_PAD = "x" * 1200  # padding so download fixtures clear the 512-byte floor


def _search_contract(cid: str, product: str) -> dict:
    return {
        "task_id": cid,
        "natural_language_task": f"Search MockShop for '{product}'",
        "expected_outcome": "results page shows the product",
        "success_conditions": [
            {"type": "text_visible", "value": "results for"},
            {"type": "text_visible", "value": product.title()},
            {"type": "url_contains", "value": "/results"},
        ],
        "forbidden_conditions": [
            {"type": "captcha_visible", "value": "captcha"},
            {"type": "error_text_visible", "value": "no results"},
        ],
    }


def _download_contract(cid: str, needle: str) -> dict:
    return {
        "task_id": cid,
        "natural_language_task": f"Download the filing section '{needle}'",
        "expected_outcome": "a real document containing the section is on disk",
        "success_conditions": [{"type": "download_exists", "value": needle}],
        "forbidden_conditions": [],
    }


_ANSWER_RE = r"[\$][0-9][0-9,\.]+\s*(billion|million)?"


def _answer_contract(cid: str) -> dict:
    return {
        "task_id": cid,
        "natural_language_task": "找出頁面上的營收數字",
        "expected_outcome": "the extracted answer carries the revenue figure",
        "success_conditions": [{"type": "answer_matches", "value": _ANSWER_RE}],
        "forbidden_conditions": [],
    }


def _nav_contract(cid: str, page: str) -> dict:
    return {
        "task_id": cid,
        "natural_language_task": f"Open the {page} page",
        "expected_outcome": f"the {page} page is shown on the right domain",
        "success_conditions": [
            {"type": "url_contains", "value": f"/docs/{page}"},
            {"type": "text_visible", "value": page.title()},
        ],
        "forbidden_conditions": [{"type": "wrong_domain", "value": "mockshop.local"}],
    }


def build_cases() -> list[dict]:
    """Deterministic calibration set: 24 known-success + 26 corrupted
    (4 corruption classes x 6, + answer_wrong x 2). No randomness — same
    cases every run."""
    cases: list[dict] = []

    # --- known success: search (6) ---
    for p in _PRODUCTS:
        cases.append({
            "case_id": f"cal-ok-search-{p}", "label": "success", "corruption_class": None,
            "contract": _search_contract(f"cal-ok-search-{p}", p),
            "observation": {"url": f"http://mockshop.local/results?q={p}", "title": "Results",
                            "visible_text": f"3 results for {p}: {p.title()} Pro — in stock",
                            "modal_present": False},
            "download_file": None,
        })

    # --- known success: download with content needle (6) ---
    for s in _SECTIONS:
        slug = s.lower().replace(" ", "-")
        cases.append({
            "case_id": f"cal-ok-dl-{slug}", "label": "success", "corruption_class": None,
            "contract": _download_contract(f"cal-ok-dl-{slug}", s),
            "observation": {"url": "http://mockshop.local/sec-filings/aapl-10k", "title": "Filing",
                            "visible_text": "Filing viewer", "modal_present": False},
            "download_file": {"name": f"aapl-10k-{slug}.htm",
                              "content": f"<h1>Item — {s}</h1>" + _PAD},
        })

    # --- known success: download, no needle required (4) ---
    for i in range(4):
        cases.append({
            "case_id": f"cal-ok-dl-plain-{i}", "label": "success", "corruption_class": None,
            "contract": _download_contract(f"cal-ok-dl-plain-{i}", ""),
            "observation": {"url": "http://mockshop.local/downloads", "title": "Downloads",
                            "visible_text": "Download center", "modal_present": False},
            "download_file": {"name": f"report-{i}.htm", "content": "y" * 2000},
        })

    # --- known success: navigation on the right domain (6) ---
    for page in _PAGES:
        cases.append({
            "case_id": f"cal-ok-nav-{page}", "label": "success", "corruption_class": None,
            "contract": _nav_contract(f"cal-ok-nav-{page}", page),
            "observation": {"url": f"http://mockshop.local/docs/{page}", "title": page,
                            "visible_text": f"{page.title()} — everything you need to know.",
                            "modal_present": False},
            "download_file": None,
        })

    # --- corruption class 1: needle_removed (6) — success text mutated away ---
    for p in _PRODUCTS[:3]:  # product name scrambled (query echo removed so it can't leak the needle)
        scrambled = p[1] + p[0] + p[2:]
        cases.append({
            "case_id": f"cal-bad-needle-{p}", "label": "corrupted", "corruption_class": "needle_removed",
            "contract": _search_contract(f"cal-bad-needle-{p}", p),
            "observation": {"url": f"http://mockshop.local/results?q={p}", "title": "Results",
                            "visible_text": f"3 results for your query: {scrambled.title()} Pro",
                            "modal_present": False},
            "download_file": None,
        })
    for p in _PRODUCTS[3:]:  # 'results for' phrasing gone entirely
        cases.append({
            "case_id": f"cal-bad-phrase-{p}", "label": "corrupted", "corruption_class": "needle_removed",
            "contract": _search_contract(f"cal-bad-phrase-{p}", p),
            "observation": {"url": f"http://mockshop.local/results?q={p}", "title": "Results",
                            "visible_text": f"Showing matches: {p.title()} Pro — in stock",
                            "modal_present": False},
            "download_file": None,
        })

    # --- corruption class 2: wrong_url (6) — page text deceptively right, URL wrong ---
    for p in _PRODUCTS[:3]:  # error page carrying copied results text
        cases.append({
            "case_id": f"cal-bad-url-{p}", "label": "corrupted", "corruption_class": "wrong_url",
            "contract": _search_contract(f"cal-bad-url-{p}", p),
            "observation": {"url": f"http://mockshop.local/error?src=search&q={p}", "title": "Error",
                            "visible_text": f"3 results for {p}: {p.title()} Pro — in stock",
                            "modal_present": False},
            "download_file": None,
        })
    for p in _PRODUCTS[3:]:  # lookalike domain -> forbidden wrong_domain must fire
        cases.append({
            "case_id": f"cal-bad-domain-{p}", "label": "corrupted", "corruption_class": "wrong_url",
            "contract": {**_search_contract(f"cal-bad-domain-{p}", p),
                         "forbidden_conditions": [{"type": "wrong_domain", "value": "mockshop.local"}]},
            "observation": {"url": f"http://phish.example/results?q={p}", "title": "Results",
                            "visible_text": f"3 results for {p}: {p.title()} Pro — in stock",
                            "modal_present": False},
            "download_file": None,
        })

    # --- corruption class 3: download_wrong_content (6) — right-looking file, wrong bytes ---
    _captcha = "Are you a robot? Please verify you are human to continue." + _PAD
    for s in _SECTIONS[:2]:  # blocked page saved under the right name
        slug = s.lower().replace(" ", "-")
        cases.append({
            "case_id": f"cal-bad-dlcontent-{slug}", "label": "corrupted",
            "corruption_class": "download_wrong_content",
            "contract": _download_contract(f"cal-bad-dlcontent-{slug}", s),
            "observation": {"url": "http://mockshop.local/sec-filings/aapl-10k", "title": "Filing",
                            "visible_text": "Filing viewer", "modal_present": False},
            "download_file": {"name": f"aapl-10k-{slug}.htm", "content": _captcha},
        })
    for s in _SECTIONS[2:4]:  # trivially small stub is not a document
        slug = s.lower().replace(" ", "-")
        cases.append({
            "case_id": f"cal-bad-dlstub-{slug}", "label": "corrupted",
            "corruption_class": "download_wrong_content",
            "contract": _download_contract(f"cal-bad-dlstub-{slug}", s),
            "observation": {"url": "http://mockshop.local/sec-filings/aapl-10k", "title": "Filing",
                            "visible_text": "Filing viewer", "modal_present": False},
            "download_file": {"name": f"aapl-10k-{slug}.htm", "content": "stub"},
        })
    # needle appears ONLY in the filename, bytes are a blocked page. This used
    # to be a REAL false positive (the verifier accepted the basename as
    # proof, FG-BROWSER-002); the content-first fix reads the bytes: readable
    # content without the needle -> fail, however right the filename looks.
    cases.append({
        "case_id": "cal-bad-dlname-annual-report", "label": "corrupted",
        "corruption_class": "download_wrong_content",
        "contract": _download_contract("cal-bad-dlname-annual-report", "annual report"),
        "observation": {"url": "http://mockshop.local/sec-filings/aapl-10k", "title": "Filing",
                        "visible_text": "Filing viewer", "modal_present": False},
        "download_file": {"name": "annual report 2025.htm", "content": _captcha},
    })
    # extracted points at a path that does not exist -> honest unknown
    cases.append({
        "case_id": "cal-bad-dlmissing", "label": "corrupted",
        "corruption_class": "download_wrong_content",
        "contract": _download_contract("cal-bad-dlmissing", "Risk Factors"),
        "observation": {"url": "http://mockshop.local/sec-filings/aapl-10k", "title": "Filing",
                        "visible_text": "Filing viewer", "modal_present": False},
        "download_file": None, "extracted_missing_path": True,
    })

    # --- known success: answer channel (2) — extracted answer matches the pattern ---
    for i, ans in enumerate(["Total revenue: $53.1 billion, up 8% year over year.",
                             "Revenue was $790.9 million in Q4."]):
        cases.append({
            "case_id": f"cal-ok-answer-{i}", "label": "success", "corruption_class": None,
            "contract": _answer_contract(f"cal-ok-answer-{i}"),
            "observation": {"url": "http://mockcorp.local/investors", "title": "Investors",
                            "visible_text": "MockCorp investor relations", "modal_present": False},
            "download_file": None, "answer": ans,
        })

    # --- corruption class 5: answer_wrong (2) — the P2 answer-channel failures.
    # (a) an answer WAS delivered but it is the wrong text (regex unmatched);
    # (b) no answer at all — the agent never made a delivery move (the INTC
    #     shape: claiming the number without extracting it). Both must be fail.
    cases.append({
        "case_id": "cal-bad-answer-wrong-text", "label": "corrupted",
        "corruption_class": "answer_wrong",
        "contract": _answer_contract("cal-bad-answer-wrong-text"),
        "observation": {"url": "http://mockcorp.local/investors", "title": "Investors",
                        "visible_text": "MockCorp investor relations", "modal_present": False},
        "download_file": None,
        "answer": "MockCorp designs widgets. Founded in 1998, operating in 14 countries.",
    })
    cases.append({
        "case_id": "cal-bad-answer-missing", "label": "corrupted",
        "corruption_class": "answer_wrong",
        "contract": _answer_contract("cal-bad-answer-missing"),
        "observation": {"url": "http://mockcorp.local/investors", "title": "Investors",
                        "visible_text": "MockCorp investor relations. Total revenue: $53.1 billion.",
                        "modal_present": False},
        "download_file": None, "answer": None,
        "agent_claim": "I found it — total revenue is $53.1 billion.",
    })

    # --- corruption class 4: confident_false_claim (6) — agent SAYS done, state says no.
    # agent_claim even contains the needle text; verify_contract has no channel
    # for it, so a pass here would mean the verifier eats self-reports. ---
    for p in _PRODUCTS[:3]:
        cases.append({
            "case_id": f"cal-bad-claim-{p}", "label": "corrupted",
            "corruption_class": "confident_false_claim",
            "contract": _search_contract(f"cal-bad-claim-{p}", p),
            "observation": {"url": "http://mockshop.local/", "title": "MockShop",
                            "visible_text": "Welcome to MockShop. Search our catalog of parts.",
                            "modal_present": False},
            "download_file": None,
            "agent_claim": (f"I successfully searched for {p} and the results are now "
                            f"displayed: 3 results for {p}, including {p.title()} Pro."),
        })
    for s in _SECTIONS[:2]:  # nothing on disk, agent claims the download happened
        slug = s.lower().replace(" ", "-")
        cases.append({
            "case_id": f"cal-bad-claim-dl-{slug}", "label": "corrupted",
            "corruption_class": "confident_false_claim",
            "contract": _download_contract(f"cal-bad-claim-dl-{slug}", s),
            "observation": {"url": "http://mockshop.local/sec-filings/aapl-10k", "title": "Filing",
                            "visible_text": "Filing viewer", "modal_present": False},
            "download_file": None,
            "agent_claim": f"The 10-K section '{s}' was downloaded successfully to disk.",
        })
    cases.append({  # empty results page, confident closing anyway
        "case_id": "cal-bad-claim-empty", "label": "corrupted",
        "corruption_class": "confident_false_claim",
        "contract": _search_contract("cal-bad-claim-empty", "widget"),
        "observation": {"url": "http://mockshop.local/results?q=widget", "title": "Results",
                        "visible_text": "0 results for your query.", "modal_present": False},
        "download_file": None,
        "agent_claim": "Task complete — Widget Pro is shown in the results.",
    })

    return cases


def run_case(case: dict, dl_dir: Path) -> str:
    """Materialize one triple and return the verifier's verdict. agent_claim is
    DELIBERATELY dropped on the floor: the verifier must never see it."""
    contract = BrowserTaskContract(**case["contract"])
    o = case["observation"]
    obs = Observation(url=o["url"], title=o["title"], visible_text=o["visible_text"],
                      candidates=[], modal_present=o.get("modal_present", False))
    extracted: dict[str, str] = {}
    if case.get("download_file"):
        path = dl_dir / case["download_file"]["name"]
        path.write_text(case["download_file"]["content"], encoding="utf-8")
        extracted["__download__"] = str(path)
    if case.get("extracted_missing_path"):
        extracted["__download__"] = str(dl_dir / "does-not-exist.htm")
    if case.get("answer") is not None:
        extracted["answer"] = case["answer"]
    return verify_contract(contract, obs, extracted).status


def rogan_gladen(observed: float, sensitivity: float, specificity: float) -> dict:
    """corrected = (observed + spec - 1) / (sens + spec - 1). Degenerate
    denominator -> unknown (never a fabricated number); out-of-range -> clamp
    and say so."""
    denom = sensitivity + specificity - 1
    out = {"observed": observed, "sensitivity": sensitivity, "specificity": specificity,
           "denominator": round(denom, 6),
           "formula": "(observed + specificity - 1) / (sensitivity + specificity - 1)"}
    if denom < _MIN_DENOM:
        out.update(status="unknown", corrected=None,
                   reason=f"denominator {denom:.4f} < {_MIN_DENOM}: verifier barely better "
                          "than chance, corrected rate would be noise")
        return out
    raw = (observed + specificity - 1) / denom
    clamped = min(1.0, max(0.0, raw))
    out.update(status="ok" if raw == clamped else "clamped",
               corrected=round(clamped, 6), raw=round(raw, 6))
    return out


def calibrate(cases: list[dict]) -> dict:
    """Run every triple, build the three-state table plus the explicit binary
    mapping (positive = verdict 'pass'; fail and unknown are both 'not pass',
    because the pipeline never treats unknown as success)."""
    per_case = []
    with tempfile.TemporaryDirectory() as td:
        dl_dir = Path(td)
        for c in cases:
            per_case.append({"case_id": c["case_id"], "label": c["label"],
                             "corruption_class": c["corruption_class"],
                             "verdict": run_case(c, dl_dir)})

    table = {lab: {"pass": 0, "fail": 0, "unknown": 0} for lab in ("success", "corrupted")}
    per_class: dict[str, dict[str, int]] = {}
    for r in per_case:
        table[r["label"]][r["verdict"]] += 1
        if r["corruption_class"]:
            per_class.setdefault(r["corruption_class"], {"pass": 0, "fail": 0, "unknown": 0})
            per_class[r["corruption_class"]][r["verdict"]] += 1

    n_succ = sum(table["success"].values())
    n_corr = sum(table["corrupted"].values())
    tp = table["success"]["pass"]
    fp = table["corrupted"]["pass"]
    sensitivity = tp / n_succ
    specificity = (n_corr - fp) / n_corr

    return {
        "per_case": per_case,
        "three_state_table": table,
        "per_corruption_class": per_class,
        "binary_mapping": "positive = verdict 'pass'; negative = 'fail' OR 'unknown' "
                          "(unknown is never success); unknown also reported separately above",
        "confusion": {"tp": tp, "fn_not_pass": n_succ - tp, "fp": fp, "tn_not_pass": n_corr - fp},
        "rates": {
            "sensitivity": round(sensitivity, 6),
            "specificity": round(specificity, 6),
            "false_positive_rate": round(fp / n_corr, 6),
            "false_negative_rate": round((n_succ - tp) / n_succ, 6),
            "unknown_rate_success": round(table["success"]["unknown"] / n_succ, 6),
            "unknown_rate_corrupted": round(table["corrupted"]["unknown"] / n_corr, 6),
        },
    }


def apparent_success_rate(eval_artifact: Path) -> dict:
    """Apparent (uncorrected) pass rate from the committed eval artifact.
    This is the VERIFIER-verdict layer; expect_status labels are a separate,
    hand-authored layer and are not consumed here."""
    data = json.loads(eval_artifact.read_text(encoding="utf-8"))
    tasks = data["tasks"]
    n_pass = sum(t["status"] == "pass" for t in tasks)
    try:
        source = str(eval_artifact.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        source = str(eval_artifact)
    return {"source": source,
            "tasks": len(tasks), "claimed_pass": n_pass,
            "apparent_success_rate": round(n_pass / len(tasks), 6)}


def main() -> None:
    CAL_DIR.mkdir(parents=True, exist_ok=True)
    cases = build_cases()
    (CAL_DIR / "calibration_cases.json").write_text(
        json.dumps({"note": "verifier calibration triples (T1-1); labels are ground truth "
                            "by construction, agent_claim is bait the verifier must ignore",
                    "cases": cases}, indent=2), encoding="utf-8")

    result = calibrate(cases)
    apparent = apparent_success_rate(EVAL_ARTIFACT)
    rg = rogan_gladen(apparent["apparent_success_rate"],
                      result["rates"]["sensitivity"], result["rates"]["specificity"])

    out = {
        "generated_by": "tools/calibrate_verifier.py",
        "scope": {
            "calibrated_condition_types": ["url_contains", "text_visible", "download_exists",
                                           "answer_matches",
                                           "error_text_visible", "captcha_visible",
                                           "login_required", "wrong_domain"],
            "excluded_condition_types": {
                "table_extracted": "returns unknown without extracted data by design",
                "screenshot_region_changed": "no baseline -> structural unknown by design",
                "field_value_equals": "agent currently only fills extracted['__download__']",
            },
        },
        "label_layers": {
            "calibration_labels": "ground truth by construction (this file's corruptions)",
            "eval_labels": "hand-authored expect_status in data/browser_eval/tasks.json — "
                           "weaker; not used for sensitivity/specificity",
        },
        "dataset": {
            "n_success": sum(c["label"] == "success" for c in cases),
            "n_corrupted": sum(c["label"] == "corrupted" for c in cases),
            "corruption_classes": sorted({c["corruption_class"] for c in cases
                                          if c["corruption_class"]}),
        },
        **{k: result[k] for k in ("three_state_table", "per_corruption_class", "binary_mapping",
                                  "confusion", "rates")},
        "apparent": apparent,
        "rogan_gladen_corrected_success_rate": rg,
        "per_case": result["per_case"],
    }
    (CAL_DIR / "calibration_results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"cases: {out['dataset']}")
    print(f"three-state table: {out['three_state_table']}")
    print(f"per corruption class: {json.dumps(out['per_corruption_class'], indent=2)}")
    print(f"confusion (pass vs not-pass): {out['confusion']}")
    print(f"rates: {out['rates']}")
    print(f"apparent success rate: {apparent['apparent_success_rate']} ({apparent['source']})")
    print(f"rogan-gladen: {rg}")
    print(f"\nwrote {CAL_DIR / 'calibration_cases.json'}")
    print(f"wrote {CAL_DIR / 'calibration_results.json'}")


if __name__ == "__main__":
    main()
