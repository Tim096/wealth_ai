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
    target: ElementTarget


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
        SnapshotAction,
        BackAction,
    ],
    Field(discriminator="type"),
]
