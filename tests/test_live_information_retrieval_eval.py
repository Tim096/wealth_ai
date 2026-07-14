import json

import pytest

from tools import live_information_retrieval_eval as live_eval


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload

    def raise_for_status(self):
        return None


def test_runner_waits_for_terminal_state_before_submitting_next(monkeypatch, tmp_path):
    tasks = tmp_path / "tasks.json"
    tasks.write_text(json.dumps({
        "suite": "test",
        "protocol": "single launch",
        "tasks": [
            {"id": "a", "domain": "a.test", "task": "a", "url": "https://a.test",
             "success": ["answer_matches:.+"], "expected_answer_regex": "alpha",
             "max_steps": 2},
            {"id": "b", "domain": "b.test", "task": "b", "url": "https://b.test",
             "success": ["answer_matches:.+"], "expected_answer_regex": "beta",
             "max_steps": 2},
        ],
    }), encoding="utf-8")

    class _Client:
        submitted = []
        polls = {"t-a": 0, "t-b": 0}

        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, path, json):
            if self.submitted == ["t-a"]:
                assert self.polls["t-a"] >= 3
            task_id = "t-a" if not self.submitted else "t-b"
            self.submitted.append(task_id)
            return _Response({"task_id": task_id})

        def get(self, path):
            if path == "/api/health":
                return _Response({"ok": True})
            task_id = path.rsplit("/", 1)[-1]
            self.polls[task_id] += 1
            if self.polls[task_id] < 3:
                return _Response({"status": "running"})
            answer = "alpha" if task_id == "t-a" else "beta"
            return _Response({
                "status": "pass", "answer": answer, "verifier": "pass",
                "trace": {"repetition": {"n_steps": 1}, "total_latency_ms": 10},
            })

    monkeypatch.setattr(live_eval.httpx, "Client", _Client)
    monkeypatch.setattr(live_eval.time, "sleep", lambda _: None)
    output = tmp_path / "results.json"
    result = live_eval.run("https://agent.test", tasks, output, slow_threshold_s=60)

    assert result["summary"]["passed"] == 2
    assert result["summary"]["total"] == 2
    assert result["summary"]["pass_rate"] == 1.0
    assert result["summary"]["llm_calls_total"] == 0
    assert all(row["gold_pass"] for row in result["results"])
    assert json.loads(output.read_text(encoding="utf-8"))["taskset_sha256"]


def test_runner_can_score_verifier_contract_without_hidden_gold(monkeypatch, tmp_path):
    tasks = tmp_path / "tasks.json"
    tasks.write_text(json.dumps({
        "suite": "mixed",
        "protocol": "single launch",
        "tasks": [{
            "id": "click", "domain": "example.test", "task_type": "click",
            "task": "click", "url": "https://example.test",
            "success": ["text_visible:done"], "max_steps": 2,
        }],
    }), encoding="utf-8")

    class _Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, path):
            if path == "/api/health":
                return _Response({"ok": True})
            return _Response({
                "status": "pass", "answer": "", "verifier": "pass",
                "llm_calls": 1, "llm_tokens": 10, "llm_cost_usd": 0.001,
                "trace": {"repetition": {"n_steps": 1}, "total_latency_ms": 10},
            })

        def post(self, path, json):
            return _Response({"task_id": "t-click"})

    monkeypatch.setattr(live_eval.httpx, "Client", _Client)
    result = live_eval.run(
        "https://agent.test", tasks, tmp_path / "results.json", slow_threshold_s=60
    )

    assert result["summary"]["passed"] == 1
    assert result["summary"]["task_types"] == ["click"]
    assert result["results"][0]["scored_pass"] is True
    assert result["results"][0]["gold_match"] is None


def test_runner_refuses_unattested_deployment(monkeypatch, tmp_path):
    tasks = tmp_path / "tasks.json"
    tasks.write_text(json.dumps({"suite": "attest", "protocol": "single launch",
                                 "tasks": []}), encoding="utf-8")

    class _Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, path):
            return _Response({"ok": True, "build_sha": "wrong"})

    monkeypatch.setattr(live_eval.httpx, "Client", _Client)
    monkeypatch.setattr(live_eval, "_head", lambda: "expected")
    with pytest.raises(RuntimeError, match="does not match"):
        live_eval.run(
            "https://agent.test", tasks, tmp_path / "results.json",
            slow_threshold_s=60, require_build_sha=True,
        )
