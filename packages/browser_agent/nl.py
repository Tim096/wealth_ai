"""Natural-language helpers shared by the agent front-ends (chat window,
CLI, web test center): derive a verifier success condition from a task
description when the operator didn't supply one explicitly."""

from __future__ import annotations

import re

_STOP = {"the", "a", "an", "for", "to", "and", "of", "in", "on", "open", "search",
         "find", "go", "click", "read", "article", "page", "play", "this", "that",
         "with", "並", "然後", "打開", "搜尋", "按", "撥放", "播放", "到", "幫我", "請"}


def _target_phrase(task: str) -> str:
    """A distinctive phrase the destination/document should contain: a quoted
    string, else a Title-Case phrase (e.g. 'Risk Factors'), else the longest
    Latin token. '' when nothing confident can be picked from Chinese prose."""
    quoted = re.findall(r"['\"“」『]([^'\"”」』]{2,60})['\"”」』]", task)
    if quoted:
        return quoted[0]
    titles = [t for t in re.findall(r"\b(?:[A-Z][a-z]+)(?:\s+[A-Z][a-z]+){0,3}\b", task)
              if t.lower() not in _STOP]
    if titles:
        titles.sort(key=len, reverse=True)
        return titles[0]
    latin = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9\-\.]{2,}", task)
             if w.lower() not in _STOP]
    if latin:
        latin.sort(key=len, reverse=True)
        return latin[0]
    return ""


def derive_success(task: str) -> list[str]:
    """Derive a verifier condition ONLY when it can be done confidently:
    download intent, a quoted phrase, or a distinctive Latin token (brand /
    proper noun). Unsegmented Chinese prose has no word boundaries — the whole
    sentence regex-matches as one 'word' — so rather than produce a garbage
    condition (e.g. text_visible:<half the task sentence>), return [] and let
    the caller ask the operator for an explicit condition. Honest > guessy."""
    # A token INSIDE a URL (e.g. a Google-Form id FAIpQLSe…) is never page-visible
    # text — mining it as a text_visible needle guarantees a false FAIL even when
    # the task succeeded. Strip URLs before picking a phrase.
    clean = re.sub(r"https?://\S+", " ", task)
    # Strip leading/trailing punctuation so a mined token like 'sirloin.' (the
    # latin regex keeps a trailing '.') becomes the clean needle 'sirloin' — the
    # exact trailing-period artifact that made a substantively-done task FAIL
    # (BUCKET 2). Internal punctuation (hyphens, dots in tickers) is preserved.
    phrase = _target_phrase(clean).strip(" \t\r\n.,;:!?\"'`()[]{}")
    if re.search(r"download|下載|下载|存檔|save file", task, re.I):
        # A download task that also names a section ("…and find Risk Factors")
        # must VERIFY the saved file contains it — a bare download_exists would
        # rubber-stamp any file, which is exactly the false pass we were told
        # about. Carry the phrase so the verifier reads the bytes.
        return [f"download_exists:{phrase}"] if phrase else ["download_exists:"]
    # Form fill/submit: completion is the POST-SUBMIT landing page, not a phrase
    # from the prompt. Google Forms navigates to …/formResponse on submit, which
    # is true only when actually done — the correct, non-garbage condition.
    if re.search(r"填寫|填答|填表|送出|提交|submit|fill (in|out)|complete the form", task, re.I):
        if re.search(r"docs\.google\.com/forms|/forms/", task):
            return ["url_contains:formResponse"]
        return [f"text_visible:{phrase}"] if phrase else []
    if phrase:
        return [f"text_visible:{phrase}"]
    return []
