"""Controlled browser action space (SPEC 6.5).

The LLM never emits Playwright code — only these validated action objects.
This keeps every step safe, verifiable, replayable, evaluable, repairable.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field


class ElementTarget(BaseModel):
    """How an action addresses an element. Exactly the info selector repair needs."""

    selector: str
    selector_type: Literal["css", "xpath", "role", "text", "semantic"] = "css"
    description: str = ""  # element purpose in plain language, e.g. 'main search box'


class WaitCondition(BaseModel):
    kind: Literal["url_contains", "text_visible", "selector_visible", "network_idle"]
    value: str = ""
    timeout_ms: int = 10_000


class GotoAction(BaseModel):
    type: Literal["goto"] = "goto"
    url: str


class ClickAction(BaseModel):
    type: Literal["click"] = "click"
    target: ElementTarget


class FillAction(BaseModel):
    type: Literal["fill"] = "fill"
    target: ElementTarget
    value: str


class PressAction(BaseModel):
    type: Literal["press"] = "press"
    target: ElementTarget
    key: str


class SelectAction(BaseModel):
    type: Literal["select"] = "select"
    target: ElementTarget
    value: str


class ScrollAction(BaseModel):
    type: Literal["scroll"] = "scroll"
    direction: Literal["up", "down"]
    amount: int


class WaitForAction(BaseModel):
    type: Literal["wait_for"] = "wait_for"
    condition: WaitCondition


class ExtractTextAction(BaseModel):
    type: Literal["extract_text"] = "extract_text"
    target: ElementTarget


class DownloadAction(BaseModel):
    type: Literal["download"] = "download"
    # Download works three ways, in priority order: an explicit `url` (save
    # that file directly — best for an inline-rendered document like an SEC
    # .htm), else a clickable `target` element, else the CURRENT page. A
    # document that renders inline has no download control, so element-only
    # downloading would dead-end.
    target: Optional[ElementTarget] = None
    url: str = ""


class MouseAction(BaseModel):
    """Screen-level click by viewport coordinate — no selector. The hybrid
    fallback for anything the DOM enumeration can't address (a canvas hit-area,
    an image-map, a custom widget, an option only known by its pixel box). The
    verifier still judges the outcome, so a mis-aimed click cannot fake success."""

    type: Literal["mouse"] = "mouse"
    x: int
    y: int
    button: Literal["left", "right"] = "left"
    clicks: int = 1  # 2 => double-click


class KeyboardAction(BaseModel):
    """Screen-level keyboard, not scoped to an element: type text at the current
    focus, or press a key/chord ("Enter", "Tab", "Escape", "Control+A"). Lets the
    agent drive a widget that took focus by click but exposes no fillable target."""

    type: Literal["keyboard"] = "keyboard"
    text: str = ""  # literal text to type at the current focus
    keys: str = ""  # a key or chord to press instead, e.g. "Enter" / "Control+A"


class SnapshotAction(BaseModel):
    type: Literal["snapshot"] = "snapshot"


class BackAction(BaseModel):
    type: Literal["back"] = "back"


BrowserAction = Annotated[
    Union[
        GotoAction,
        ClickAction,
        FillAction,
        PressAction,
        SelectAction,
        ScrollAction,
        WaitForAction,
        ExtractTextAction,
        DownloadAction,
        MouseAction,
        KeyboardAction,
        SnapshotAction,
        BackAction,
    ],
    Field(discriminator="type"),
]
