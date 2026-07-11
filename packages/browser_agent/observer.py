"""Page observer (SPEC 6.6): after every step, capture URL, title, visible
text, and the candidate interactive elements with their accessibility
attributes — the raw material selector repair searches over.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# JS that enumerates interactive elements with the attributes repair needs.
# We stamp a stable data-aid on each element at observe time so a repaired
# target can be addressed by [data-aid=N] — an exact, unambiguous handle on the
# element we actually saw, instead of reconstructing a possibly-non-unique CSS
# selector from its attributes. (Technique adapted from EmergenceAI/Agent-E's
# `mmid` DOM-distillation idea — MIT-licensed; see docs/ATTRIBUTION.md.)
_ENUMERATE_JS = r"""
() => {
  // Native controls PLUS ARIA choice controls: radio/checkbox/option/switch/tab
  // are how custom widgets (e.g. a Google Form's single/multiple-choice answers,
  // rendered as <div role=radio>) expose their clickable options. Without these
  // the planner literally cannot see — or click — a choice question and loops.
  const sel = 'input,button,a,select,textarea,'
    + '[role=button],[role=link],[role=searchbox],[role=textbox],'
    + '[role=radio],[role=checkbox],[role=switch],[role=option],'
    + '[role=menuitemradio],[role=menuitemcheckbox],[role=tab]';
  const els = Array.from(document.querySelectorAll(sel));
  return els.slice(0, 200).map((el, i) => {
    el.setAttribute('data-aid', String(i));
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
      // enclosing form (id, else its document.forms index) — repair's
      // form-context signal for disambiguating fields (FG-BROWSER-005)
      form: (function () { const f = el.closest('form');
        return f ? (f.id || 'form' + Array.prototype.indexOf.call(document.forms, f)) : ''; })(),
      // selection state for a choice control, so the planner knows which option
      // is ALREADY chosen and does not click it again (that would unselect it)
      checked: el.getAttribute('aria-checked') || (el.checked === true ? 'true' : ''),
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
    checked: str = ""       # aria-checked / .checked for radio/checkbox options
    form: str = ""          # enclosing form id / index ('' = outside any form)
    is_new: bool = False    # P0-4: not present in the PREVIOUS observation

    def css(self) -> str:
        """A durable selector to REMEMBER this element across runs — prefers a
        semantic attribute (id/name/aria) that survives a page reload. Used for
        selector memory, so it must not depend on the volatile data-aid."""
        if self.id:
            return f"#{self.id}"
        if self.name:
            return f"{self.tag}[name={self.name}]"
        if self.aria_label:
            return f'{self.tag}[aria-label="{self.aria_label}"]'
        if self.placeholder:
            return f'{self.tag}[placeholder="{self.placeholder}"]'
        return self.tag

    def aid_selector(self) -> str:
        """An exact, unambiguous handle on THIS observed element for the
        immediate action (data-aid is stamped fresh each observe())."""
        return f'[data-aid="{self.index}"]'


@dataclass
class Observation:
    url: str
    title: str
    visible_text: str
    candidates: list[ElementCandidate] = field(default_factory=list)
    modal_present: bool = False


def _identity_key(c: ElementCandidate) -> tuple:
    return (c.tag, c.id, c.name, c.text, c.x, c.y)


def diff_observations(prev: Observation | None, cur: Observation) -> str:
    """P0-4 env-change evidence. Mechanism precedent: Agent-E's
    dom_mutation_observer (MutationObserver + a 100ms post-action sleep), which
    is blind to attribute/style changes and races slow async updates. Diffing
    two CONSECUTIVE OBSERVATIONS by an element identity key instead needs no
    timing window and also sees disappearances. Side effect: candidates of
    `cur` absent from `prev` get is_new=True ('*' in the planner's candidate
    list). Returns a one-sentence summary of what the last action changed —
    URL change / elements appeared or gone / first changed visible-text line —
    or the literal "page unchanged" (the silent-failure signal after a click).
    '' on the first observation (nothing to diff against)."""
    if prev is None:
        return ""
    if cur.url != prev.url:
        # a navigation replaces everything; '*' on every element would be noise
        return f"URL -> {cur.url[:120]}"
    prev_keys = {_identity_key(c) for c in prev.candidates}
    cur_keys = set()
    new = 0
    for c in cur.candidates:
        k = _identity_key(c)
        cur_keys.add(k)
        if k not in prev_keys:
            c.is_new = True
            new += 1
    gone = len(prev_keys - cur_keys)
    parts = []
    if new:
        parts.append(f"{new} new element(s) appeared (marked * in the candidate list)")
    if gone:
        parts.append(f"{gone} element(s) gone")
    prev_lines = prev.visible_text.splitlines()
    cur_lines = cur.visible_text.splitlines()
    for a, b in zip(prev_lines, cur_lines):
        if a != b:
            parts.append(f'text changed: "{b.strip()[:60]}"')
            break
    else:
        if len(cur_lines) > len(prev_lines):
            parts.append(f'text added: "{cur_lines[len(prev_lines)].strip()[:60]}"')
        elif len(cur_lines) < len(prev_lines):
            parts.append("text removed")
    return "; ".join(parts) if parts else "page unchanged"


class PageObserver:
    def __init__(self, page: Any) -> None:
        self.page = page

    def observe(self) -> Observation:
        raw = self.page.evaluate(_ENUMERATE_JS)
        candidates = [ElementCandidate(**c) for c in raw]
        modal = self.page.evaluate(
            "() => !!document.querySelector('.cookie-modal,[role=dialog],[aria-modal=\"true\"],"
            ".modal,#cookie,.popup,.overlay,.interstitial')"
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

    def snapshot_state(self):
        """Capture persistent/residual page state (localStorage / sessionStorage /
        cookies / leftover form input) for a before/after side-effect diff (T1-4).
        Separate from observe(): it captures durable state, not page content."""
        from browser_agent.trajectory import StateSnapshot
        return StateSnapshot.capture(self.page)
