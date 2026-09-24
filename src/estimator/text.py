"""Small text helpers shared by the proposal and the price sheet."""
from __future__ import annotations

import re

_SPACE = re.compile(r"\s+")
# What Word draws in front of a list item, once pasted into Excel as plain text.
_LIST_MARKER = re.compile(r"^(?:\d{1,3}\.|o|⮚|➢|·|•|▪|◦)\s+")


def squash(text: str) -> str:
    """Collapse every run of whitespace, non-breaking spaces included, to one space."""
    return _SPACE.sub(" ", text.replace("\xa0", " ")).strip()


def strip_list_marker(text: str) -> str:
    """Remove one leading list number or bullet, as found in a pasted price sheet."""
    return _LIST_MARKER.sub("", squash(text), count=1)
