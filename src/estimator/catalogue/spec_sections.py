"""Spec sections and the pages they run over; which of them are controls sections."""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from estimator.catalogue.register import PageRecord

_NUMBER = r"(\d{2}\s?\d{2}\s?\d{2}(?:\.\d{1,2})?|\d{5})"
# A section heading is "SECTION" in capitals, near the top of its page, not followed by punctuation:
# "Section 16727, "Data Cabling System"." in the body is a cross-reference, not a heading.
_HEADER = re.compile(rf"^[ \t]*SECTION[ \t]+{_NUMBER}\b[ \t]*[-–:]?[ \t]*(.*)$", re.M)
# A running header repeated at the top of every page: "Section 23 09 00" alone on its line, the title
# on the next (26-0356), or the number, page and title on one line: "230900-4    Instrumentation and
# Control of HVAC" (26-0344).
_RUNNING = re.compile(rf"^[ \t]*SECTION[ \t]+{_NUMBER}[ \t]*$", re.I | re.M)
_NUMBERED_TITLE = re.compile(rf"^[ \t]*{_NUMBER}[ \t]*[-–][ \t]*\d{{1,3}}[ \t]{{2,}}(\S.*?)[ \t]*$", re.M)
HEADER_LINES = 8            # a heading sits within the first eight lines of text on its page
_NOT_A_TITLE = re.compile(r"^[,.;:)”\"'’]|^[a-z]")
_FOOTER = re.compile(rf"^\s*{_NUMBER}\s*[-–]\s*\d{{1,3}}\s*$", re.M)
_END = re.compile(r"END\s+OF\s+SECTION", re.I)
_CONTROLS_TITLE = re.compile(
    r"building\s+(?:management|automation)|temperature\s+control|instrumentation\s+and\s+control|"
    r"\bDDC\b|direct\s+digital|sequences?\s+of\s+operations?|\bBMS\b|\bBAS\b|energy\s+management", re.I)


def section_number(raw: str) -> str:
    digits, _, suffix = raw.replace(" ", "").partition(".")
    number = f"{digits[0:2]} {digits[2:4]} {digits[4:6]}" if len(digits) == 6 else digits
    return f"{number}.{suffix}" if suffix else number


def is_controls_section(number: str, title: str) -> bool:
    if number.startswith(("23 09", "25 ")):
        return True
    if len(number) >= 5 and number[:5].isdigit() and 15900 <= int(number[:5]) <= 15999:
        return True
    return bool(_CONTROLS_TITLE.search(title))


@dataclass(frozen=True)
class SpecSection:
    number: str
    title: str
    document: str
    first_page: int
    last_page: int

    @property
    def controls(self) -> bool:
        return is_controls_section(self.number, self.title)


def _title_after(match: re.Match, text: str) -> str:
    title = " ".join(match.group(2).split()).strip(" -–:")
    if title:
        return title
    rest = text[match.end():].lstrip("\n")
    following = rest.split("\n", 1)[0].strip()
    return " ".join(following.split()) if following.isupper() else ""


def _next_line(match: re.Match, text: str) -> str:
    following = text[match.end():].lstrip("\n").split("\n", 1)[0].strip()
    looks_like_a_title = following[:1].isupper() and len(following) <= 80 and "INTENTIONALLY" not in following.upper()
    return " ".join(following.split()) if looks_like_a_title else ""


def _section_on(text: str) -> tuple[str | None, str]:
    """The section a page belongs to, and its title if the page gives it."""
    top = "\n".join([line for line in text.split("\n") if line.strip()][:HEADER_LINES])
    headers = [h for h in _HEADER.finditer(top) if not _NOT_A_TITLE.match(h.group(2).strip())]
    if headers:
        return section_number(headers[0].group(1)), _title_after(headers[0], top)
    running = _RUNNING.search(top)
    if running:
        return section_number(running.group(1)), _next_line(running, top)
    numbered = _NUMBERED_TITLE.search(top)
    if numbered:
        return section_number(numbered.group(1)), " ".join(numbered.group(2).split())
    footer = _FOOTER.search(text)
    return (section_number(footer.group(1)), "") if footer else (None, "")


def index_sections(pages: Sequence[PageRecord]) -> list[SpecSection]:
    sections: list[SpecSection] = []
    current: dict | None = None

    def close():
        nonlocal current
        if current is not None:
            sections.append(SpecSection(**current))
            current = None

    for record in pages:
        if current is not None and record.document != current["document"]:
            close()
        if len({section_number(h.group(1)) for h in _HEADER.finditer(record.text)}) >= 3:
            continue                                   # a table of contents
        number, title = _section_on(record.text)
        if number is not None and (current is None or current["number"] != number):
            close()
            current = {"number": number, "title": title, "document": record.document,
                       "first_page": record.page, "last_page": record.page}
        elif current is not None:
            current["last_page"] = record.page
            if title and not current["title"]:
                current["title"] = title
        if current is not None and _END.search(record.text):
            close()
    close()
    return sections
