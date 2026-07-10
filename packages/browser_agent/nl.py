"""Natural-language helpers shared by the agent front-ends (chat window,
CLI, web test center): derive a verifier success condition from a task
description when the operator didn't supply one explicitly."""

from __future__ import annotations

import re

_STOP = {"the", "a", "an", "for", "to", "and", "of", "in", "on", "open", "search",
         "find", "go", "click", "read", "article", "page", "play", "this", "that",
         "with", "並", "然後", "打開", "搜尋", "按", "撥放", "播放", "到", "幫我", "請"}


def derive_success(task: str) -> list[str]:
    """Derive a verifier condition ONLY when it can be done confidently:
    download intent, a quoted phrase, or a distinctive Latin token (brand /
    proper noun). Unsegmented Chinese prose has no word boundaries — the whole
    sentence regex-matches as one 'word' — so rather than produce a garbage
    condition (e.g. text_visible:<half the task sentence>), return [] and let
    the caller ask the operator for an explicit condition. Honest > guessy."""
    if re.search(r"download|下載|下载|存檔|save file", task, re.I):
        return ["download_exists:"]
    quoted = re.findall(r"['\"“」『]([^'\"”」』]{2,60})['\"”」』]", task)
    if quoted:
        return [f"text_visible:{quoted[0]}"]
    latin = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9\-\.]{2,}", task)
             if w.lower() not in _STOP]
    if latin:
        latin.sort(key=len, reverse=True)
        return [f"text_visible:{latin[0]}"]
    return []
