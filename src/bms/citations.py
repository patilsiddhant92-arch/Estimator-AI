"""Client-text cleanup, decided in one place: source ids, places and clarification labels.

S is a schedule line, Q a keynote, I a drawing, F a fact, C a count. A token shaped like one ("F1", "C101") is a
source id ONLY when this run issued it (a `Ref.source_id` in the job, or an id in the writer's evidence), and never
when it equals a family tag or reads as a sheet number ("sheet C101", "C1.01"). `SourceIds` holds that decision.

The renderer (`render`), the validator (`validate`) and the intake (`ai`) all import this module: the id pattern,
the issued-ids check, the place lookup, the id stripper and the label stripper of each clarification kind.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

ONE_ID_TEXT = r"\b[SQIFC]\d{1,4}[a-z]?\b"
WITH_NOTE = rf"{ONE_ID_TEXT}(?:\s+(?:note|paragraph)\s+\d+)?"
ONE_ID = re.compile(ONE_ID_TEXT)
SOURCE_ID = re.compile(WITH_NOTE)
ID_GROUP = re.compile(rf"{WITH_NOTE}(?:\s*(?:,|and|to|through|thru|-|–)\s*{WITH_NOTE})*")
BRACKETED = re.compile(rf"\[\s*({WITH_NOTE}(?:\s*(?:,|and|to|through|thru|-|–)\s*{WITH_NOTE})*)\s*\]")

SHEET = re.compile(r"\b[A-Z]{1,2}-?\d{1,3}(?:\.\d{1,3})?[A-Z]?\b")
_FILE_PART = re.compile(r"\.(?:pdf|docx?|xlsx?|dwg|txt|png|jpe?g)\b|\bpage\s+\d+\b", re.IGNORECASE)
_NOT_A_DOCUMENT = ("equipment counts",)          # the dossier's own label for a combined count, not a document
_NOT_A_PLACE = re.compile(r"^\s*ledger\b|\.(?:png|jpe?g)\b", re.IGNORECASE)   # a ledger fact or a picture file
# "sheet C101", "sheets C101 and C102", "dwg C3"; not "drawing", which the writer uses for a picture id ("drawing I12")
_SHEET_BEFORE = re.compile(r"\b(?:sheets?|dwgs?\.?)\s*$", re.IGNORECASE)
_SHEET_AFTER = re.compile(r"^[.\-]\d")             # "C1.01", "F1-2": the token is part of a sheet number
_TAG_WORD = re.compile(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*")

DANGLING = re.compile(r"\s*\b(?:because|per|in|on|by|from|of|and|see|the)\s*(?=[,;:.)]|$)", re.IGNORECASE)
TRADE = re.compile(r"\b(plumbing|electrical|mechanical|architectural|fire protection|civil|structural)\b",
                   re.IGNORECASE)


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def plain_id(source_id) -> str:
    """A source id as issued: "[C3]" and " C3 " are "C3"."""
    return str(source_id or "").strip().strip("[]").strip()


def _field(ref, name: str) -> str:
    """A ref's field, whether the ref is a `Ref` or the writer's dict."""
    value = ref.get(name, "") if isinstance(ref, Mapping) else getattr(ref, name, "")
    return str(value or "")


# ---- what this run issued ----------------------------------------------------------------------------------------

def system_refs(system) -> list:
    """Every Ref a System carries: its sequence refs, its families' counts, its devices' refs and quantities."""
    refs = list(system.sequence_refs)
    for family in system.families:
        refs += list(family.count.sources) + [o.ref for o in family.count.others]
    for device in system.devices:
        refs += _device_refs(device)
    return refs


def _device_refs(device) -> list:
    return [*device.refs, *device.quantity.sources, *(o.ref for o in device.quantity.others)]


def system_tags(system) -> list[str]:
    """Every tag a System names: its families' tags and the units and heaters its duct heater entries name."""
    tags = [t for f in system.families for t in f.tags]
    for served in getattr(system, "serves", ()):
        tags += list(served.tags) + list(served.heaters)
    return tags


@dataclass(frozen=True)
class SourceIds:
    """The one decision: which tokens in a text are this run's source ids, and where each one is."""
    ids: frozenset[str] = frozenset()
    tags: frozenset[str] = frozenset()      # the words of every family tag, upper case

    @classmethod
    def of(cls, ids: Iterable[str] = (), tags: Iterable[str] = ()) -> "SourceIds":
        words = {w.upper() for tag in tags for w in _TAG_WORD.findall(str(tag or ""))}
        return cls(frozenset(plain_id(i) for i in ids if plain_id(i)), frozenset(words))

    @classmethod
    def of_job(cls, job) -> "SourceIds":
        """Every id a Ref of the job carries (systems, front end, exceptions), less every family tag."""
        refs, tags = [], []
        for system in job.systems:
            refs += system_refs(system)
            tags += system_tags(system)
        if job.front_end is not None:
            for device in job.front_end.devices:
                refs += _device_refs(device)
        for exception in job.exceptions:
            refs += list(exception.refs)
        return cls.of((r.source_id for r in refs), tags)

    def is_id(self, token: str) -> bool:
        """An issued id that is not a family tag."""
        token = plain_id(token)
        return token in self.ids and token.upper() not in self.tags

    def _run_ids(self, text: str, match: re.Match) -> list[str]:
        """The source ids in one id-shaped run of `text`; none when the run reads as a sheet number."""
        if _SHEET_BEFORE.search(text[:match.start()]) or _SHEET_AFTER.match(text[match.end():]):
            return []
        return [t for t in ONE_ID.findall(match.group(0)) if self.is_id(t)]

    def found(self, text: str) -> list[str]:
        """The source ids `text` names, in order (what the validator reports)."""
        text = text or ""
        return [i for m in ID_GROUP.finditer(text) for i in self._run_ids(text, m)]

    # ---- places: a sheet number or a section, never a file name, never an id ----

    def sheet(self, where: str, *own: str) -> str:
        """The first sheet number in `where` that is not a source id (this run's or `own`); "" for a ledger fact or
        a picture file."""
        text = squash(re.sub(r"\([^)]*\)", " ", where or ""))
        if _NOT_A_PLACE.search(text) or text.lower().startswith(_NOT_A_DOCUMENT):
            return ""
        own_ids = {plain_id(o) for o in own}
        for found in SHEET.finditer(text):
            if found.group(0) not in own_ids and not self.is_id(found.group(0)):
                return found.group(0)
        return ""

    def place(self, where: str, *own: str) -> str:
        """Where a source is, as the client reads it: the first sheet number in it ("M-112.00"); else the schedule,
        section or document name with the file name and its page left out; else "" (no place). A ledger fact, a
        picture file, or any part naming a source id is no place."""
        found = self.sheet(where, *own)
        if found:
            return found
        text = squash(re.sub(r"\([^)]*\)", " ", where or ""))
        if _NOT_A_PLACE.search(text) or text.lower().startswith(_NOT_A_DOCUMENT):
            return ""
        own_ids = {plain_id(o) for o in own}
        for part in re.split(r"[,;]", text):
            part = squash(part)
            ids = ONE_ID.findall(part)
            if part and not _FILE_PART.search(part) and not any(i in own_ids or self.is_id(i) for i in ids):
                return part
        return ""

    def place_of(self, source_id: str, groups) -> str:
        """The place of the first ref naming `source_id` in `groups` (sequences of refs) that names one."""
        for group in groups:
            for ref in group:
                if plain_id(_field(ref, "source_id")) == source_id:
                    place = self.place(_field(ref, "where"), source_id)
                    if place:
                        return place
        return ""

    # ---- the stripper ----

    def strip(self, text: str, *groups) -> str:
        """The text with every source id ("S141", "[Q2]", "S394 note 1", "S243 to S250") put as the place of its
        ref in `groups`, or taken out (the words around it tidied) when no ref names a place for it. Any other
        token shaped like an id (a tag, a sheet number, an id this run did not issue) is left as written, and a
        text with no source id comes back unchanged."""
        text = text or ""
        if not any(self._run_ids(text, m) for m in ID_GROUP.finditer(text)):
            return text
        out = BRACKETED.sub(lambda m: m.group(1) if any(self.is_id(t) for t in ONE_ID.findall(m.group(1)))
                            else m.group(0), text)

        def swap(match: re.Match) -> str:
            ids = self._run_ids(out, match)
            if not ids:
                return match.group(0)
            kept = [t for t in ONE_ID.findall(match.group(0)) if t not in ids]
            places = [p for p in (self.place_of(i, groups) for i in ids) if p]
            return " and ".join(dict.fromkeys(kept + places))

        out = ID_GROUP.sub(swap, out)
        out = re.sub(r"[(\[]\s*(?:(?:,|;|and)\s*)*[)\]]", " ", out)        # an emptied bracket
        out = re.sub(r"\(\s+", "(", out)
        out = re.sub(r"\s+([,;:.)])", r"\1", out)
        while True:
            tidy = DANGLING.sub("", out)
            tidy = re.sub(r"([,;:])\s*(?=[,;:.)]|$)", "", tidy)          # a separator left with nothing after it
            if tidy == out:
                break
            out = tidy
        return squash(out).lstrip(",;: ")


# ---- the clarification labels: each kind strips only the label its own form prints ---------------------------

# A label with its colon ("Assumed:", "Note:") is a label whatever the kind; a bare label word ("Confirm",
# "Assumed", "Quantity per") only in the kind whose form prints it ("Confirm with the owner ..." is a note's words).
_ANY_KIND = r"\*+|(?:confirm|assumed|assumption|note)\s*:"
_LABELS = {
    "confirm": re.compile(rf"^\s*(?:{_ANY_KIND}|confirm\b)\s*", re.IGNORECASE),
    "assumed": re.compile(rf"^\s*(?:{_ANY_KIND}|assumed\b|assumption\b)\s*:?\s*", re.IGNORECASE),
    "note": re.compile(rf"^\s*(?:{_ANY_KIND})\s*", re.IGNORECASE),
    "per_drawings": re.compile(rf"^\s*(?:{_ANY_KIND}|quantity\s+per\b|as\s+per\b|per\b)\s*:?\s*", re.IGNORECASE),
}


def strip_label(kind: str, text: str) -> str:
    """The text without the leading label of its kind's form ("*", "Confirm", "Assumed:", "Note:", "Quantity per"),
    so the form does not print it twice. Only the label word and its colon come off: "Confirm ownership of ..."
    keeps "ownership of ...", "Confirm quantity: 4 ..." keeps "quantity: 4 ...". Applying it twice changes nothing
    more."""
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


def clarification_text(kind: str, text: str, ids: SourceIds, *groups) -> str:
    """A clarification's text as its form takes it: its source ids put in words, its own kind's label off (a
    per-drawings text its trade word only)."""
    text = ids.strip(text, *groups)
    return per_drawings_text(text) if kind == "per_drawings" else strip_label(kind, text)
