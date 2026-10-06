"""Source ids in client text: detected and refused, never rewritten. Also the places of refs and the labels of the
clarification kinds.

S is a schedule line, Q a keynote, I a drawing, F a fact, C a count. A token is id-shaped when it reads `[SQIFC]` +
1 to 4 digits + an optional letter as a whole token, in any case ("S141", "s141", "S141A"; not "F12" for "F1", not
"S141.5", not "S141ft"). Detection reads a copy of the text made for detection only: NFKC (full-width forms read as
ASCII), zero-width characters taken out. The text itself is never rewritten by detection.

`SourceIds.scan` sorts the id-shaped tokens of a text that are not tags (T, every tag of the job, a range "F1-F4"
covering F1 to F4) into four kinds (the estimator's ruling of 2026-10-05):

- sheet: a sheet number kept as written and never reported: one the planner's wheres name as a sheet (K,
  `job_sheets`: the where "S101, Structural.pdf page 3" on a sequence ref makes S101 a sheet of the job), or an
  unissued token right after a sheet word ("sheet C2", "sheets C101 and C102", "(sheet C101)"). A where on a
  writer's device ref is the writer's and makes no sheet; the run passes the whole plan's K to every intake. A sheet
  word never makes an issued id a sheet (the lead's ruling on L-D, lead/final-c): "sheet S141" with S141 issued and
  not in K is issued, in client text and in a where the writer typed alike.
- issued: any other id the job issued (I, every `Ref.source_id`; at intake also the evidence's ids). The intake
  refuses the text; the validator reports must_fix; the renderer's safety net takes out exactly that token.
- cited: an unissued token joined by and / or / , / to / through / thru / a dash / a slash to an issued id, along
  the run ("S141 and S999", "S141-S145"): the writer is citing ids. The intake refuses the text; the validator
  reports a check.
- loose: any other unissued token ("Fan C2 serves the lab", "(F1, F2)", "See C101"): a tag, a sheet or a part
  number the job never issued as a source id. Accepted as written, never reported, in brackets or after a cue word
  too.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

ONE_ID_TEXT = r"\b[SQIFC]\d{1,4}[A-Za-z]?\b"
ONE_ID = re.compile(ONE_ID_TEXT, re.IGNORECASE)
# a token on the detection copy: no letter or digit on either side, no decimal part ("S141.5" is a number)
_TOKEN = re.compile(r"(?<![^\W_])(?<![0-9]\.)[SQIFC][0-9]{1,4}[A-Za-z]?(?![^\W_])(?!\.[0-9])", re.IGNORECASE)
# the ledger's own bracket form of an id ("[S41]"), which the planner takes out of its texts
LEDGER_BRACKET = re.compile(r"\[[SQIFC]\d{1,4}[a-z]?\]", re.IGNORECASE)

SHEET = re.compile(r"\b[A-Z]{1,2}-?\d{1,3}(?:\.\d{1,3})?[A-Z]?\b")
_FILE_PART = re.compile(r"\.(?:pdf|docx?|xlsx?|dwg|txt|png|jpe?g)\b|\bpage\s+\d+\b", re.IGNORECASE)
_NOT_A_DOCUMENT = ("equipment counts",)          # the dossier's own label for a combined count, not a document
_NOT_A_PLACE = re.compile(r"^\s*ledger\b|\.(?:png|jpe?g)\b", re.IGNORECASE)   # a ledger fact or a picture file
# "sheet C101", "sheets C101 and C102", "dwg C3"; not "drawing", which the writer uses for a picture id ("drawing I12")
_SHEET_BEFORE = re.compile(r"(?<![^\W_])(?:sheets?|dwgs?\.?)\s*$", re.IGNORECASE)
_JOIN = re.compile(r"\s*(?:,|and|or|to|through|thru|[-–—/‐‑])\s*", re.IGNORECASE)
_WINDOW = 32                                      # how far back a sheet word is looked for
_ZERO_WIDTH = frozenset("​‌‍⁠﻿­")
# a range of plain ids in a tag ("F1-F4", "F1 thru 4"); a hyphen between the letter and the digits ("F-1 thru F-4")
# is no plain id, so it is no range of them either
_TAG_RANGE = re.compile(r"\b([SQIFC])(\d{1,4})\s*(?:-|–|\bthru\b|\bthrough\b|\bto\b)\s*(?:\1)?(\d{1,4})\b",
                        re.IGNORECASE)
MAX_RANGE = 500                                   # a tag range wider than this is not expanded
TRADE = re.compile(r"\b(plumbing|electrical|mechanical|architectural|fire protection|civil|structural)\b",
                   re.IGNORECASE)
REFUSAL = "name the document in words; cite it as a Ref, never print an id"


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def plain_id(source_id) -> str:
    """A source id as issued: "[C3]" and " C3 " are "C3"."""
    return str(source_id or "").strip().strip("[]").strip()


def _key(token) -> str:
    return unicodedata.normalize("NFKC", plain_id(token)).upper()


def without_ledger_brackets(text: str) -> str:
    """A planner text without the ledger's bracket form of an id ("Fire alarm by others [S14]" -> "Fire alarm by
    others"), whitespace collapsed. Anything else is the validator's to report."""
    return squash(LEDGER_BRACKET.sub(" ", text or ""))


# ---- T and I: what the job tags and what it issued ------------------------------------------------------------

def system_refs(system) -> list:
    """Every Ref a System carries: its sequence refs, its families' counts, its devices' refs and quantities."""
    refs = plan_refs(system)
    for device in system.devices:
        refs += _device_refs(device)
    return refs


def _device_refs(device) -> list:
    return [*device.refs, *device.quantity.sources, *(o.ref for o in device.quantity.others)]


def device_refs(device) -> list:
    """Every Ref a Device carries: its refs, its quantity's sources and its other counts' refs."""
    return _device_refs(device)


def system_tags(system) -> list[str]:
    """Every tag a System names: its families' tags and the units and heaters its duct heater entries name."""
    tags = [t for f in system.families for t in f.tags]
    for served in getattr(system, "serves", ()):
        tags += list(served.tags) + list(served.heaters)
    return tags


def job_tags(job) -> tuple[str, ...]:
    """T: every tag of the whole job, as printed (the renderer, the validator and the run's writers use this)."""
    return tuple(dict.fromkeys(t for s in job.systems for t in system_tags(s) if str(t or "").strip()))


def job_ids(job) -> tuple[str, ...]:
    """I: every source id a Ref of the job carries (systems, front end, exceptions)."""
    return tuple(dict.fromkeys(plain_id(r.source_id) for r in job_refs(job) if plain_id(r.source_id)))


def plan_refs(system) -> list:
    """The Refs the planner set on a System, which the writer cannot change: its sequence refs and its families'
    counts (the counts cross-check's sheet refs among them). Never its devices' refs."""
    refs = list(system.sequence_refs)
    for family in system.families:
        refs += list(family.count.sources) + [o.ref for o in family.count.others]
    return refs


def job_sheets(job) -> frozenset[str]:
    """K of the whole job: the sheet numbers the planner's wheres name (`ref_sheets` of every system's
    `plan_refs`, the front end's devices and the exceptions, which the planner makes). A where on a writer's
    device ref never counts: a writer could type any id there."""
    refs = [r for s in job.systems for r in plan_refs(s)]
    if job.front_end is not None:
        refs += [r for d in job.front_end.devices for r in _device_refs(d)]
    return ref_sheets(refs + [r for x in job.exceptions for r in x.refs])


def job_refs(job) -> list:
    """Every Ref of the job (systems, front end, exceptions)."""
    refs = [r for s in job.systems for r in system_refs(s)]
    if job.front_end is not None:
        refs += [r for d in job.front_end.devices for r in _device_refs(d)]
    return refs + [r for x in job.exceptions for r in x.refs]


def _sheet_form(text: str, found: re.Match) -> bool:
    """`found` (a sheet-number match in a where) reads as a sheet: a sheet word comes before it ("Sheet C501") or
    it stands first with a file part after it ("C101, Controls.pdf page 2", the ledger's own sheet form)."""
    if _SHEET_BEFORE.search(text[max(0, found.start() - _WINDOW):found.start()]):
        return True
    return found.start() == 0 and bool(_FILE_PART.search(text[found.end():]))


def _where_text(where) -> str:
    """The copy of a where that every where check reads (`ref_sheets`, `where_issued`, `sheet`, `place`): the
    detection copy `scan` reads client text on (NFKC per character, zero-width characters out), then its bracketed
    parts out and its whitespace collapsed. A place is printed from this copy, so it prints as detection read it."""
    return squash(re.sub(r"\([^)]*\)", " ", _for_detection(str(where or ""))[0]))


def ref_sheets(refs) -> frozenset[str]:
    """K: the id-shaped sheet numbers the wheres of `refs` (Refs or their dicts) name in sheet form, upper case. A
    where naming its own ref's source id as the sheet is not trusted (that is the id, misplaced)."""
    out: set[str] = set()
    for ref in refs:
        get = ref.get if isinstance(ref, dict) else (lambda name, default="": getattr(ref, name, default))
        text, own = _where_text(get("where", "")), _key(get("source_id", ""))
        if _NOT_A_PLACE.search(text) or text.lower().startswith(_NOT_A_DOCUMENT):
            continue
        for found in SHEET.finditer(text):
            token = _key(found.group(0))
            if ONE_ID.fullmatch(token) and token != own and _sheet_form(text, found):
                out.add(token)
    return frozenset(out)


def tag_tokens(tags: Iterable[str]) -> frozenset[str]:
    """The id-shaped tokens the tags protect, upper case: a tag is protected only in the form it is written. Each
    token the scanner itself reads inside the tag ("F1", "C2", "AHU-S1" and "AHU_S12" as "S1" and "S12") and each one
    a range of them covers ("F1-F4", "F1 thru 4": F1, F2, F3, F4). "S-1", "S_1A", "F-1 thru F-4", "EF-S-1" and
    "AHU_S12X3" protect nothing: the scanner never reads a plain id out of them, and their plain forms are issued ids
    of the job (facts F1, counts C1), never the tag."""
    out: set[str] = set()
    for tag in tags:
        tag = unicodedata.normalize("NFKC", str(tag or ""))
        out |= {match.group(0).upper() for match in _TOKEN.finditer(tag)}
        for found in _TAG_RANGE.finditer(tag):
            first, last = int(found.group(2)), int(found.group(3))
            if first <= last <= first + MAX_RANGE:
                out |= {f"{found.group(1).upper()}{n}" for n in range(first, last + 1)}
    return frozenset(out)


# ---- detection ---------------------------------------------------------------------------------------------------

def _for_detection(text: str) -> tuple[str, list[int] | None]:
    """The detection copy of `text` (NFKC per character, zero-width characters out) and, for each of its
    characters, the index of the character of `text` it came from (None: the copy is the text)."""
    if text.isascii():
        return text, None
    out: list[str] = []
    origin: list[int] = []
    for n, char in enumerate(text):
        if char in _ZERO_WIDTH:
            continue
        piece = unicodedata.normalize("NFKC", char) if not char.isascii() else char
        out.append(piece)
        origin += [n] * len(piece)
    return "".join(out), origin


@dataclass(frozen=True)
class Found:
    """One id-shaped token that is not a tag: as written on the detection copy, its span in the text, its kind."""
    token: str
    start: int
    end: int
    kind: str                       # "sheet", "issued", "cited" or "loose"


@dataclass(frozen=True)
class SourceIds:
    """The one decision: which id-shaped tokens in a text are sheets, issued ids, citations or loose tokens."""
    ids: frozenset[str] = frozenset()       # I, upper case
    tags: frozenset[str] = frozenset()      # T's id-shaped tokens, upper case
    sheets: frozenset[str] = frozenset()    # K, the planner's id-shaped sheet numbers (`job_sheets`), upper case

    @classmethod
    def of(cls, ids: Iterable[str] = (), tags: Iterable[str] = (), sheets: Iterable[str] = ()) -> "SourceIds":
        return cls(frozenset(_key(i) for i in ids if _key(i)), tag_tokens(tags),
                   frozenset(_key(k) for k in sheets if _key(k)))

    @classmethod
    def of_job(cls, job) -> "SourceIds":
        """T, I and K of the job (`job_tags`, `job_ids`, `job_sheets`: the planner's wheres only)."""
        return cls.of(job_ids(job), job_tags(job), job_sheets(job))

    def is_tag(self, token: str) -> bool:
        return _key(token) in self.tags

    def is_id(self, token: str) -> bool:
        """An issued id that is not a tag and not a sheet number the planner's wheres name (K)."""
        return _key(token) in self.ids and not self.is_tag(token) and _key(token) not in self.sheets

    def scan(self, text: str) -> list[Found]:
        """Every id-shaped token of `text` that is not a tag, in text order, with its kind (module docstring).
        Linear in the length of the text."""
        text = text or ""
        copy, origin = _for_detection(text)
        tokens = list(_TOKEN.finditer(copy))
        if not tokens:
            return []
        found: list[list] = []           # [token, start, end, kind, joined to the one before], on the copy
        listed = False                   # the token is in a list after a sheet word ("sheets C101, S141 and C102")
        for match in tokens:
            token, start, end = match.group(0), match.start(), match.end()
            if self.is_tag(token):
                found.append([token, start, end, "tag", False])
                listed = False
                continue
            joined = bool(found) and start - found[-1][2] <= _WINDOW and bool(_JOIN.fullmatch(copy[found[-1][2]:start]))
            listed = bool(_SHEET_BEFORE.search(copy[max(0, start - _WINDOW):start])) or (joined and listed)
            if _key(token) in self.sheets:
                kind = "sheet"
            elif self.is_id(token):
                kind = "issued"              # a sheet word before it changes nothing (L-D)
            elif listed:
                kind = "sheet"
            else:
                kind = "loose"
            found.append([token, start, end, kind, joined])
        # a loose token joined to an issued id ("S141 and S999", "S999-S141") is a citation too, along the run
        for order in (range(1, len(found)), range(len(found) - 2, -1, -1)):
            for n in order:
                other = n - 1 if order.step == 1 else n + 1
                link = found[n][4] if order.step == 1 else found[n + 1][4]
                if link and found[n][3] == "loose" and found[other][3] in ("issued", "cited"):
                    found[n][3] = "cited"
        out: list[Found] = []
        for token, start, end, kind, _ in found:
            if kind == "tag":
                continue
            if origin is not None:
                start, end = origin[start], origin[end - 1] + 1
            out.append(Found(token, start, end, kind))
        return out

    def refusal(self, text: str) -> str:
        """Why the intake refuses `text` ("" when it does not): an issued id that is no tag and no sheet number, or
        an unissued token joined to one, named in text order."""
        named = list(dict.fromkeys(f.token for f in self.scan(text) if f.kind in ("issued", "cited")))
        if not named:
            return ""
        return f"prints the source id{'s' if len(named) > 1 else ''} {', '.join(named)}: {REFUSAL}"

    def without_issued(self, text: str) -> str:
        """The renderer's safety net: `text` with exactly each issued id token taken out, whitespace collapsed;
        `text` itself (unchanged) when it has none."""
        text = text or ""
        cut = [f for f in self.scan(text) if f.kind == "issued"]
        if not cut:
            return text
        pieces, at = [], 0
        for found in cut:
            pieces.append(text[at:found.start])
            at = found.end
        pieces.append(text[at:])
        return squash(" ".join(pieces))

    # ---- places: a sheet number or a section, never a file name, never a source id ----

    def _sheet_ok(self, text: str, found: re.Match) -> bool:
        """A sheet number found in a where: printable unless it is id-shaped and the ledger does not know it as a
        sheet. An id-shaped token is a sheet when the planner's wheres name it as a sheet (K); else only when it is
        no issued id and reads as a sheet: a sheet word comes before it ("Sheet C501") or it stands first with a file
        part after it ("C101, Controls.pdf page 2"). A sheet word never makes an issued id printable (L-D)."""
        token = found.group(0)
        if not ONE_ID.fullmatch(token):
            return True
        if _key(token) in self.sheets:
            return True
        return _key(token) not in self.ids and _sheet_form(text, found)

    def where_issued(self, where: str) -> list[str]:
        """The issued ids (not in K) that `where` names after a sheet word ("Sheet S141, Mechanical.pdf page 3"),
        as written, in order: the where reads them as its sheet, but no issued id prints as a place (`place` leaves
        them out). The intake refuses a writer's where naming one; the validator reports it must_fix. Read on the
        detection copy (`_where_text`), so a full-width or zero-width id is found as `scan` finds it."""
        text = _where_text(where)
        if _NOT_A_PLACE.search(text) or text.lower().startswith(_NOT_A_DOCUMENT):
            return []
        return list(dict.fromkeys(
            f.group(0) for f in SHEET.finditer(text)
            if ONE_ID.fullmatch(f.group(0)) and _key(f.group(0)) in self.ids and _key(f.group(0)) not in self.sheets
            and _SHEET_BEFORE.search(text[max(0, f.start() - _WINDOW):f.start()])))

    def sheet(self, where: str) -> str:
        """The first printable sheet number in `where` (`_sheet_ok`), as the detection copy reads it
        (`_where_text`); "" for a ledger fact or a picture file."""
        text = _where_text(where)
        if _NOT_A_PLACE.search(text) or text.lower().startswith(_NOT_A_DOCUMENT):
            return ""
        return next((f.group(0) for f in SHEET.finditer(text) if self._sheet_ok(text, f)), "")

    def place(self, where: str) -> str:
        """Where a source is, as the client reads it: the first printable sheet number in it ("M-112.00", "C101");
        else the schedule, section or document name with the file name and its page left out; else "" (no place).
        A ledger fact, a picture file, an issued id, or a part holding an id-shaped token that is not a known sheet
        is no place. Every part is read on the detection copy (`_where_text`)."""
        found = self.sheet(where)
        if found:
            return found
        text = _where_text(where)
        if _NOT_A_PLACE.search(text) or text.lower().startswith(_NOT_A_DOCUMENT):
            return ""
        for part in re.split(r"[,;]", text):
            part = squash(part)
            if part and not _FILE_PART.search(part) and not ONE_ID.search(part):
                return part
        return ""


# ---- the clarification labels: each kind strips only the label its own form prints ---------------------------

# A label with its colon ("Assumed:", "Note:", "**Confirm**:") is a label whatever the kind; a bare label word
# ("Confirm", "Assumed", "Quantity per") only in the kind whose form prints it, and only when a space, a colon, an
# asterisk or the end follows it ("Assumption-based count" is words). The colon, dash or asterisks after a label go
# with it.
_AFTER = r"(?:[\s:*–—]|-(?=\s|$))*"          # a hyphen only as a dash ("Assumed - x"), never a minus ("-20 F")
_WORD_END = r"\**(?=[\s:*–—]|$)"             # "Assumed—two valves" is a label; "Assumption-based" is a word
_ANY_KIND = r"\*+|(?:confirm|assumed|assumption|note)\**\s*:"
_LABELS = {
    "confirm": re.compile(rf"^\s*(?:{_ANY_KIND}|confirm{_WORD_END}){_AFTER}", re.IGNORECASE),
    "assumed": re.compile(rf"^\s*(?:{_ANY_KIND}|assumed{_WORD_END}|assumption{_WORD_END}){_AFTER}", re.IGNORECASE),
    "note": re.compile(rf"^\s*(?:{_ANY_KIND}){_AFTER}", re.IGNORECASE),
    "per_drawings": re.compile(rf"^\s*(?:{_ANY_KIND}|quantity\s+per{_WORD_END}|as\s+per{_WORD_END}|per{_WORD_END})"
                               rf"{_AFTER}", re.IGNORECASE),
}


def strip_label(kind: str, text: str) -> str:
    """The text without the leading label of its kind's form ("*", "Confirm", "Assumed:", "Note:", "Quantity per"),
    so the form does not print it twice. Only the label word and the punctuation after it come off: "Confirm
    ownership of ..." keeps "ownership of ...", "Confirm quantity: 4 ..." keeps "quantity: 4 ...". Applying it
    twice changes nothing more."""
    label = _LABELS[kind]
    text = text or ""
    while True:
        stripped = label.sub("", text, count=1)
        if stripped == text:
            return text.strip()
        text = stripped


def per_drawings_text(text: str) -> str:
    """What a per-drawings clarification puts in its form: the trade its text names ("plumbing"), else the text
    without its own "Quantity per" and "drawings"."""
    trade = TRADE.search(text or "")
    if trade:
        return trade.group(1).lower()
    text = strip_label("per_drawings", text)
    return re.sub(r"\s*\bdrawings?\b\s*$", "", text, flags=re.IGNORECASE).strip(" .:;,")


def label_off(kind: str, text: str) -> str:
    """A clarification's text without its kind's label (a per-drawings text its discipline word only). This is
    the first step on every clarification, at intake and at render, before anything reads the text."""
    return per_drawings_text(text) if kind == "per_drawings" else strip_label(kind, text)


def clarification_text(kind: str, text: str, ids: SourceIds) -> str:
    """A clarification's text as its form prints it: the label off first, then the safety net (an issued id left
    in a stale text taken out, token only), then the label off again so it never prints twice."""
    return label_off(kind, ids.without_issued(label_off(kind, text)))
