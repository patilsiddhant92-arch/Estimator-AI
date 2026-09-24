"""The scope of one job — everything the proposal says and the price sheet prices.

A Job is the single list both documents are produced from (the one-list,
two-documents guarantee). Nothing reaches the client document unless it is a
field here.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Run(_Model):
    """A stretch of text with one emphasis — "(Rack Mounted)" in bold, say."""

    text: str
    bold: bool = False


class Item(_Model):
    """One line under a block header or under the front end.

    A "line" has a bullet. Depth 1 sits directly under the header, depth 2 under
    a line, and so on down to 5. A "note" has no bullet — a remark such as
    "*ENCLOSURE BY OTHERS" — and always has depth 1.

    quantity is what the price sheet puts in its Quantities column. A line with
    a quantity is a priced line.
    """

    kind: Literal["line", "note"]
    depth: int = Field(default=1, ge=1, le=5)
    runs: tuple[Run, ...] = Field(min_length=1)
    quantity: int | None = Field(default=None, ge=0)
    tech_hours: float | None = Field(default=None, ge=0)

    @property
    def text(self) -> str:
        return "".join(run.text for run in self.runs)

    @model_validator(mode="after")
    def _check(self) -> "Item":
        if not self.text.strip():
            raise ValueError("an item needs some text")
        if self.kind == "note" and self.depth != 1:
            raise ValueError("a note always has depth 1")
        if self.kind == "note" and self.quantity is not None:
            raise ValueError("a note has no quantity")
        return self


class Block(_Model):
    """An equipment block: a numbered "Qty (N) ..." header and what sits under it."""

    header: str = Field(min_length=1)
    items: tuple[Item, ...] = ()
    tech_hours: float | None = Field(default=None, ge=0)


class FrontEnd(_Model):
    """The front-end block. `mode` picks which of the template's two openings is used."""

    mode: Literal["new-system", "extend-existing"]
    existing_system_name: str | None = None
    items: tuple[Item, ...] = ()
    tech_hours: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _check(self) -> "FrontEnd":
        if self.mode == "extend-existing" and not (self.existing_system_name or "").strip():
            raise ValueError("extending an existing BMS needs the existing system's name")
        if self.mode == "new-system" and self.existing_system_name is not None:
            raise ValueError("a new system has no existing system name")
        if any(item.depth > 2 for item in self.items):
            raise ValueError("a front-end line can be at most two levels deep — the template's front-end lists have two")
        return self


class Alternate(_Model):
    label: str = "ALT #:"
    blocks: tuple[Block, ...] = ()


class Header(_Model):
    """The table on the cover page."""

    to: str = "All Bidders"
    date: dt.date
    quote_number: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    mep_engineer: str = Field(min_length=1)
    based_on: tuple[str, ...] = Field(min_length=1)


class Job(_Model):
    header: Header
    scope_heading_suffix: str = ""
    front_end: FrontEnd
    blocks: tuple[Block, ...] = ()
    add_alternates: tuple[Alternate, ...] = ()
    deduct_alternates: tuple[Alternate, ...] = ()
    named_exceptions: tuple[str, ...] = ()
