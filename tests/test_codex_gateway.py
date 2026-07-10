"""Codex gateway HTTP + response-shaping tests (mock backend, no codex/key).
The codex subprocess backend is exercised manually with `codex login`; this
locks in the OpenAI-compatible surface the agent depends on."""

import json
import threading
from http.server import ThreadingHTTPServer

import pytest

import tools.codex_gateway as gw
from llm_core.openai_client import OpenAIClient


@pytest.fixture()
def mock_gateway():
    server = ThreadingHTTPServer(("127.0.0.1", 0), gw.make_handler(gw.MockBackend(), "mock-model"))
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}/v1"
    server.shutdown()


def test_models_endpoint_for_preflight(mock_gateway):
    import httpx
    r = httpx.get(f"{mock_gateway}/models", timeout=5)
    assert r.status_code == 200
    assert r.json()["data"][0]["id"] == "mock-model"


def test_chat_completions_returns_openai_shape(mock_gateway):
    client = OpenAIClient(api_key="placeholder", base_url=mock_gateway, model="mock-model")
    user = ("TASK: Search for 'widget'\nCANDIDATE ELEMENTS:\n"
            'aid=0 <input> type=text id="q" label="Search products"\n'
            'aid=1 <button> type=submit id="go" label="Search"')
    parsed, rec = client.complete_json("system rules", user)
    assert parsed["action"] == "fill" and parsed["aid"] == 0
    assert rec.model == "mock-model"


def test_extract_json_object_from_chatter():
    text = "Thinking...\nHere is the result:\n{\"action\": \"done\", \"reason\": \"ok\"}\nBye."
    obj = json.loads(gw._extract_json_object(text))
    assert obj["action"] == "done"


def test_split_messages_extracts_text_and_image():
    msgs = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": [
            {"type": "text", "text": "look here"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAB"}},
        ]},
    ]
    system, user, image = gw.split_messages(msgs)
    assert system == "SYS" and user == "look here"
    assert image == "data:image/png;base64,AAAB"
    # plain string content still works
    s2, u2, i2 = gw.split_messages([{"role": "user", "content": "hi"}])
    assert u2 == "hi" and i2 == ""


def test_data_uri_to_temp_roundtrips(tmp_path):
    import base64
    import os
    raw = b"\x89PNG\r\n\x1a\nfake"
    uri = "data:image/png;base64," + base64.b64encode(raw).decode()
    path = gw.data_uri_to_temp(uri)
    try:
        assert path and path.endswith(".png")
        with open(path, "rb") as fh:
            assert fh.read() == raw
    finally:
        if path:
            os.unlink(path)
    assert gw.data_uri_to_temp("not a data uri") is None


def test_codex_backend_attaches_image(tmp_path, monkeypatch):
    # the codex backend must pass a Set-of-Marks image via `codex exec --image`
    img = tmp_path / "som.png"
    img.write_bytes(b"x")
    captured = {}

    class _Proc:
        stdout = '{"action":"done","aid":null,"value":"","x":null,"y":null,"keys":"","reason":"ok"}'
        stderr = ""

    def _fake_run(args, **kw):
        captured["args"] = args
        return _Proc()

    monkeypatch.setattr(gw.subprocess, "run", _fake_run)
    be = gw.CodexBackend("default", [])
    be.codex = "codex"  # avoid the .cmd COMSPEC wrapping in the assertion
    out = be.complete("sys", "user", image_path=str(img))
    assert json.loads(out)["action"] == "done"
    assert "--image" in captured["args"]
    assert str(img) in captured["args"]


def test_action_schema_matches_planner_actions():
    assert set(gw.ACTION_SCHEMA["properties"]["action"]["enum"]) == {
        "fill", "click", "press", "goto", "extract_text", "download",
        "mouse", "keyboard", "done", "give_up"}
    # the screen-level fields must be declared (and required, for strict output)
    for k in ("x", "y", "keys"):
        assert k in gw.ACTION_SCHEMA["properties"] and k in gw.ACTION_SCHEMA["required"]
