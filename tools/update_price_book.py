"""Bring the app's price book up to date with the estimator's AME pricing workbook (T-002).

    python tools/update_price_book.py            copy Brain's workbook into assets/price_book/ and check it
    python tools/update_price_book.py --check    only say whether the app's copy is the same file (exit 1 if not)

Run it after every change to `Brain/AME Std Pricing Spreadsheet.xlsx.xlsx`. Brain's workbook is the one source of
truth: the app's copy (`assets/price_book/AME Std Pricing Spreadsheet.xlsx`, the path the app reads) is that file byte
for byte, and the test suite fails while the two differ. Before copying, the workbook is read the way the app reads
it, with the alias file: a workbook the app can't read, or one that drops or renames an item an alias points at, is
refused and the app's copy is left as it was. Then it prints how many priced items each sheet has.
Writes only the app's copy; reads nothing from a job.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from estimator.price_sheet.price_book import PriceBook  # noqa: E402

SOURCE = ROOT / "Brain" / "AME Std Pricing Spreadsheet.xlsx.xlsx"
TARGET = ROOT / "assets" / "price_book" / "AME Std Pricing Spreadsheet.xlsx"
ALIASES = ROOT / "assets" / "price_book" / "aliases.json"


def is_current(source: Path, target: Path) -> bool:
    return target.is_file() and target.read_bytes() == source.read_bytes()


def update(source: Path, target: Path, aliases: Path) -> PriceBook:
    """Check the workbook with the aliases, then copy it over the app's copy. Raises ValueError when it can't be read."""
    with tempfile.TemporaryDirectory() as scratch:     # read a copy: the estimator may have the workbook open
        copy = Path(scratch) / "book.xlsx"
        shutil.copyfile(source, copy)
        book = PriceBook.load(copy, aliases)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return book


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="only check that the app's copy is up to date")
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--target", type=Path, default=TARGET)
    parser.add_argument("--aliases", type=Path, default=ALIASES)
    args = parser.parse_args(argv)
    if not args.source.is_file():
        print(f"The pricing workbook is not there: {args.source}")
        return 1
    if args.check:
        if is_current(args.source, args.target):
            print("The app's price book is the estimator's workbook.")
            return 0
        print(f"The app's price book is out of date: run python tools/update_price_book.py\n"
              f"  workbook: {args.source}\n  app copy: {args.target}")
        return 1
    try:
        book = update(args.source, args.target, args.aliases)
    except ValueError as error:      # includes a file that isn't a workbook
        print(f"Not copied, the app's price book is unchanged: {error}")
        return 1
    per_sheet = Counter(item.sheet for item in book.items)
    total = len(book.items)
    print(f"Copied {args.source.name} to {args.target}: {total} priced item{'s' if total != 1 else ''}.")
    for sheet, count in per_sheet.items():
        print(f"  {sheet}: {count}")
    review = [item.name for item in book.items if item.needs_review]
    if review:
        print(f"  marked as needing review by the workbook itself: {len(review)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
