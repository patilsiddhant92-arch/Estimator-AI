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
    r"\b(?:night|weekend|evening|second|third)s?[- ](?:work|shifts?|hours)\b|\bnights?\s+(?:and|or)\s+weekends?\b|"
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


def calls_for_off_hours(quote: str) -> bool:
    """True when the quote calls for work outside normal hours: its words, or a time range starting in the evening."""
    if _OFF_HOURS.search(quote or ""):
        return True
    found = _RANGE.search(quote or "")
    return bool(found) and "P" in _clock(found.group(1))


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


def labor_conditions(overview) -> tuple[LaborCondition, ...]:
    """At most one off-hours and one prevailing-wage condition, from the first row whose quote calls for it."""
    out: dict[str, LaborCondition] = {}
    if overview is None:
        return ()
    for row in _rows(overview):
        quote = " ".join(row.quote.split())
        if OFF_HOURS not in out and calls_for_off_hours(quote):
            hours = hours_of(quote)
            out[OFF_HOURS] = LaborCondition(kind=OFF_HOURS, source=source_of(row), quote=quote,
                                            text=OFF_HOURS_LINE.format(hours=f" ({hours})" if hours else "",
                                                                       source=source_of(row)))
        if PREVAILING_WAGE not in out and calls_for_prevailing_wage(quote):
            state = state_of(quote)
            out[PREVAILING_WAGE] = LaborCondition(kind=PREVAILING_WAGE, source=source_of(row), quote=quote,
                                                  text=WAGE_LINE.format(state=f"{state} " if state else "",
                                                                        source=source_of(row)))
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
