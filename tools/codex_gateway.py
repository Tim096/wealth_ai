"""Local OpenAI-compatible gateway -> Codex CLI (ChatGPT OAuth).

Bridges the browser agent (which speaks OpenAI /v1/chat/completions) to OpenAI
Codex authenticated via your ChatGPT subscription — no API key, no key handed
to this repo. You run `codex login` once (browser OAuth), then run this
gateway; the agent defaults to it.

  # one-time (in your shell, uses your ChatGPT account):
  npm i -g @openai/codex        # or: brew install codex
  codex login                   # opens browser OAuth

  # run the gateway:
  python tools/codex_gateway.py --port 8791 --model gpt-5.3-codex

  # then, in another shell, the agent already defaults here:
  python tools/browser_agent_live.py --task "..." --url "https://..." --success "text_visible:..."

Backends:
  --backend codex   (default) shell out to `codex exec` per request
  --backend mock    canned JSON action, for verifying the gateway with no codex
  --backend openai  forward to real OpenAI (needs OPENAI_API_KEY) — for A/B

Endpoints: GET /v1/models (preflight), POST /v1/chat/completions.

NOTE: the codex backend is built to OpenAI's documented `codex exec` interface
(developers.openai.com/codex/noninteractive). It shells out to the CLI on your
machine; verify once against your installed codex version. The HTTP + response
shaping layer is covered by tests/test_codex_gateway.py via the mock backend.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# JSON Schema for the single action we want back (mirrors planner._build_action)
ACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    # OpenAI strict structured-output requires every property in `required`
    "required": ["action", "aid", "value", "reason"],
    "properties": {
        "action": {"enum": ["fill", "click", "press", "goto", "extract_text", "download",
                            "done", "give_up"]},
        "aid": {"type": ["integer", "null"]},
        "value": {"type": "string"},
        "reason": {"type": "string"},
    },
}


def _extract_json_object(text: str) -> str:
    """Pull the first well-formed JSON object out of arbitrary CLI chatter."""
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                candidate = text[start:i + 1]
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    start = -1
    return text


class Backend:
    def complete(self, system: str, user: str) -> str:
        raise NotImplementedError


_CAND_LINE = re.compile(
    r'aid=(\d+)\s+<(\w+)(?:\s+role=(\w+))?>\s+type=(\S+)\s+id="([^"]*)"\s+label="([^"]*)"')


class MockBackend(Backend):
    """Deterministic but candidate-AWARE: parses the CANDIDATE ELEMENTS the
    planner sends and picks the search box then the submit control (avoiding
    decoys) — enough to drive the real agent loop to PASS with no codex/key,
    proving the whole gateway path end to end."""

    def __init__(self) -> None:
        self._n = 0

    @staticmethod
    def _query(user: str) -> str:
        m = re.search(r"for '([^']+)'|for \"([^\"]+)\"", user)
        return (m.group(1) or m.group(2)) if m else "widget"

    def complete(self, system: str, user: str) -> str:
        self._n += 1
        cands = [(int(a), tag, (role or ""), typ, cid.lower(), label.lower())
                 for a, tag, role, typ, cid, label in _CAND_LINE.findall(user)]

        def pick(tags, words, prefer_submit=False):
            scored = []
            for aid, tag, role, typ, cid, label in cands:
                if "decoy" in cid or "fake" in cid or "decoy" in label:
                    continue  # id reveals the decoy even when its text mimics the real control
                if tag in tags or role in tags:
                    s = 1 + (2 if prefer_submit and typ == "submit" else 0) \
                        + (1 if any(w in label for w in words) else 0)
                    scored.append((s, aid))
            scored.sort(reverse=True)
            return scored[0][1] if scored else None

        if self._n == 1:
            aid = pick({"input", "textarea", "searchbox", "textbox"}, {"search", "query", "find"})
            if aid is not None:
                return json.dumps({"action": "fill", "aid": aid, "value": self._query(user),
                                   "reason": "mock: fill search box"})
        if self._n == 2:
            aid = pick({"button"}, {"search", "submit", "go", "find"}, prefer_submit=True)
            if aid is not None:
                return json.dumps({"action": "click", "aid": aid, "reason": "mock: click submit"})
        return json.dumps({"action": "done", "reason": "mock: results should be visible"})


class CodexBackend(Backend):
    def __init__(self, model: str, extra_args: list[str], timeout_s: int = 180) -> None:
        self.model = model
        self.extra_args = extra_args
        self.timeout_s = timeout_s
        import shutil
        self.codex = shutil.which("codex") or "codex"

    def complete(self, system: str, user: str) -> str:
        # instruction goes as the prompt arg; page state is piped via stdin
        # (codex treats piped content as additional context) — this keeps the
        # large/quoted page text out of argv entirely.
        instruction = ("Choose the next browser action for the task using the page state on stdin. "
                       "Return ONLY a JSON object matching the output schema, no prose.")
        context = system + "\n\n" + user
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(ACTION_SCHEMA, f)
            schema_path = f.name
        args = [self.codex, "exec", "--sandbox", "read-only", "--skip-git-repo-check",
                "--output-schema", schema_path, *self.extra_args]
        # ChatGPT-account Codex rejects explicit --model for the codex-* names;
        # omit it to use the account default (e.g. gpt-5.5). Pass one only if
        # the operator set a concrete non-sentinel model.
        if self.model and self.model.lower() not in ("default", "auto", ""):
            args += ["--model", self.model]
        args.append(instruction)
        # on Windows, codex resolves to a .CMD which CreateProcess can't launch
        # directly — go through the command interpreter.
        if os.name == "nt" and self.codex.lower().endswith((".cmd", ".bat")):
            args = [os.environ.get("COMSPEC", "cmd.exe"), "/c", *args]
        try:
            proc = subprocess.run(args, input=context, capture_output=True, text=True,
                                  timeout=self.timeout_s, encoding="utf-8", errors="replace")
            out = proc.stdout or proc.stderr or ""
        except subprocess.TimeoutExpired:
            out = '{"action":"give_up","reason":"codex exec timed out"}'
        finally:
            try:
                os.unlink(schema_path)
            except OSError:
                pass
        return _extract_json_object(out)


class OpenAIBackend(Backend):
    def __init__(self, model: str) -> None:
        self.model = model

    def complete(self, system: str, user: str) -> str:
        import httpx
        key = os.environ.get("OPENAI_API_KEY", "")
        base = os.environ.get("OPENAI_UPSTREAM_URL", "https://api.openai.com/v1")
        r = httpx.post(f"{base}/chat/completions",
                       headers={"Authorization": f"Bearer {key}"},
                       json={"model": self.model, "response_format": {"type": "json_object"},
                             "messages": [{"role": "system", "content": system},
                                          {"role": "user", "content": user}], "temperature": 0},
                       timeout=60)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


def make_handler(backend: Backend, model: str):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, obj: dict) -> None:
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path.rstrip("/").endswith("/models"):
                self._send(200, {"object": "list", "data": [{"id": model, "object": "model"}]})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            if not self.path.rstrip("/").endswith("/chat/completions"):
                self._send(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(length) or b"{}")
            msgs = req.get("messages", [])
            system = "\n".join(m["content"] for m in msgs if m.get("role") == "system")
            user = "\n".join(m["content"] for m in msgs if m.get("role") == "user")
            try:
                content = backend.complete(system, user)
            except Exception as e:  # noqa: BLE001
                self._send(502, {"error": {"message": f"backend failed: {type(e).__name__}: {e}"}})
                return
            self._send(200, {
                "id": f"chatcmpl-{int(time.time())}", "object": "chat.completion",
                "model": req.get("model", model),
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": len(user) // 4, "completion_tokens": len(content) // 4,
                          "total_tokens": (len(user) + len(content)) // 4},
            })

        def log_message(self, *a):  # quiet
            pass

    return Handler


def build_backend(name: str, model: str) -> Backend:
    if name == "mock":
        return MockBackend()
    if name == "openai":
        return OpenAIBackend(model)
    return CodexBackend(model, [])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--model", default=os.environ.get("CODEX_MODEL", "default"),
                    help="'default' = account default (recommended for ChatGPT OAuth, which "
                         "rejects explicit codex-* model names); or e.g. gpt-5.3-codex on an API key")
    ap.add_argument("--backend", choices=["codex", "mock", "openai"], default="codex")
    args = ap.parse_args()
    backend = build_backend(args.backend, args.model)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(backend, args.model))
    print(f"[codex-gateway] backend={args.backend} model={args.model} "
          f"listening on http://127.0.0.1:{args.port}/v1")
    print("[codex-gateway] point the agent at it: set OPENAI_BASE_URL=http://127.0.0.1:"
          f"{args.port}/v1 (already the default)")
    server.serve_forever()


if __name__ == "__main__":
    main()
