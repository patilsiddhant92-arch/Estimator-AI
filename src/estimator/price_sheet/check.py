"""Compare a generated price sheet with the workup that was actually sent.

Nothing here fails a build. The price book holds the generic price used on most
jobs; a job can use a different price for a line — usually a vendor quote sourced for
that job — so a difference is not an error in the book. The report lists those
differences, and the lines the price book can't price yet, so an estimator can
confirm which price book item each unmatched line means.
"""
from __future__ import annotations

from pathlib import Path

from estimator.price_sheet.price_book import PriceBook
from estimator.price_sheet.rows import align, read_sent_rows
from estimator.text import strip_list_marker


def _money(value: float | None) -> str:
    return "—" if value is None else f"${value:,.2f}"


def price_check(generated: Path, sent: Path, book: PriceBook, title: str) -> str:
    ours_by_sheet, theirs_by_sheet = read_sent_rows(generated), read_sent_rows(sent)
    differs, same, pending, unpriced_sent, questioned = [], 0, [], [], []
    for sheet, ours in ours_by_sheet.items():
        theirs = theirs_by_sheet.get(sheet, [])
        partner = dict(align([r.text for r in ours], [r.text for r in theirs]))
        for index, row in enumerate(ours):
            if row.quantity is None:
                continue
            line = strip_list_marker(row.text)
            sent_price = theirs[partner[index]].unit_price if index in partner else None
            if row.unit_price is None:
                pending.append((line, row.quantity, sent_price, book.closest(line)))
                continue
            match = book.lookup(line)
            if match is not None and match.needs_review:
                questioned.append((line, row.quantity, row.unit_price))
            if sent_price is None:
                unpriced_sent.append((line, row.quantity, row.unit_price))
            elif sent_price == row.unit_price:
                same += 1
            else:
                differs.append((line, row.quantity, row.unit_price, sent_price))

    priced = same + len(differs) + len(unpriced_sent)
    out = [
        f"# Price check — {title}",
        "",
        "This price sheet was priced from the AME price book. Each line that carries a quantity is "
        "compared below with the workup that was sent for this job. The price book holds the generic "
        "price used on most jobs; where the sent workup used a different price, it was usually a vendor "
        "quote sourced for this job — so a difference here is not a mistake in the price book.",
        "",
        "| | Lines |",
        "|---|---|",
        f"| Lines with a quantity | {priced + len(pending)} |",
        f"| Priced from the price book | {priced} |",
        f"| — same price as the sent workup | {same} |",
        f"| — a different price was used for this job | {len(differs)} |",
        f"| — the sent workup had no price | {len(unpriced_sent)} |",
        f"| No price book match yet (PRICE PENDING) | {len(pending)} |",
        "",
        "## The sent workup used a different price",
        "",
        "Usually a vendor quote sourced for this job. The price book stays as it is.",
        "",
        "| Line | Qty | Price book | Sent workup |",
        "|---|---|---|---|",
        *[f"| {line} | {qty} | {_money(book_price)} | {_money(sent_price)} |" for line, qty, book_price, sent_price in differs],
        "",
        "## No price book match yet",
        "",
        "Each of these needs an estimator to say which price book item it is, if any. A confirmed "
        "match goes in `assets/price_book/aliases.json`, and the line is priced from then on.",
        "",
        "| Line | Qty | Sent workup price | Closest price book items |",
        "|---|---|---|---|",
        *[f"| {line} | {qty} | {_money(sent_price)} | {', '.join(i.name for i in near) or '—'} |"
          for line, qty, sent_price, near in pending],
        "",
        "## Priced by the book, but the sent workup had no price",
        "",
        "| Line | Qty | Price book |",
        "|---|---|---|",
        *[f"| {line} | {qty} | {_money(book_price)} |" for line, qty, book_price in unpriced_sent],
        "",
        "## Priced, but the price book itself marks the price as needing review",
        "",
        "| Line | Qty | Price book |",
        "|---|---|---|",
        *[f"| {line} | {qty} | {_money(book_price)} |" for line, qty, book_price in questioned],
        "",
    ]
    return "\n".join(out)
