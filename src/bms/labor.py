"""Off-hours work and prevailing wage (T-005e; estimator 2026-10-11: "add and highlight").

When the job's documents call for off-hours work (e.g. 6 PM to 6 AM) or prevailing wage (e.g. NJ prevailing wage),
the proposal and the price sheet carry it, in red for the estimator, citing where the documents say it. It is never
excluded in silence: the template's "normal business working hours" clarification and its "All off-hours or overtime
labor" exclusion give way to the red line (`estimator.proposal.write`).

- `labor_conditions(overview)`: the conditions the Spec overview found (`estimator.catalogue.overview.SpecOverview`:
  its "Project conditions that change the price" rows and the standard lines the job speaks to), each a
  `estimator.scope.LaborCondition` (kind, the red line's text, where the documents say it, the quote).
- `labor_block(conditions)`: the scope's "Labor Conditions" block, its lines in red (no quantity: the labor premium is
  the estimator's to price; the price sheet flags each row).
- `with_labor(draft, conditions)`: the rendered draft (`bms.render.render`) with that block last in the base bid and
  `scope.labor_conditions` set, its lines traced under the key "labor"; the draft as it is when there is none. The run
  calls it between render and the writers (render's signature is the interface spec's, so it is not given these).

A quote that names normal working hours only is not off-hours work. Pure; reads nothing but its argument.
"""
from __future__ import annotations

import re
from dataclasses import replace

from estimator.price_sheet.write import PriceSheetError, check_fit
from estimator.scope import Block, Item, Job as ScopeJob, LaborCondition, Run

OFF_HOURS, PREVAILING_WAGE = "off-hours", "prevailing-wage"
HEADING = "Labor Conditions"
LABOR_KEY = "labor"                  # the system key of the block's traced lines (`bms.render.RenderedLine`)
OFF_HOURS_LINE = "Off-Hours Labor{hours} Included (As per {source})"
WAGE_LINE = "{state}Prevailing Wage Labor Rates Included (As per {source})"

_OFF_HOURS = re.compile(
    r"\boff[- ]hours?\b|\bafter[- ]hours\b|\bovertime\b|\bpremium\s+time\b|"
    r"\b(?:night|weekend|evening|second|third)s?[- ](?:work|shifts?|hours)\b|\bnights?\s*(?:,|and|or)\s*weekends?\b|"
    r"\boutside\s+(?:of\s+)?(?:the\s+)?(?:normal|regular|standard)\s+(?:business\s+|working\s+|work\s+)*hours\b", re.I)
_TIME = r"\d{1,2}(?::\d{2})?\s*(?:a\.?\s?m\.?|p\.?\s?m\.?)"
_RANGE = re.compile(rf"({_TIME})\s*(?:to|and|until|thru|through|-|–|—)\s*({_TIME})", re.I)
_WAGE = re.compile(r"\bprevailing\s+wages?\b|\bDavis[- ]Bacon\b|\bcertified\s+payrolls?\b|"
                   r"\bwage\s+(?:rates?|determinations?)\b", re.I)
_STATES = (("New Jersey", "NJ"), ("New York", "NY"), ("Pennsylvania", "PA"), ("Connecticut", "CT"),
           ("Massachusetts", "MA"), ("Delaware", "DE"), ("Maryland", "MD"))
_STATE_ABBR = re.compile(r"\b(NJ|NY|PA|CT|MA|DE|MD)\b")
_SECTION = re.compile(r"^\d{2}\s?\d{2}\s?\d{2}")


def _clock(text: str) -> str:
    """"6:00 p.m." -> "6:00 PM"."""
    found = re.match(r"(\d{1,2}(?::\d{2})?)\s*([ap])", text.strip(), re.I)
    return f"{found.group(1)} {found.group(2).upper()}M" if found else text.strip()


def hours_of(quote: str) -> str:
    """The time range a quote gives ("6 PM to 6 AM"), "" for none."""
    found = _RANGE.search(quote or "")
    return f"{_clock(found.group(1))} to {_clock(found.group(2))}" if found else ""


# a clause that forbids the work ("No overtime work is permitted", "work outside normal hours is not allowed") is no
# call for it (T-005e review finding 5)
_NEGATION = re.compile(r"\b(?:no|not|never|nor|without|prohibited|forbidden|disallowed)\b|\bshall\s+not\b|"
                       r"\bcannot\b|\bcan't\b|\bwon't\b", re.I)
_CLAUSES = re.compile(r"[.;:]\s+|\s+(?:but|however|except|then)\s+", re.I)


def calls_for_off_hours(quote: str) -> bool:
    """True when the quote calls for work outside normal hours: its words, or a time range starting in the evening,
    in a clause that does not forbid it (a ban on overtime or off-hours work is no call for it)."""
    for clause in _CLAUSES.split(quote or ""):
        if _NEGATION.search(clause):
            continue
        if _OFF_HOURS.search(clause):
            return True
        found = _RANGE.search(clause)
        if found and "P" in _clock(found.group(1)):
            return True
    return False


# a fact of the ledger or a key note of the plans speaks to many things; it calls for off-hours work only when the
# sentence is about the work (a work word) and not about a control sequence (a control word: an "after-hours
# override", an "unoccupied 6 PM to 6 AM" schedule, a "night setback") (T-008 review 2A)
_WORK = re.compile(r"\bwork(?:s|ing|ed)?\b|\bconstruction\b|\bshut[- ]?downs?\b|\btie[- ]ins?\b|\bactivit(?:y|ies)\b|"
                   r"\bcontractors?\b|\bpermitted\b|\bperform(?:s|ed|ing)?\b|\blabou?r\b", re.I)
_CONTROL = re.compile(r"\b(?:un)?occupied\b|\boverrides?\b|\bset[- ]?backs?\b|\bschedul(?:e|es|ed|ing)\b|\bmodes?\b|"
                      r"\bset[- ]?points?\b", re.I)
_SENTENCES = re.compile(r";\s+|\.\s+(?=[A-Z])")
# a fact from a sequence of operation or a points list, or a plan note in such a block, is never a labor condition
_SEQUENCE_PLACE = re.compile(r"\b23\s?09\s?93\b|\bsequences?\s+of\s+operations?\b|\bpoints?\s+(?:list|schedule)s?\b",
                             re.I)


def calls_for_off_hours_work(quote: str) -> bool:
    """`calls_for_off_hours` for a ledger fact or a key note: true only for a sentence that has a work word and no
    control word."""
    return any(_WORK.search(s) and not _CONTROL.search(s) and calls_for_off_hours(s)
               for s in _SENTENCES.split(quote or ""))


def calls_for_prevailing_wage(quote: str) -> bool:
    return bool(_WAGE.search(quote or ""))


def state_of(quote: str) -> str:
    for name, abbr in _STATES:
        if re.search(rf"\b{name}\b", quote or "", re.I):
            return abbr
    found = _STATE_ABBR.search(quote or "")
    return found.group(1) if found else ""


def source_of(found) -> str:
    """Where the documents say it, as a person says it: "Spec Section 01 10 00", "Sheet M-001", else the document and
    page; "the documents" when the row names no place."""
    places = getattr(found, "places", ()) or ()
    if not places:
        return "the documents"
    place = places[0]
    section = (getattr(place, "section", None) or "").strip()
    if section:
        return f"Spec Section {section}" if _SECTION.match(section) else section
    sheet = (getattr(place, "sheet", None) or "").strip()
    if sheet:
        return f"Sheet {sheet}"
    document = (getattr(place, "document", "") or "").replace("\\", "/").rsplit("/", 1)[-1]
    page = getattr(place, "page", None)
    return f"{document} page {page}".strip() if document else "the documents"


def _rows(overview):
    """The overview rows that can speak to working hours or wages: the project conditions, then the standard lines
    the job speaks to; found ones only."""
    for row in (*(getattr(overview, "conditions", ()) or ()), *(getattr(overview, "standard_lines", ()) or ())):
        if getattr(row, "status", "") == "Found" and (getattr(row, "quote", "") or "").strip():
            yield row


def _condition(kind: str, source: str, quote: str) -> LaborCondition:
    if kind == OFF_HOURS:
        hours = hours_of(quote)
        return LaborCondition(kind=kind, source=source, quote=quote,
                              text=OFF_HOURS_LINE.format(hours=f" ({hours})" if hours else "", source=source))
    state = state_of(quote)
    return LaborCondition(kind=kind, source=source, quote=quote,
                          text=WAGE_LINE.format(state=f"{state} " if state else "", source=source))


def _sources(overview, ledger, notes):
    """(quote, source, strict) in order: the overview rows, the ledger facts (any kind and state), then the key notes.
    A fact or a note is strict (`calls_for_off_hours_work`); a fact from a sequence of operation or a points list,
    and a note in such a block, is left out."""
    if overview is not None:
        for row in _rows(overview):
            yield " ".join(row.quote.split()), source_of(row), False
    if ledger is not None:
        from estimator.ledger.facts import where_short
        for fact in ledger.facts.values():
            where = where_short(ledger.sources.get(fact.source_id, ""))
            if fact.kind == "sequence_match" or fact.stage == "sequence" or _SEQUENCE_PLACE.search(where):
                continue
            yield " ".join(str(fact.quote or "").split()), where or "the documents", True
    for note in notes or ():
        if _SEQUENCE_PLACE.search(getattr(note, "block", "") or ""):
            continue
        where = f"Sheet {note.sheet}" if getattr(note, "sheet", None) else (
            f"{(note.document or '').replace(chr(92), '/').rsplit('/', 1)[-1]} page {note.page}".strip())
        yield " ".join((note.text or "").split()), where or "the documents", True


def labor_conditions(overview, ledger=None, notes=()) -> tuple[LaborCondition, ...]:
    """At most one off-hours and one prevailing-wage condition, from the first source whose quote calls for it: the
    Spec overview rows (Found), then the ledger's facts, then the plans' key notes (T-008; a fact or a note only when
    it is about the work, not a control sequence: `calls_for_off_hours_work`)."""
    out: dict[str, LaborCondition] = {}
    for quote, source, strict in _sources(overview, ledger, notes):
        if not quote:
            continue
        off_hours = calls_for_off_hours_work(quote) if strict else calls_for_off_hours(quote)
        if OFF_HOURS not in out and off_hours:
            out[OFF_HOURS] = _condition(OFF_HOURS, source, quote)
        if PREVAILING_WAGE not in out and calls_for_prevailing_wage(quote):
            out[PREVAILING_WAGE] = _condition(PREVAILING_WAGE, source, quote)
    return tuple(out[k] for k in (OFF_HOURS, PREVAILING_WAGE) if k in out)


def labor_block(conditions) -> Block | None:
    """The "Labor Conditions" block (an unnumbered heading, like the Master Template's group headings), one red line
    per condition; None when there is none."""
    conditions = tuple(conditions or ())
    if not conditions:
        return None
    return Block(header=HEADING, numbered=False,
                 items=tuple(Item(kind="line", runs=(Run(text=c.text, red=True),)) for c in conditions))


def with_labor(draft, conditions):
    """The draft with the "Labor Conditions" block last in the base bid (before the alternates) and
    `scope.labor_conditions` set; the same draft when there is no condition. Raises `bms.render.RenderError` when the
    block no longer fits the price sheet."""
    from bms.render import RenderedLine, RenderError
    conditions = tuple(conditions or ())
    block = labor_block(conditions)
    if block is None:
        return draft
    data = draft.scope.model_dump()
    data["blocks"] = [*data["blocks"], block.model_dump()]
    data["labor_conditions"] = [c.model_dump() for c in conditions]
    try:
        scope = ScopeJob.model_validate(data)
        check_fit(scope)
    except (ValueError, PriceSheetError) as error:      # pydantic's ValidationError is a ValueError
        raise RenderError(f"the labor conditions cannot be printed: {error}") from error
    # traced last (the lines' trace keeps no mark of where the base bid ends; the scope holds the print order)
    traced = [RenderedLine(LABOR_KEY, None, "header", block.header, None, None)]
    traced += [RenderedLine(LABOR_KEY, None, "line", item.text, None, None) for item in block.items]
    return replace(draft, scope=scope, lines=(*draft.lines, *traced))


# ---- the warranty lines of the front end (T-005e addendum: the Master Template's front end, template ~83-86) -----

WARRANTY_WORDS = re.compile(r"\bwarranty\b", re.I)


def warranty_items(overview) -> tuple[Item, ...]:
    """The Master Template's warranty lines ("Warranty scope of work-", the one-year preventative maintenance
    contract, and the extension when the documents give its years), printed only when the Spec overview finds the
    warranty with its length stated (rules.md "Warranty lines"; the wording is assets/front_end.json "warranty", the
    old writer's `estimator.writing.front_end._warranty`). () when there is no overview or no warranty."""
    if overview is None or not getattr(overview, "services", None):
        return ()
    from estimator.writing.front_end import FRONT_END_FILE, _load, _warranty
    return tuple(_warranty(overview, _load(FRONT_END_FILE)["warranty"], [], []))


def with_warranty(draft, overview):
    """The draft with the warranty lines after the front end's lines (before its "*" clarification), traced under the
    front end (system key ""); the same draft when the documents state no warranty, or the writer already wrote a
    warranty line. Raises `bms.render.RenderError` when the front end can no longer be printed."""
    from bms.render import RenderedLine, RenderError
    items = warranty_items(overview)
    front = draft.scope.front_end
    if not items or any(WARRANTY_WORDS.search(i.text) for i in front.items if i.kind == "line"):
        return draft
    lines = [i for i in front.items if i.kind == "line"]
    notes = [i for i in front.items if i.kind != "line"]
    data = draft.scope.model_dump()
    data["front_end"] = {**front.model_dump(), "items": [i.model_dump() for i in (*lines, *items, *notes)]}
    try:
        scope = ScopeJob.model_validate(data)
        check_fit(scope)
    except (ValueError, PriceSheetError) as error:      # pydantic's ValidationError is a ValueError
        raise RenderError(f"the warranty lines cannot be printed: {error}") from error
    traced = list(draft.lines)
    at = max((n + 1 for n, line in enumerate(traced) if line.system_key == "" and line.kind != "note"), default=0)
    added = [RenderedLine("", None, "line", i.text, None, None) for i in items]
    return replace(draft, scope=scope, lines=(*traced[:at], *added, *traced[at:]))


# ---- the labor conditions as findings: the Evidence Package's Findings tab and Review.html (T-005e review 8) ------

LABOR_RULE = "Off-hours work and prevailing wage"      # the Playbook rule the T-005e report proposes


def labor_findings(conditions):
    """One "check" finding per condition, about the whole job (system key ""), so the estimator sees it on the review
    page and in the Evidence Package's Findings tab, with the documents' words and where they are."""
    from bms.model import Finding
    what = {OFF_HOURS: "The documents call for off-hours work", PREVAILING_WAGE: "The documents call for prevailing wage"}
    return tuple(Finding(rule=LABOR_RULE, system_key="", device_id=None, severity="check",
                         what=f"{what.get(c.kind, c.kind)} ({c.source}): \u201c{c.quote}\u201d. The proposal prints "
                              f"\u201c{c.text}\u201d in red.",
                         fix="Price the labor premium on the price sheet (its row is flagged red). The line follows "
                             "the documents: a decision on this card does not change it.")
                 for c in tuple(conditions or ()))
