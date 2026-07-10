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


def test_action_schema_matches_planner_actions():
    assert set(gw.ACTION_SCHEMA["properties"]["action"]["enum"]) == {
        "fill", "click", "press", "goto", "extract_text", "download",
        "mouse", "keyboard", "done", "give_up"}
    # the screen-level fields must be declared (and required, for strict output)
    for k in ("x", "y", "keys"):
        assert k in gw.ACTION_SCHEMA["properties"] and k in gw.ACTION_SCHEMA["required"]
