"""SEC EDGAR fetcher (SPEC 7.5): declared user-agent, rate limiting, raw
cache with hashes, append-only fetch log, deterministic re-runs.

The user-agent is never fabricated: it must be supplied explicitly or via
SEC_EDGAR_USER_AGENT. SEC's fair-access policy requires a real contact.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from observability_core import sha256_bytes

DEFAULT_MIN_INTERVAL_S = 0.5  # ≤2 req/s, well under SEC's 10 req/s ceiling


@dataclass
class FetchResult:
    url: str
    content: bytes
    sha256: str
    from_cache: bool
    status_code: int
    latency_ms: float


class EdgarFetcher:
    def __init__(
        self,
        cache_dir: Path | str,
        user_agent: str | None = None,
        min_interval_s: float = DEFAULT_MIN_INTERVAL_S,
        timeout_s: float = 30.0,
    ) -> None:
        self.user_agent = user_agent or os.environ.get("SEC_EDGAR_USER_AGENT", "")
        if not self.user_agent.strip():
            raise ValueError(
                "SEC EDGAR requires a declared user-agent with contact info; "
                "pass user_agent= or set SEC_EDGAR_USER_AGENT"
            )
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval_s = min_interval_s
        self.timeout_s = timeout_s
        self._last_request_at = 0.0
        self._log_path = self.cache_dir / "fetch_log.jsonl"

    # -- cache ----------------------------------------------------------------
    def _cache_paths(self, url: str) -> tuple[Path, Path]:
        key = sha256_bytes(url.encode("utf-8"))[:32]
        return self.cache_dir / f"{key}.bin", self.cache_dir / f"{key}.meta.json"

    def _log(self, entry: dict) -> None:
        with self._log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    # -- fetch ----------------------------------------------------------------
    def get(self, url: str, force: bool = False) -> FetchResult:
        blob_path, meta_path = self._cache_paths(url)
        if not force and blob_path.exists() and meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            content = blob_path.read_bytes()
            digest = sha256_bytes(content)
            if digest != meta.get("sha256"):
                raise ValueError(f"cache corruption for {url}: hash mismatch")
            self._log({"url": url, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "from_cache": True, "sha256": digest})
            return FetchResult(url=url, content=content, sha256=digest,
                               from_cache=True, status_code=meta.get("status_code", 200),
                               latency_ms=0.0)

        wait = self.min_interval_s - (time.monotonic() - self._last_request_at)
        if wait > 0:
            time.sleep(wait)

        t0 = time.perf_counter()
        resp = httpx.get(
            url,
            headers={"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=self.timeout_s,
            follow_redirects=True,
        )
        self._last_request_at = time.monotonic()
        latency_ms = (time.perf_counter() - t0) * 1000
        resp.raise_for_status()

        content = resp.content
        digest = sha256_bytes(content)
        blob_path.write_bytes(content)
        meta_path.write_text(json.dumps({
            "url": url,
            "sha256": digest,
            "status_code": resp.status_code,
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "content_length": len(content),
        }, indent=2), encoding="utf-8")
        self._log({"url": url, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "from_cache": False, "sha256": digest,
                   "status_code": resp.status_code, "latency_ms": round(latency_ms, 1)})
        return FetchResult(url=url, content=content, sha256=digest,
                           from_cache=False, status_code=resp.status_code,
                           latency_ms=latency_ms)
