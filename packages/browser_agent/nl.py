"""Natural-language helpers shared by the agent front-ends (chat window,
CLI, web test center): derive a verifier success condition from a task
description when the operator didn't supply one explicitly."""

from __future__ import annotations

import re

_STOP = {"the", "a", "an", "for", "to", "and", "of", "in", "on", "open", "search",
         "find", "go", "click", "read", "article", "page", "play", "this", "that",
         "with", "並", "然後", "打開", "搜尋", "按", "撥放", "播放", "到", "幫我", "請"}


def derive_success(task: str) -> list[str]:
    """Prefer an explicit download intent, then a quoted phrase, then the most
    salient long word (works for Chinese and English tasks)."""
    if re.search(r"download|下載|下载|存檔|save file", task, re.I):
        return ["download_exists:"]
    quoted = re.findall(r"['\"“」『]([^'\"”」』]{2,60})['\"”」』]", task)
    if quoted:
        return [f"text_visible:{quoted[0]}"]
    words = [w for w in re.findall(r"[A-Za-z0-9一-鿿]{2,}", task) if w not in _STOP]
    words.sort(key=len, reverse=True)
    return [f"text_visible:{words[0]}"] if words else ["url_contains:."]
