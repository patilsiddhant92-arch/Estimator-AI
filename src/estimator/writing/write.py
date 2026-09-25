"""Write each system from the Master Template (design §10): lines, quantities, tech hours,
confidence and the review list.

For each system (a bundle from systems.py) the template's lines are chosen by reading the job:
each condition is looked for in the unit's schedule, the sequence passages, the notes, the tag
prefixes and the Spec overview. A line whose conditions hold goes in, with the words that decided
it. A template default that nothing in the job decides goes in as an ASSUMPTION. A line that can't
be checked, because the evidence it needs isn't there, is PENDING: it is never printed, and it goes
on the review list. The optional AI judge can settle an ASSUMPTION or a PENDING line with a quote;
when it disagrees with a rule that has evidence, the rule's answer is kept and the review list says so.
It may also add a line the evidence calls for that no template option covers: that line is ADDED,
never surer than 0.7, with a review line.

A system with no Master Template entry is written by the AI from its evidence, in the house style,
like its nearest templates and the phrasing bank's examples: every line ADDED (at most 0.7), with a
review line to check the wording, and the AI's tech hours as an ASSUMPTION when they follow a real
template. Without the AI it stays a PENDING block, kept out of the proposal.

The client sees only the Block (estimator.scope). Categories, confidence, sources and evidence stay
in the ScopeLines, for the Evidence Package.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache

from estimator.catalogue.overview import FOUND, short_place
from estimator.scope import Block, FrontEnd, Item, Job, Run
from estimator.writing.front_end import front_end, job_header
from estimator.writing.judge import NO_KEY
from estimator.writing.phrasing import examples_for, load_bank
from estimator.writing.style import load_house_style
from estimator.writing.systems import OWN_TAGS, SystemBundle, build_bundles, naming, unbundled_flags
from estimator.writing.templates import (HARDWARE_VERBS, TEMPLATES_FILE, Condition, SystemTemplate, TemplateLine,
                                         TechHours, integration_trio, load_templates, nearest_templates,
                                         template_for)

HOLDS, NO, UNKNOWN = "holds", "no", "unknown"
CONFIRMED, ADDED, ASSUMPTION, PENDING = "CONFIRMED", "ADDED", "ASSUMPTION", "PENDING"
_STRENGTH = {CONFIRMED: 3, ADDED: 2, ASSUMPTION: 1, PENDING: 0}
_RULE_CONFIDENCE = {"schedule": 0.8, "sequence": 0.8, "prefix": 0.8, "spec_overview": 0.8, "notes": 0.7}
_RULE_CATEGORY = {"notes": ADDED}
COUNTED_CONFIDENCE, DEFAULT_CONFIDENCE, AI_SEQUENCE, AI_OTHER = 0.9, 0.5, 0.9, 0.7
AI_THRESHOLD = 0.7
AI_WRITTEN_CAP = 0.7        # a line the AI wrote itself is never surer than this
NO_AI = "judgement pending — the AI was not asked on this run"
WAITING_FOR_AI = "waiting for the AI to write this system (no Master Template entry)"
_BLANK_CELLS = {"", "-", "--", "—", "–", "N/A", "NA", "NONE", "0", "0.0", "0.00", "X"}
_PLACE_WORDS = {"schedule": "the schedule", "sequence": "the sequence", "notes": "the notes",
                "prefix": "the tag prefixes", "spec_overview": "the Spec overview"}
_CATEGORY_IN_FLAG = re.compile(r"\((EXTRA|ORPHANED|PENDING|DISCREPANCY|MISSING|CONFLICT)\)")
_MAX_EVIDENCE_ROWS = 20
_QUOTE_LIMIT = 300


@dataclass(frozen=True)
class ScopeLine:
    system: str
    text: str
    depth: int
    quantity: int | None
    tech_hours: float | None
    category: str        # CONFIRMED | ADDED | ASSUMPTION | PENDING
    confidence: float
    source: str          # "rule: reheat_hot_water (M-601 VAV BOX SCHEDULE, GPM column)" | "AI: …" | "default"
    evidence: str        # where + quote
    client: bool         # goes into the proposal


@dataclass(frozen=True)
class ReviewItem:
    """One thing the estimator decides before the proposal goes out."""
    system: str
    category: str        # the estimator's word (PENDING, ASSUMPTION, EXTRA, …) or "" for a plain check
    decide: str          # what to decide, in plain words
    evidence: str
    action: str

    def __str__(self) -> str:
        head = f"{self.system}: {self.decide}" if self.system else self.decide
        return head + (f" — {self.action}" if self.action else "")


@dataclass(frozen=True)
class WrittenSystem:
    bundle_key: str
    blocks: tuple[Block, ...]            # the client view; a group lists one header per family, stacked
    lines: tuple[ScopeLine, ...]
    review: tuple[ReviewItem, ...]
    printed: bool = True                 # False: kept out of the proposal until the estimator writes it
    template: str | None = None
    tech_hours: float | None = None

    @property
    def block(self) -> Block:
        return self.blocks[0]

    @property
    def confidence(self) -> float:
        """The lowest confidence of the lines in the proposal (Evidence Package only)."""
        printed = [line.confidence for line in self.lines if line.client]
        return min(printed) if printed else 0.0


# --- the settings ------------------------------------------------------------------------------------

@lru_cache(maxsize=2)
def _settings(path=TEMPLATES_FILE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=512)
def _word(word: str) -> re.Pattern:
    body = r"\s+".join(re.escape(part) for part in word.split())
    return re.compile(rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])", re.I)


def _squash(text: str) -> str:
    return " ".join((text or "").split())


def _plain(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").casefold()).strip()


def _paragraph_at(text: str, at: int) -> str:
    """The paragraph of a passage (paragraphs are joined by a blank line) holding position `at`."""
    start = text.rfind("\n\n", 0, at)
    end = text.find("\n\n", at)
    return text[start + 2 if start >= 0 else 0: end if end >= 0 else len(text)]


def _sentence(text: str, start: int, end: int) -> str:
    stop = text.rfind(". ", 0, start)
    lo = max(stop + 2 if stop >= 0 else 0, text.rfind("\n", 0, start) + 1)
    ends = [i for i in (text.find(". ", end), text.find("\n", end)) if i != -1]
    hi = min(ends) + 1 if ends else len(text)
    quote = _squash(text[lo:hi])
    return quote if len(quote) <= _QUOTE_LIMIT else quote[:_QUOTE_LIMIT].rstrip() + "…"


def tag_list(tags) -> str:
    """The tags as the proposal writes them: "VAV-21-01 thru 12", "AHU-1, 2, 3"."""
    def stem(tag: str) -> str:
        cut = max(tag.rfind("-"), tag.rfind("."))
        return tag[:cut + 1] if cut > 0 else ""

    runs: list[list[str]] = []
    for tag in tags:
        m = re.match(r"^(.*?)(\d+)$", tag)
        if runs and m:
            last = re.match(r"^(.*?)(\d+)$", runs[-1][-1])
            if last and last.group(1) == m.group(1) and int(last.group(2)) + 1 == int(m.group(2)) \
                    and (len(last.group(2)) == len(m.group(2)) or not last.group(2).startswith("0")):
                runs[-1].append(tag)
                continue
        runs.append([tag])
    pieces = []
    for run in runs:
        pieces += [f"{run[0]} thru {run[-1]}"] if len(run) >= 3 else run

    parts, previous = [], None
    for part in pieces:
        first, _, last = part.partition(" thru ")
        own = stem(first)
        shown = first[len(own):] if own and own == previous else first
        if last:
            shown += " thru " + (last[len(own):] if own and last.startswith(own) else last)
        parts.append(shown)
        previous = own
    return ", ".join(parts)


# --- reading the conditions ------------------------------------------------------------------------

@dataclass(frozen=True)
class Hit:
    condition: str
    place: str
    where: str
    quote: str
    own: bool = True     # the words sit where the system's own units are named (its schedule rows, a
                         # paragraph naming its tags); False for a paragraph naming only its kind or prefix

    @property
    def text(self) -> str:
        return f"{self.where}: “{self.quote}”" if self.quote else self.where


@dataclass(frozen=True)
class _Check:
    state: str                  # HOLDS | NO | UNKNOWN
    hit: Hit | None = None
    partial: str = ""           # "held for 2 of 5 units" — the schedule shows it for some units only


class _Reading:
    """One bundle's evidence, and each template condition checked against it once."""

    def __init__(self, bundle: SystemBundle, catalogue, template: SystemTemplate | None = None):
        self.bundle = bundle
        self.rows = bundle.schedule_rows
        self.passages = bundle.passages
        self.notes: list[tuple[str, str]] = [("the schedule's notes", n) for n in bundle.controls_by]
        self.notes += [("the schedule's notes", n) for n in bundle.schedule_notes if n not in bundle.controls_by]
        self._schedule_notes = len(self.notes)
        for note in bundle.notes:
            label = " ".join(p for p in (note.sheet, note.block.title() if note.block else "", note.number) if p)
            self.notes.append((label or "a drawing note", note.text))
        self.prefixes = [f.prefix for f in bundle.families]
        overview = getattr(catalogue, "overview", None)
        self.topics = [t for t in (overview.topics if overview is not None else ()) if t.status == FOUND]
        self.names = naming(bundle, (template.name, *template.kinds) if template is not None else ())
        self._seen: dict[str, _Check] = {}

    def checks(self) -> list[_Check]:
        return list(self._seen.values())

    def available(self, place: str) -> bool:
        return {"schedule": bool(self.rows), "sequence": bool(self.passages), "notes": bool(self.notes),
                "prefix": True, "spec_overview": True}[place]

    def check(self, condition: Condition) -> _Check:
        if condition.name not in self._seen:
            self._seen[condition.name] = self._evaluate(condition)
        return self._seen[condition.name]

    def _evaluate(self, c: Condition) -> _Check:
        places = [(p, getattr(c, p)) for p in ("schedule", "sequence", "notes", "prefix", "spec_overview")
                  if getattr(c, p)]
        partial = ""
        for place, words in places:
            if not self.available(place):
                continue
            found, partial_here = getattr(self, f"_in_{place}")(c.name, words)
            if found is not None:
                return _Check(HOLDS, found, partial_here)
            partial = partial or partial_here
        if any(self.available(place) for place, _ in places):
            return _Check(NO, None, partial)
        return _Check(UNKNOWN)

    def _in_schedule(self, name: str, words) -> tuple[Hit | None, str]:
        tables: dict[tuple, list] = {}
        for row in self.rows:
            tables.setdefault((row.sheet, row.title, row.headers), []).append(row)
        for (sheet, title, headers), rows in tables.items():
            label = f"{sheet} {title}" if sheet else title
            for word in words:
                pattern = _word(word)
                if pattern.search(title or ""):
                    return Hit(name, "schedule", label, title), ""
                for header in headers:
                    if not pattern.search(header or ""):
                        continue
                    filled = [r for r in rows if _squash(r.cells.get(header, "")).upper() not in _BLANK_CELLS]
                    if filled:
                        partial = (f"{word} holds for {len(filled)} of {len(rows)} units ({header} column)"
                                   if len(filled) < len(rows) else "")
                        return (Hit(name, "schedule", f"{label}, {header} column",
                                    f"{header}: {_squash(filled[0].cells.get(header, ''))}"), partial)
                for row in rows:
                    for header, cell in row.cells.items():
                        if not cell or _squash(cell) == row.tag:
                            continue
                        if pattern.search(cell):
                            return Hit(name, "schedule", f"{label}, {row.tag}", f"{header}: {_squash(cell)}"), ""
        return None, ""

    def _in_sequence(self, name: str, words) -> tuple[Hit | None, str]:
        """The words, in a paragraph that names the system (its tags, prefix or kind) or in the
        system's own section: a sentence about every fan decides nothing for this one."""
        for passage in self.passages:
            for word in words:
                for m in _word(word).finditer(passage.text):
                    rank = self.names(_paragraph_at(passage.text, m.start()))
                    if rank or passage.section:
                        return Hit(name, "sequence", passage.where, _sentence(passage.text, m.start(), m.end()),
                                   own=rank == OWN_TAGS), ""
        return None, ""

    def _in_notes(self, name: str, words) -> tuple[Hit | None, str]:
        for n, (where, text) in enumerate(self.notes):
            for word in words:
                m = _word(word).search(text)
                if m:
                    own = n < self._schedule_notes or self.names(text) == OWN_TAGS
                    return Hit(name, "notes", where, _sentence(text, m.start(), m.end()), own=own), ""
        return None, ""

    def quote_names_units(self, quote: str) -> bool:
        """The AI's quote sits in a sequence paragraph naming the system's own tags."""
        wanted = _plain(quote)
        if not wanted:
            return False
        for passage in self.passages:
            for paragraph in passage.text.split("\n\n"):
                if wanted in _plain(paragraph) and self.names(paragraph) == OWN_TAGS:
                    return True
        return False

    def _in_prefix(self, name: str, words) -> tuple[Hit | None, str]:
        for prefix in self.prefixes:
            if prefix.upper() in (w.upper() for w in words):
                return Hit(name, "prefix", "the tag prefix", prefix), ""
        return None, ""

    def _in_spec_overview(self, name: str, words) -> tuple[Hit | None, str]:
        for topic in self.topics:
            if any(_word(w).search(topic.item) for w in words):
                return Hit(name, "spec_overview", short_place(topic.places), topic.quote, own=False), ""
        return None, ""

    def factory_controls(self, words) -> Hit | None:
        """The unit comes with the manufacturer's own controls, when the schedule says so."""
        for where, text in [("the schedule's notes", n) for n in (*self.bundle.controls_by,
                                                                    *self.bundle.schedule_notes)]:
            for word in words:
                m = _word(word).search(text)
                if m:
                    return Hit("factory_controls", "schedule", where, _sentence(text, m.start(), m.end()))
        hit, _ = self._in_schedule("factory_controls", words)
        return hit

    # -- where each quote came from, for the AI's answers
    def locate(self, quote: str) -> tuple[str, str] | None:
        """(place, where) of the words the AI quoted, or None when they are not in the evidence."""
        wanted = _plain(quote)
        if not wanted:
            return None
        for passage in self.passages:
            if wanted in _plain(passage.text):
                return "sequence", passage.where
        for where, text in self.notes:
            if wanted in _plain(text):
                return "notes", where
        for row in self.rows:
            label = f"{row.sheet} {row.title}" if row.sheet else row.title
            if wanted in _plain(" ".join([row.title, *row.headers, *row.cells.values()])):
                return "schedule", label
        for device in self.bundle.devices:
            if wanted in _plain(f"{device.label} {device.device}"):
                return "plans", f"{device.sheet or device.document} ({device.label} counted on the plans)"
        return None


# --- one line's decision ----------------------------------------------------------------------------

@dataclass
class _State:
    text: str
    depth: int
    quantity_rule: str
    of: tuple[str, ...]
    hardware: bool
    choice: str | None = None
    include: bool = False
    category: str = ""           # CONFIRMED | ADDED | ASSUMPTION | PENDING, or "" when left out
    confidence: float = 0.0
    source: str = ""
    evidence: str = ""
    decided: str = ""            # "rule" | "absence" | "unless" | "default" | "pending" | "alternative" | "ai" | "factory"
    quantity: int | None = None
    listed: bool = False          # a left-out line kept in the Evidence Package (the AI decided it)
    default: bool = False
    words: str = ""              # what the rule looked for, for a disagreement
    specific: int = 0            # how many conditions the line needs (a choice prefers the most)
    counted: str = ""            # the device count behind the quantity, for the review list
    stated: int | None = None    # a count the AI quoted from the evidence (a line it wrote itself)
    hits: tuple = ()             # what the rule found (the words that put the line in, or kept it out)
    won: bool = False            # the AI's answer beat the rule's

    @property
    def open(self) -> bool:
        """A decision the AI may settle: a default, a PENDING line, or an alternative nothing checked."""
        return self.decided in ("default", "pending", "alternative")


def _looked_for(template: SystemTemplate, names) -> str:
    """What the conditions look for, in words: “GPM”, “HW COIL” or “HOT WATER” in the schedule; …"""
    parts = []
    for name in names:
        c = template.conditions[name]
        for place in _places(c):
            words = getattr(c, place)
            shown = ", ".join(f"“{w}”" for w in words[:4]) + (" …" if len(words) > 4 else "")
            parts.append(f"{shown} in {_PLACE_WORDS[place]}")
    return "; ".join(parts)


_MISSING_PLACE = {"schedule": "schedule row", "sequence": "sequence passage", "notes": "schedule or drawing note"}


def _decide(line: TemplateLine, template: SystemTemplate, reading: _Reading, pending_reason: str) -> _State:
    state = _State(line.text, line.depth, line.quantity, line.of, line.hardware_point, line.choice,
                   default=line.default, specific=len(line.when))
    whens = [(n, reading.check(template.conditions[n])) for n in line.when]
    unless = [(n, reading.check(template.conditions[n])) for n in line.unless]
    blocked = [(n, c) for n, c in unless if c.state == HOLDS]
    if blocked:
        name, check = blocked[0]
        state.decided, state.evidence, state.hits = "unless", check.hit.text, (check.hit,)
        state.words = f"the rule left it out because of {check.hit.text}"
        return state
    unsure_unless = [n for n, c in unless if c.state == UNKNOWN]
    if "{" in line.text:
        state.decided, state.category = "pending", PENDING
        state.evidence = "The line needs a detail the job has to give (the part in braces)"
        return state
    if whens:
        states = [c.state for _, c in whens]
        if all(s == HOLDS for s in states):
            hits = [c.hit for _, c in whens]
            weakest = min(hits, key=lambda h: _RULE_CONFIDENCE[h.place])
            state.include, state.decided, state.hits = True, "rule", tuple(hits)
            state.category = _RULE_CATEGORY.get(weakest.place, CONFIRMED)
            state.confidence = _RULE_CONFIDENCE[weakest.place]
            state.source = "rule: " + "; ".join(f"{h.condition} ({h.where})" for h in hits)
            state.evidence = " | ".join(h.text for h in hits)
            state.words = state.evidence
            if unsure_unless:
                state.category, state.confidence = ASSUMPTION, DEFAULT_CONFIDENCE
                state.source += f" — could not check {', '.join(unsure_unless)}"
                state.evidence += f" (could not check for {_looked_for(template, unsure_unless)})"
            return state
        if NO in states:
            missing = [n for n, c in whens if c.state == NO]
            state.decided = "absence"
            state.words = f"the rule found none of {_looked_for(template, missing)}"
            return state
        state.decided, state.category = "pending", PENDING
        unknown = [n for n, c in whens if c.state == UNKNOWN]
        where = sorted({_MISSING_PLACE[p] for n in unknown for p in _places(template.conditions[n])
                        if p in _MISSING_PLACE})
        state.evidence = (f"Nothing to check it against — the line needs {_looked_for(template, unknown)}, and "
                          f"this system has no {' or '.join(where)}; {pending_reason}")
        return state
    if line.default:
        state.include, state.decided, state.category = True, "default", ASSUMPTION
        state.confidence, state.source = DEFAULT_CONFIDENCE, "default"
        state.evidence = "Master Template default — nothing in the job decides it"
        if unsure_unless:
            state.evidence += f" (could not check for {_looked_for(template, unsure_unless)})"
        return state
    state.decided, state.category = "pending", PENDING
    state.evidence = f"The Master Template gives no rule for this line; {pending_reason}"
    return state


def _places(condition: Condition) -> list[str]:
    return [p for p in ("schedule", "sequence", "notes", "prefix", "spec_overview") if getattr(condition, p)]


def _choose(states: list[_State]) -> None:
    """Each choice group: the most specific winner whose conditions all hold, else the default."""
    groups: dict[str, list[_State]] = {}
    for s in states:
        if s.choice:
            groups.setdefault(s.choice, []).append(s)
    for members in groups.values():
        winners = [s for s in members if s.decided == "rule"]
        default = next((s for s in members if s.default), None)
        if winners:
            best = max(winners, key=lambda s: (s.specific, s.confidence))
            for s in members:
                if s is not best:
                    s.include, s.category, s.decided, s.hits = False, "", "absence", best.hits
                    s.words = f"the rule chose {best.text} instead ({best.evidence})"
            continue
        unchecked = [s for s in members if s.decided == "pending"]
        for s in unchecked:
            s.decided, s.category = "alternative", ""
        if default is not None and default.decided == "default" and unchecked:
            default.evidence = ("Master Template default — the other choices could not be checked "
                                f"({'; '.join(s.text for s in unchecked)})")


# --- the AI --------------------------------------------------------------------------------------------

def _rules_text(template: SystemTemplate) -> list[str]:
    rules = []
    for name, c in template.conditions.items():
        places = [f"any of {', '.join(repr(w) for w in getattr(c, p))} in {_PLACE_WORDS[p]}" for p in _places(c)]
        rules.append(f"Condition {name} holds when it finds {'; or '.join(places)}.")
    for line in template.lines:
        parts = []
        if line.when:
            parts.append(f"needs {' and '.join(line.when)}")
        if line.unless:
            parts.append(f"not when {' or '.join(line.unless)}")
        if line.choice:
            parts.append(f"is one choice of '{line.choice}'" + (" (the default)" if line.default else ""))
        elif line.default and not line.when:
            parts.append("is included by default")
        if parts:
            rules.append(f"'{line.text}' {', '.join(parts)}.")
    rules += [f"Hint: {hint}" for hint in template.hints]
    return rules


def _evidence_text(bundle: SystemBundle, reading: _Reading) -> str:
    parts = []
    if bundle.schedule_rows:
        parts.append("Schedule rows:")
        for row in bundle.schedule_rows[:_MAX_EVIDENCE_ROWS]:
            label = f"{row.sheet} {row.title}" if row.sheet else row.title
            cells = "; ".join(f"{h}: {_squash(v)}" for h, v in row.cells.items() if _squash(v))
            parts.append(f"- [{label}] {row.tag} — {cells}")
        if len(bundle.schedule_rows) > _MAX_EVIDENCE_ROWS:
            parts.append(f"- … and {len(bundle.schedule_rows) - _MAX_EVIDENCE_ROWS} more rows like these")
    if reading.notes:
        parts.append("Notes:")
        parts += [f"- [{where}] {_squash(text)}" for where, text in reading.notes]
    if bundle.devices:
        parts.append("Devices counted on the plans where this system's tags are:")
        parts += [f"- [{d.sheet or d.document}] {d.label} ({d.device}): {d.total}" for d in bundle.devices]
    if bundle.passages:
        parts.append("Passages from the sequence of operation and points list:")
        for passage in bundle.passages:
            parts.append(f"[{passage.where}]\n{passage.text.strip()}")
    return "\n".join(parts)


def _note_is_borne_out(note: str, evidence: str) -> bool:
    words = [w for w in _plain(note.lstrip("*")).split() if len(w) >= 4]
    have = set(_plain(evidence).split())
    return bool(words) and all(w in have for w in words)


def _apply_ai(states, judgement, reading: _Reading, system: str, review: list[ReviewItem]) -> None:
    answers = {c.line: c for c in judgement.choices}
    for s in states:
        c = answers.get(s.text)
        if c is None:
            continue
        located = reading.locate(c.quote) if c.quote else None
        strong = c.confidence >= AI_THRESHOLD and bool(c.quote)
        if strong and located is None:
            if not (s.open or s.include != c.include):
                continue      # it agrees with the rule: nothing to check
            review.append(ReviewItem(system, "", f"The AI {'includes' if c.include else 'leaves out'} {s.text}, "
                                     "but its quote is not in the job's documents", f"“{c.quote}”",
                                     "Check the line by hand"))
            continue
        if not strong:
            if s.decided == "pending" and c.why:
                s.evidence += f" (the AI: {c.why})"
            continue
        place, where = located
        category = CONFIRMED if place == "sequence" else ADDED
        confidence = AI_SEQUENCE if place == "sequence" else AI_OTHER
        quoted = f"{where}: “{c.quote}”"
        disagrees = (s.decided == "rule" and not c.include) or (s.decided in ("absence", "unless") and c.include)
        if s.open:
            s.include, s.decided, s.category, s.confidence = c.include, "ai", category, confidence
            s.source = f"AI: {c.why}" if c.include else f"AI: left out — {c.why}"
            s.evidence, s.listed = quoted, True
        elif disagrees and place == "sequence" and reading.quote_names_units(c.quote) \
                and not any(h.own for h in s.hits):
            # The AI quotes a paragraph naming this system's own units; the rule's words did not.
            rule_said = s.evidence if s.decided == "rule" else s.words
            s.include, s.decided, s.category, s.confidence = c.include, "ai", category, confidence
            s.source = f"AI: {c.why}" if c.include else f"AI: left out — {c.why}"
            s.evidence, s.listed, s.won = quoted, True, True
            review.append(ReviewItem(system, "", f"The AI's answer is kept over the rule on {s.text} — its quote "
                                     "names this system's own units; the rule's words did not",
                                     f"{rule_said} vs {quoted}",
                                     f"Check it: the AI {'includes' if c.include else 'leaves out'} the line"))
        elif s.decided == "rule" and not c.include:
            review.append(ReviewItem(system, "CONFLICT", f"The rule and the AI disagree on {s.text} — "
                                     f"{s.evidence} vs {quoted}", f"The rule includes it; the AI says: {c.why}",
                                     "The rule's answer is kept — check it and delete the line if the AI is right"))
        elif s.decided in ("absence", "unless") and c.include:
            review.append(ReviewItem(system, "CONFLICT", f"The rule and the AI disagree on {s.text} — "
                                     f"{s.words} vs {quoted}", f"The AI says: {c.why}",
                                     "The rule's answer is kept (left out) — add the line if the AI is right"))
    # A choice the AI settled replaces the default the rule fell back on.
    groups: dict[str, list[_State]] = {}
    for s in states:
        if s.choice:
            groups.setdefault(s.choice, []).append(s)
    for members in groups.values():
        chosen = [s for s in members if s.decided == "ai" and s.include]
        if not chosen:
            if any(s.won and not s.include for s in members) and not any(s.include for s in members):
                default = next((s for s in members if s.default), None)
                if default is not None:          # the AI took out the rule's choice: the default stands
                    default.include, default.decided, default.category = True, "default", ASSUMPTION
                    default.confidence, default.source = DEFAULT_CONFIDENCE, "default"
                    default.evidence = ("Master Template default — the AI left out "
                                        + "; ".join(s.text for s in members if s.won))
            continue
        best = max(chosen, key=lambda s: (s.won, s.confidence))
        for s in members:
            if s is not best and s.include and (s.decided in ("default", "ai") or (best.won and s.decided == "rule")):
                s.include, s.category, s.listed = False, "", False
    if judgement.dropped:
        review.append(ReviewItem(system, "", "The AI answered lines that are not in the Master Template; they were "
                                 "thrown away", "; ".join(judgement.dropped), "Nothing to do unless a line is missing"))
    _refused_review(system, getattr(judgement, "refused", ()), review)


def _refused_review(system: str, refused, review: list[ReviewItem]) -> None:
    if refused:
        review.append(ReviewItem(system, "", "The AI wrote lines or notes that break the house style; they were "
                                 "thrown away", "; ".join(refused), "Nothing to do unless a line is missing"))


def _hardware(text: str) -> bool:
    verb = load_house_style().verb(text)
    not_points = [s.lower() for s in _settings().get("not_hardware_points_containing", ())]
    return (verb is not None and verb.lower() in HARDWARE_VERBS
            and not any(s in text.lower() for s in not_points))


def _quoted(reading: _Reading, quote: str) -> str | None:
    """Where the AI's quote is in the job's documents, with the quote; None when it is not there."""
    located = reading.locate(quote) if quote else None
    return f"{located[1]}: “{quote}”" if located else None


def _extra_lines(states: list[_State], judgement, reading: _Reading, system: str,
                 review: list[ReviewItem]) -> None:
    """Lines the evidence calls for that no template option covers: ADDED, never surer than 0.7,
    each with a review line. One whose quote is not in the job's documents is only reviewed."""
    have = {s.text.lower() for s in states}
    for extra in getattr(judgement, "extra_lines", ()):
        if extra.text.lower() in have:
            continue
        have.add(extra.text.lower())
        quoted = _quoted(reading, extra.quote)
        if quoted is None:
            review.append(ReviewItem(system, "", f"The AI adds “{extra.text}”, but its quote is not in the job's "
                                     "documents", f"“{extra.quote}” — {extra.why}", "Add the line by hand if the job "
                                     "needs it"))
            continue
        states.append(_State(extra.text, extra.depth, "ai", (), _hardware(extra.text), include=True,
                             category=ADDED, confidence=min(extra.confidence, AI_WRITTEN_CAP),
                             source=f"AI: {extra.why}", evidence=quoted, decided="ai-extra", listed=True,
                             stated=extra.quantity))
        review.append(ReviewItem(system, ADDED, "Line added beyond the Master Template",
                                 f"“{extra.text}” — {quoted}", "check"))


# --- quantities and hours -------------------------------------------------------------------------------

def _count(families, of) -> int | None:
    chosen = [f for f in families if not of or f.prefix in of]
    if not chosen or any(f.quantity is None for f in chosen):
        return None
    return sum(f.quantity for f in chosen)


def _counted_labels(text: str) -> tuple[str, ...]:
    table = _settings()["counted_devices"]["lines"]
    low = text.lower()
    matches = [(len(k), v) for k, v in table.items() if k.lower() in low]
    return tuple(max(matches)[1]) if matches else ()


def _ai_quantity(text: str, stated: int | None, bundle: SystemBundle) -> tuple[int | None, str]:
    """A line the AI wrote: counted on the plans when the device maps, else the count the evidence
    states (the AI quoted it), else one per unit. With the note behind a plan count."""
    labels = _counted_labels(text)
    found = [d for d in bundle.devices if d.label in labels]
    total = sum(d.total for d in found)
    if total:
        places = ", ".join(sorted({d.sheet or d.document for d in found}))
        return total, (f"{total} × {', '.join(sorted({d.label for d in found}))} counted on the plans where "
                       f"this system's tags are ({places})")
    if stated is not None:
        return stated, ""
    return _count(bundle.families, ()), ""


def _quantity(s: _State, bundle: SystemBundle) -> None:
    if s.quantity_rule == "ai":
        s.quantity, s.counted = _ai_quantity(s.text, s.stated, bundle)
        if s.counted:
            s.evidence += f" (quantity: {s.counted})"
    elif s.quantity_rule == "one":
        s.quantity = 1
    elif s.quantity_rule == "none":
        s.quantity = None
    elif s.quantity_rule == "per_unit":
        s.quantity = _count(bundle.families, s.of)
    elif s.quantity_rule == "counted":
        labels = _counted_labels(s.text)
        found = [d for d in bundle.devices if d.label in labels]
        total = sum(d.total for d in found)
        if total:
            s.quantity = total
            if s.include and s.category in (ASSUMPTION, CONFIRMED, ADDED):
                places = ", ".join(sorted({d.sheet or d.document for d in found}))
                s.category, s.confidence = CONFIRMED, COUNTED_CONFIDENCE
                s.source = f"counted: {', '.join(sorted({d.label for d in found}))} on the plans"
                s.evidence = f"{total} counted on {places}"
                s.counted = (f"{total} × {', '.join(sorted({d.label for d in found}))} counted on the plans where "
                             f"this system's tags are ({places})")
            return
        if bundle.group and not s.of:
            s.quantity = None
            return
        s.quantity = _count(bundle.families, s.of)
        if s.include and s.category in (CONFIRMED, ADDED):
            s.category, s.confidence = ASSUMPTION, DEFAULT_CONFIDENCE
        if s.include:
            s.evidence += " (quantity: one per unit — no device count on the plans)"


def _hours_of(th: TechHours, template: SystemTemplate, reading: _Reading, bundle: SystemBundle,
              printed: list[_State], notes: list[str]) -> float | None:
    hours, unsure = th.hours, []
    for conditions, override in th.overrides:
        checks = [reading.check(template.conditions[c]) for c in conditions]
        if all(c.state == HOLDS for c in checks):
            hours = override
            break
        if any(c.state == UNKNOWN for c in checks) and not any(c.state == NO for c in checks):
            unsure.append((conditions, override))
    if hours is None:
        return None
    for conditions, override in unsure:
        notes.append(f"The tech hours ({hours:g} h each) assume the job does not show "
                     f"{_looked_for(template, conditions)} — that could not be checked; if it does, they are "
                     f"{override:g} h each")
    if th.per == "fixed":
        return hours
    if th.per == "hardware_point":
        return hours * sum(s.quantity or 0 for s in printed if s.hardware)
    if th.per == "line":
        return hours * sum(s.quantity or 0 for s in printed)
    n = _count(bundle.families, th.of)
    if n is None:
        chosen = [f for f in bundle.families if not th.of or f.prefix in th.of]
        return 0.0 if not chosen else None
    return hours * n


# --- one system ----------------------------------------------------------------------------------------

def _review_flag(system: str, flag: str) -> ReviewItem:
    decide, _, action = flag.partition(" — ")
    m = _CATEGORY_IN_FLAG.search(decide)
    category = m.group(1) if m else ""
    return ReviewItem(system, category, decide, "", action)


def _named_template(name: str, templates) -> SystemTemplate | None:
    """A system made from a sequence heading takes the template its name matches: the name or
    one of its kinds, singular or plural, or one written whole inside it ("Ductless Split System")."""
    plain = _plain(name)
    singular = " ".join(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w
                        for w in plain.split())
    for template in templates:
        names = {_plain(n) for n in (template.name, *template.kinds)}
        if plain in names or singular in names:
            return template
    for template in templates:
        for n in (template.name, *template.kinds):
            wanted = _plain(n)
            if len(wanted.split()) >= 2 and re.search(rf"(?<![a-z0-9]){re.escape(wanted)}s?(?![a-z0-9])", singular):
                return template
    return None


def _choose_template(bundle: SystemBundle, templates) -> SystemTemplate | None:
    if bundle.existing:
        return template_for("", bundle.name, templates)
    if bundle.heading:
        named = _named_template(bundle.name, templates)
        prefixes = [f.prefix for f in bundle.families if f.prefix]
        return named or next((template_for(p, "", templates) for p in prefixes if template_for(p, "", templates)),
                             None)
    if bundle.group:
        return template_for("", bundle.name, templates) or template_for(bundle.families[0].prefix, "", templates)
    family = bundle.families[0]
    template = template_for(family.prefix, family.kind, templates)
    if template is not None and template.group and template.prefixes and family.prefix != template.prefixes[0] \
            and not (template.name.lower() == family.kind.lower()
                     or family.kind.lower() in (k.lower() for k in template.kinds)):
        return None     # a plant's member standing alone (a lone pump) is not written as the whole plant
    return template


def _headers(template: SystemTemplate, bundle: SystemBundle) -> list[str]:
    headers = []
    for family in bundle.families:
        if family.quantity is None:
            continue
        kind = template.family_names.get(family.prefix, family.kind) if bundle.group else family.kind
        text = template.header.format(n=family.quantity, kind=kind, tags=tag_list(family.tags))
        headers.append(_squash(text))
        if "{n}" not in template.header and "{tags}" not in template.header:
            break
    return headers


def _no_template(catalogue, bundle: SystemBundle, templates, judge) -> WrittenSystem:
    """A system the Master Template has no entry for: the AI writes it from the evidence when it
    can; otherwise a PENDING block waits for it, kept out of the proposal."""
    name = bundle.name
    review = [_review_flag(name, f) for f in bundle.flags]
    tags = ", ".join(tag_list(f.tags) for f in bundle.families)
    if bundle.existing:
        header = f"{name} {tags}"
        review.insert(0, ReviewItem(name, "EXISTING", f"{name} ({tags}) is marked existing — no system is written",
                                    "", "Add scope by hand if the job reuses, relocates or removes them"))
        return WrittenSystem(bundle.key, (Block(header=header),), (), tuple(review), printed=False)
    reason = _pending_reason(judge)
    if judge is not None and getattr(judge, "available", False) and hasattr(judge, "compose"):
        written, reason = _compose_system(catalogue, bundle, templates, judge, review)
        if written is not None:
            return written
    header = f"{name} — {WAITING_FOR_AI}"
    evidence = f"Tags: {tags}; {reason}"
    line = ScopeLine(name, header, 1, None, None, PENDING, 0.0, "no template", evidence, False)
    review.insert(0, ReviewItem(name, PENDING, header, evidence,
                                "Run the estimate with the AI (--ai chat or --ai api), or write the block by hand "
                                "and price it"))
    return WrittenSystem(bundle.key, (Block(header=header),), (line,), tuple(review), printed=False)


def _units_text(bundle: SystemBundle) -> str:
    parts = [(f"{f.kind} ({f.prefix}): {tag_list(f.tags)}" if f.prefix else f.kind)
             + (f" — {f.quantity} {'named in the sequence' if bundle.heading else 'scheduled'}"
                if f.quantity is not None else " — not counted yet")
             for f in bundle.families]
    return "Units: " + "; ".join(parts)


def _uncounted(bundle: SystemBundle) -> str:
    return ", ".join(f.prefix or f.kind for f in bundle.families if f.quantity is None)


def _template_named(name: str, templates) -> SystemTemplate | None:
    wanted = " ".join((name or "").split()).lower()
    return next((t for t in templates if t.name.lower() == wanted), None) if wanted else None


def _hint_hours(hint, bundle: SystemBundle, printed: list[tuple]) -> float | None:
    """The AI's suggested tech hours for the whole system. `printed` holds (text, quantity, hardware)."""
    if hint.per == "fixed":
        return hint.hours
    if hint.per == "hardware_point":
        return hint.hours * sum(q or 0 for _, q, hardware in printed if hardware)
    if hint.per == "line":
        return hint.hours * sum(q or 0 for _, q, _ in printed)
    n = _count(bundle.families, ())
    return None if n is None else hint.hours * n


def _compose_system(catalogue, bundle: SystemBundle, templates, judge,
                    review: list[ReviewItem]) -> tuple[WrittenSystem | None, str]:
    """The block the AI writes for a system with no template: every line ADDED, never surer than
    0.7, like its nearest template; the tech hours the AI suggests when they follow a real template
    (an ASSUMPTION). None, with the reason, when the AI gives no usable block."""
    name = bundle.name
    reading = _Reading(bundle, catalogue)
    kind = name if bundle.group or len(bundle.families) != 1 else bundle.families[0].kind
    prefix = bundle.families[0].prefix if bundle.families else ""
    analogs = nearest_templates(kind, prefix, templates)
    examples = examples_for([f.prefix for f in bundle.families], kind, load_bank())
    evidence = _units_text(bundle) + "\n" + _evidence_text(bundle, reading)
    composition = judge.compose(name, evidence, examples, load_house_style(), analogs)
    if composition is None:
        error = getattr(judge, "last_error", None) or "the AI gave no answer"
        return None, error if error.startswith("judgement pending") else f"judgement pending — {error}"
    _refused_review(name, composition.refused, review)
    if not composition.lines:
        return None, "the AI wrote no line that follows the house style"

    hint = composition.tech_hours
    like = _template_named(hint.like, templates) if hint is not None else None
    analog = like.name if like is not None else (analogs[0].name if analogs else None)
    source = f"written from the evidence (like {analog})" if analog else "written from the evidence"
    style = load_house_style()

    lines: list[tuple] = []          # (text, depth, quantity, confidence, evidence, hardware, counted)
    previous = 0
    for written in composition.lines:
        depth = max(1, min(written.depth, previous + 1))
        previous = depth
        quoted = _quoted(reading, written.quote)
        confidence = min(written.confidence, AI_WRITTEN_CAP)
        stated = written.quantity
        if quoted is None:
            quoted = f"“{written.quote}” — not found word for word in the job's documents"
            confidence, stated = min(confidence, DEFAULT_CONFIDENCE), None
        if style.is_trio(written.text) and not style.verb(written.text):
            quantity, counted = None, ""                 # "Map Available Points …", "AME requires …"
        else:
            quantity, counted = _ai_quantity(written.text, stated, bundle)
        lines.append((written.text, depth, quantity, confidence, f"{quoted} ({written.why})",
                      _hardware(written.text), counted))

    counted_units = bool(bundle.families) and all(f.quantity is not None for f in bundle.families)
    headers = []
    for family in bundle.families:
        if family.quantity is None:
            continue
        family_kind = composition.header if len(bundle.families) == 1 and composition.header else family.kind
        headers.append(_squash(f"Qty ({family.quantity}) {family_kind} {tag_list(family.tags)}"))
    is_printed = bool(headers) and counted_units
    if not headers:
        headers = [_squash(f"Qty (?) {composition.header or name} "
                           f"{', '.join(tag_list(f.tags) for f in bundle.families)}")]

    notes = []
    for note in composition.client_notes:
        if _note_is_borne_out(note, evidence):
            notes.append(note)
        else:
            review.append(ReviewItem(name, "", f"The AI suggests the client note “{note}”, but the evidence does "
                                     "not bear it out", "", "Add it by hand if it applies"))

    printed = [(text, quantity, hardware) for text, _, quantity, _, _, hardware, _ in lines]
    hours = None
    if like is not None and counted_units:
        hours = _hint_hours(hint, bundle, printed)
    items = [Item(kind="line", depth=depth, runs=(Run(text=text),), quantity=quantity)
             for text, depth, quantity, *_ in lines]
    items += [Item(kind="note", runs=(Run(text=n),)) for n in notes]
    blocks = [Block(header=h, joined=i > 0) for i, h in enumerate(headers)]
    blocks[0] = blocks[0].model_copy(update={"tech_hours": hours})
    blocks[-1] = blocks[-1].model_copy(update={"items": tuple(items)})

    category = ADDED if is_printed else PENDING
    scope_lines = [ScopeLine(name, text, depth, quantity, None, category, confidence if is_printed else 0.0,
                             source, where, is_printed)
                   for text, depth, quantity, confidence, where, _, _ in lines]
    scope_lines += [ScopeLine(name, n, 1, None, None, category, AI_OTHER if is_printed else 0.0,
                              "AI: a clarification the evidence bears out", "the job's documents", is_printed)
                    for n in notes]

    review.insert(0, ReviewItem(name, ADDED, "New system written from the evidence",
                                f"No Master Template entry; written like {analog or 'no template'}, "
                                f"{len(lines)} {'line' if len(lines) == 1 else 'lines'}", "check the wording"))
    if not counted_units:
        review.insert(0, ReviewItem(name, PENDING, f"The {_uncounted(bundle)} units could not be counted from the "
                                    "schedule, so this system is left out of the proposal",
                                    ", ".join(tag_list(f.tags) for f in bundle.families if f.quantity is None),
                                    "Count them by eye, then add the block"))
    elif like is not None and hours is not None:
        review.append(ReviewItem(name, ASSUMPTION, f"Tech hours taken from {like.name}",
                                 f"{hint.hours:g} h per {hint.per.replace('_', ' ')}, {hours:g} h in all", "confirm"))
    else:
        suggested = f"the AI suggested {hint.hours:g} h per {hint.per.replace('_', ' ')} like “{hint.like}”, " \
                    "which is not a Master Template entry" if hint is not None else "the AI suggested none"
        review.append(ReviewItem(name, "", f"No tech hours for {name} (no Master Template entry) — enter them",
                                 suggested, "Type the hours on the block's header row of the price sheet"))
    for text, _, quantity, _, _, _, counted in lines:
        if counted:
            review.append(ReviewItem(name, "", f"Check the count for “{text}”: {quantity}", counted,
                                     "A sheet can carry devices of other systems — correct the quantity if so"))
    return WrittenSystem(bundle.key, tuple(blocks), tuple(scope_lines), tuple(review), printed=is_printed,
                         template=None, tech_hours=hours), ""


def _pending_reason(judge) -> str:
    if judge is None:
        return NO_AI
    if not getattr(judge, "available", False):
        return NO_KEY
    return "judgement pending — the AI did not settle it"


def _factory(states: list[_State], lines, bundle: SystemBundle, factory: Hit) -> list[_State]:
    """The unit comes with the manufacturer's controls: the integration trio replaces the DDC controller."""
    source = f"rule: factory controls ({factory.where})"
    trio_texts = {line.text for line in lines if line.trio}
    if trio_texts:
        for s in states:
            if s.text in trio_texts and s.decided == "default":
                s.include, s.decided, s.category, s.confidence = True, "factory", CONFIRMED, 0.8
                s.source, s.evidence = source, factory.text
        return states
    ddc = [i for i, s in enumerate(states) if "ddc controller" in s.text.lower()]
    if not ddc:
        return states
    depths = _settings().get("integration_trio_depths", [1, 1, 2])
    texts = integration_trio("" if bundle.group else bundle.families[0].kind)
    made = [_State(text, depth, "per_unit" if k == 0 else "none", (), False, include=True, category=CONFIRMED,
                   confidence=0.8, source=source, evidence=factory.text, decided="factory")
            for k, (text, depth) in enumerate(zip(texts, depths))]
    kept = [s for i, s in enumerate(states) if i not in ddc]
    at = ddc[0]
    return kept[:at] + made + kept[at:]


# --- schedule columns and notes beat the template's defaults -------------------------------------------

@lru_cache(maxsize=1)
def _override_rules() -> tuple[dict, ...]:
    rules = []
    for raw in _settings().get("schedule_overrides", {}).get("rules", ()):
        rule = dict(raw)
        rule["_patterns"] = tuple(re.compile(p, re.I) for p in raw["patterns"])
        rule["_disagrees"] = tuple(re.compile(p, re.I) for p in raw.get("disagrees", ()))
        rule["_prefer"] = re.compile(raw["prefer"], re.I) if raw.get("prefer") else None
        rules.append(rule)
    return tuple(rules)


def _schedule_texts(bundle: SystemBundle) -> list[tuple[str, str, str]]:
    """(where, column, text) for each schedule cell and note of the system's units; a note has no column."""
    out = []
    for row in bundle.schedule_rows:
        label = f"{row.sheet} {row.title}" if row.sheet else row.title
        for header, cell in row.cells.items():
            if cell and _squash(cell) != row.tag:
                out.append((f"{label}, {row.tag}", header or "", cell))
    out += [("the schedule's notes", "", n) for n in dict.fromkeys((*bundle.controls_by, *bundle.schedule_notes))]
    return out


def _override_hit(rule: dict, texts) -> Hit | None:
    columns = [c.upper() for c in rule.get("columns", ())]
    for where, header, text in texts:
        if columns and not any(re.search(rf"\b{re.escape(c)}\b", header.upper()) for c in columns):
            continue
        for pattern in rule["_patterns"]:
            m = pattern.search(text)
            if m:
                if header:
                    return Hit(rule["name"], "schedule", f"{where}, {header} column", f"{header}: {_squash(text)}")
                return Hit(rule["name"], "schedule", where, _sentence(text, m.start(), m.end()))
    return None


def _use_line(states: list[_State], rule: dict, hit: Hit) -> bool:
    """Put the rule's line in, in place of the lines it replaces. False when the template has no
    place for it."""
    use = rule["use"]
    instead = [w.lower() for w in rule.get("instead_of", ())]
    target = next((s for s in states if s.text.lower() == use.lower()), None)
    if target is None and rule["_prefer"] is not None:
        target = next((s for s in states if rule["_prefer"].search(s.text)), None)
    replaced = [s for s in states if s is not target and any(w in s.text.lower() for w in instead)]
    if target is None and replaced:
        slot = replaced[0]
        target = _State(use, slot.depth, rule.get("quantity", slot.quantity_rule), slot.of, _hardware(use),
                        choice=slot.choice)
        states.insert(states.index(slot), target)
    elif target is None and rule.get("add_if_missing"):
        target = _State(use, 1, rule.get("quantity", "per_unit"), (), _hardware(use))
        states.append(target)
    if target is None:
        return False
    target.include, target.decided, target.category = True, "override", CONFIRMED
    target.confidence, target.listed = _RULE_CONFIDENCE["schedule"], False
    target.source, target.evidence = f"schedule: {rule['name']} ({hit.where})", hit.text
    if "quantity" in rule:
        target.quantity_rule = rule["quantity"]
    out = replaced + [s for s in states if target.choice and s.choice == target.choice and s is not target]
    for s in out:
        s.include, s.category, s.decided, s.listed = False, "", "override", False
        s.words = f"the schedule decides it: {hit.text}"
    return True


def _apply_overrides(states: list[_State], lines, bundle: SystemBundle, name: str,
                     review: list[ReviewItem]) -> tuple[list[_State], list[tuple]]:
    """What the unit's schedule columns and notes say, applied over the template's defaults and
    rules. Returns the states and the client notes the rules add."""
    texts = _schedule_texts(bundle)
    notes: list[tuple] = []
    for rule in _override_rules():
        hit = _override_hit(rule, texts)
        if hit is None:
            continue
        if rule.get("trio"):
            states = _factory(states, lines, bundle, hit)
            for s in states:
                if s.decided == "factory":
                    s.decided = "override"
        if rule.get("use") and not _use_line(states, rule, hit):
            continue
        if rule.get("note"):
            notes.append((rule["note"], CONFIRMED, _RULE_CONFIDENCE["schedule"], f"schedule: {rule['name']}",
                          hit.text))
        for passage in bundle.passages:
            m = next((m for p in rule["_disagrees"] for m in [p.search(passage.text)] if m), None)
            if m:
                review.append(ReviewItem(
                    name, "CONFLICT", f"The schedule and the sequence disagree ({rule['name']}) — the schedule's "
                    "reading is kept", f"{hit.text} vs {passage.where}: “{_sentence(passage.text, m.start(), m.end())}”",
                    "Check with the engineer; change the block if the sequence is right"))
                break
    return states, notes


def _follow_parents(states: list[_State]) -> None:
    """A sub-line is printed only under a printed line; under a PENDING line it is PENDING too."""
    last_at: dict[int, _State] = {}
    for s in states:
        if s.depth > 1:
            parent = last_at.get(s.depth - 1)
            if parent is None or not parent.include:
                parent_pending = parent is not None and parent.category == PENDING
                if s.include or s.category == PENDING or s.listed:
                    s.include, s.listed = False, False
                    s.category = PENDING if parent_pending else ""
                    if parent_pending:
                        s.decided, s.evidence = "pending", f"The line above it ({parent.text}) is PENDING"
        last_at[s.depth] = s
        for deeper in [d for d in last_at if d > s.depth]:
            del last_at[deeper]


def write_system(catalogue, bundle: SystemBundle, templates, judge=None) -> WrittenSystem:
    template = _choose_template(bundle, templates)
    if template is None:
        return _no_template(catalogue, bundle, templates, judge)
    name = bundle.name
    reading = _Reading(bundle, catalogue, template)
    review: list[ReviewItem] = [_review_flag(name, f) for f in bundle.flags]
    pending_reason = _pending_reason(judge)

    present = {f.prefix for f in bundle.families}
    lines = [line for line in template.lines if not line.of or present & set(line.of)]
    states = [_decide(line, template, reading, pending_reason) for line in lines]
    _choose(states)
    factory = reading.factory_controls(_settings()["factory_controls"]["words"])
    if factory is not None:
        states = _factory(states, lines, bundle, factory)
    states, schedule_notes = _apply_overrides(states, lines, bundle, name, review)

    ai_notes: list[str] = []
    if judge is not None:
        evidence = _evidence_text(bundle, reading)
        judgement = judge.judge(template.name, evidence, list(dict.fromkeys(s.text for s in states)),
                                _rules_text(template))
        if judgement is None:
            error = getattr(judge, "last_error", None) or "the AI gave no answer"
            reason = error if error.startswith("judgement pending") else f"judgement pending — {error}"
            for s in states:
                if s.decided == "pending":
                    s.evidence = s.evidence.replace(pending_reason, reason)
        else:
            _apply_ai(states, judgement, reading, name, review)
            _extra_lines(states, judgement, reading, name, review)
            for note in judgement.client_notes:
                if _note_is_borne_out(note, evidence):
                    ai_notes.append(note)
                else:
                    review.append(ReviewItem(name, "", f"The AI suggests the client note “{note}”, but the "
                                             "evidence does not bear it out", "", "Add it by hand if it applies"))

    for s in states:
        _quantity(s, bundle)
        if s.include and s.quantity is None and s.quantity_rule in ("per_unit", "counted", "ai"):
            s.include, s.category, s.confidence, s.decided = False, PENDING, 0.0, "pending"
            s.evidence = (s.evidence + "; " if s.evidence else "") + "the number of units could not be counted"
    _follow_parents(states)

    printed = [s for s in states if s.include]
    counted_units = all(f.quantity is not None for f in bundle.families)
    hour_notes: list[str] = []
    parts = [_hours_of(th, template, reading, bundle, printed, hour_notes)
             for th in (template.tech_hours, *template.extra_tech_hours)]
    hours = None if any(p is None for p in parts) else float(sum(parts))

    # The client notes: the template's own, then the AI's that the evidence bears out.
    notes = [(n, ASSUMPTION, DEFAULT_CONFIDENCE, "Master Template note", "Master Template note")
             for n in template.client_notes]
    notes += [note for note in schedule_notes if note[0] not in template.client_notes]
    have = {n for n, *_ in notes}
    notes += [(n, ADDED, AI_OTHER, "AI: a clarification the evidence bears out", "the job's documents")
              for n in ai_notes if n not in have]

    headers = _headers(template, bundle)
    is_printed = bool(headers) and counted_units
    if not headers:
        headers = [_squash(f"Qty (?) {name} {', '.join(tag_list(f.tags) for f in bundle.families)}")]
    items = [Item(kind="line", depth=s.depth, runs=(Run(text=s.text),), quantity=s.quantity) for s in printed]
    items += [Item(kind="note", runs=(Run(text=n),)) for n, *_ in notes]
    blocks = [Block(header=h, joined=i > 0) for i, h in enumerate(headers)]
    blocks[0] = blocks[0].model_copy(update={"tech_hours": hours})
    blocks[-1] = blocks[-1].model_copy(update={"items": tuple(items)})

    scope_lines = []
    point_hours = template.tech_hours.hours if template.tech_hours.per == "hardware_point" else None
    for s in states:
        if not (s.include or s.category == PENDING or s.listed):
            continue
        category = s.category if is_printed or not s.include else PENDING
        line_hours = (point_hours * (s.quantity or 0)
                      if s.include and point_hours is not None and s.hardware and is_printed else None)
        scope_lines.append(ScopeLine(name, s.text, s.depth, s.quantity, line_hours, category,
                                     0.0 if category == PENDING else s.confidence,
                                     s.source or "no rule decided it", s.evidence, s.include and is_printed))
    for text, category, confidence, source, where in notes:
        scope_lines.append(ScopeLine(name, text, 1, None, None, category if is_printed else PENDING,
                                     confidence if is_printed else 0.0, source, where, is_printed))

    if not counted_units:
        review.insert(0, ReviewItem(name, PENDING, f"The {_uncounted(bundle)} units could not be counted from the "
                                    "schedule, so this system is left out of the proposal",
                                    ", ".join(tag_list(f.tags) for f in bundle.families if f.quantity is None),
                                    "Count them by eye, then add the block"))
    else:
        if hours is None:
            review.append(ReviewItem(name, "", f"No tech hours in the Master Template for {template.name} — "
                                     "enter them", "", "Type the hours on the block's header row of the price sheet"))
        review += [ReviewItem(name, ASSUMPTION, note, "", "Check the tech hours") for note in hour_notes]
        for s in states:
            if s.category == PENDING and not s.include:
                review.append(ReviewItem(name, PENDING, f"Decide whether “{s.text}” is needed", s.evidence,
                                         "Add the line to the proposal if the job needs it"))
        for s in printed:
            if s.counted:
                review.append(ReviewItem(name, "", f"Check the count for “{s.text}”: {s.quantity}", s.counted,
                                         "A sheet can carry devices of other systems — correct the quantity if so"))
        defaults = [s for s in printed if s.category == ASSUMPTION]
        if defaults:
            review.append(ReviewItem(name, ASSUMPTION,
                                     f"{len(defaults)} {'line is a' if len(defaults) == 1 else 'lines are'} Master "
                                     f"Template {'default' if len(defaults) == 1 else 'defaults'} that nothing in "
                                     "the job confirms", "; ".join(s.text for s in defaults),
                                     "Keep each line the job needs; delete the rest from the proposal"))
        for partial in sorted({c.partial for c in reading.checks() if c.partial}):
            review.append(ReviewItem(name, "", f"The schedule shows this for some units only: {partial}", "",
                                     "Split the block if the units differ"))
    return WrittenSystem(bundle.key, tuple(blocks), tuple(scope_lines), tuple(review), printed=is_printed,
                         template=template.name, tech_hours=hours)



def write_systems(catalogue, reading, bundles, templates, judge) -> list[WrittenSystem]:
    """Each system written from its Master Template entry, in the bundles' order."""
    return [write_system(catalogue, bundle, templates, judge) for bundle in bundles]


# --- the job -----------------------------------------------------------------------------------------------

_FRONT_END_CONFIDENCE = {CONFIRMED: 0.8, ASSUMPTION: DEFAULT_CONFIDENCE, PENDING: 0.0}


def _front_end_system(fe, flags, evidence, header_flags) -> WrittenSystem:
    lines = tuple(ScopeLine("Front end", e.line, 1, None, None, e.status, _FRONT_END_CONFIDENCE.get(e.status, 0.5),
                            "the Spec overview" if e.status == CONFIRMED else "default",
                            f"{e.where}: “{e.quote}”" if e.quote else e.where, True) for e in evidence)
    review = [ReviewItem("Front end", PENDING if "PENDING" in f or "Name the" in f else "", *_split(f)) for f in flags]
    review += [ReviewItem("Cover page", PENDING, *_split(f)) for f in header_flags]
    defaults = [e.line for e in evidence if e.status == ASSUMPTION]
    if defaults:
        review.append(ReviewItem("Front end", ASSUMPTION, "Front-end lines that are Master Template defaults",
                                 "; ".join(defaults), "Keep each line the job needs; delete the rest"))
    return WrittenSystem("Front end", (), lines, tuple(review), printed=True, template="Front end")


def _split(flag: str) -> tuple[str, str, str]:
    decide, _, rest = flag.partition(" — ")
    return decide, rest, ""


def _empty_bundle(name: str) -> SystemBundle:
    """No unit of the system on the job: only the Spec overview can say the job calls for it."""
    return SystemBundle(key=name, name=name, families=(), schedule_rows=(), schedule_notes=(), controls_by=(),
                        notes=(), passages=(), devices=(), sheets=(), flags=())


def apply_exceptions(fe: FrontEnd, bundles, catalogue, templates
                     ) -> tuple[list[SystemBundle], list[WrittenSystem], tuple[str, ...]]:
    """A system whose template says it becomes an exception (becomes_exception_when): when the front
    end prints the template's front-end line and the job calls for the system, the system is not
    written as a block. Its template line goes into the proposal's exceptions, with a review line.

    Returns the bundles still to write, the systems put in the exceptions (no block, for the
    Evidence Package) and the exceptions' text, in the templates' order."""
    front = {item.text for item in fe.items if item.kind == "line"}
    to_write = list(bundles)
    excepted: list[WrittenSystem] = []
    exceptions: list[str] = []
    for template in templates:
        rule = template.becomes_exception_when
        if rule is None or rule.front_end_line not in front:
            continue
        mine = [b for b in to_write if _choose_template(b, templates) is template]
        hit = None
        for bundle in [*mine, _empty_bundle(template.name)]:
            check = _Reading(bundle, catalogue, template).check(rule.called_for)
            if check.state == HOLDS:
                hit = check.hit
                break
        if hit is None:
            continue
        to_write = [b for b in to_write if b not in mine]
        exceptions.append(rule.exception)
        line = ScopeLine(template.name, rule.exception, 1, None, None, CONFIRMED, _RULE_CONFIDENCE[hit.place],
                         f"rule: {rule.front_end_line} is in the front end, and the job calls for "
                         f"{template.name} ({hit.where})", hit.text, True)
        review = [ReviewItem(template.name, "", rule.review.format(where=hit.where), hit.quote, "")]
        review += [_review_flag(template.name, f) for b in mine for f in b.flags]
        key = mine[0].key if mine else template.name
        excepted.append(WrittenSystem(key, (), (line,), tuple(review), printed=True, template=template.name))
    return to_write, excepted, tuple(exceptions)


def build_job(catalogue, reading, judge, today, templates=None) -> tuple[Job, list[WrittenSystem], list[str]]:
    """The whole scope: the cover header, the front end and every system, in the proposal's order.

    Returns the Job (the client view), the written systems (the front end first, then each system,
    then any put in the exceptions instead) and the flags for the review list that belong to no
    system: families on the drawings but on no schedule."""
    templates = templates or load_templates()
    header, header_flags = job_header(catalogue, reading, today)
    fe, fe_flags, fe_evidence = front_end(catalogue)
    bundles, excepted, exceptions = apply_exceptions(fe, build_bundles(catalogue, reading), catalogue, templates)
    systems = write_systems(catalogue, reading, bundles, templates, judge) + excepted
    blocks = tuple(b for s in systems if s.printed for b in s.blocks)
    job = Job(header=header, front_end=fe, blocks=blocks, named_exceptions=exceptions)
    return job, [_front_end_system(fe, fe_flags, fe_evidence, header_flags)] + systems, unbundled_flags(reading)
