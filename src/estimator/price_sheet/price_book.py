"""The AME price book: what each device costs, and which device is the standard pick.

Lookup is deliberately strict. A scope line is priced only when its name — with
the list marker, the leading verb and any "(Qty. N Total)" taken off — is the
same as a price book item's name, or when an estimator has confirmed the match
in the alias file. Anything else is PRICE PENDING: guessing a price is the same
failure as guessing a quantity.
"""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import openpyxl

from estimator.text import squash, strip_list_marker

SHEETS = ("Parts Pricing", "BMS-DDC-Panels")
_QUANTITY = re.compile(r"\s*[–-]\s*\(qty\.?\s*\d+\s*total\).*$", re.IGNORECASE)
_VERB = re.compile(r"^(?:furnish and install|furnish and wire|install and wire|furnish|install|provide)\s+", re.IGNORECASE)


def price_key(text: str) -> str:
    """The part of a scope line that names the device, in lower case."""
    text = strip_list_marker(text)
    text = _QUANTITY.sub("", text)
    text = _VERB.sub("", text)
    return squash(text).casefold()


@dataclass(frozen=True)
class BookItem:
    name: str             # as the price book writes it
    price: float          # the Estimation Price column
    sheet: str
    row: int
    needs_review: bool    # the price book's own note says this price needs checking


class PriceBook:
    def __init__(self, items: list[BookItem], aliases: dict[str, str]) -> None:
        self.items = list(items)
        self._by_key: dict[str, BookItem] = {}
        for item in self.items:
            key = price_key(item.name)
            if key in self._by_key:
                raise ValueError(f"two price book items read the same once the verb is taken off: "
                                 f"{self._by_key[key].name!r} and {item.name!r}")
            self._by_key[key] = item
        by_name = {item.name: item for item in self.items}
        self._aliases: dict[str, BookItem] = {}
        for line, name in aliases.items():
            if name not in by_name:
                raise ValueError(f"the alias for {line!r} points at {name!r}, which isn't in the price book")
            self._aliases[price_key(line)] = by_name[name]

    @classmethod
    def load(cls, book_path: Path, aliases_path: Path) -> "PriceBook":
        workbook = openpyxl.load_workbook(str(book_path), data_only=True)
        items = []
        for sheet in SHEETS:
            ws = workbook[sheet]
            for row in range(1, ws.max_row + 1):
                name, price = ws.cell(row, 2).value, ws.cell(row, 3).value
                if isinstance(name, str) and name.strip() and isinstance(price, (int, float)) and not isinstance(price, bool):
                    note = ws.cell(row, 1).value
                    items.append(BookItem(name=name.strip(), price=float(price), sheet=sheet, row=row,
                                          needs_review=isinstance(note, str) and note.strip().startswith("Need")))
        aliases = json.loads(Path(aliases_path).read_text(encoding="utf-8"))["aliases"]
        return cls(items, aliases)

    def lookup(self, scope_text: str) -> BookItem | None:
        key = price_key(scope_text)
        return self._by_key.get(key) or self._aliases.get(key)

    def closest(self, scope_text: str, count: int = 3) -> list[BookItem]:
        """Price book items whose names come nearest — to help an estimator confirm a match, never to price."""
        keys = difflib.get_close_matches(price_key(scope_text), list(self._by_key), n=count, cutoff=0.4)
        return [self._by_key[key] for key in keys]
