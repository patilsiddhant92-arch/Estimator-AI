"""Client-text cleanup, decided in one place: source ids, places and clarification labels.

S is a schedule line, Q a keynote, I a drawing, F a fact, C a count. A token is id-shaped when it reads
`[SQIFC]` + 1 to 4 digits + an optional letter, in any case ("S141", "s141", "S141A"). `SourceIds` decides what
happens to one:

- T, every tag of the whole job (family tags and the served units' and heaters' tags; a range "F1-F4" protects
  F1 to F4): kept as written.
- I, every `Ref.source_id` the run issued (the job's refs, and at intake the writer's evidence): stripped (put as
  the place of its ref, or taken out).
- Neither, inside a citation: stripped too, and reported as an unissued id removed. A citation is a round or
  square bracket group holding an id-shaped token that is not a tag; a run joined to an issued id by and / or / , /
  to / through / thru / - / – / — / slash; or the ids right after a cue word (per, see, from, ref, refer to, cited
  in) up to the first tag ("from C2, S999" cites C2 only).
- Neither, outside any citation ("Fan C2 serves the lab"): kept as written (more likely a tag or a part number);
  the validator reports it so the estimator looks.
- A token that reads as a sheet number ("sheet C101", "sheets C101 and C102", "C1.01") is kept and never
  reported. In a ref's where, an id-shaped sheet ("Sheet C501", "C101, Controls.pdf page 2") is a place unless it
  is an issued id.

Only the words around an id taken out are tidied: its cue word goes with it, at a clause end the dangling words
and separators before it, and a bracket left empty. Cleaning twice gives what cleaning once gives.

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
_JOIN = r"\s*(?:,|\band\b|\bor\b|\bto\b|\bthrough\b|\bthru\b|[-–—/‐‑])\s*"
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
_INNERMOST = re.compile(r"\[[^\[\]()]*\]|\([^()\[\]]*\)")     # a bracket with no bracket inside it
_TAG_RANGE = re.compile(r"\b([SQIFC])-?(\d{1,4})\s*(?:-|–|\bthru\b|\bthrough\b|\bto\b)\s*(?:\1-?)?(\d{1,4})\b",
                        re.IGNORECASE)
MAX_RANGE = 500                                   # a tag range wider than this is not expanded

DANGLING_WORDS = frozenset(("because", "per", "in", "on", "by", "from", "of", "and", "see", "the"))
DANGLING = re.compile(rf"\s*\b(?:{'|'.join(sorted(DANGLING_WORDS))})\s*(?=[,;:.)]|$)", re.IGNORECASE)
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

    # ---- places: a sheet number or a section, never a file name, never a source id ----

    def _sheet_ok(self, text: str, found: re.Match) -> bool:
        """A sheet number found in a where: printable unless it is id-shaped and the ledger does not know it as a
        sheet. An id-shaped token is a sheet only when it is not an issued id and either a sheet word comes before
        it ("Sheet C501") or it stands first with a file part after it ("C101, Controls.pdf page 2")."""
        token = found.group(0)
        if not ONE_ID.fullmatch(token):
            return True
        if _key(token) in self.ids:
            return False
        if _SHEET_BEFORE.search(text[max(0, found.start() - _WINDOW):found.start()]):
            return True
        return found.start() == 0 and bool(_FILE_PART.search(text[found.end():]))

    def sheet(self, where: str) -> str:
        """The first printable sheet number in `where` (`_sheet_ok`); "" for a ledger fact or a picture file."""
        text = squash(re.sub(r"\([^)]*\)", " ", where or ""))
        if _NOT_A_PLACE.search(text) or text.lower().startswith(_NOT_A_DOCUMENT):
            return ""
        return next((f.group(0) for f in SHEET.finditer(text) if self._sheet_ok(text, f)), "")

    def place(self, where: str) -> str:
        """Where a source is, as the client reads it: the first printable sheet number in it ("M-112.00", "C101");
        else the schedule, section or document name with the file name and its page left out; else "" (no place).
        A ledger fact, a picture file, an issued id, or a part holding an id-shaped token that is not a known sheet
        is no place."""
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
        a citation put as the place of its ref in `groups`, or taken out. Tags (a tag range whole, with its own
        joiners), sheet numbers and unissued tokens outside any citation are left as written; a text with nothing
        to strip comes back unchanged. The words are tidied only where an id was taken out: its cue word goes with
        it ("Fans per S999 stay on." -> "Fans stay on."), and at the end of a clause the dangling words and
        separators before it ("valves, see S999." -> "valves."); a bracket left empty is taken out. Idempotent."""
        text = text or ""
        if not ONE_ID.search(text):
            return Cleaned(text)
        out, spans = self._unbracket(text)
        # a bracket group, round or square, holding an id-shaped token that is not a tag is a citation
        spans += [(m.start(), m.end()) for m in _BRACKET.finditer(out)
                  if any(not self.is_tag(t) for t in ONE_ID.findall(m.group(0)))]
        issued: list[str] = []
        removed: list[str] = []
        kept: list[str] = []
        found: dict[str, str] = {}          # each id's place, looked up once per text
        pieces: list[str] = []
        written = ""                        # the end of the text as rewritten so far (for the cue word)
        at = 0
        spans.sort()
        reach: list[int] = []               # the furthest end of the spans up to each one (they may nest)
        for _, b in spans:
            reach.append(max(b, reach[-1]) if reach else b)
        next_span = 0                       # runs come in order: the spans opened before this run
        for run in ID_GROUP.finditer(out):
            start, end = run.start(), run.end()
            members = ONE_ID.findall(run.group(0))
            # sheet numbers kept as written: the token after a sheet word ("sheet C101", and the unissued ones
            # listed with it: "sheets C101 and C102"), and a token that a sheet number goes on from ("C1.01")
            sheets: set[int] = set()
            if _SHEET_BEFORE.search(out[max(0, start - _WINDOW):start]):
                sheets = {0} | {i for i, t in enumerate(members) if i and not self.is_id(t)}
            if _SHEET_AFTER.match(out[end:end + 2]):
                sheets.add(len(members) - 1)
            while next_span < len(spans) and spans[next_span][0] <= start:
                next_span += 1
            inside = next_span > 0 and reach[next_span - 1] > start
            free = [i for i in range(len(members)) if i not in sheets]
            mine = [members[i] for i in free if self.is_id(members[i])]
            loose = [i for i in free if not self.is_tag(members[i]) and not self.is_id(members[i])]
            left = (written + out[at:start])[-_WINDOW:]
            if mine or (not sheets and inside):
                cited = set(loose)                          # joined to an issued id, or in a bracket: all of them
            elif not sheets and _CUE.search(left):          # after a cue word: up to the first tag ("from C2, S999"
                first_tag = next((i for i, t in enumerate(members) if self.is_tag(t)), len(members))
                cited = {i for i in loose if i < first_tag}  # cites C2 only)
            else:
                cited = set()
            kept += [members[i] for i in loose if i not in cited]
            if not mine and not cited:
                continue
            sheets = sheets | {i for i in loose if i not in cited}     # kept as written in the rewrite
            issued += mine
            removed += [members[i] for i in sorted(cited)]
            new = self._rewrite(run.group(0), groups, found, sheets)
            before = out[at:start]
            if not new:                     # the run is gone: its cue word goes too, and at a clause end the rest
                before = _cut_cue(before)
                if _AT_STOP.match(out[end:]):
                    before = _without_chain(before)
                    while not before and pieces:        # back over runs taken out just before ("on I3 and in F17")
                        before = _without_chain(pieces.pop())
            pieces += [before, new]
            at = end
            last = len(members) - 1
            if last not in sheets and not self.is_tag(members[last]) and _GLUED_AFTER.match(out[end:end + 2]):
                pieces.append(" ")          # the joiner to a word after an id taken out goes ("i8-EF-1" -> " EF-1")
                at = end + 1
            written = _last(pieces, _WINDOW)
        if not issued and not removed:
            return Cleaned(text, unissued_kept=kept)
        pieces.append(out[at:])
        return Cleaned(_tidy("".join(pieces)), issued, removed, kept)

    def _rewrite(self, run: str, groups, found: dict[str, str], sheets: set[int] = frozenset()) -> str:
        """A run of ids as printed: each stretch of tags (or sheet numbers, `sheets`) as written, with its own
        joiners ("F5-F8", "F5 to F8"), and the place of each issued id, in order, joined by "and"; unissued ids and
        places no ref names left out."""
        members = list(SOURCE_ID.finditer(run))            # each member with its own "note N"
        tokens = [ONE_ID.match(m.group(0)).group(0) for m in members]
        parts: list[str] = []
        places: set[str] = set()

        def verbatim(n: int) -> bool:
            return n in sheets or self.is_tag(tokens[n])

        i = 0
        while i < len(members):
            if verbatim(i):
                j = i
                while j + 1 < len(members) and verbatim(j + 1):
                    j += 1
                parts.append(run[members[i].start():members[j].end()])
                i = j + 1
                continue
            if self.is_id(tokens[i]):
                place = self._cached_place(tokens[i], groups, found)
                if place and place not in places:
                    places.add(place)
                    parts.append(place)
            i += 1
        return " and ".join(parts)

    def _cached_place(self, source_id: str, groups, found: dict[str, str]) -> str:
        key = _key(source_id)
        if key not in found:
            found[key] = self.place_of(source_id, groups)
        return found[key]

    def strip(self, text: str, *groups) -> str:
        return self.clean(text, *groups).text

    def _unbracket(self, text: str) -> tuple[str, list[tuple[int, int]]]:
        """Square brackets around a run of ids ("[S141, S999]", "valves[S141]") put as spaces, so a glued id
        stands apart; where each run now is (a citation)."""
        pieces: list[str] = []
        spans: list[tuple[int, int]] = []
        at = length = 0
        for m in _SQUARE.finditer(text):
            inner = m.group(1).strip()
            if not ID_GROUP.fullmatch(inner) or all(self.is_tag(t) for t in ONE_ID.findall(inner)):
                continue
            before = text[at:m.start()] + " "
            pieces += [before, inner, " "]
            length += len(before)
            spans.append((length, length + len(inner)))
            length += len(inner) + 1
            at = m.end()
        pieces.append(text[at:])
        return "".join(pieces), spans


_CUE_CUT = re.compile(r"\b(?:per|see|from|ref\.?|refer(?:\s+to)?|cited\s+in)\s*[:\-–]?\s*$", re.IGNORECASE)
_GLUED_AFTER = re.compile(r"[-–—/‐‑]\w")
_AT_STOP = re.compile(r"\s*(?:[,;:.)\]]|$)")       # what follows a run: a stop or the end (a clause ends there)
CHAIN_WORDS = DANGLING_WORDS | {"ref", "refer", "to", "cited", "or"}
_EMPTY_INSIDE = re.compile(rf"(?:\s|[,;:/]|\b(?:{'|'.join(sorted(CHAIN_WORDS))})\b\.?)*", re.IGNORECASE)


def _last(pieces: list[str], size: int) -> str:
    """The last `size` characters of the pieces joined (only the pieces needed are read)."""
    tail = ""
    for piece in reversed(pieces):
        tail = piece + tail
        if len(tail) >= size:
            break
    return tail[-size:]


def _cut_cue(before: str) -> str:
    """`before` without the cue word it ends with ("Fans per " -> "Fans ")."""
    tail = before[-_WINDOW:]
    found = _CUE_CUT.search(tail)
    return before[:len(before) - len(tail) + found.start()] if found else before


def _without_chain(before: str) -> str:
    """`before` without the dangling words, cue words and separators it ends with ("valves, see " -> "valves")."""
    tokens = _TOKEN.findall(before)
    n = len(tokens)
    while n and (tokens[n - 1].isspace() or tokens[n - 1] in ",;:/" or tokens[n - 1].lower() in CHAIN_WORDS):
        n -= 1
    return "".join(tokens[:n])


def _tidy(out: str) -> str:
    """The rewritten text tidied: a bracket left with nothing but separators or cue words taken out (nested ones
    too), no space before a stop or after an opening bracket, no separator before a stop or at the end, single
    spaces."""
    while True:
        tidy = _INNERMOST.sub(lambda m: " " if _EMPTY_INSIDE.fullmatch(m.group(0)[1:-1]) else m.group(0), out)
        if tidy == out:
            break
        out = tidy
    out = re.sub(r"([(\[])\s+", r"\1", out)
    out = re.sub(r"\s+([,;:.)\]])", r"\1", out)
    out = re.sub(r"[,;:]+(?=[.,;:)\]]|\s*$)", "", out)
    return squash(out).lstrip(",;: ")


_TOKEN = re.compile(r"\s+|\w+|[^\w\s]")


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


def clarification_text(kind: str, text: str, ids: SourceIds, *groups) -> str:
    """A clarification's text as its form takes it: its source ids put in words, its own kind's label off (a
    per-drawings text its trade word only)."""
    text = ids.strip(text, *groups)
    return per_drawings_text(text) if kind == "per_drawings" else strip_label(kind, text)
