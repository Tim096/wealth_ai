"""WebJudge advisory scorer for Online-Mind2Web trajectory runs.

Official-protocol reimplementation (ADAPTED) of WebJudge from:
  Online-Mind2Web, OSU-NLP-Group — src/methods/webjudge_online_mind2web.py
  (MIT License, Copyright (c) 2025 OSU Natural Language Processing)
  https://github.com/OSU-NLP-Group/Online-Mind2Web  (arXiv:2504.01382)
Prompt text is reused/adapted under MIT; see docs/ATTRIBUTION.md.

Protocol (same three stages as the official implementation):
  1. key-point identification from the task description;
  2. per-screenshot judging (1-5 relevance score, threshold gates which
     screenshots count as key evidence);
  3. final trajectory judgment from task + key points + action history +
     key-screenshot reasoning (+ screenshot image evidence).

DEVIATIONS from the official implementation (an honest, non-comparable list —
numbers produced here must NOT be compared 1:1 against paper/leaderboard
numbers):
  * judge model: the local codex gateway's ChatGPT-account default
    (gpt-5.5-class), NOT the paper's o4-mini / WebJudge-7B;
  * the gateway attaches at most ONE image per request (codex exec -i), so the
    final judgment carries the single highest-scored key screenshot as image
    evidence plus the textual reasoning for ALL key screenshots (official
    attaches up to 50 images);
  * responses ride through the gateway's action-schema coercion, so every
    stage asks for a JSON object and unwraps the gateway's
    {"action": "done", "value": "<json>"} envelope (same pattern as
    browser_agent.second_judge._unwrap_gateway_action);
  * an explicit ABSTAIN verdict exists: malformed/failed LLM output after a
    retry, or a trajectory with no screenshots AND no actions, abstains
    instead of guessing (the official protocol forces binary success/failure).
    Abstains stay in the denominator of the reported success rate and are
    never counted as success;
  * action history is reconstructed from the harness step log
    (evidence/agent-live-<id>.jsonl: tool + planner reason per step), not from
    agent-native action strings.

ADVISORY ONLY: output never changes the runtime verifier's verdict; it is a
separate scoring axis written under <run>/webjudge/.

Usage:
  .venv/Scripts/python tools/webjudge.py \
      --run runs/browser_eval/m2w_full300_20260711 \
      --tasks data/browser_eval/external/m2w_full300_20260711.json
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "packages"))

from llm_core.openai_client import OpenAIClient  # noqa: E402

GATEWAY_URL = "http://127.0.0.1:8791/v1"
GATEWAY_KEY = "codex-oauth-gateway"
JUDGE_MODEL_LABEL = ("codex-gateway/default (ChatGPT-account Codex default, "
                     "gpt-5.5-class) — NOT the official o4-mini/WebJudge-7B")
MAX_IMAGE_THOUGHTS = 50   # official MAX_IMAGE cap on key-screenshot evidence
RETRIES = 1               # one retry per LLM stage before abstaining

# ---------------------------------------------------------------------------
# Prompts. System prompts below are adapted from the official WebJudge
# implementation (MIT); the semantic content (instructions, scoring scale,
# evaluation criteria 1-7) is kept verbatim, only the response-format section
# is changed from free text to a JSON object (gateway constraint).
# ---------------------------------------------------------------------------

KEYPOINT_SYSTEM = """You are an expert tasked with analyzing a given task to identify the key points explicitly stated in the task description.

**Objective**: Carefully analyze the task description and extract the critical elements explicitly mentioned in the task for achieving its goal.

**Instructions**:
1. Read the task description carefully.
2. Identify and extract **key points** directly stated in the task description.
   - A **key point** is a critical element, condition, or step explicitly mentioned in the task description.
   - Do not infer or add any unstated elements.
   - Words such as "best," "highest," "cheapest," "latest," "most recent," "lowest," "closest," "highest-rated," "largest," and "newest" must go through the sort function(e.g., the key point should be "Filter by highest").

**Respond with a JSON object only**:
{"key_points": ["<key point 1>", "<key point 2>", ...]}"""

IMAGE_JUDGE_SYSTEM = """You are an expert evaluator tasked with determining whether an image contains information about the necessary steps to complete a task.

**Objective**: Analyze the provided image and decide if it shows essential steps or evidence required for completing the task. Use your reasoning to explain your decision before assigning a score.

**Instructions**:
1. Provide a detailed description of the image, including its contents, visible elements, text (if any), and any notable features.

2. Carefully examine the image and evaluate whether it contains necessary steps or evidence crucial to task completion:
- Identify key points that could be relevant to task completion, such as actions, progress indicators, tool usage, applied filters, or step-by-step instructions.
- Does the image show actions, progress indicators, or critical information directly related to completing the task?
- Is this information indispensable for understanding or ensuring task success?
- If the image contains partial but relevant information, consider its usefulness rather than dismissing it outright.

3. Score scale:
    - 1: The image does not contain any necessary steps or relevant information.
    - 2: The image contains minimal or ambiguous information, unlikely to be essential.
    - 3: The image includes some relevant steps or hints but lacks clarity or completeness.
    - 4: The image contains important steps or evidence that are highly relevant but not fully comprehensive.
    - 5: The image clearly displays necessary steps or evidence crucial for completing the task.

**Respond with a JSON object only**:
{"reasoning": "<your explanation>", "score": <integer 1-5>}"""

FINAL_JUDGE_SYSTEM = """You are an expert in evaluating the performance of a web navigation agent. The agent is designed to help a human user navigate a website to complete a task. Given the user's task, the agent's action history, key points for task completion, some potentially important web pages in the agent's trajectory and their reasons, your goal is to determine whether the agent has completed the task and achieved all requirements.

Your response must strictly follow the following evaluation criteria!
*Important Evaluation Criteria*:
1: The filtered results must be displayed correctly. If filters were not properly applied (i.e., missing selection, missing confirmation, or no visible effect in results), the task is not considered successful.
2: You must carefully check whether these snapshots and action history meet these key points. Ensure that specific filter conditions, such as "best," "highest," "cheapest," "latest," "most recent," "lowest," "closest," "highest-rated," "largest," and "newest" are correctly applied using the filter function(e.g., sort function).
3: Certain key points or requirements should be applied by the filter. Otherwise, a search with all requirements as input will be deemed a failure since it cannot guarantee that all results meet the requirements!
4: If the task requires filtering by a specific range of money, years, or the number of beds and bathrooms, the applied filter must exactly match the given requirement. Any deviation results in failure. To ensure the task is successful, the applied filter must precisely match the specified range without being too broad or too narrow.
Examples of Failure Cases:
- If the requirement is less than $50, but the applied filter is less than $25, it is a failure.
- If the requirement is $1500-$2500, but the applied filter is $2000-$2500, it is a failure.
- If the requirement is $25-$200, but the applied filter is $0-$200, it is a failure.
- If the required years are 2004-2012, but the filter applied is 2001-2012, it is a failure.
- If the required years are before 2015, but the applied filter is 2000-2014, it is a failure.
- If the task requires exactly 2 beds, but the filter applied is 2+ beds, it is a failure.
5: Some tasks require a submission action or a display of results to be considered successful.
6: If the retrieved information is invalid or empty(e.g., No match was found), but the agent has correctly performed the required action, it should still be considered successful.
7: If the current page already displays all available items, then applying a filter is not necessary. As long as the agent selects items that meet the requirements (e.g., the cheapest or lowest price), the task is still considered successful.

**Respond with a JSON object only**:
{"thoughts": "<your reasoning based on double-checking each key point and the evaluation criteria>", "status": "success" or "failure"}"""


# ---------------------------------------------------------------------------
# Gateway plumbing
# ---------------------------------------------------------------------------

def _unwrap_gateway_action(parsed: dict, want_keys: set[str]) -> dict:
    """The codex gateway force-fits every completion into the planner's action
    schema; the judge payload comes back as {"action": "done", "value": "<the
    actual JSON as a string>", ...}. Unwrap that shape; pass anything already
    carrying the wanted keys through unchanged."""
    if isinstance(parsed, dict) and "action" in parsed and not (want_keys & parsed.keys()):
        for field in ("value", "reason"):
            raw = parsed.get(field) or ""
            try:
                inner = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if isinstance(inner, dict) and (want_keys & inner.keys()):
                return inner
    return parsed


def _envelope_note(example: str) -> str:
    """The gateway's codex backend bakes in a 'choose the next browser action'
    instruction and an action output schema; without an explicit counter-brief
    the model answers as a planner (observed live: it returned a 'press ENTER'
    action to a judge prompt). Tell it to ride the schema instead."""
    return ("\n\nIMPORTANT: You are an EVALUATOR reviewing a finished trajectory, "
            "not a browser-driving agent. Do NOT choose a next browser action. "
            "If your output must fit an action schema, use action \"done\" and put "
            "your ENTIRE response as a JSON string in the \"value\" field, e.g. "
            '{"action":"done","value":"' + example + '"}')


def _call_json(client: OpenAIClient, system: str, user: str, want_keys: set[str],
               image_path: str | None = None) -> tuple[dict | None, float]:
    """One judged LLM call with a retry; returns (payload|None, cost). None
    means both attempts failed/malformed — the caller abstains."""
    cost = 0.0
    for _ in range(1 + RETRIES):
        try:
            parsed, resp = client.complete_json(system, user, image_path=image_path)
            cost += resp.cost_usd
        except Exception:  # noqa: BLE001 — network/backend failure -> retry then abstain
            continue
        parsed = _unwrap_gateway_action(parsed, want_keys)
        if isinstance(parsed, dict) and not parsed.get("_parse_error") \
                and (want_keys & parsed.keys()):
            return parsed, cost
    return None, cost


# ---------------------------------------------------------------------------
# Trajectory loading
# ---------------------------------------------------------------------------

def load_actions(run_dir: Path, task_id: str) -> list[str]:
    """Reconstruct the action history from the harness step log: one line per
    planner step, 'tool: reason'. Missing/corrupt lines are skipped."""
    p = run_dir / "evidence" / f"agent-live-{task_id}.jsonl"
    if not p.exists():
        return []
    actions: list[str] = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        step_id = rec.get("step_id", "")
        if "-step" not in step_id or "planner" not in step_id:
            continue
        tool = (rec.get("tool_used") or "").rsplit(".", 1)[-1]
        reason = ((rec.get("verifier_result") or {}).get("reason") or "").strip()
        actions.append(f"{tool}: {reason}" if reason else tool)
    return actions


def load_screenshots(task_dir: Path) -> list[Path]:
    def order(p: Path) -> int:
        m = re.search(r"agent-(\d+)\.png$", p.name)
        return int(m.group(1)) if m else 10**9
    return sorted(task_dir.glob("agent-*.png"), key=order)


# ---------------------------------------------------------------------------
# WebJudge stages
# ---------------------------------------------------------------------------

def identify_key_points(client: OpenAIClient, task: str) -> tuple[list[str], float]:
    user = f"Task: {task}" + _envelope_note(
        '{\\"key_points\\": [\\"...\\", \\"...\\"]}')
    parsed, cost = _call_json(client, KEYPOINT_SYSTEM, user, {"key_points"})
    if parsed is None or not isinstance(parsed.get("key_points"), list):
        return [], cost
    return [str(k).strip() for k in parsed["key_points"] if str(k).strip()], cost


def judge_image(client: OpenAIClient, task: str, key_points: list[str],
                image: Path) -> tuple[dict, float]:
    user = ("**Task**: {t}\n\n**Key Points for Task Completion**: {k}\n\n"
            "The snapshot of the web page is shown in the image.").format(
        t=task, k="\n".join(f"{i+1}. {p}" for i, p in enumerate(key_points)))
    user += _envelope_note('{\\"reasoning\\": \\"...\\", \\"score\\": 3}')
    parsed, cost = _call_json(client, IMAGE_JUDGE_SYSTEM, user,
                              {"score", "reasoning"}, image_path=str(image))
    if parsed is None:
        return {"image": image.name, "score": 0, "reasoning": "",
                "error": "malformed/failed judge output"}, cost
    try:
        score = max(0, min(5, int(parsed.get("score", 0))))
    except (TypeError, ValueError):
        score = 0
    return {"image": image.name, "score": score,
            "reasoning": str(parsed.get("reasoning", "")).strip()}, cost


def final_judgment(client: OpenAIClient, task: str, key_points: list[str],
                   actions: list[str], answer: str, image_records: list[dict],
                   task_dir: Path, threshold: int) -> tuple[dict, float]:
    key_shots = [r for r in image_records
                 if r["score"] >= threshold and r.get("reasoning")][:MAX_IMAGE_THOUGHTS]
    thoughts = "\n".join(f"{i+1}. [{r['image']}] {r['reasoning']}"
                         for i, r in enumerate(key_shots))
    history = "\n".join(f"{i+1}. {a}" for i, a in enumerate(actions))
    if answer:
        history += f"\n{len(actions)+1}. final answer reported by the agent: {answer!r}"
    user = f"User Task: {task}\n\nKey Points: " \
           + "\n".join(f"{i+1}. {p}" for i, p in enumerate(key_points)) \
           + f"\n\nAction History:\n{history}"
    best_image: str | None = None
    if key_shots:
        user += ("\n\nThe potentially important snapshots of the webpage in the "
                 f"agent's trajectory and their reasons:\n{thoughts}")
        top = max(key_shots, key=lambda r: r["score"])
        best_image = str(task_dir / top["image"])
        user += (f"\n\nThe single highest-scored snapshot ({top['image']}) is "
                 "attached as the image.")
    user += _envelope_note('{\\"thoughts\\": \\"...\\", \\"status\\": \\"success|failure\\"}')
    parsed, cost = _call_json(client, FINAL_JUDGE_SYSTEM, user,
                              {"status", "thoughts"}, image_path=best_image)
    if parsed is None:
        return {"verdict": "abstain",
                "reason": "final judgment output malformed/failed after retry",
                "thoughts": "", "key_screenshots": [r["image"] for r in key_shots]}, cost
    status = str(parsed.get("status", "")).strip().lower()
    if status not in ("success", "failure"):
        return {"verdict": "abstain",
                "reason": f"final judgment status not binary: {status!r}",
                "thoughts": str(parsed.get("thoughts", "")),
                "key_screenshots": [r["image"] for r in key_shots]}, cost
    return {"verdict": status, "reason": "",
            "thoughts": str(parsed.get("thoughts", "")),
            "key_screenshots": [r["image"] for r in key_shots]}, cost


def judge_task(client: OpenAIClient, run_dir: Path, task_dir: Path,
               task_text: str, summary: dict, threshold: int,
               image_workers: int) -> dict:
    task_id = summary["task_id"]
    t0 = time.perf_counter()
    actions = load_actions(run_dir, task_id)
    answer = str((summary.get("row") or {}).get("answer") or "")
    shots = load_screenshots(task_dir)
    total_cost = 0.0

    if not shots and not actions:
        return {"task_id": task_id, "verdict": "abstain",
                "reason": "no screenshots and no action log — insufficient evidence",
                "key_points": [], "image_scores": [], "thoughts": "",
                "cost_usd": 0.0, "wall_s": round(time.perf_counter() - t0, 1)}

    key_points, cost = identify_key_points(client, task_text)
    total_cost += cost
    if not key_points:
        return {"task_id": task_id, "verdict": "abstain",
                "reason": "key-point identification failed/malformed after retry",
                "key_points": [], "image_scores": [], "thoughts": "",
                "cost_usd": round(total_cost, 6),
                "wall_s": round(time.perf_counter() - t0, 1)}

    image_records: list[dict] = []
    if shots:
        with cf.ThreadPoolExecutor(max_workers=image_workers) as pool:
            futs = {pool.submit(judge_image, client, task_text, key_points, s): s
                    for s in shots}
            done_map = {}
            for f in cf.as_completed(futs):
                rec, c = f.result()
                total_cost += c
                done_map[futs[f].name] = rec
        image_records = [done_map[s.name] for s in shots]

    final, cost = final_judgment(client, task_text, key_points, actions, answer,
                                 image_records, task_dir, threshold)
    total_cost += cost
    return {"task_id": task_id, "verdict": final["verdict"],
            "reason": final["reason"], "key_points": key_points,
            "image_scores": image_records, "thoughts": final["thoughts"],
            "key_screenshots": final.get("key_screenshots", []),
            "cost_usd": round(total_cost, 6),
            "wall_s": round(time.perf_counter() - t0, 1)}


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

VERIFIER_AXES = ("pass", "fail", "unknown", "env_blocked")
WEBJUDGE_AXES = ("success", "failure", "abstain")


def aggregate(run_dir: Path, per_task: dict[str, dict], summaries: dict[str, dict],
              n_total_tasks: int, threshold: int) -> dict:
    done = {tid: s for tid, s in summaries.items()
            if s.get("harness_status") == "done"}
    judged = {tid: per_task[tid] for tid in done if tid in per_task}

    # confusion matrix: verifier status x webjudge verdict (done tasks only)
    matrix = {v: {w: 0 for w in WEBJUDGE_AXES} for v in VERIFIER_AXES}
    pairs = []
    for tid, s in done.items():
        v = ((s.get("row") or {}).get("status") or "unknown")
        if v not in VERIFIER_AXES:
            v = "unknown"
        w = judged.get(tid, {}).get("verdict")
        if w in WEBJUDGE_AXES:
            matrix[v][w] += 1
            pairs.append((v, w))

    n_done = len(done)
    n_judged = len(judged)
    n_success = sum(1 for r in judged.values() if r["verdict"] == "success")
    n_failure = sum(1 for r in judged.values() if r["verdict"] == "failure")
    n_abstain = sum(1 for r in judged.values() if r["verdict"] == "abstain")

    decided = [(v, w) for v, w in pairs if v in ("pass", "fail") and w in ("success", "failure")]
    agree = sum(1 for v, w in decided
                if (v == "pass") == (w == "success"))

    verifier_counts = {a: 0 for a in VERIFIER_AXES}
    for s in done.values():
        v = ((s.get("row") or {}).get("status") or "unknown")
        verifier_counts[v if v in VERIFIER_AXES else "unknown"] += 1
    n_error = sum(1 for s in summaries.values() if s.get("harness_status") != "done")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_dir": str(run_dir).replace("\\", "/"),
        "protocol": "WebJudge (Online-Mind2Web official auto-eval), adapted — see deviations",
        "judge_model": JUDGE_MODEL_LABEL,
        "score_threshold": threshold,
        "advisory_only": True,
        "comparability_warning": (
            "NOT directly comparable to the official leaderboard (e.g. Browser Use "
            "~97% was judged with the official WebJudge + o4-mini on their own "
            "trajectories): different judge model (gpt-5.5-class codex default), "
            "single-image evidence limit, JSON-coerced responses, explicit abstain "
            "verdict, and this run snapshot covers only the tasks attempted so far."),
        "deviations_from_official": [
            "judge model is the codex gateway ChatGPT-account default (gpt-5.5-class), not o4-mini/WebJudge-7B",
            "final judgment attaches only the single highest-scored key screenshot (gateway 1-image limit); other key screenshots contribute reasoning text only",
            "all stages request JSON objects and unwrap the gateway action-schema envelope",
            "explicit abstain verdict on malformed/failed judge output or evidence-free trajectories (official forces binary); abstains stay in the denominator",
            "action history reconstructed from the harness step log, not agent-native action strings",
        ],
        "run_snapshot": {
            "n_total_tasks": n_total_tasks,
            "n_attempted": len(summaries),
            "n_done": n_done,
            "n_harness_error": n_error,
            "n_not_run": n_total_tasks - len(summaries),
        },
        "verifier_axis": {
            **verifier_counts,
            "success_rate_done": round(verifier_counts["pass"] / n_done, 4) if n_done else None,
        },
        "webjudge_axis": {
            "judged": n_judged,
            "success": n_success,
            "failure": n_failure,
            "abstain": n_abstain,
            "abstain_rate": round(n_abstain / n_judged, 4) if n_judged else None,
            "success_rate_official_denominator": (
                round(n_success / n_judged, 4) if n_judged else None),
            "note": "success_rate = WebJudge success / total done-and-judged; abstain counts in the denominator, never as success",
        },
        "confusion_matrix_verifier_x_webjudge": matrix,
        "agreement_on_decided": {
            "n_decided_pairs": len(decided),
            "n_agree": agree,
            "rate": round(agree / len(decided), 4) if decided else None,
            "note": "verifier pass/fail vs WebJudge success/failure only; verifier unknown and WebJudge abstain excluded",
        },
        "total_judge_cost_usd": round(sum(r.get("cost_usd", 0.0) for r in judged.values()), 6),
        "per_task": {tid: judged[tid] for tid in sorted(judged)},
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", default="runs/browser_eval/m2w_full300_20260711")
    ap.add_argument("--tasks", default="data/browser_eval/external/m2w_full300_20260711.json")
    ap.add_argument("--score-threshold", type=int, default=3,
                    help="min per-image score for a screenshot to count as key evidence")
    ap.add_argument("--task-workers", type=int, default=2)
    ap.add_argument("--image-workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0, help="judge at most N tasks (0 = all)")
    ap.add_argument("--no-resume", action="store_true",
                    help="re-judge even when a per-task result already exists")
    args = ap.parse_args()

    run_dir = (_REPO / args.run).resolve() if not Path(args.run).is_absolute() else Path(args.run)
    out_dir = run_dir / "webjudge"
    per_task_dir = out_dir / "per_task"
    per_task_dir.mkdir(parents=True, exist_ok=True)

    tasks_file = (_REPO / args.tasks) if not Path(args.tasks).is_absolute() else Path(args.tasks)
    task_text = {t["task_id"]: t["natural_language_task"]
                 for t in json.loads(tasks_file.read_text(encoding="utf-8"))["tasks"]}
    n_total = len(task_text)

    summaries: dict[str, dict] = {}
    for d in sorted(run_dir.glob("m2w-*")):
        sp = d / "summary.json"
        if sp.exists():
            s = json.loads(sp.read_text(encoding="utf-8"))
            summaries[s["task_id"]] = s

    client = OpenAIClient(api_key=os.environ.get("OPENAI_API_KEY", GATEWAY_KEY),
                          base_url=os.environ.get("OPENAI_BASE_URL", GATEWAY_URL),
                          model=os.environ.get("OPENAI_MODEL", "default"),
                          timeout_s=240.0)

    todo = []
    per_task: dict[str, dict] = {}
    for tid, s in sorted(summaries.items()):
        if s.get("harness_status") != "done":
            continue
        cached = per_task_dir / f"{tid}.json"
        if cached.exists() and not args.no_resume:
            rec = json.loads(cached.read_text(encoding="utf-8"))
            if rec.get("verdict") in WEBJUDGE_AXES:
                per_task[tid] = rec
                continue
        todo.append((tid, s))
    if args.limit:
        todo = todo[:args.limit]

    print(f"[webjudge] run={run_dir.name} done_tasks={sum(1 for s in summaries.values() if s.get('harness_status')=='done')} "
          f"cached={len(per_task)} to_judge={len(todo)} model={JUDGE_MODEL_LABEL}")

    def run_one(item):
        tid, s = item
        if tid not in task_text:
            return tid, {"task_id": tid, "verdict": "abstain",
                         "reason": "task text not found in task file",
                         "key_points": [], "image_scores": [], "thoughts": "",
                         "cost_usd": 0.0, "wall_s": 0.0}
        return tid, judge_task(client, run_dir, run_dir / tid, task_text[tid],
                               s, args.score_threshold, args.image_workers)

    with cf.ThreadPoolExecutor(max_workers=args.task_workers) as pool:
        for tid, rec in pool.map(run_one, todo):
            per_task[tid] = rec
            (per_task_dir / f"{tid}.json").write_text(
                json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"[webjudge] {tid}: {rec['verdict']} "
                  f"(cost=${rec['cost_usd']:.4f}, {rec['wall_s']}s)")

    report = aggregate(run_dir, per_task, summaries, n_total, args.score_threshold)
    out = out_dir / "webjudge_results.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    wj = report["webjudge_axis"]
    vx = report["verifier_axis"]
    print(f"\n[webjudge] wrote {out}")
    print(f"  verifier axis (done={report['run_snapshot']['n_done']}): "
          f"pass={vx['pass']} fail={vx['fail']} unknown={vx['unknown']} "
          f"env_blocked={vx['env_blocked']} SR={vx['success_rate_done']}")
    print(f"  webjudge axis: success={wj['success']} failure={wj['failure']} "
          f"abstain={wj['abstain']} SR={wj['success_rate_official_denominator']} "
          f"abstain_rate={wj['abstain_rate']}")
    print(f"  agreement on decided pairs: {report['agreement_on_decided']['rate']} "
          f"({report['agreement_on_decided']['n_agree']}/{report['agreement_on_decided']['n_decided_pairs']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
