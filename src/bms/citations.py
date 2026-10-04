"""Client-text cleanup, decided in one place: source ids, places and clarification labels.

S is a schedule line, Q a keynote, I a drawing, F a fact, C a count. A token is id-shaped when it reads
`[SQIFC]` + 1 to 4 digits + an optional letter, in any case ("S141", "s141", "S141A"). `SourceIds` decides what
happens to one:

- T, every tag of the whole job (family tags and the served units' and heaters' tags; a range "F1-F4" protects
  F1 to F4): kept as written.
- I, every `Ref.source_id` the run issued (the job's refs, and at intake the writer's evidence): stripped (put as
  the place of its ref, or taken out).
- Neither, inside a citation (a bracket group holding an id, a run joined to an issued id by and / or / , / to /
  through / thru / - / –, or right after a cue word: per, see, from, ref, refer to, cited in): stripped too, and
  reported as an unissued id removed.
- Neither, outside any citation ("Fan C2 serves the lab"): kept as written (more likely a tag or a part number);
  the validator reports it so the estimator looks.
- A token that reads as a sheet number ("sheet C101", "C1.01") is kept and never reported.

The renderer (`render`), the validator (`validate`) and the intake (`ai`) all import this module: the id pattern,
T and I (`job_tags`, `job_ids`, `SourceIds.of_job`), the place lookup, the id stripper and the label stripper of
each clarification kind.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

ONE_ID_TEXT = r"\b[SQIFC]\d{1,4}[A-Za-z]?\b"
WITH_NOTE = rf"{ONE_ID_TEXT}(?:\s+(?:note|paragraph)\s+\d+)?"
_JOIN = r"\s*(?:,|\band\b|\bor\b|\bto\b|\bthrough\b|\bthru\b|-|–)\s*"
ONE_ID = re.compile(ONE_ID_TEXT, re.IGNORECASE)
SOURCE_ID = re.compile(WITH_NOTE, re.IGNORECASE)
ID_GROUP = re.compile(rf"{WITH_NOTE}(?:{_JOIN}{WITH_NOTE})*", re.IGNORECASE)

SHEET = re.compile(r"\b[A-Z]{1,2}-?\d{1,3}(?:\.\d{1,3})?[A-Z]?\b")
_FILE_PART = re.compile(r"\.(?:pdf|docx?|xlsx?|dwg|txt|png|jpe?g)\b|\bpage\s+\d+\b", re.IGNORECASE)
_NOT_A_DOCUMENT = ("equipment counts",)          # the dossier's own label for a combined count, not a document
_NOT_A_PLACE = re.compile(r"^\s*ledger\b|\.(?:png|jpe?g)\b", re.IGNORECASE)   # a ledger fact or a picture file
# "sheet C101", "sheets C101 and C102", "dwg C3"; not "drawing", which the writer uses for a picture id ("drawing I12")
_SHEET_BEFORE = re.compile(r"\b(?:sheets?|dwgs?\.?)\s*$", re.IGNORECASE)
_SHEET_AFTER = re.compile(r"^[.\-]\d")             # "C1.01", "F1-2": the token is part of a sheet number
_CUE = re.compile(r"\b(?:per|see|from|ref\.?|refer(?:\s+to)?|cited\s+in)\s*[:\-–]?\s*[\[(]?\s*$", re.IGNORECASE)
_WINDOW = 24                                      # how far back a cue or a sheet word is looked for
_SQUARE = re.compile(r"\[([^\[\]]*)\]")
_BRACKET = re.compile(r"\[[^\[\]]*\]|\([^()]*\)")
_TAG_RANGE = re.compile(r"\b([SQIFC])-?(\d{1,4})\s*(?:-|–|\bthru\b|\bthrough\b|\bto\b)\s*(?:\1-?)?(\d{1,4})\b",
                        re.IGNORECASE)
MAX_RANGE = 500                                   # a tag range wider than this is not expanded

DANGLING = re.compile(r"\s*\b(?:because|per|in|on|by|from|of|and|see|the)\s*(?=[,;:.)]|$)", re.IGNORECASE)
TRADE = re.compile(r"\b(plumbing|electrical|mechanical|architectural|fire protection|civil|structural)\b",
                   re.IGNORECASE)


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def plain_id(source_id) -> str:
    """A source id as issued: "[C3]" and " C3 " are "C3"."""
    return str(source_id or "").strip().strip("[]").strip()


def _key(token) -> str:
    return plain_id(token).upper()


def _field(ref, name: str) -> str:
    """A ref's field, whether the ref is a `Ref` or the writer's dict."""
    value = ref.get(name, "") if isinstance(ref, Mapping) else getattr(ref, name, "")
    return str(value or "")


# ---- T and I: what this run issued and what the job tags --------------------------------------------------------

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


def job_tags(job) -> tuple[str, ...]:
    """T: every tag of the whole job, as printed (the renderer, the validator and the run's writers use this)."""
    return tuple(dict.fromkeys(t for s in job.systems for t in system_tags(s) if str(t or "").strip()))


def job_ids(job) -> tuple[str, ...]:
    """I: every source id a Ref of the job carries (systems, front end, exceptions)."""
    refs = [r for s in job.systems for r in system_refs(s)]
    if job.front_end is not None:
        refs += [r for d in job.front_end.devices for r in _device_refs(d)]
    refs += [r for x in job.exceptions for r in x.refs]
    return tuple(dict.fromkeys(plain_id(r.source_id) for r in refs if plain_id(r.source_id)))


def tag_tokens(tags: Iterable[str]) -> frozenset[str]:
    """The id-shaped tokens the tags protect, upper case: each one named ("F1", "C2") and each one a range covers
    ("F1-F4", "F1 thru 4": F1, F2, F3, F4)."""
    out: set[str] = set()
    for tag in tags:
        tag = str(tag or "")
        out |= {t.upper() for t in ONE_ID.findall(tag)}
        for found in _TAG_RANGE.finditer(tag):
            first, last = int(found.group(2)), int(found.group(3))
            if first <= last <= first + MAX_RANGE:
                out |= {f"{found.group(1).upper()}{n}" for n in range(first, last + 1)}
    return frozenset(out)


@dataclass(frozen=True)
class Cleaned:
    """One text cleaned: the new text and what was found in it."""
    text: str
    issued: list[str] = field(default_factory=list)            # issued ids stripped
    unissued_removed: list[str] = field(default_factory=list)  # unissued ids stripped (in a citation)
    unissued_kept: list[str] = field(default_factory=list)     # unissued ids kept (outside any citation)


@dataclass(frozen=True)
class SourceIds:
    """The one decision: which id-shaped tokens in a text are stripped, and where each issued one is."""
    ids: frozenset[str] = frozenset()       # I, upper case
    tags: frozenset[str] = frozenset()      # T's id-shaped tokens, upper case

    @classmethod
    def of(cls, ids: Iterable[str] = (), tags: Iterable[str] = ()) -> "SourceIds":
        return cls(frozenset(_key(i) for i in ids if _key(i)), tag_tokens(tags))

    @classmethod
    def of_job(cls, job) -> "SourceIds":
        """T and I of the job (`job_tags`, `job_ids`)."""
        return cls.of(job_ids(job), job_tags(job))

    def is_tag(self, token: str) -> bool:
        return _key(token) in self.tags

    def is_id(self, token: str) -> bool:
        """An issued id that is not a tag."""
        return _key(token) in self.ids and not self.is_tag(token)

    # ---- places: a sheet number or a section, never a file name, never an id-shaped token ----

    def sheet(self, where: str) -> str:
        """The first sheet number in `where` that is not id-shaped; "" for a ledger fact or a picture file."""
        text = squash(re.sub(r"\([^)]*\)", " ", where or ""))
        if _NOT_A_PLACE.search(text) or text.lower().startswith(_NOT_A_DOCUMENT):
            return ""
        return next((f.group(0) for f in SHEET.finditer(text) if not ONE_ID.fullmatch(f.group(0))), "")

    def place(self, where: str) -> str:
        """Where a source is, as the client reads it: the first sheet number in it ("M-112.00"); else the schedule,
        section or document name with the file name and its page left out; else "" (no place). A ledger fact, a
        picture file, or any part holding an id-shaped token (issued or not) is no place."""
        found = self.sheet(where)
        if found:
            return found
        text = squash(re.sub(r"\([^)]*\)", " ", where or ""))
        if _NOT_A_PLACE.search(text) or text.lower().startswith(_NOT_A_DOCUMENT):
            return ""
        for part in re.split(r"[,;]", text):
            part = squash(part)
            if part and not _FILE_PART.search(part) and not ONE_ID.search(part):
                return part
        return ""

    def place_of(self, source_id: str, groups) -> str:
        """The place of the first ref naming `source_id` in `groups` (sequences of refs) that names one."""
        for group in groups:
            for ref in group:
                if _key(_field(ref, "source_id")) == _key(source_id):
                    place = self.place(_field(ref, "where"))
                    if place:
                        return place
        return ""

    # ---- the stripper ----

    def clean(self, text: str, *groups) -> Cleaned:
        """The text with every issued id ("S141", "[Q2]", "S394 note 1", "S243 to S250") and every unissued id in
        a citation put as the place of its ref in `groups`, or taken out (the words around it tidied). Tags,
        sheet numbers and unissued tokens outside any citation are left as written; a text with nothing to strip
        comes back unchanged."""
        text = text or ""
        if not ONE_ID.search(text):
            return Cleaned(text)
        out, spans = self._unbracket(text)
        spans += [(m.start(), m.end()) for m in _BRACKET.finditer(out)
                  if any(self.is_id(t) for t in ONE_ID.findall(m.group(0)))]
        issued: list[str] = []
        removed: list[str] = []
        kept: list[str] = []
        pieces: list[str] = []
        at = 0
        for run in ID_GROUP.finditer(out):
            start, end = run.start(), run.end()
            if _SHEET_BEFORE.search(out[max(0, start - _WINDOW):start]) or _SHEET_AFTER.match(out[end:end + 2]):
                continue
            members = [t for t in ONE_ID.findall(run.group(0))]
            mine = [t for t in members if self.is_id(t)]
            other = [t for t in members if not self.is_tag(t) and not self.is_id(t)]
            cited = bool(mine) or any(a <= start < b for a, b in spans) or bool(
                _CUE.search(out[max(0, start - _WINDOW):start]))
            if not cited:
                kept += other
                continue
            if not mine and not other:
                continue
            issued += mine
            removed += other
            tags = [t for t in members if self.is_tag(t)]
            places = [p for p in (self.place_of(i, groups) for i in mine) if p]
            pieces += [out[at:start], " and ".join(dict.fromkeys(tags + places))]
            at = end
        if not issued and not removed:
            return Cleaned(text, unissued_kept=kept)
        pieces.append(out[at:])
        return Cleaned(_tidy("".join(pieces)), issued, removed, kept)

    def strip(self, text: str, *groups) -> str:
        return self.clean(text, *groups).text

    def _unbracket(self, text: str) -> tuple[str, list[tuple[int, int]]]:
        """Square brackets around a run of ids ("[S141, S999]") taken off; where each run now is (a citation)."""
        pieces: list[str] = []
        spans: list[tuple[int, int]] = []
        at = length = 0
        for m in _SQUARE.finditer(text):
            inner = m.group(1).strip()
            if not ID_GROUP.fullmatch(inner) or all(self.is_tag(t) for t in ONE_ID.findall(inner)):
                continue
            before = text[at:m.start()]
            pieces += [before, inner]
            length += len(before)
            spans.append((length, length + len(inner)))
            length += len(inner)
            at = m.end()
        pieces.append(text[at:])
        return "".join(pieces), spans


def _tidy(out: str) -> str:
    out = re.sub(r"[(\[]\s*(?:(?:,|;|and|or)\s*)*[)\]]", " ", out)        # an emptied bracket
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

# A label with its colon ("Assumed:", "Note:", "**Confirm**:") is a label whatever the kind; a bare label word
# ("Confirm", "Assumed", "Quantity per") only in the kind whose form prints it, and only when a space, a colon, an
# asterisk or the end follows it ("Assumption-based count" is words). The colon, dash or asterisks after a label go
# with it.
_AFTER = r"[\s:\-–—*]*"
_WORD_END = r"\**(?=[\s:*]|$)"
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


def clarification_text(kind: str, text: str, ids: SourceIds, *groups) -> str:
    """A clarification's text as its form takes it: its source ids put in words, its own kind's label off (a
    per-drawings text its trade word only)."""
    text = ids.strip(text, *groups)
    return per_drawings_text(text) if kind == "per_drawings" else strip_label(kind, text)
