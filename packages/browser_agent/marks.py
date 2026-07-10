"""Set-of-Marks (SoM): render the page to an image with a numbered box over
each interactive element, so a VISION model can pick the element to act on by
its number and we translate that number back to a real, observed coordinate.

This is the grounding bridge for the screen-level hands (MouseAction): the model
looks at the picture instead of guessing pixels, but the pixels it ultimately
uses are the live layout's — not hallucinated. The numbers are the SAME data-aid
the DOM path already stamps (see observer._ENUMERATE_JS), so the visual channel
and the text-candidate channel agree on element identity.

Adapted from the Set-of-Mark prompting idea (Yang et al., 2023); the numbering
reuses our existing data-aid stamps rather than a fresh detector.
"""

from __future__ import annotations

from typing import Any

# Draw one labelled box per [data-aid] element currently in the viewport, inside
# a single top-layer container so cleanup is one removal. Rects are viewport-
# relative (getBoundingClientRect), matching a default (viewport) screenshot.
_SOM_DRAW_JS = r"""
(max) => {
  const prev = document.getElementById('__som__'); if (prev) prev.remove();
  const box = document.createElement('div');
  box.id = '__som__';
  box.style.cssText = 'position:fixed;inset:0;z-index:2147483647;pointer-events:none';
  let n = 0;
  for (const el of document.querySelectorAll('[data-aid]')) {
    if (n >= max) break;
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) continue;
    if (r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) continue;
    const aid = el.getAttribute('data-aid');
    const b = document.createElement('div');
    b.style.cssText = `position:absolute;left:${r.left}px;top:${r.top}px;`
      + `width:${r.width}px;height:${r.height}px;box-sizing:border-box;`
      + `border:2px solid #e11;`;
    const lbl = document.createElement('div');
    lbl.textContent = aid;
    lbl.style.cssText = `position:absolute;left:${r.left}px;top:${Math.max(0, r.top - 14)}px;`
      + `background:#e11;color:#fff;font:11px/14px monospace;padding:0 3px`;
    box.appendChild(b); box.appendChild(lbl); n++;
  }
  document.body.appendChild(box);
  return n;
}
"""

_SOM_CLEAR_JS = "() => { const e = document.getElementById('__som__'); if (e) e.remove(); }"


def set_of_marks(page: Any, path: str, max_marks: int = 60) -> int:
    """Overlay numbered boxes on the elements the observer already stamped
    (call after observe()), screenshot the viewport to `path`, then remove the
    overlay. Returns the number of marks drawn. Best-effort: never raises into
    the agent loop — a failed screenshot just means no image this turn."""
    try:
        n = int(page.evaluate(_SOM_DRAW_JS, max_marks))
    except Exception:  # noqa: BLE001
        return 0
    try:
        page.screenshot(path=str(path))
    except Exception:  # noqa: BLE001
        n = 0
    finally:
        try:
            page.evaluate(_SOM_CLEAR_JS)
        except Exception:  # noqa: BLE001
            pass
    return n
