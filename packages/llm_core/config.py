"""LLM config loader for the browser agent's Agent Mode.

Default is Codex via the local gateway (config/agent.toml). Environment
variables always win, so an operator can override without editing files.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

_CONFIG = Path(__file__).resolve().parents[2] / "config" / "agent.toml"


@dataclass
class LLMConfig:
    mode: str          # gateway | direct | mock
    base_url: str
    model: str
    api_key: str       # for gateway mode this is a placeholder (gateway does auth)


def load_llm_config() -> LLMConfig:
    data = {}
    if _CONFIG.exists():
        data = tomllib.loads(_CONFIG.read_text(encoding="utf-8")).get("llm", {})
    mode = os.environ.get("AGENT_LLM_MODE", data.get("mode", "gateway"))
    base_url = os.environ.get("OPENAI_BASE_URL", data.get("base_url", "http://127.0.0.1:8791/v1"))
    model = os.environ.get("OPENAI_MODEL", data.get("model", "gpt-5.3-codex"))
    # gateway mode: the gateway authenticates via OAuth, so a placeholder key
    # satisfies the OpenAI-compatible client; direct mode requires a real key.
    if mode == "gateway":
        api_key = os.environ.get("OPENAI_API_KEY", data.get("api_key_placeholder", "codex-oauth-gateway"))
    else:
        api_key = os.environ.get("OPENAI_API_KEY", "")
    return LLMConfig(mode=mode, base_url=base_url, model=model, api_key=api_key)
