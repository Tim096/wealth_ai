"""Render apps/web/eval-dashboard/index.html from template.html + data.json.

Replaces the hand-pasted DATA snapshot: template.html carries a single
`const DATA = __DATA__;` placeholder and this script injects data.json into it.
Run tools/build_dashboard_data.py first, then this.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "apps" / "web" / "eval-dashboard"
PLACEHOLDER = "__DATA__"
_DATA_RE = re.compile(r"^const DATA = (.+);$", re.M)


def render(template: str, data: dict) -> str:
    if template.count(PLACEHOLDER) != 1:
        raise ValueError(f"template must contain exactly one {PLACEHOLDER} placeholder "
                         f"(found {template.count(PLACEHOLDER)})")
    # `</` escaped so the JSON blob can never close the surrounding <script> tag
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return template.replace(PLACEHOLDER, blob)


def extract_data(html: str) -> dict:
    m = _DATA_RE.search(html)
    if not m:
        raise ValueError("no embedded `const DATA = ...;` line found")
    return json.loads(m.group(1))  # \/ is a valid JSON escape for /


def main() -> None:
    template = (DASH / "template.html").read_text(encoding="utf-8")
    data = json.loads((DASH / "data.json").read_text(encoding="utf-8"))
    html = render(template, data)
    out = DASH / "index.html"
    out.write_text(html, encoding="utf-8")
    assert extract_data(html) == data  # round-trip guard
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
