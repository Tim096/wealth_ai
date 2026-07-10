"""OpenAI / Codex-compatible chat client (dependency-light, via httpx).

Used by the browser agent's Agent Mode. Configured entirely from the
environment so the operator supplies their own credentials — this codebase
never stores or asks for a key (SPEC: asking for a key is disqualifying):

  OPENAI_API_KEY   required for a live call (an OpenAI key, or a token your
                   gateway accepts as a Bearer credential)
  OPENAI_BASE_URL  default https://api.openai.com/v1 — point this at an
                   OpenClaw / proxy gateway if you drive Codex via OAuth
                   (a ChatGPT OAuth token cannot hit api.openai.com directly)
  OPENAI_MODEL     default gpt-5-codex-mini

Every call is accounted as an LLMCallRecord (cost/latency/schema-valid) so the
Agent-Mode escalation has measured economics, not estimates.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

from observability_core import sha256_text

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-5-codex-mini"

# rough public $/1M tokens for cost accounting; override via OPENAI_PRICE_IN/OUT
_DEFAULT_PRICE_IN = 0.25
_DEFAULT_PRICE_OUT = 2.0


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    model: str
    prompt_sha256: str


class LLMConfigError(RuntimeError):
    pass


class OpenAIClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 model: str | None = None, timeout_s: float = 60.0) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.model = model or os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
        self.timeout_s = timeout_s
        self.price_in = float(os.environ.get("OPENAI_PRICE_IN", _DEFAULT_PRICE_IN))
        self.price_out = float(os.environ.get("OPENAI_PRICE_OUT", _DEFAULT_PRICE_OUT))

    def available(self) -> bool:
        return bool(self.api_key.strip())

    def complete_json(self, system: str, user: str,
                      image_path: str | None = None) -> tuple[dict, LLMResponse]:
        """Ask the model for a single JSON object. Raises LLMConfigError if no
        key is configured (callers should fall back to a deterministic path).

        If `image_path` is given, the user turn is sent as multimodal content
        (text + the image as a data: URI) so a vision-capable model — e.g. the
        gpt-5.5 default behind the Codex gateway, which accepts `codex exec -i` —
        can look at a Set-of-Marks screenshot and pick an element by its number."""
        if not self.available():
            raise LLMConfigError(
                "no OPENAI_API_KEY configured; set it (and OPENAI_BASE_URL for a gateway) to use Agent Mode")
        import httpx  # local import keeps llm_core import-light

        prompt = system + "\n\n" + user
        user_content: object = user
        if image_path:
            import base64
            with open(image_path, "rb") as fh:
                b64 = base64.b64encode(fh.read()).decode("ascii")
            user_content = [
                {"type": "text", "text": user},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ]
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user_content}],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        t0 = time.perf_counter()
        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=body, timeout=self.timeout_s,
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        in_tok = int(usage.get("prompt_tokens", 0))
        out_tok = int(usage.get("completion_tokens", 0))
        cost = in_tok / 1e6 * self.price_in + out_tok / 1e6 * self.price_out
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = {"_raw": text, "_parse_error": True}
        return parsed, LLMResponse(
            text=text, input_tokens=in_tok, output_tokens=out_tok, cost_usd=cost,
            latency_ms=latency_ms, model=self.model, prompt_sha256=sha256_text(prompt),
        )
