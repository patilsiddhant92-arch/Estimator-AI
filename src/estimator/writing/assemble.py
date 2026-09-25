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

The shapes it reads are the plan's (docs/superpowers/plans/2026-09-26-whole-job-writing.md): a
Dossier (text, images, sources, families, device_totals, counts), a JobPlan of PlannedSystems and
a WrittenScope of WrittenLines per system. They are read by their field names only.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache

from estimator.writing.style import load_house_style
from estimator.writing.templates import load_templates, template_for
from estimator.writing.write import (ASSUMPTION, CONFIRMED, PENDING, ReviewItem, _hardware, _word, tag_list)

DISCREPANCY = "DISCREPANCY"
SOURCE = "AI (whole job)"
UNSOURCED_CONFIDENCE = 0.4    # a planned system that cites no source: still written, never surer than this
UNQUOTED_CAP = 0.5            # a line whose quote is not in the dossier
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
        if self.category == PENDING:
            return "left out — no quantity"
        if s.alternate in ("add", "deduct"):
            return f"{s.alternate} alternate"
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


def _check_system(system, dossier) -> PlanCheck:
    name = _name(system)
    counts, columns = _counts_for(system, dossier)
    ids = _system_ids(system)
    sourced = bool(ids)
    qid = (source_ids(system.quantity_source) or [""])[0]
    where = (dossier.sources or {}).get(qid, "") if qid else ""
    quote = system.quantity_quote or ""
    found = bool(quote) and quote_in_dossier(quote, dossier)
    quoted = f"{where + ': ' if where else ''}“{quote}”" if quote else "no quote"
    review: list[ReviewItem] = []
    q = system.quantity
    if q is None:
        category = PENDING
        review.append(ReviewItem(name, PENDING, f"No quantity for {name} — the plan gives none, so the block is left "
                                 "out of the proposal", f"The counts: {_counts_text(counts)}. The plan says: "
                                 f"{system.why or 'nothing'}", "Count the units, then add the block"))
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


def _uncovered(plan, dossier, reading) -> list[ReviewItem]:
    planned = {t.upper() for s in plan.systems for t in expand_tags(s.tags)}
    prefixes = {_tag_prefix(t) for t in planned}
    kinds = {_plain(s.kind) for s in plan.systems}
    existing = _existing(reading)
    missed = []
    for family, own in _families(dossier):
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


def plan_checks(plan, dossier, reading) -> tuple[list[PlanCheck], list[ReviewItem]]:
    """Each planned system checked, in the plan's order, and the review lines that belong to no
    system (families the plan didn't write)."""
    return [_check_system(s, dossier) for s in plan.systems], _uncovered(plan, dossier, reading)


def check_plan(plan, dossier, reading) -> list[ReviewItem]:
    """Every review line the plan's cross-checks give: each system's quantity (CONFIRMED needs none,
    DISCREPANCY, ASSUMPTION, PENDING), a system with no source, and the families not written."""
    checks, general = plan_checks(plan, dossier, reading)
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
    kept at confidence 0.5 at most, with a review line; every line of a system the plan cites no
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
        quoted = bool(quote) and quote_in_dossier(quote, dossier)
        confidence = max(0.0, min(float(line.confidence or 0.0), 1.0))
        quantity = line.quantity
        if not quoted:
            confidence, quantity = min(confidence, UNQUOTED_CAP), None
            review.append(ReviewItem(name, "", f"The quote for “{text}” is not in the job's documents",
                                     f"“{quote}”" if quote else "no quote", "Check the line by hand"))
        if not sourced:
            confidence = min(confidence, UNSOURCED_CONFIDENCE)
        sid = (source_ids(getattr(line, "source_id", "") or "") or [""])[0]
        kept.append(CheckedLine(text, depth, quantity, quote, sid, line.why or "", confidence, quoted))
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
    from estimator.writing.templates import nearest_templates

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
    from estimator.writing.phrasing import examples_for, load_bank

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
