"""Page observer (SPEC 6.6): after every step, capture URL, title, visible
text, and the candidate interactive elements with their accessibility
attributes — the raw material selector repair searches over.
"""

from __future__ import annotations

import hashlib
import re
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
  const interactive = Array.from(document.querySelectorAll(sel)).slice(0, 160);
  // Plain article text is also actionable for `extract_text`. Keep a bounded
  // set of semantic reading blocks after the interactive controls so an
  // answer in an infobox/table/paragraph can receive a grounded data-aid.
  const seen = new Set(interactive);
  const readable = [];
  // Selector-list querySelectorAll returns document order, so a long nav <li>
  // list can otherwise consume every slot before an early infobox <tr>.
  const readableGroups = [
    'main tr,article tr,[role=main] tr',
    'main dt,main dd,article dt,article dd,[role=main] dt,[role=main] dd',
    'main h1,main h2,main h3,main h4,article h1,article h2,article h3,article h4,'
      + '[role=main] h1,[role=main] h2,[role=main] h3',
    'main p,main li,main blockquote,main pre,article p,article li,'
      + '[role=main] p,[role=main] li'
  ];
  for (const group of readableGroups) {
    for (const el of document.querySelectorAll(group)) {
      if (!seen.has(el) && (el.innerText || '').trim()) {
        readable.push(el); seen.add(el);
      }
      if (readable.length >= 40) break;
    }
    if (readable.length >= 40) break;
  }
  const els = interactive.concat(readable);
  return els.map((el, i) => {
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
      text: (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 200),
      href: el.getAttribute('href') || '',
      // enclosing form (id, else its document.forms index) — repair's
      // form-context signal for disambiguating fields (FG-BROWSER-005)
      form: (function () { const f = el.closest('form');
        return f ? (f.id || 'form' + Array.prototype.indexOf.call(document.forms, f)) : ''; })(),
      // selection state for a choice control, so the planner knows which option
      // is ALREADY chosen and does not click it again (that would unselect it)
      checked: el.getAttribute('aria-checked') || (el.checked === true ? 'true' : ''),
      // P0-7 structural-identity raw material: class list + a short ancestor
      // tag chain, so the element can be hashed and re-found after drift
      classes: el.getAttribute('class') || '',
      parent_path: (function () { const p = []; let n = el.parentElement;
        for (let k = 0; k < 3 && n && n !== document.body; k++) {
          p.unshift(n.tagName.toLowerCase()); n = n.parentElement; }
        return p.join('>'); })(),
      visible: visible,
      x: Math.round(r.x), y: Math.round(r.y)
    };
  });
}
"""

# P0-7: extract ONE element's structural fields (same shape _ENUMERATE_JS
# emits) so a selector that just WORKED can be hashed into selector memory.
_ELEMENT_FIELDS_JS = r"""
(sel) => {
  let el = null;
  try { el = document.querySelector(sel); } catch (e) { return null; }
  if (!el) return null;
  const p = []; let n = el.parentElement;
  for (let k = 0; k < 3 && n && n !== document.body; k++) {
    p.unshift(n.tagName.toLowerCase()); n = n.parentElement; }
  return {
    tag: el.tagName.toLowerCase(), type: el.getAttribute('type') || '',
    id: el.id || '', name: el.getAttribute('name') || '',
    role: el.getAttribute('role') || '', aria_label: el.getAttribute('aria-label') || '',
    placeholder: el.getAttribute('placeholder') || '',
    text: (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 200),
    href: el.getAttribute('href') || '',
    classes: el.getAttribute('class') || '',
    parent_path: p.join('>')
  };
}
"""

# P0-7 (BU 5-level cascading locator / SK cleaned-JSON SHA256 rebind):
# transient CSS classes that churn between renders — state flags, CSS-in-JS /
# framework-generated names, hashy or numbered suffixes. Filtered out before
# hashing so a cosmetic re-render does not break the EXACT identity.
DYNAMIC_CLASS_PATTERNS = (
    re.compile(r"^(is-|has-)"),                              # state prefixes
    re.compile(r"^(active|hover|focus|focused|selected|open|opened|show|shown"
               r"|hidden|collapsed|expanded|disabled|checked|loading|animating"
               r"|animated|visible|current|highlight|highlighted)$", re.I),
    re.compile(r"^(css|jss|jsx|sc|svelte|ng|emotion|chakra|mui)-", re.I),
    re.compile(r"\d{3,}"),                                   # ember123, uid-45821
    re.compile(r"[0-9a-f]{6,}", re.I),                       # content-hash suffixes
)

# field sets for the two identity levels; position is in NEITHER (layout drift
# must not change identity) and neither is `checked` (selection is transient)
_EXACT_FIELDS = ("tag", "type", "id", "name", "role", "aria_label",
                 "placeholder", "text", "href", "parent_path")
_STABLE_FIELDS = ("tag", "type", "name", "role", "aria_label",
                  "placeholder", "parent_path")


def _clean_classes(raw: str) -> str:
    kept = [c for c in (raw or "").split()
            if not any(p.search(c) for p in DYNAMIC_CLASS_PATTERNS)]
    return " ".join(sorted(kept))


def structural_hashes(el: Any) -> tuple[str, str]:
    """P0-7 per-element cleaned structural hash, two levels of the rebind
    cascade. EXACT covers every structural field plus the cleaned class list;
    STABLE keeps only the drift-tolerant subset (no id / text / href /
    classes), so it survives an id rename or a copy change. Accepts an
    ElementCandidate or the raw field dict the JS emits."""
    if isinstance(el, dict):
        get = lambda k: str(el.get(k, "") or "")            # noqa: E731
    else:
        get = lambda k: str(getattr(el, k, "") or "")       # noqa: E731
    exact = "|".join(get(f) for f in _EXACT_FIELDS) + "|" + _clean_classes(get("classes"))
    stable = "|".join(get(f) for f in _STABLE_FIELDS)
    def h(s: str) -> str:
        return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]
    return h(exact), h(stable)


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
    classes: str = ""       # P0-7: raw class list (cleaned before hashing)
    parent_path: str = ""   # P0-7: up-to-3-ancestor tag chain, e.g. "form>div"

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
            body_text = self.page.inner_text("body")[:12_000]
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
