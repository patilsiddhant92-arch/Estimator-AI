"""The AME price book: what each device costs, and which device is the standard pick.

Lookup is deliberately strict. A scope line is priced only when its name — with
the list marker, the leading verb and any "(Qty. N Total)" taken off — is the
same as a price book item's name, or when an estimator has confirmed the match
in the alias file. Anything else is PRICE PENDING: guessing a price is the same
failure as guessing a quantity.

The book is the estimator's AME Std Pricing workbook, read in its own layout (T-002):
on each price sheet the item's name is column B and its Estimation Price column C.
A row without a name (a second part number for the item above) or without a price
above 0 is not an item. On "Control Valves & Meters" a row named only by a size
takes the heading above it ('Modulating Control Valves 1/2"'), a "High Performance"
row takes the item above it, and the side table (name H, price I) is read too.
Rows under the book's own "Below is not completed" note, and rows whose column A
note starts with "Need", are priced but marked as needing review.
assets/price_book/ holds a byte copy of Brain's workbook: tools/update_price_book.py.
"""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from estimator.files import open_workbook
from estimator.text import squash, strip_list_marker

PARTS, PANELS, VALVES = "Std Parts Pricing", "BMS-DDC-Panels", "Control Valves & Meters"
SHEETS = (PARTS, PANELS, VALVES)
_TABLES = {PARTS: ((2, 3),), PANELS: ((2, 3),), VALVES: ((2, 3), (8, 9))}   # (name column, price column) pairs
_NOT_COMPLETED = "below is not completed"                                 # the book's own note above unfinished rows
_SIZE_ONLY = re.compile(r'^[\d\s/&.\-]+"$')                                  # '1/2"', '1-1/4 & 1-1/2"'
_VARIANT = "high performance"
# "(Qty. 6 Total)", "(Qty. ##)" and the old "– (Qty. 6 Total)": only a bracket that starts with "Qty" is taken off.
_QUANTITY = re.compile(r"\s*(?:[–-]\s*)?\(qty\.?\s*(?:\d+|##)\s*(?:total)?\s*\).*$", re.IGNORECASE)
# "install" and "install and wire" are deliberately not stripped: an install-only line's device
# is furnished by others, so pricing its material from the book's furnish-and-install price would
# be a guessed price for the part AME isn't supplying. Those lines go PRICE PENDING instead.
_VERB = re.compile(r"^(?:furnish and install|furnish and wire|furnish|provide)\s+", re.IGNORECASE)


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
            key = price_key(line)
            if key in self._by_key and self._by_key[key] is not by_name[name]:
                raise ValueError(f"the alias {line!r} is itself a price book item ({self._by_key[key].name!r}), "
                                 f"so it can't point at {name!r}")
            self._aliases[key] = by_name[name]

    @classmethod
    def load(cls, book_path: Path, aliases_path: Path) -> "PriceBook":
        workbook = open_workbook(book_path, data_only=True)
        missing = [sheet for sheet in SHEETS if sheet not in workbook.sheetnames]
        if missing:
            raise ValueError(f"{Path(book_path).name} has no {', '.join(repr(m) for m in missing)} sheet: "
                             f"is it the AME Std Pricing workbook?")
        items = []
        for sheet in SHEETS:
            ws = workbook[sheet]
            for name_col, price_col in _TABLES[sheet]:
                items += _read_table(ws, sheet, name_col, price_col)
        aliases = json.loads(Path(aliases_path).read_text(encoding="utf-8"))["aliases"]
        return cls(items, aliases)

    def unpriced(self, scope_lines: list[str]) -> list[str]:
        """The lines the book can't price, as given: each one is PRICE PENDING, never priced at 0."""
        return [line for line in scope_lines if self.lookup(line) is None]

    def lookup(self, scope_text: str) -> BookItem | None:
        key = price_key(scope_text)
        return self._by_key.get(key) or self._aliases.get(key)

    def closest(self, scope_text: str, count: int = 3) -> list[BookItem]:
        """Price book items whose names come nearest — to help an estimator confirm a match, never to price."""
        keys = difflib.get_close_matches(price_key(scope_text), list(self._by_key), n=count, cutoff=0.4)
        return [self._by_key[key] for key in keys]


def _price(value) -> float | None:
    """A price above 0, or None: a blank, a word or a 0 is not a price."""
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return float(value)
    return None


def _read_table(ws, sheet: str, name_col: int, price_col: int) -> list[BookItem]:
    items: list[BookItem] = []
    heading, unfinished = "", False
    for row in range(1, ws.max_row + 1):
        name, price = ws.cell(row, name_col).value, _price(ws.cell(row, price_col).value)
        if not (isinstance(name, str) and name.strip()):
            continue
        name = squash(name)
        if name.casefold().startswith(_NOT_COMPLETED):
            unfinished = True
            continue
        if price is None:
            heading = name                 # a heading, or an item with no price yet: neither is priced
            continue
        if _SIZE_ONLY.match(name) and heading:
            name = f"{heading} {name}"
        elif name.casefold() == _VARIANT and items:
            name = f"{items[-1].name} - {name}"
        note = ws.cell(row, 1).value if name_col == 2 else None
        needs = unfinished or (isinstance(note, str) and note.strip().startswith("Need"))
        items.append(BookItem(name=name, price=price, sheet=sheet, row=row, needs_review=needs))
    return items
