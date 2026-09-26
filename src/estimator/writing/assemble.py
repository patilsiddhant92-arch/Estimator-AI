"""The whole-job path, after the judge: cross-check the AI's plan and scope, then assemble the job.

The judge reads the whole dossier and plans every system (estimator.writing.whole_job), then
writes each planned system's scope. Nothing here decides scope. It checks:

- every planned quantity against the counts the dossier gathered (the schedule's QUANTITY column,
  the distinct tags, the placements on the plans, the riser): CONFIRMED when one agrees or the
  quote states it, DISCREPANCY with both numbers when the counts disagree, PENDING when the plan
  gives none. The AI's number is never changed silently;
- every family on the drawings that no planned system covers (listed, never silently added);
- every written line for its quote (in the dossier, word for word or nearly), the house style, and
  the words the client must never see;
- each scope against its Master Template entry, as a checklist: lines usually present that the AI
  left out are listed;
- the tech hours: the Master Template's rule when it fits the kind, else the AI's suggestion as an
  ASSUMPTION, else none, with a review line. Never invented.

And it never loses a planned system: a header too long for a block is shortened (or stacked, one
header per family), a system with no quantity is printed "Qty (##)" with the count to give at the top
of the review list, and a system whose lines were all refused is printed with the Master Template's
lines, marked ASSUMPTION. The review list is ranked, the most urgent first, and repeated rows merged.

The shapes it reads are the plan's (docs/superpowers/plans/2026-09-26-whole-job-writing.md): a
Dossier (text, images, sources, families, device_totals, counts), a JobPlan of PlannedSystems and
a WrittenScope of WrittenLines per system. They are read by their field names only.
"""
from __future__ import annotations

import dataclasses
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from typing import NamedTuple

from estimator.scope import Alternate, Block, Item, Job, Run
from estimator.writing.front_end import (FRONT_END_FILE, _load as _front_end_data, extended_warranty_block,
                                         front_end, global_points_block, job_header)
from estimator.writing.judge import MAX_HEADER
from estimator.writing.phrasing import examples_for, load_bank
from estimator.writing.style import load_house_style
from estimator.writing.templates import load_templates, nearest_templates, template_for
from estimator.writing.write import (ADDED, ASSUMPTION, CONFIRMED, PENDING, ReviewItem, ScopeLine, WrittenSystem,
                                     _front_end_system, _hardware, _note_is_borne_out, _word, tag_list)

DISCREPANCY = "DISCREPANCY"
SOURCE = "AI (whole job)"
UNSOURCED_CONFIDENCE = 0.4    # a planned system that cites no source: still written, never surer than this
UNQUOTED_CAP = 0.5            # a line whose quote is not in the dossier
PICTURE_CAP = 0.7             # a quote the judge read off a picture (I1, I2 …): it cannot be machine-checked
COUNT_TO_FILL = "##"          # "Qty (##)": the house form of a count still to be filled
FALLBACK = "System written with fallback lines — check"
MAX_FRONT_END_LINES = 12      # the front end's lines (under each, its own sub-lines); the rest go to the review
NEAR_DUPLICATE = 0.6          # a plan front-end line sharing this share of its words with a line already there
CONTROLS_TRADES = ("Mechanical", "Controls")     # a schedule on these sheets is the controls trade's
# How urgent a review row is: the order of the ranked review list.
TIER_FIRST, TIER_DISCREPANCY, TIER_QUESTION, TIER_DISAGREE, TIER_REST = 1, 2, 3, 4, 5
QUOTE_SHARE = 0.6             # of the quote's words, in order, that must be in the dossier
SHORT_QUOTE = 3               # a quote of this many words or fewer must be there word for word
_COUNT_LABELS = (("quantity_column", "the schedule's QUANTITY column"), ("distinct_tags", "distinct tags"),
                 ("plan_placements", "placements on the plans"), ("riser", "the riser"))
_COUNT_COLUMNS = ("schedule_rows", "quantity_column", "distinct_tags", "plan_placements", "riser")
_NUMBER_WORDS = {w: n for n, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen twenty".split())}
_ID = re.compile(r"\[?\s*([A-Z]{1,3}\d+)\s*\]?")
_NEVER = re.compile(r"\$|\bhours?\b|\bhrs?\b|confidence|\brule:|\bAI:", re.I)


def _squash(text: str) -> str:
    return " ".join((text or "").split())


def _plain(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").casefold()).strip()


# --- tags and source ids ----------------------------------------------------------------------------

def _stem(tag: str) -> str:
    cut = max(tag.rfind("-"), tag.rfind("."))
    return tag[:cut + 1] if cut > 0 else ""


def expand_tags(tags) -> list[str]:
    """Every tag, one by one: "VAV-101 thru VAV-112, VAV-114", "RTU-1 thru 3", "AHU-1, 2, 3" or a
    tuple of such pieces."""
    items = [tags] if isinstance(tags, str) else list(tags or ())
    out: list[str] = []
    stem = ""
    for item in items:
        for part in (p.strip() for p in str(item).split(",")):
            if not part:
                continue
            m = re.match(r"^(.+?)\s+thru\s+(.+)$", part, re.I)
            first, last = (m.group(1).strip(), m.group(2).strip()) if m else (part, None)
            if stem and re.fullmatch(r"\d+[A-Za-z]?", first):
                first = stem + first
            stem = _stem(first)
            if last is None:
                out.append(first)
                continue
            if re.fullmatch(r"\d+[A-Za-z]?", last):
                last = stem + last
            a, b = re.match(r"^(.*?)(\d+)$", first), re.match(r"^(.*?)(\d+)$", last)
            if a and b and a.group(1) == b.group(1) and 0 <= int(b.group(2)) - int(a.group(2)) <= 1000:
                width = len(a.group(2)) if a.group(2).startswith("0") else 0
                out += [f"{a.group(1)}{str(k).zfill(width)}" for k in range(int(a.group(2)), int(b.group(2)) + 1)]
            else:
                out += [first, last]
    return list(dict.fromkeys(out))


def _tag_prefix(tag: str) -> str:
    m = re.match(r"[A-Za-z]+", tag or "")
    return m.group(0).upper() if m else ""


def source_ids(*values) -> list[str]:
    """The source ids in "[S41]", "S41", or a tuple of them, in order, each once."""
    ids: list[str] = []
    for value in values:
        for piece in ([value] if isinstance(value, str) else list(value or ())):
            ids += [m.group(1) for m in _ID.finditer(str(piece))]
    return list(dict.fromkeys(ids))


def _system_ids(system) -> list[str]:
    return source_ids(system.quantity_source, system.sequence_sources, system.schedule_sources)


def cited_text(dossier, source_id: str) -> str:
    """The dossier's paragraph or row that carries `[source_id]`: from the id to the next blank line
    or the next line that starts with an id. "" when the text does not carry it."""
    text = dossier.text or ""
    at = text.find(f"[{source_id}]")
    if at < 0:
        return ""
    end = len(text)
    blank = re.search(r"\n\s*\n", text[at:])
    if blank:
        end = at + blank.start()
    nxt = re.search(r"\n\s*\[[A-Z]{1,3}\d+\]", text[at:end])
    if nxt:
        end = at + nxt.start()
    return text[at:end].strip()[:4000]


# --- the quote check ------------------------------------------------------------------------------------

def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").casefold())


class _Index:
    """The dossier's words, for finding a quote: whitespace and punctuation ignored."""

    def __init__(self, text: str):
        self.words = _tokens(text)
        self.joined = " " + " ".join(self.words) + " "
        self.at: dict[str, list[int]] = defaultdict(list)
        for i, w in enumerate(self.words):
            self.at[w].append(i)

    def holds(self, quote: str, share: float = QUOTE_SHARE) -> bool:
        wanted = _tokens(quote)[:60]
        if not wanted:
            return False
        if " " + " ".join(wanted) + " " in self.joined:
            return True
        if len(wanted) <= SHORT_QUOTE:
            return False
        need = math.ceil(share * len(wanted))
        present = [w for w in dict.fromkeys(wanted) if w in self.at]
        anchors = sorted(present, key=lambda w: len(self.at[w]))[:3]
        n = len(wanted)
        for word in anchors:
            for pos in self.at[word][:300]:
                window = self.words[max(0, pos - 2 * n): pos + 2 * n]
                if _in_order(wanted, window) >= need:
                    return True
        return False


def _in_order(a: list[str], b: list[str]) -> int:
    """How many of a's words appear in b in the same order (the longest common subsequence)."""
    previous = [0] * (len(b) + 1)
    for x in a:
        current = [0]
        for j, y in enumerate(b):
            current.append(previous[j] + 1 if x == y else max(previous[j + 1], current[j]))
        previous = current
    return previous[-1]


@lru_cache(maxsize=4)
def _index(text: str) -> _Index:
    return _Index(text)


def quote_in_dossier(quote: str, dossier) -> bool:
    return _index(dossier.text or "").holds(quote)


def _states(quote: str, n: int) -> bool:
    """The quote states the number n (as digits or a word)."""
    if re.search(rf"(?<![\w.-]){n}(?![\d.])", quote or ""):
        return True
    return any(_NUMBER_WORDS.get(w) == n for w in _tokens(quote))


# --- C1: the plan against the counts ----------------------------------------------------------------------

@dataclass(frozen=True)
class PlanCheck:
    """One planned system, checked: its quantity's category, the counts it was checked against,
    and the review lines."""
    system: object                 # the PlannedSystem
    category: str                  # CONFIRMED | DISCREPANCY | ASSUMPTION | PENDING
    counts: dict                   # label -> n: the counts the quantity was checked against
    columns: dict                  # the dossier's counts for the system's families, summed (for the Plan tab)
    quote_found: bool
    sourced: bool                  # the plan cites at least one source id for it
    where: str                     # where its quantity source is, in words
    review: tuple[ReviewItem, ...]

    @property
    def goes(self) -> str:
        s = self.system
        if s.exception:
            return "the exceptions"
        if s.alternate in ("add", "deduct"):
            return f"{s.alternate} alternate" + (", Qty (##)" if self.category == PENDING else "")
        if self.category == PENDING:
            return "the base bid, Qty (##)"
        return "the base bid"


def _families(dossier) -> list[tuple[object, set[str]]]:
    return [(f, {t.upper() for t in expand_tags(getattr(f, "tags", "") or "")}) for f in dossier.families or ()]


def _name(system) -> str:
    return _squash(re.sub(r"^\s*Qty\s*\([^)]*\)\s*", "", system.header or "")) or system.key


def _counts_for(system, dossier) -> tuple[dict, dict]:
    """(label -> n to check the quantity against, column -> n summed for the Plan tab)."""
    tags = {t.upper() for t in expand_tags(system.tags)}
    if not tags:
        return {}, {}
    families = _families(dossier)
    touched = [(f, own) for f, own in families if own & tags]
    known = set().union(*(own for _, own in families)) if families else set()
    prefixes = [f.prefix.upper() for f, _ in touched]
    prefixes += [p for p in dict.fromkeys(_tag_prefix(t) for t in tags - known)
                 if p and p not in prefixes and p in {k.upper() for k in (dossier.counts or {})}]
    counts = {k.upper(): v for k, v in (dossier.counts or {}).items()}
    columns = {}
    for column in _COUNT_COLUMNS:
        values = [counts.get(p, {}).get(column) for p in prefixes]
        if values and all(isinstance(v, int) for v in values):
            columns[column] = sum(values)
    subset = any(not own <= tags for _, own in touched)
    if subset:
        mine = len(tags & known)
        return ({"its own tags on the schedule": mine} if mine else {}), columns
    return {label: columns[key] for key, label in _COUNT_LABELS if key in columns}, columns


def _counts_text(counts: dict) -> str:
    return ", ".join(f"{n} by {label}" for label, n in counts.items()) or "no count"


def _one_per_type(q: int, counts: dict, columns: dict) -> bool:
    """The quantity agrees only with the distinct tags, but the schedule's QUANTITY column counts more:
    a type row counted as one unit, when it is that many."""
    column = columns.get("quantity_column")
    agree = [label for label, n in counts.items() if n == q]
    return column is not None and column != q and agree == ["distinct tags"]


def _is_picture(source_id: str, dossier) -> bool:
    """The id is one of the dossier's pictures (I1 … In): what the judge read there cannot be machine-checked."""
    m = re.fullmatch(r"I(\d+)", source_id or "")
    return bool(m) and 1 <= int(m.group(1)) <= len(dossier.images or ())


def _check_system(system, dossier) -> PlanCheck:
    name = _name(system)
    counts, columns = _counts_for(system, dossier)
    ids = _system_ids(system)
    sourced = bool(ids)
    qid = (source_ids(system.quantity_source) or [""])[0]
    where = (dossier.sources or {}).get(qid, "") if qid else ""
    quote = system.quantity_quote or ""
    found = bool(quote) and (quote_in_dossier(quote, dossier) or _is_picture(qid, dossier))
    quoted = f"{where + ': ' if where else ''}“{quote}”" if quote else "no quote"
    review: list[ReviewItem] = []
    q = system.quantity
    if q is None:
        category = PENDING
        if not system.exception:
            review.append(ReviewItem(name, PENDING, f"Give the count for {shape_header(system, None).headers[0]}",
                                     f"The plan gives no quantity. The counts: {_counts_text(counts)}. The plan says: "
                                     f"{system.why or 'nothing'}", "Count the units and type the count in the header",
                                     tier=TIER_FIRST))
    elif counts and q in counts.values() and not _one_per_type(q, counts, columns):
        category = CONFIRMED
    elif counts:
        category = DISCREPANCY
        stated = " (its quote states it)" if found and _states(quote, q) else ""
        review.append(ReviewItem(name, DISCREPANCY, f"The plan counts {q} for {name}{stated}; the counts disagree: "
                                 f"{_counts_text(counts)}", quoted,
                                 "The plan's number is kept — correct it if one of the counts is right"))
    elif found and _states(quote, q):
        category = CONFIRMED
    else:
        category = ASSUMPTION
        why = "its quote is not in the job's documents" if quote and not found else "its quote does not state it"
        review.append(ReviewItem(name, ASSUMPTION, f"The plan counts {q} for {name}, with no count to check it "
                                 f"against, and {why}", quoted, "Confirm the count"))
    if not sourced:
        review.append(ReviewItem(name, "", f"The plan cites no source for {name} — it is written, but check every "
                                 "line", system.why or "", "Check the block against the drawings and the sequence"))
    return PlanCheck(system, category, counts, columns, found, sourced, where, tuple(review))


def _existing(reading) -> set[str]:
    return {i.tag.upper() for i in getattr(reading, "inventory", ()) or () if i.category == "EXISTING"}


_OTHER_TRADE = re.compile(r"\b(?:plumbing|electrical|fire\s+protection|sprinkler|lighting|architectural)\b", re.I)


def _on_controls_schedule(prefix: str, reading, catalogue) -> bool:
    """A schedule row of the family on a controls-trade sheet (mechanical or controls). Without the
    sheet's discipline, the schedule's title decides: a plumbing or electrical schedule is another trade's."""
    disciplines = {(s.document, s.page): s.discipline for s in getattr(catalogue, "sheets", ()) or ()}
    for schedule in getattr(reading, "schedules", ()) or ():
        if not any(_tag_prefix(getattr(row, "tag", "") or "") == prefix for row in schedule.rows):
            continue
        discipline = disciplines.get((schedule.document, schedule.page))
        if discipline in CONTROLS_TRADES or (discipline is None and not _OTHER_TRADE.search(schedule.title or "")):
            return True
    return False


def _reading_noise(family, dossier, reading, catalogue) -> bool:
    """A family the reading found only as model numbers (B, CT, AS …) or only on another trade's schedule:
    no placement on the plans and no row on a controls-trade schedule."""
    prefix = family.prefix.upper()
    counts = {k.upper(): v for k, v in (dossier.counts or {}).items()}.get(prefix) or {}
    if (counts.get("plan_placements") or 0) > 0:
        return False
    return not _on_controls_schedule(prefix, reading, catalogue)


def _uncovered(plan, dossier, reading, catalogue=None) -> list[ReviewItem]:
    planned = {t.upper() for s in plan.systems for t in expand_tags(s.tags)}
    prefixes = {_tag_prefix(t) for t in planned}
    kinds = {_plain(s.kind) for s in plan.systems}
    existing = _existing(reading)
    missed = []
    for family, own in _families(dossier):
        if _reading_noise(family, dossier, reading, catalogue):
            continue
        if not own:
            if family.prefix.upper() not in prefixes and _plain(family.kind) not in kinds:
                missed.append(f"{family.kind} ({family.prefix})")
            continue
        left = [t for t in expand_tags(family.tags) if t.upper() not in planned and t.upper() not in existing]
        if left:
            missed.append(f"{family.kind} {tag_list(left)}")
    if not missed:
        return []
    return [ReviewItem("The plan", DISCREPANCY, "Equipment on the drawings the plan didn't write: " + "; ".join(missed),
                       "On the schedules, but in no planned system", "Add a block for each the job needs")]


def plan_checks(plan, dossier, reading, catalogue=None) -> tuple[list[PlanCheck], list[ReviewItem]]:
    """Each planned system checked, in the plan's order, and the review lines that belong to no
    system (families the plan didn't write; `catalogue` gives the schedules' trades)."""
    return [_check_system(s, dossier) for s in plan.systems], _uncovered(plan, dossier, reading, catalogue)


def check_plan(plan, dossier, reading, catalogue=None) -> list[ReviewItem]:
    """Every review line the plan's cross-checks give: each system's quantity (CONFIRMED needs none,
    DISCREPANCY, ASSUMPTION, PENDING), a system with no source, and the families not written."""
    checks, general = plan_checks(plan, dossier, reading, catalogue)
    return [item for c in checks for item in c.review] + general


# --- C1: the scope against its quotes, the house style and the Master Template --------------------------------

@dataclass(frozen=True)
class CheckedLine:
    text: str
    depth: int
    quantity: int | None     # the count the quote states; None when it states none (the writer counts per unit)
    quote: str
    source_id: str
    why: str
    confidence: float
    quoted: bool             # the quote is in the dossier


def system_template(system, templates=None):
    """The Master Template entry that fits the system's kind (or its tag prefix); None when none fits."""
    templates = templates if templates is not None else load_templates()
    tags = expand_tags(system.tags)
    prefix = _tag_prefix(tags[0]) if tags else ""
    return template_for(prefix, system.kind or "", templates)


def system_evidence(system, dossier) -> str:
    """What the judge reads to write one planned system: the units, the counts, the devices on the
    plans, and every dossier paragraph the plan cited."""
    tags = expand_tags(system.tags)
    parts = [f"System: {_name(system)} ({system.kind})",
             f"Tags: {tag_list(tags) if tags else 'none'}",
             f"Planned quantity: {system.quantity if system.quantity is not None else 'not stated'}"
             + (f" — {system.quantity_source} “{system.quantity_quote}”" if system.quantity_quote else "")]
    prefixes = list(dict.fromkeys(_tag_prefix(t) for t in tags))
    counts = {k.upper(): v for k, v in (dossier.counts or {}).items()}
    for p in prefixes:
        if p in counts:
            shown = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in counts[p].items() if v is not None)
            parts.append(f"Counts for {p}: {shown}")
    if dossier.device_totals:
        parts.append("Devices counted on the plans (whole job): "
                     + "; ".join(f"{label}: {n}" for label, n in dossier.device_totals.items()))
    for sid in _system_ids(system):
        where = (dossier.sources or {}).get(sid, "")
        body = cited_text(dossier, sid)
        parts.append(f"[{sid}] {where}\n{body}" if body else f"[{sid}] {where}")
    return "\n".join(parts)


def _holds(condition, evidence: str) -> bool:
    words = [w for place in ("schedule", "sequence", "notes", "prefix", "spec_overview")
             for w in getattr(condition, place)]
    return any(_word(w).search(evidence) for w in words)


def _left_out(template, kept, system, evidence: str) -> list[str]:
    """The Master Template's lines usually present for this system that the scope leaves out: its
    defaults, and a line whose conditions the evidence names."""
    have = {_plain(line.text) for line in kept}
    prefixes = {_tag_prefix(t) for t in expand_tags(system.tags)}
    missing, groups = [], set()
    for line in template.lines:
        if line.of and not prefixes & set(line.of):
            continue
        if "{" in line.text:
            continue
        if any(_holds(template.conditions[n], evidence) for n in line.unless):
            continue
        if line.choice:
            if line.choice in groups:
                continue
            groups.add(line.choice)
            members = [m for m in template.lines if m.choice == line.choice]
            if not any(_plain(m.text) in have for m in members):
                missing.append(" or ".join(m.text for m in members))
            continue
        expected = (all(_holds(template.conditions[n], evidence) for n in line.when) if line.when
                    else line.default)
        if expected and _plain(line.text) not in have:
            missing.append(line.text)
    return missing


def check_scope(system, scope, dossier, templates=None, style=None, sourced: bool = True
                ) -> tuple[list[CheckedLine], list[ReviewItem]]:
    """The lines kept, and the review. A line naming prices, hours, confidence or a category word,
    or breaking the house style, is dropped and listed. A line whose quote is not in the dossier is
    kept at confidence 0.5 at most, with a review line; a quote the judge read off a picture (its
    source is an image id) is accepted at 0.7 at most; every line of a system the plan cites no
    source for, at 0.4 at most. The Master Template's lines usually present that the AI left out
    are listed."""
    style = style or load_house_style()
    name = _name(system)
    review: list[ReviewItem] = []
    kept: list[CheckedLine] = []
    dropped: list[str] = []
    previous = 0
    for line in scope.lines:
        text = _squash(line.text)
        problem = ("it names prices, hours, confidence or the tool's own words" if _NEVER.search(text)
                   else style.check_line(text, line.depth))
        if problem:
            dropped.append(f"“{text}” ({problem})")
            continue
        depth = max(1, min(int(line.depth or 1), previous + 1))
        previous = depth
        quote = line.quote or ""
        sid = (source_ids(getattr(line, "source_id", "") or "") or [""])[0]
        picture = _is_picture(sid, dossier)
        quoted = bool(quote) and (picture or quote_in_dossier(quote, dossier))
        confidence = max(0.0, min(float(line.confidence or 0.0), 1.0))
        if picture:
            confidence = min(confidence, PICTURE_CAP)
        quantity = line.quantity
        if not quoted:
            confidence, quantity = min(confidence, UNQUOTED_CAP), None
            review.append(ReviewItem(name, "", f"The quote for “{text}” is not in the job's documents",
                                     f"“{quote}”" if quote else "no quote", "Check the line by hand"))
        if not sourced:
            confidence = min(confidence, UNSOURCED_CONFIDENCE)
        kept.append(CheckedLine(text, depth, quantity, quote, sid, line.why or "", confidence, quoted))
    dropped += [_squash(str(r)) for r in getattr(scope, "refused", ()) or ()]     # thrown away by the judge
    if dropped:
        review.append(ReviewItem(name, "", "The AI wrote lines the client must never see, or that break the house "
                                 "style; they were dropped", "; ".join(dropped), "Nothing to do unless a line is missing"))
    template = system_template(system, templates)
    if template is not None:
        missing = _left_out(template, kept, system, system_evidence(system, dossier))
        if missing:
            review.append(ReviewItem(name, "", f"Usually present in the Master Template's {template.name}; the AI left "
                                     "out: " + "; ".join(missing), "", "Add any line the job needs"))
    for note in getattr(scope, "review_notes", ()) or ():
        review.append(ReviewItem(name, "", _squash(note), "the AI's note", ""))
    return kept, review


# --- C1: tech hours -------------------------------------------------------------------------------------------

def _hours(per: str, hours: float, of, quantity: int | None, lines, prefixes) -> float | None:
    if per == "fixed":
        return hours
    if per == "hardware_point":
        return hours * sum(q or 0 for text, q in lines if _hardware(text))
    if per == "line":
        return hours * sum(q or 0 for _, q in lines)
    if of and not prefixes & set(of):
        return 0.0
    return None if quantity is None else hours * quantity


def tech_hours(system, quantity: int | None, lines, hint, templates=None, evidence: str = ""
               ) -> tuple[float | None, ReviewItem | None]:
    """The system's tech hours and the review line they need. `lines` holds (text, quantity) of the
    printed lines. The Master Template's rule when it fits the kind; else the AI's suggestion, an
    ASSUMPTION; else None, with a review line to enter them."""
    name = _name(system)
    prefixes = {_tag_prefix(t) for t in expand_tags(system.tags)}
    template = system_template(system, templates)
    if template is not None and template.tech_hours.hours is not None:
        parts = []
        for th in (template.tech_hours, *template.extra_tech_hours):
            hours = th.hours
            for conditions, override in th.overrides:
                if all(_holds(template.conditions[c], evidence) for c in conditions):
                    hours = override
                    break
            parts.append(None if hours is None else _hours(th.per, hours, th.of, quantity, lines, prefixes))
        if all(p is not None for p in parts):
            return float(sum(parts)), None
    if hint is not None and getattr(hint, "hours", None) is not None:
        total = _hours(hint.per, float(hint.hours), (), quantity, lines, prefixes)
        if total is not None:
            return total, ReviewItem(name, ASSUMPTION, "Tech hours are the AI's suggestion",
                                     f"{hint.hours:g} h per {str(hint.per).replace('_', ' ')}"
                                     + (f", like {hint.like}" if getattr(hint, "like", "") else "")
                                     + f", {total:g} h in all", "Confirm them")
    return None, ReviewItem(name, "", f"No tech hours for {name} — enter them",
                            "No Master Template rule fits it" + ("" if hint is None else ", and the AI's suggestion "
                                                                 "could not be counted"),
                            "Type the hours on the block's header row of the price sheet")


# --- what the judge is asked --------------------------------------------------------------------------------

def checklist_text(templates=None) -> str:
    """The Master Template's systems, one line each on when they apply, for the plan's prompt."""
    templates = templates if templates is not None else load_templates()
    lines = []
    for t in templates:
        applies = []
        if t.prefixes:
            applies.append("tags " + ", ".join(t.prefixes))
        if t.kinds:
            applies.append("also called " + ", ".join(t.kinds))
        hint = next((_squash(h).lstrip("*( ").rstrip(")") for h in t.hints
                     if h.strip() and not re.search(r"tech hour|\bhours?\b", h, re.I)), "")
        lines.append(f"- {t.name}" + (f" ({'; '.join(applies)})" if applies else "") + (f": {hint}" if hint else ""))
    return "\n".join(lines)


def template_options(system, templates=None) -> list[str]:
    """The nearest Master Template entry's lines, as a checklist of what is usually present."""
    templates = templates if templates is not None else load_templates()
    template = system_template(system, templates)
    if template is None:
        tags = expand_tags(system.tags)
        near = nearest_templates(system.kind or _name(system), _tag_prefix(tags[0]) if tags else "", templates, k=1)
        template = near[0] if near else None
    if template is None:
        return []
    return list(dict.fromkeys(line.text for line in template.lines))


def system_examples(system) -> list[dict]:
    """Blocks from past proposals for the same prefix or kind (up to 4)."""
    prefixes = list(dict.fromkeys(_tag_prefix(t) for t in expand_tags(system.tags)))
    return examples_for(prefixes, system.kind or _name(system), load_bank())


def system_images(system, dossier) -> list:
    """The dossier's pictures the plan cites for this system ("I3" is the third)."""
    images = list(dossier.images or ())
    wanted = [sid for sid in _system_ids(system) if sid.startswith("I")]
    for sid in _system_ids(system):
        wanted += re.findall(r"\bimage (I\d+)", cited_text(dossier, sid))
    out = []
    for sid in dict.fromkeys(wanted):
        n = int(sid[1:])
        if 1 <= n <= len(images) and images[n - 1] not in out:
            out.append(images[n - 1])
    return out


# --- C2: the block header: never too long, never a pipe ---------------------------------------------------------

_TAG = r"[A-Z]{1,6}(?:-[A-Z0-9]+(?:\.\d+)?)+"
_TAG_RUN = re.compile(rf"(?<![A-Za-z0-9-])({_TAG}(?:\s*(?:,|&|\band\b|\bthru\b)\s*"
                      rf"(?:{_TAG}|\d+(?:\.\d+)?[A-Z]?)(?![A-Za-z0-9-]))*)")


class HeaderShape(NamedTuple):
    """How a planned system's header is printed: one header, or several stacked (one per family),
    each with its count, and the descriptors taken out of a header too long, as a note for the block's
    first line ("" when none)."""
    headers: tuple[str, ...]
    quantities: tuple
    note: str


def _named_tags(text: str) -> list[str]:
    """The equipment tags a text names ("UH-1 thru 6", "RTU-4, 5", "RTU-3 only"), one by one, in capitals."""
    out: list[str] = []
    for m in _TAG_RUN.finditer(text or ""):
        out += expand_tags(re.sub(r"\s*(?:&|\band\b)\s*", ", ", m.group(1)))
    return list(dict.fromkeys(t.upper() for t in out))


def _base_name(system) -> str:
    """The plan's header without its count, with the tags when it names none."""
    base = _name(system)
    tags = expand_tags(system.tags)
    if tags and not any(t.upper() in base.upper() for t in (tags[0], *system.tags[:1])):
        base = f"{base} {tag_list(tags)}"
    return base


def _count(quantity) -> str:
    return COUNT_TO_FILL if quantity is None else str(quantity)


def _split_kind(name: str) -> tuple[str, str]:
    """(the words before the first tag, the rest)."""
    m = _TAG_RUN.search(name)
    if m is None:
        return name, ""
    return name[:m.start()].strip(" -–,"), name[m.start():]


def _strip_descriptors(name: str) -> tuple[str, list[str]]:
    """The header without the words after " w/ " and without its brackets, and what was taken out."""
    found = []
    m = re.search(r"\s+w/\s*(.+)$", name, re.I)
    if m:
        found.append(m.group(1).strip())
        name = name[:m.start()]
    found += [p.strip() for p in re.findall(r"\(([^()]*)\)", name)]
    name = re.sub(r"\s*\([^()]*\)", "", name)
    return _squash(name).strip(" -–,"), [f for f in found if f]


def _by_family(kind: str, tags: list[str], quantity) -> list[tuple[str, object]]:
    """One header per family, stacked: the tags grouped by prefix (then by stem, when one prefix is too
    long for a header), packed while a header fits; a group too long alone is cut."""
    def fits(chunk):
        return len(f"{kind} {tag_list(chunk)}") <= MAX_HEADER

    def runs(seq, key):
        out: list[list[str]] = []
        for tag in seq:
            if out and key(out[-1][-1]).upper() == key(tag).upper():
                out[-1].append(tag)
            else:
                out.append([tag])
        return out

    groups: list[list[str]] = []
    for family in runs(tags, _tag_prefix):
        groups += [family] if fits(family) else runs(family, _stem)
    chunks: list[list[str]] = []
    for group in groups:
        if chunks and fits(chunks[-1] + group):
            chunks[-1] += group
            continue
        current: list[str] = []
        for tag in group:
            if current and not fits(current + [tag]):
                chunks.append(current)
                current = []
            current.append(tag)
        chunks.append(current)
    return [(f"{kind} {tag_list(chunk)}", None if quantity is None else len(chunk)) for chunk in chunks]


def _fit(name: str, tags: list[str], quantity, moved: list[str]) -> list[tuple[str, object]]:
    """A header piece made to fit: the tags compacted, then the descriptors moved out, then one header per
    family. Each is (the header without its count, the count)."""
    if len(name) <= MAX_HEADER:
        return [(name, quantity)]
    kind, rest = _split_kind(name)
    if kind and tags and not _TAG_RUN.sub("", rest).strip(" ,&-–"):
        name = f"{kind} {tag_list(tags)}"
        if len(name) <= MAX_HEADER:
            return [(name, quantity)]
    stripped, found = _strip_descriptors(name)
    if found:
        moved.extend(found)
        name = stripped
        if len(name) <= MAX_HEADER:
            return [(name, quantity)]
    kind, _ = _split_kind(name)
    own = [t for t in tags if t.upper() in set(_named_tags(name))] or tags
    if kind and own:
        return _by_family(kind, own, quantity)
    cut = name[:MAX_HEADER].rsplit(" ", 1)[0]
    moved.append(name[len(cut):].strip())
    return [(cut, quantity)]


def _piece_tags(piece: str, tags: list[str]) -> list[str]:
    named = set(_named_tags(piece))
    own = [t for t in tags if t.upper() in named]
    if own:
        return own
    return [t for t in tags if re.search(rf"(?<![A-Za-z]){re.escape(_tag_prefix(t))}-", piece)]


def shape_header(system, quantity) -> HeaderShape:
    """The system's block header(s), in the house style: "Qty (3) Rooftop Unit RTU-1 thru 3", "Qty (##) …"
    when the count is still to fill. A pipe never goes in a header: two families are two stacked headers.
    A header longer than a block header drops the words after " w/ " and its brackets (they go into the
    block's first line, as a note), and when it is still too long, it is one header per family, stacked."""
    name = _base_name(system)
    tags = expand_tags(system.tags)
    pieces = [p.strip() for p in name.split("|") if p.strip()] or [name]
    headers, quantities, moved = [], [], []
    for piece in pieces:
        own = _piece_tags(piece, tags) if len(pieces) > 1 else tags
        q = len(own) if len(pieces) > 1 and own and quantity is not None else quantity
        for text, n in _fit(piece, own, q, moved):
            headers.append(_squash(f"Qty ({_count(n)}) {text}"))
            quantities.append(n)
    note = ("**Includes " + "; ".join(moved)) if moved else ""
    return HeaderShape(tuple(headers), tuple(quantities), note)


def block_header(system, quantity) -> str:
    """"Qty (3) Variable Air Volume Box VAV-1 thru 3": the system's first header."""
    return shape_header(system, quantity).headers[0]


# --- C2: a line's quantity comes from the line; the house-style polish ----------------------------------------

_QTY_IN_LINE = re.compile(r"\bQty\.?\s*\(?\s*(\d+)\s*\)?", re.I)
_LOCATION = re.compile(r"\(Location:\s*([^)]*)\)", re.I)
_ROOM_WORDS = frozenset("room rooms office garage closet lobby corridor gym gymnasium toilet restroom kitchen lab "
                        "laboratory classroom vestibule stair stairs storage laundry lounge locker shaft suite "
                        "library cafeteria auditorium hall".split())
_POINT_CODE = re.compile(r"\s*\((?:AO|DO|AI|DI|BO|BI)\)")
_AS_PER_SEQUENCE = re.compile(r"\s*\(as per sequence\)\s*$", re.I)


def _location_items(text: str) -> list[str]:
    m = _LOCATION.search(text or "")
    return [i.strip() for i in re.split(r",|&|\band\b", m.group(1)) if i.strip()] if m else []


def _is_room(item: str) -> bool:
    words = _plain(item).split()
    return bool(re.search(r"\b\d+[A-Za-z]?\b", item)) or any(w in _ROOM_WORDS for w in words)


def _rooms(text: str) -> list[str]:
    """The rooms a line lists in its "(Location: …)", when it is a list of two or more rooms."""
    items = _location_items(text)
    if len(items) < 2 or any(re.search(r"\b(?:each|all|every)\b", i, re.I) for i in items):
        return []
    return items if all(_is_room(i) for i in items) else []


def _line_count(text: str, quote: str, ai_quantity, system, quantity) -> tuple[int | None, bool]:
    """(the line's count, whether it is the line's own count rather than the system's)."""
    m = _QTY_IN_LINE.search(text or "")
    if m:
        return int(m.group(1)), True
    if ai_quantity is not None:
        return ai_quantity, True
    tags = [t.upper() for t in expand_tags(system.tags)]
    if len(tags) > 1 and (quantity is None or quantity == len(tags)):
        named = [t for t in _named_tags(text) if t in set(tags)]
        if named and len(named) < len(tags):
            return len(named), True
    rooms = _rooms(text)
    if rooms:
        return len(rooms), True
    return quantity, False


def line_quantity(text: str, quote: str, ai_quantity, system, quantity) -> int | None:
    """A line's quantity, from the line: the count it states ("(Qty. 9 Total)"), the AI's count when its
    quote states it, the subset of the system's tags it names ("UH-7", "RTU-3 only"), the rooms it lists;
    else the system's quantity (None: the count is still to fill)."""
    return _line_count(text, quote, ai_quantity, system, quantity)[0]


@lru_cache(maxsize=1)
def _template_texts() -> frozenset[str]:
    texts = {_plain(line.text) for t in load_templates() for line in t.lines}
    data = _front_end_data(FRONT_END_FILE)
    for variant in data.get("variants", {}).values():
        for line in variant:
            texts.add(_plain(line.get("text", "")))
            texts.update(_plain(sub) for sub in line.get("lines", ()))
    return frozenset(texts)


def polish_line(text: str) -> list[str]:
    """The house-style polish: no point-type code ("(AO)"), no trailing "(as per sequence)" unless the line
    is the template's own, and a line joining two actions with ";" split into two lines."""
    text = _squash(_POINT_CODE.sub("", text or ""))
    if _plain(text) not in _template_texts():
        text = _AS_PER_SEQUENCE.sub("", text).strip()
    style = load_house_style()
    parts = [p.strip() for p in text.split(";")]
    if len(parts) > 1 and all(p and (style.verb(p) or style.starts_without_verb(p)) for p in parts):
        return parts
    return [text]


# --- C2: a system whose lines were all refused ---------------------------------------------------------------

_REFUSED = re.compile(r"^[“\"](?P<text>.+?)[”\"]\s*(?:—|-|\()\s*(?P<why>.*)$")


def _nearest_template(system, templates):
    template = system_template(system, templates)
    if template is None:
        tags = expand_tags(system.tags)
        near = nearest_templates(system.kind or _name(system), _tag_prefix(tags[0]) if tags else "", templates, k=1)
        template = near[0] if near else None
    return template


def _template_defaults(template, system, evidence: str) -> list[tuple[str, int]]:
    """The Master Template's lines usually present for the system: its defaults and the lines whose
    conditions the evidence names, one of each choice, in the template's order."""
    prefixes = {_tag_prefix(t) for t in expand_tags(system.tags)}
    out, groups = [], set()
    for line in template.lines:
        if line.of and prefixes and not prefixes & set(line.of):
            continue
        text = _squash(line.text.replace("{what} ", "").replace(" {what}", ""))
        if "{" in text:
            continue
        if any(_holds(template.conditions[n], evidence) for n in line.unless):
            continue
        if line.choice:
            if line.choice in groups:
                continue
            groups.add(line.choice)
            out.append((text, line.depth))
            continue
        expected = (all(_holds(template.conditions[n], evidence) for n in line.when) if line.when
                    else line.default)
        if expected:
            out.append((text, line.depth))
    return out


def _rewritten(refused) -> list[str]:
    """The refused lines that lacked only a verb, with one added: "Wire …" for a device furnished by
    others, else "Furnish …". A line refused for anything else stays out."""
    out = []
    for entry in refused or ():
        m = _REFUSED.match(_squash(str(entry)))
        if m is None or "verb" not in m.group("why"):
            continue
        text = m.group("text").strip()
        verb = "Wire" if re.search(r"\(Furnished by", text, re.I) else "Furnish"
        text = f"{verb} {text}"
        if load_house_style().check_line(text, 1) is None and not _NEVER.search(text):
            out.append(text)
    return out


def _fallback(system, scope, dossier, templates) -> tuple[list[CheckedLine], str]:
    """The lines a system is printed with when the AI wrote none that could be used: the nearest Master
    Template entry's usual lines, else the refused lines rewritten with a verb. (lines, where they came from)."""
    template = _nearest_template(system, templates)
    if template is not None:
        lines = _template_defaults(template, system, system_evidence(system, dossier))
        if lines:
            why = f"the Master Template's {template.name} line"
            return [CheckedLine(text, depth, None, "", "", why, _EVIDENCE_CONFIDENCE[ASSUMPTION], False)
                    for text, depth in lines], f"the Master Template's {template.name} lines"
    texts = _rewritten(getattr(scope, "refused", ()) if scope is not None else ())
    why = "the AI's line, refused for want of a verb, rewritten with one"
    return ([CheckedLine(t, 1, None, "", "", why, _EVIDENCE_CONFIDENCE[ASSUMPTION], False) for t in texts],
            "the AI's refused lines, rewritten with a verb" if texts else "no line at all")


# --- C2: one device, one place ----------------------------------------------------------------------------------

_DEVICE_STOP = frozenset("furnish install and wire the a an of for to with at in on each new per provided by unit "
                         "mfr furnished others qty total location via".split())


def _device_words(text: str) -> frozenset[str]:
    text = re.sub(r"\([^)]*\)", " ", text or "")
    text = re.sub(r"\s+[–-]\s+.*$", " ", text)
    return frozenset(w for w in _plain(text).split() if w not in _DEVICE_STOP and not w.isdigit())


def _room_keys(text: str) -> frozenset[str]:
    keys = set()
    for item in _location_items(text):
        numbers = re.findall(r"\b(\d+[A-Za-z]?)\b", item)
        keys.update(n.lower() for n in numbers) if numbers else keys.add(_plain(item))
    return frozenset(keys)


def _names_all(evidence: str, rooms: frozenset[str], tags: frozenset[str]) -> bool:
    plain = f" {_plain(evidence)} "
    wanted = rooms or {t.lower() for t in tags}
    return bool(wanted) and all(f" {_plain(w)} " in plain for w in wanted)


def _one_place(entries: list, dossier) -> None:
    """The same device named for the same rooms or tags in two systems is kept in the system whose cited
    evidence names them, and taken out of the other, with a review line there. `entries` holds
    [system, kept lines, review] in the plan's order; they are changed in place."""
    evidence = {}
    for i, (system, kept, _) in enumerate(entries):
        for j in range(i + 1, len(entries)):
            other, other_kept, _ = entries[j]
            for a in list(kept):
                for b in list(other_kept):
                    if a not in kept or b not in other_kept:
                        continue
                    wa, wb = _device_words(a.text), _device_words(b.text)
                    if not (wa and wb and (wa <= wb or wb <= wa)):
                        continue
                    ra, rb = _room_keys(a.text), _room_keys(b.text)
                    ta, tb = frozenset(_named_tags(a.text)), frozenset(_named_tags(b.text))
                    if not ((ra and ra == rb) or (not ra and not rb and ta and ta == tb)):
                        continue
                    for s in (system, other):
                        if s.key not in evidence:
                            evidence[s.key] = system_evidence(s, dossier)
                    first = _names_all(evidence[system.key], ra, ta)
                    second = _names_all(evidence[other.key], rb, tb)
                    keep_first = first or not second
                    winner, loser, line, lines, review = ((system, other, b, other_kept, entries[j][2]) if keep_first
                                                          else (other, system, a, kept, entries[i][2]))
                    what = ", ".join(sorted(ra or ta))
                    lines.remove(line)
                    why = (f"its evidence names {what}" if (first if keep_first else second)
                           else "neither system's evidence names them, so it stays where the plan lists it first")
                    review.append(ReviewItem(_name(loser), "", f"“{line.text}” was named in both {_name(loser)} and "
                                             f"{_name(winner)}; kept in {_name(winner)} — {why}",
                                             f"One device, one place: {what}", "Move it back if it belongs here",
                                             tier=TIER_DISAGREE))


# --- C2: the job from the plan -------------------------------------------------------------------------------

_FRONT_END_KEY = "Front end"
_GLOBAL_POINTS = "Global Points"
_WARRANTY = "Extended Warranty"
_ADDED_CONFIDENCE = 0.7
_EXCEPTION_CONFIDENCE = 0.8
_EVIDENCE_CONFIDENCE = {CONFIRMED: 0.8, ASSUMPTION: 0.5, PENDING: 0.0}
_MFR = re.compile(r"\s*(?:,\s*)?(?:(?:is|are|to be|will be)\s+)?(?:furnished\s+|provided\s+|supplied\s+)?by\s+"
                  r"(?:the\s+)?(?:unit\s+)?(?:mfr\.?|manufacturer)\b.*$", re.I)
_MFR_TOPICS = ("leak detect", "transformer", "integral thermostat", "airflow station", "airflow measuring",
               "air flow station", "air flow measuring")


@dataclass
class _Part:
    """One planned system, written: its headers, items and lines, before a group's headers are stacked."""
    system: object
    headers: tuple
    items: list
    lines: list
    review: list
    hours: float | None
    printed: bool

    @property
    def header(self) -> str:
        return self.headers[0]


def _where(dossier, sid: str) -> str:
    return (dossier.sources or {}).get(sid, "") if sid else ""


def _source(sid: str) -> str:
    return f"{SOURCE} [{sid}]" if sid else SOURCE


def _by_unit_mfr(note: str, evidence: str, pictured: bool) -> str | None:
    """The standing house rule: a note giving a device to the unit manufacturer (leak detection, a
    transformer, an integral thermostat, an airflow station) is the house's "*… BY UNIT MFR." note, when
    the evidence names the device or the system rests on a picture."""
    low = note.lower()
    topic = next((t for t in _MFR_TOPICS if t in low), None)
    if topic is None or not _MFR.search(note.lstrip("*")):
        return None
    if not (pictured or topic.split()[0] in evidence.lower()):
        return None
    subject = _MFR.sub("", note.lstrip("*")).strip(" ,.-–")
    return f"*{subject.upper()} BY UNIT MFR." if subject else None


def _dedupe(rows: list[tuple]) -> list[tuple]:
    """(line, quantity, own) rows: the same line twice in a block is kept once; two subset lines that say the
    same thing (UH-1 thru 6 and UH-7) add their counts."""
    out: dict[tuple, list] = {}
    for line, q, own in rows:
        key = (line.depth, _plain(line.text))
        if key not in out:
            out[key] = [line, q, own]
        elif own and out[key][2] and q is not None:
            out[key][1] = (out[key][1] or 0) + q
    return [tuple(v) for v in out.values()]


def _written_part(system, check: PlanCheck, scope, got, dossier, templates, style) -> _Part:
    """One planned system written: its checked lines polished and counted, its notes, its tech hours. A
    system with no usable line falls back to the Master Template; one with no quantity is "Qty (##)"."""
    name = _name(system)
    quantity = system.quantity
    kept, scope_review = got if got is not None else ([], [])
    review = [*check.review, *scope_review]
    evidence = system_evidence(system, dossier)
    shape = shape_header(system, quantity)
    fallback = ""
    if not kept:
        kept, fallback = _fallback(system, scope, dossier, templates)
        what = "the AI has not written it yet" if scope is None else "the AI wrote no line that could be used"
        review.insert(0, ReviewItem(name, ASSUMPTION, f"{FALLBACK} {shape.headers[0]}",
                                    f"{what}; it is printed with {fallback}", "Rewrite the block from the drawings "
                                    "and the sequence", tier=TIER_FIRST))
    one_kind = "|" not in _base_name(system)          # a pipe's families count their own units
    if one_kind and len(shape.headers) > 1 and quantity is not None and check.category != DISCREPANCY \
            and sum(n for n in shape.quantities if n is not None) != quantity:
        review.append(ReviewItem(name, DISCREPANCY, f"The plan counts {quantity} for {name}; its stacked headers "
                                 f"count their own tags: {', '.join(shape.headers)}", "",
                                 "Correct the headers' counts", tier=TIER_DISCREPANCY))
    rows = []
    for line in kept:
        if style.is_trio(line.text) and not style.verb(line.text):
            q, own = None, False               # "Map Available Points …": no count
        else:
            q, own = _line_count(line.text, line.quote, line.quantity, system, quantity)
        for text in ([line.text] if fallback else polish_line(line.text)):
            rows.append((dataclasses.replace(line, text=text), q, own))
    rows = _dedupe(rows)
    items = [Item(kind="note", runs=(Run(text=shape.note),))] if shape.note and not style.forbidden(shape.note) else []
    items += [Item(kind="line", depth=line.depth, runs=(Run(text=line.text),), quantity=q) for line, q, _ in rows]
    pictured = (any(_is_picture(sid, dossier) for sid in _system_ids(system))       # the judge read a picture
                or any(_is_picture(line.source_id, dossier) for line in kept))     # for this system
    notes, seen = [], {_plain(i.text) for i in items if i.kind == "note"}
    for note in getattr(scope, "client_notes", ()) or ():
        note = _squash(note)
        house = _by_unit_mfr(note, evidence, pictured)
        if house is not None:
            text, problem = house, style.forbidden(house)
        else:
            text = note
            on_picture = pictured and re.search(r"schedul", note, re.I)    # it rests on the schedule's picture
            problem = style.check_note(note) or (None if _note_is_borne_out(note, evidence) or on_picture
                                                 else "the evidence does not bear it out")
        if problem is None:
            if _plain(text) in seen:
                continue
            seen.add(_plain(text))
            notes.append(text)
            items.append(Item(kind="note", runs=(Run(text=text),)))
        else:
            review.append(ReviewItem(name, "", f"The AI suggests the client note “{note}”, but {problem}", "",
                                     "Add it by hand if it applies"))
    hours, hours_note = tech_hours(system, quantity, [(line.text, q) for line, q, _ in rows],
                                   getattr(scope, "tech_hours_hint", None), templates, evidence)
    if hours_note is not None:
        review.append(hours_note)
    template = system_template(system, templates)
    point = (template.tech_hours.hours if template is not None and template.tech_hours.per == "hardware_point"
             else None)
    lines = []
    for line, q, _ in rows:
        category = ASSUMPTION if fallback or not line.quoted else CONFIRMED
        where = _where(dossier, line.source_id)
        said = f"{where + ': ' if where else ''}“{line.quote}”" if line.quote else (line.why or "no quote")
        line_hours = point * (q or 0) if point is not None and _hardware(line.text) else None
        lines.append(ScopeLine(name, line.text, line.depth, q, line_hours, category, line.confidence,
                               "the Master Template (fallback)" if fallback else _source(line.source_id),
                               said + (f" ({line.why})" if line.why and line.quote else ""), True))
    if shape.note:
        lines.insert(0, ScopeLine(name, shape.note, 1, None, None, CONFIRMED, _ADDED_CONFIDENCE, SOURCE,
                                  f"taken out of the plan's header: “{_base_name(system)}”", True))
    lines += [ScopeLine(name, n, 1, None, None, CONFIRMED, _ADDED_CONFIDENCE, SOURCE,
                        "a clarification the evidence bears out", True) for n in notes]
    return _Part(system, shape.headers, items, lines, review, hours, True)


def _merge(items) -> tuple:
    """Several systems' items under one stack of headers: the same line once, its quantities added."""
    merged: dict[tuple, Item] = {}
    for item in items:
        key = (item.kind, item.depth, _plain(item.text))
        if key not in merged:
            merged[key] = item
        elif item.kind == "line" and (merged[key].quantity is not None or item.quantity is not None):
            have = merged[key]
            merged[key] = have.model_copy(update={"quantity": (have.quantity or 0) + (item.quantity or 0)})
    return tuple(merged.values())


def _written_system(key: str, parts: list[_Part], template: str | None) -> WrittenSystem:
    """One block, or several headers stacked over the lines they share (a group, or one system whose header
    is one header per family)."""
    headers = [h for p in parts for h in p.headers]
    blocks = [Block(header=h, joined=i > 0) for i, h in enumerate(headers)]
    hours = None if any(p.hours is None for p in parts) else float(sum(p.hours for p in parts))
    blocks[0] = blocks[0].model_copy(update={"tech_hours": hours})
    items = [i for p in parts for i in p.items]
    blocks[-1] = blocks[-1].model_copy(update={"items": _merge(items) if len(parts) > 1 else tuple(items)})
    review = [r for p in parts for r in p.review]
    lines = [line for p in parts for line in p.lines]
    return WrittenSystem(key, tuple(blocks), tuple(lines), tuple(review), printed=True, template=template,
                         tech_hours=hours)


def _exception(system, check: PlanCheck, style) -> tuple[WrittenSystem, str | None]:
    """A unit that needs no BMS work: its one line goes into the proposal's exceptions."""
    name = _name(system)
    text = _squash(system.exception)
    review = list(check.review)
    ids = _system_ids(system)
    evidence = (system.quantity_quote or system.why or "") + (f" [{', '.join(ids)}]" if ids else "")
    bad = style.forbidden(text) or ("it names prices, hours or confidence" if _NEVER.search(text) else None)
    if bad:
        review.insert(0, ReviewItem(name, "", f"The AI's exception for {name} was left out — {bad}", text,
                                    "Write the exception by hand"))
        return WrittenSystem(system.key, (), (), tuple(review), printed=False), None
    confidence = _EXCEPTION_CONFIDENCE if check.sourced else UNSOURCED_CONFIDENCE
    line = ScopeLine(name, text, 1, None, None, CONFIRMED if check.sourced else ASSUMPTION, confidence,
                     _source(ids[0] if ids else ""), evidence, True)
    review.insert(0, ReviewItem(name, "", f"{name} not priced — put in the exceptions", system.why or evidence,
                                "Price it if the job wants the BMS to see it"))
    return WrittenSystem(system.key, (), (line,), tuple(review), printed=True), text


# --- C2: the front end ------------------------------------------------------------------------------------------

_FE_STOP = frozenset("furnish install and wire the a an of for to on in at with new all each provide necessary "
                     "bms system".split())
_WARRANTY_CLAUSE = re.compile(r"^(?P<rest>.+)(?:,\s*|\s+and\s+)(?P<clause>[^,]*\bwarrant\w*\b[^,]*)$", re.I)
_LONG_TERM = re.compile(r"\b(?:(?P<months>\d+)\s*-?\s*months?|(?P<years>\d+|two|three|four|five)\s*-?\s*years?)\b",
                        re.I)


def _plan_lines(value) -> list[str]:
    out = []
    for entry in value or ():
        text = entry.get("text", "") if isinstance(entry, dict) else str(entry)
        if _squash(text):
            out.append(_squash(text))
    return out


def _fe_words(text: str) -> frozenset[str]:
    return frozenset(w for w in _plain(text.lstrip("*")).split() if w not in _FE_STOP)


def _near_duplicate(text: str, have: list[str]) -> bool:
    words = _fe_words(text)
    if not words:
        return True
    return any(_plain(text) == _plain(h) or len(words & _fe_words(h)) / len(words) >= NEAR_DUPLICATE for h in have)


def _contradiction(text: str, have: list[str]) -> str | None:
    """The front-end line already there that the plan's line contradicts: a server furnished against a
    server by the owner (or the other way), a second workstation, a second kind of graphics."""
    low = text.lower()
    if "server" in low:
        furnishes = bool(re.match(r"furnish(?:\s+and\s+install)?\s+(?:an?\s+|the\s+)?(?:bms\s+)?server\b", low))
        for h in have:
            hl = h.lower()
            by_owner = "server" in hl and bool(re.search(r"\bby\s+(?:the\s+)?owner\b", hl))
            furnished = "server" in hl and hl.startswith("furnish")
            if (furnishes and by_owner) or (not furnishes and "owner" in low and furnished):
                return h
    for word in ("workstation", "graphic"):
        if word in low:
            match = next((h for h in have if word in h.lower()), None)
            if match is not None:
                return match
    return None


def _long_warranty(text: str) -> bool:
    """The warranty's term is longer than the standard year ("24-Month", "two-year")."""
    words = {"two": 2, "three": 3, "four": 4, "five": 5}
    for m in _LONG_TERM.finditer(text):
        if m.group("months") and int(m.group("months")) > 12:
            return True
        years = m.group("years")
        if years and (int(years) if years.isdigit() else words.get(years.lower(), 0)) > 1:
            return True
    return False


def _reconcile_front_end(fe, plan, dossier, style, warranty_block):
    """The deterministic front end (the Master Template's lines the Spec overview calls for) is the base.
    A line the plan adds goes in only when it adds something new (not a near-duplicate), cites a source and
    keeps the house style; a contradiction keeps the deterministic answer; the warranty goes into the
    Extended Warranty block, never the front end; the front end holds at most MAX_FRONT_END_LINES lines.
    Returns (front end, added scope lines, review, an Extended Warranty block the plan gives or None)."""
    raw = getattr(plan, "front_end", None) or {}
    review: list[ReviewItem] = []
    added: list[ScopeLine] = []
    ids = [i for i in source_ids(raw.get("sources", ())) if i in (dossier.sources or {})]
    where = "; ".join(f"[{i}] {_where(dossier, i)}" for i in ids) or "no source"
    mode = raw.get("mode") or ""
    if mode and mode != fe.mode:
        review.append(ReviewItem(_FRONT_END_KEY, "", f"The AI's plan reads the front end as {mode.replace('-', ' ')}; "
                                 f"the Spec overview's reading ({fe.mode.replace('-', ' ')}) is kept", where,
                                 "Change the front end by hand if the plan is right", tier=TIER_DISAGREE))
    name = _squash(raw.get("existing_name") or "")
    if name and fe.mode == "extend-existing" and _plain(name) not in _plain(fe.existing_system_name or ""):
        review.append(ReviewItem(_FRONT_END_KEY, "", f"The AI's plan names the existing BMS “{name}”; the Spec "
                                 f"overview's “{fe.existing_system_name}” is kept", where, "Check which it is",
                                 tier=TIER_DISAGREE))
    have = [i.text for i in fe.items]
    room = MAX_FRONT_END_LINES - sum(1 for i in fe.items if i.kind == "line" and i.depth == 1)
    lines, notes = _plan_lines(raw.get("lines")), _plan_lines(raw.get("notes"))
    new_lines, new_notes, left, over, warranties, contradicted = [], [], [], [], [], []
    for text, is_note in [(t, False) for t in lines] + [(t, True) for t in notes]:
        if not is_note:
            text = polish_line(text)[0]
        if re.search(r"\bwarrant", text, re.I):
            m = _WARRANTY_CLAUSE.match(text)
            if m and len(_fe_words(m.group("rest"))) >= 2:
                warranties.append(m.group("clause").strip())
                text = m.group("rest").strip()
            else:
                warranties.append(text)
                continue
        if _near_duplicate(text, have):
            continue
        against = _contradiction(text, have)
        if against is not None:
            contradicted.append(f"“{text}” against “{against}”")
            continue
        problem = None if ids else "it cites no source"
        if problem is None and _NEVER.search(text):
            problem = "it names prices, hours or confidence"
        problem = problem or (style.check_note(text) if is_note else style.check_line(text, 1))
        if problem:
            left.append(f"“{text}” ({problem})")
            continue
        if not is_note and room <= 0:
            over.append(text)
            continue
        room -= 0 if is_note else 1
        have.append(text)
        item = Item(kind="note" if is_note else "line", runs=(Run(text=text, bold=True),))
        (new_notes if is_note else new_lines).append(item)
        added.append(ScopeLine(_FRONT_END_KEY, text, 1, None, None, ADDED, _ADDED_CONFIDENCE, _source(ids[0]),
                               where, True))
    if new_lines or new_notes:
        review.append(ReviewItem(_FRONT_END_KEY, ADDED, "Front-end lines added from the AI's plan: "
                                 + "; ".join(f"“{i.text}”" for i in new_lines + new_notes), where,
                                 "Check each, and price the lines"))
    if contradicted:
        review.append(ReviewItem(_FRONT_END_KEY, "", "The AI's plan contradicts the front end; the front end's "
                                 "lines are kept: " + "; ".join(contradicted), where,
                                 "Change the front end by hand if the plan is right", tier=TIER_DISAGREE))
    if over:
        review.append(ReviewItem(_FRONT_END_KEY, "", f"Spec items the front end could add (it holds "
                                 f"{MAX_FRONT_END_LINES} lines at most)", "; ".join(over),
                                 "Add any the job needs in place of a line there"))
    block = None
    if warranties:
        if warranty_block is None and any(_long_warranty(w) for w in warranties):
            text = next(w for w in warranties if _long_warranty(w))
            block = Block(header=_front_end_data(FRONT_END_FILE)["warranty"]["extended_header"],
                          items=(Item(kind="line", runs=(Run(text=text),)),))
            review.append(ReviewItem(_WARRANTY, ADDED, f"Extended Warranty block written from the AI's plan: “{text}”",
                                     where, "Check the term and price it"))
        else:
            carried = " (the Extended Warranty block carries it)" if warranty_block else ""
            left += [f"“{w}” (a warranty never goes in the front end{carried})" for w in warranties]
    if left:
        review.append(ReviewItem(_FRONT_END_KEY, "", "Front-end lines in the AI's plan left out: " + "; ".join(left),
                                 where, "Add any by hand if the job needs it"))
    if lines:
        planned = {_plain(t) for t in lines}
        missing = [i.text for i in fe.items if i.kind == "line" and i.depth == 1 and _plain(i.text) not in planned
                   and not _near_duplicate(i.text, lines)]
        if missing:
            review.append(ReviewItem(_FRONT_END_KEY, "", "The AI's plan leaves out front-end lines the Spec overview "
                                     "gives; they are kept: " + "; ".join(missing), where,
                                     "Delete any the job does not need", tier=TIER_DISAGREE))
    if new_lines or new_notes:
        items = list(fe.items)
        at = next((k for k, i in enumerate(items) if i.kind == "note"), len(items))
        items[at:at] = new_lines
        fe = fe.model_copy(update={"items": tuple(items + new_notes)})
    return fe, added, review, block


def _evidence_system(key: str, block: Block, evidence, template: str | None = None) -> WrittenSystem:
    """A block the deterministic reading writes (Global Points, Extended Warranty), with its evidence."""
    quantities = {i.text: i.quantity for i in block.items}
    lines = tuple(ScopeLine(key, e.line, 1, quantities.get(e.line), None, e.status,
                            _EVIDENCE_CONFIDENCE.get(e.status, 0.5),
                            "the Spec overview" if e.status == CONFIRMED else "default",
                            f"{e.where}: “{e.quote}”" if e.quote else e.where, True) for e in evidence)
    return WrittenSystem(key, (block,), lines, (), printed=True, template=template)


def _order(plan) -> list[list]:
    """The planned systems in the plan's order, each group's members together where the first one is."""
    runs: list[list] = []
    seen: dict[str, list] = {}
    for system in plan.systems:
        group = _squash(system.group)
        if group and group in seen:
            seen[group].append(system)
            continue
        run = [system]
        runs.append(run)
        if group:
            seen[group] = run
    return runs


def assemble_job(catalogue, reading, dossier, plan, scopes, today, templates=None
                 ) -> tuple[Job, list[WrittenSystem], list[ReviewItem]]:
    """The Job from the whole-job plan and each system's scope, the written systems for the Evidence
    Package (the front end first) and the review lines that belong to no system.

    `scopes` maps each planned system's key to its WrittenScope, or None when the AI has not written
    it yet. Nothing planned is lost: exceptions go into the exceptions, alternates into the add or
    deduct alternates, every other system into the base bid — "Qty (##)" when it has no quantity, with
    the Master Template's lines when the AI wrote none that could be used (each with a top review line)."""
    templates = templates if templates is not None else load_templates()
    style = load_house_style()
    header, header_flags = job_header(catalogue, reading, today)
    fe, fe_flags, fe_evidence = front_end(catalogue, bid_check=getattr(catalogue, "bid", None))
    points, points_evidence = global_points_block(catalogue, templates=templates)
    warranty, warranty_flags, warranty_evidence = extended_warranty_block(catalogue)
    fe, fe_added, fe_review, plan_warranty = _reconcile_front_end(fe, plan, dossier, style, warranty)
    if warranty is not None:          # the standalone block carries the warranty: the front end's lines go
        moved = {_plain(i.text) for i in warranty.items}
        fe = fe.model_copy(update={"items": tuple(i for i in fe.items if _plain(i.text) not in moved)})
        fe_evidence = [e for e in fe_evidence if _plain(e.line) not in moved]
    front = _front_end_system(fe, fe_flags, fe_evidence, header_flags)
    extra_review = fe_review + [ReviewItem(_FRONT_END_KEY, "", *f.partition(" — ")[::2], "") for f in warranty_flags]
    front = dataclasses.replace(front, lines=front.lines + tuple(fe_added), review=front.review + tuple(extra_review))

    checks, general = plan_checks(plan, dossier, reading, catalogue)
    check_of = {id(c.system): c for c in checks}
    systems: list[WrittenSystem] = []
    base: list[Block] = []
    exceptions: list[str] = []
    alternates: dict[str, list] = {"add": [], "deduct": []}
    if points is not None:
        systems.append(_evidence_system(_GLOBAL_POINTS, points, points_evidence, _GLOBAL_POINTS))
        base.append(points)

    def merged_into_points(system) -> bool:
        return points is not None and _GLOBAL_POINTS.lower() in f"{system.header} {system.kind}".lower()

    # Each system's lines are checked first, so one device named in two systems stays in one place.
    entries, checked = [], {}
    for system in plan.systems:
        if system.exception or merged_into_points(system):
            continue
        scope = (scopes or {}).get(system.key)
        if scope is not None:
            kept, review = check_scope(system, scope, dossier, templates, style, sourced=check_of[id(system)].sourced)
            entries.append([system, kept, review])
            checked[id(system)] = entries[-1]
    _one_place(entries, dossier)

    for run in _order(plan):
        parts = []
        for system in run:
            check = check_of[id(system)]
            if system.exception:
                written, text = _exception(system, check, style)
                systems.append(written)
                if text:
                    exceptions.append(text)
                continue
            if merged_into_points(system):
                continue                  # printed: the Master Template's Global Points block carries it
            entry = checked.get(id(system))
            got = (entry[1], entry[2]) if entry is not None else None
            parts.append(_written_part(system, check, (scopes or {}).get(system.key), got, dossier, templates,
                                       style))
        if not parts:
            continue
        grouped = len(parts) > 1
        key = _squash(run[0].group) if grouped else parts[0].system.key
        template = system_template(parts[0].system, templates)
        written = _written_system(key, parts, template.name if template is not None else None)
        systems.append(written)
        side = parts[0].system.alternate if parts[0].system.alternate in ("add", "deduct") else ""
        if side:
            label = key if grouped else _squash(re.sub(r"^\s*Qty\s*\([^)]*\)\s*", "", parts[0].header))
            alternates[side].append((label, written.blocks))
        else:
            base.extend(written.blocks)
    if warranty is not None:
        systems.append(_evidence_system(_WARRANTY, warranty, warranty_evidence))
        base.append(warranty)
    elif plan_warranty is not None:
        text = plan_warranty.items[0].text
        systems.append(WrittenSystem(_WARRANTY, (plan_warranty,), (ScopeLine(
            _WARRANTY, text, 1, None, None, ADDED, _ADDED_CONFIDENCE, SOURCE, "the AI's plan of the front end",
            True),), (), printed=True))
        base.append(plan_warranty)

    add, deduct = ([Alternate(label=f"ALT #{k}: {label}", blocks=blocks)
                    for k, (label, blocks) in enumerate(alternates[side], start=1)] for side in ("add", "deduct"))
    job = Job(header=header, front_end=fe, blocks=tuple(base), add_alternates=tuple(add),
              deduct_alternates=tuple(deduct), named_exceptions=tuple(exceptions))
    general += [ReviewItem("The plan", "", _squash(q), "the AI's question",
                           "Decide it, and change the proposal by hand if needed", tier=TIER_QUESTION)
                for q in getattr(plan, "unresolved", ()) or ()]
    dropped = [_squash(str(d)) for d in getattr(plan, "dropped", ()) or ()]
    if dropped:
        general.append(ReviewItem("The plan", "", "The AI planned systems that could not be used; they were thrown "
                                  "away", "; ".join(dropped), "Add a block by hand for any the job needs",
                                  tier=TIER_FIRST))
    return job, [front] + systems, general


# --- the review list, ranked and short ----------------------------------------------------------------------------

_AI_NOTE = "the AI's note"
_HOURS_WORDS = re.compile(r"tech[\s-]*hour", re.I)


def _tier(item: ReviewItem) -> int:
    if item.tier:
        return item.tier
    if item.category == DISCREPANCY:
        return TIER_DISCREPANCY
    if item.evidence == "the AI's question":
        return TIER_QUESTION
    return TIER_REST


def _joined(items, what) -> str:
    return "; ".join(dict.fromkeys(what(i) for i in items if what(i)))


def _merge_review(items: list[ReviewItem]) -> list[ReviewItem]:
    """Repeated rows as one: every system with no tech hours in one row, every quote not found in one, the
    AI's own notes on a system in one row per system (its remarks on tech hours folded into the tech-hours
    row), the lines dropped for the house style in one, the client notes not borne out in one, the counts
    with nothing to check them against in one, the exceptions in one."""
    rules = [
        ("hours", lambda i: i.decide.startswith("No tech hours for"),
         lambda g: ReviewItem("Tech hours", "", "No tech hours for: " + _joined(g, lambda i: i.system)
                              + " — enter them", "No Master Template rule fits them, and the AI suggested none "
                              "that could be counted", "Type the hours on each block's header row of the price sheet")),
        ("hours-ai", lambda i: i.decide.startswith("Tech hours are the AI's suggestion"),
         lambda g: ReviewItem("Tech hours", ASSUMPTION, "Tech hours are the AI's suggestion for: "
                              + _joined(g, lambda i: f"{i.system} ({i.evidence})"), "", "Confirm them")),
        ("quotes", lambda i: "is not in the job's documents" in i.decide and i.decide.startswith("The quote for"),
         lambda g: ReviewItem("Quotes", "", f"Lines whose quote is not in the job's documents ({len(g)}) — check "
                              "each by hand", _joined(g, lambda i: f"{i.system}: {i.decide[len('The quote for '):]}"
                                                      .replace(" is not in the job's documents", "")), "")),
        ("dropped", lambda i: i.decide.startswith("The AI wrote lines the client must never see"),
         lambda g: ReviewItem("House style", "", "Lines the AI wrote that break the house style were dropped ("
                              + _joined(g, lambda i: i.system) + ")", _joined(g, lambda i: f"{i.system}: {i.evidence}"),
                              "Nothing to do unless a line is missing")),
        ("notes", lambda i: i.decide.startswith("The AI suggests the client note"),
         lambda g: ReviewItem("Client notes", "", f"Client notes the AI suggested that were not printed ({len(g)})",
                              _joined(g, lambda i: f"{i.system}: " + i.decide.replace("The AI suggests the client note ",
                                                                                     "")),
                              "Add any by hand if it applies")),
        ("unchecked", lambda i: i.category == ASSUMPTION and i.decide.startswith("The plan counts")
         and "with no count to check it" in i.decide,
         lambda g: ReviewItem("Counts", ASSUMPTION, "Counts with nothing to check them against: "
                              + _joined(g, lambda i: i.decide.split(" for ", 1)[1].split(",")[0] + " — "
                                        + i.decide.split("The plan counts ", 1)[1].split(" for ")[0]),
                              _joined(g, lambda i: i.evidence), "Confirm each count")),
        ("unsourced", lambda i: "cites no source for" in i.decide,
         lambda g: ReviewItem("Sources", "", "The plan cites no source for: " + _joined(g, lambda i: i.system)
                              + " — they are written, but check every line", "", "Check the blocks against the "
                              "drawings and the sequence")),
        ("exceptions", lambda i: i.decide.endswith("not priced — put in the exceptions"),
         lambda g: ReviewItem("Exceptions", "", "Not priced — put in the exceptions: " + _joined(g, lambda i: i.system),
                              _joined(g, lambda i: f"{i.system}: {i.evidence}"), "Price any the job wants the BMS to see")),
    ]
    groups: dict[str, list] = defaultdict(list)
    per_system: dict[str, list] = defaultdict(list)
    out: list = []
    for item in items:
        if "mentioned only in the specs" in item.decide:
            continue
        left_out = item.decide.startswith("Usually present in the Master Template's")
        if item.evidence == _AI_NOTE or left_out:
            if _HOURS_WORDS.search(item.decide) and not left_out:
                continue                                  # the tech-hours row says it
            if item.system not in per_system:
                out.append(("system", item.system))
            per_system[item.system].append(item)
            continue
        rule = next((r for r in rules if r[1](item)), None)
        if rule is None:
            out.append(item)
            continue
        if rule[0] not in groups:
            out.append(("rule", rule[0]))
        groups[rule[0]].append(item)
    build = {r[0]: r[2] for r in rules}
    merged = []
    for entry in out:
        if isinstance(entry, ReviewItem):
            merged.append(entry)
        elif entry[0] == "rule":
            group = groups[entry[1]]
            single = len(group) == 1 and entry[1] not in ("hours", "hours-ai")
            merged.append(group[0] if single else build[entry[1]](group))
        else:
            notes = per_system[entry[1]]
            merged.append(ReviewItem(entry[1], "", f"The AI's notes on {entry[1]} and the lines left out: "
                                     + " | ".join(dict.fromkeys(i.decide for i in notes)), "the AI's notes",
                                     "Add any line the job needs"))
    return _fold(merged)


def _fold(merged: list[ReviewItem]) -> list[ReviewItem]:
    """One urgent row per system: a system written with fallback lines and with no count is one row, and a
    system that has an urgent row (fallback lines, no count, a quantity conflict) carries its other rows
    there (the AI's notes, the lines it left out, the lines dropped). The front end's Master Template
    defaults go with the row saying the plan leaves the front end's lines out."""
    merged = list(merged)
    dropped: set[int] = set()
    fallback = {item.system: n for n, item in enumerate(merged) if item.decide.startswith(FALLBACK)}
    for n, item in enumerate(merged):
        if item.decide.startswith("Give the count for") and item.system in fallback:
            at = fallback[item.system]
            merged[at] = dataclasses.replace(merged[at], decide=f"{merged[at].decide} — and give its count",
                                             evidence=_squash(f"{merged[at].evidence} — {item.evidence}"))
            dropped.add(n)
    urgent: dict[str, int] = {}
    for n, item in enumerate(merged):
        if n not in dropped and _tier(item) <= TIER_DISCREPANCY and item.system not in urgent:
            urgent[item.system] = n
    for n, item in enumerate(merged):
        at = urgent.get(item.system)
        if n in dropped or at is None or at == n or _tier(item) <= TIER_QUESTION or item.tier:
            continue
        host = merged[at]
        merged[at] = dataclasses.replace(host, evidence=_squash(f"{host.evidence} — {item.decide}"))
        dropped.add(n)
    starts = ("The AI's plan leaves out front-end lines", "Front-end lines that are Master Template defaults")
    found = [next((n for n, i in enumerate(merged) if n not in dropped and i.system == _FRONT_END_KEY
                   and i.decide.startswith(s)), None) for s in starts]
    if None not in found:
        host, guest = found
        merged[host] = dataclasses.replace(merged[host], evidence=_squash(
            f"{merged[host].evidence} — Master Template defaults in the front end: {merged[guest].evidence}"))
        dropped.add(guest)
    return [item for n, item in enumerate(merged) if n not in dropped]


def review_list(systems, general) -> list[ReviewItem]:
    """Every review row of the job, merged and ranked: a system written with fallback lines or with no count
    first, then the quantity conflicts, the AI's unresolved questions, the rule and AI disagreements, then
    the rest. Each carries its rank (1 = the most urgent)."""
    items = [item for system in systems for item in system.review] + list(general)
    merged = _merge_review(items)
    ordered = sorted(enumerate(merged), key=lambda pair: (_tier(pair[1]), pair[0]))
    return [dataclasses.replace(item, rank=n) for n, (_, item) in enumerate(ordered, start=1)]
