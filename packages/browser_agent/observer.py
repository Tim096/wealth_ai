"""Page observer (SPEC 6.6): after every step, capture URL, title, visible
text, and the candidate interactive elements with their accessibility
attributes — the raw material selector repair searches over.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# JS that enumerates interactive elements with the attributes repair needs.
_ENUMERATE_JS = r"""
() => {
  const sel = 'input,button,a,select,textarea,[role=button],[role=link],[role=searchbox],[role=textbox]';
  const els = Array.from(document.querySelectorAll(sel));
  return els.slice(0, 200).map((el, i) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    const visible = r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none';
    return {
      index: i,
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute('type') || '',
      id: el.id || '',
      name: el.getAttribute('name') || '',
      role: el.getAttribute('role') || '',
      aria_label: el.getAttribute('aria-label') || '',
      placeholder: el.getAttribute('placeholder') || '',
      text: (el.textContent || '').trim().slice(0, 80),
      href: el.getAttribute('href') || '',
      visible: visible,
      x: Math.round(r.x), y: Math.round(r.y)
    };
  });
}
"""


@dataclass
class ElementCandidate:
    index: int
    tag: str
    type: str
    id: str
    name: str
    role: str
    aria_label: str
    placeholder: str
    text: str
    href: str
    visible: bool
    x: int
    y: int

    def css(self) -> str:
        """A best-effort stable selector for this element, for memory storage."""
        if self.id:
            return f"#{self.id}"
        if self.name:
            return f"{self.tag}[name={self.name}]"
        if self.aria_label:
            return f'{self.tag}[aria-label="{self.aria_label}"]'
        if self.placeholder:
            return f'{self.tag}[placeholder="{self.placeholder}"]'
        return self.tag


@dataclass
class Observation:
    url: str
    title: str
    visible_text: str
    candidates: list[ElementCandidate] = field(default_factory=list)
    modal_present: bool = False


class PageObserver:
    def __init__(self, page: Any) -> None:
        self.page = page

    def observe(self) -> Observation:
        raw = self.page.evaluate(_ENUMERATE_JS)
        candidates = [ElementCandidate(**c) for c in raw]
        modal = self.page.evaluate(
            "() => !!document.querySelector('.cookie-modal,[role=dialog],.modal,#cookie')"
        )
        try:
            body_text = self.page.inner_text("body")[:5000]
        except Exception:
            body_text = ""
        return Observation(
            url=self.page.url,
            title=self.page.title(),
            visible_text=body_text,
            candidates=candidates,
            modal_present=bool(modal),
        )
