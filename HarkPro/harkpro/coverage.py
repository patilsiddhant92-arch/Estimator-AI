"""The coverage gate (critique.md, flow step 5): every controls fact in the ledger must end somewhere.

Input: the app's own Ledger.json and Job.json (plain dicts), optionally the Master Template line library
(`lines.json`), a dismissals file the estimator keeps, and an AI judge's answer.

A fact is controls-relevant when it names a controls concept (`harkpro.concepts`: a device such as a sensor,
thermostat, actuator, damper, leak detector, float, alarm, RAM, occupancy sensor, interlock, valve, integration,
lighting / Lutron / BACnet, or the ATC / controls / BMS / DDC contractor), or when it is a counted device symbol.
Equipment `family` facts are checked too: each must be a printed block or a block left out with a reason.

Each relevant fact must be accounted for by a SINK:
- a printed line (a device of a system or of the front end),
- an exception, a clarification (of a block, of the front end, or a job question),
- an explicit dismissal with a reason: a block the job leaves out with its `no_scope_reason`, or an estimator
  dismissal (`dismissals.json`: {"F12": "reason"} or {"dismissals": [{"fact_id": "F12", "reason": "..."}]}).

Matching is deterministic: a fact and a sink are LINKED when they share a system key, an equipment tag, a family
name, a source id or the fact's own id (a line citing it). A fact's PRIMARY concepts must each be covered by a linked
sink carrying that concept; a fact with only secondary concepts needs one of them covered (see `concepts.py`).
A fact linked to nothing can still be covered by the one line carrying its concept whose quantity equals the
fact's count ("concept+count"). Whatever is left goes to the AI judge request (written, never sent).

Severity: an uncovered primary concept is `must_fix` and fails the gate; an uncovered secondary-only fact is
`check`. A covered counted fact whose lines print fewer than it counts is a `count gap` (a check, listed apart).
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import appio
from .concepts import LABELS, PRIMARY, concepts, subject_concepts
from .doctrine import Library, load_lines

MUST_FIX, CHECK = "must_fix", "check"
ACCOUNTED, DISMISSED, PARTIAL, UNACCOUNTED = "accounted", "dismissed", "partial", "unaccounted"
ANY = "*"          # a dismissal covers every concept of the facts it links to

_TIMES = re.compile(r"(?:×|(?<![0-9A-Za-z])x)\s*(\d{1,3})\b")
# a left-out reason that only says the documents were not read is not a dismissal
WEAK_REASON = re.compile(r"could not be read|not (?:be )?read|held as a question|unreadable|to be confirmed", re.I)
# rulings R2 (HarkPro/doctrine/rulings.md): controls items the documents give to the mechanical contractor are AME's
R2_REASON = re.compile(r"mechanical contractor|\bMC\b|HVAC contractor", re.I)


def reason_problem(reason: str) -> str:
    """Why a left-out reason is not a dismissal, or "" when it stands."""
    if WEAK_REASON.search(reason or ""):
        return "the reason only says the documents were not read or the item is a question"
    if R2_REASON.search(reason or ""):
        return "rulings R2: controls items the documents give to the mechanical contractor are AME's scope"
    return ""


# the rulings that name the line a concept must print as (rulings.md); their lines rank first in suggestions
RULING_LINES: dict[str, tuple[str, tuple[str, ...]]] = {
    "leak": ("R3", ("leak_detection.01",)),
    "high_water": ("R4", ("condensate_pump.01",)),
    "local_alarm": ("R5", ("leak_detection.02", "condensate_pump.02", "split_system.04", "vrf_system.04",
                           "crac.05")),
    "damper": ("R6", ("motorized_dampers.01",)),
    "radiation": ("R7", ("finned_tube_radiation.02", "finned_tube_radiation.01")),
    "interlock": ("R7", ("finned_tube_radiation.02",)),
    "occupancy": ("R8", ("occupancy_sensors.01", "occupancy_sensors.02")),
    "lighting_integration": ("R9", ("front_end.21",)),
}

# exclusions the house proposal template always prints; each dismisses its one concept wherever it appears
STANDARD_EXCLUSIONS = (
    ("fire_smoke", "All fire alarm system or components, smoke, combination fire/smoke dampers, smoke detectors and "
                   "associated wiring (house template exclusion)"),
)
_STOP = frozenset("the a an of for to with at in on and each new per via by from all as is are be shall unit units "
                  "provide provided contractor".split())


# ---- sinks --------------------------------------------------------------------------------------------------


@dataclass
class Sink:
    id: str
    type: str                 # line | clarification | exception | question | dismissal | front_end | block
    system_key: str
    text: str
    concepts: set[str]
    keys: set[str]
    quantity: int | None = None
    reason: str = ""
    refs: tuple = ()


def _same_passage(a: str, b: str) -> bool:
    """Two quotes of one passage: one holds the other, or they share most of their words."""
    a, b = " ".join(str(a).casefold().split()), " ".join(str(b).casefold().split())
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    ta, tb = set(re.findall(r"[a-z0-9]+", a)), set(re.findall(r"[a-z0-9]+", b))
    return len(ta & tb) / max(1, min(len(ta), len(tb))) >= 0.6


def _system_keys(system: dict) -> set[str]:
    keys = {f"sys:{system.get('key', '')}"}
    for fam in system.get("families") or []:
        keys |= {f"tag:{appio.norm_tag(t)}" for t in fam.get("tags") or []}
        name = _family_phrase(fam.get("name", ""))
        if name:
            keys.add(f"fam:{name}")
    return keys


def _family_phrase(name: str) -> str:
    """A family name as a phrase to look for in a fact ("Condensate Pump" -> "condensate pump"); "" when too short."""
    words = re.sub(r"[^a-z0-9 ]", " ", str(name).casefold()).split()
    phrase = " ".join(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in words)
    return phrase if len(phrase) >= 6 else ""


def _ref_keys(refs) -> set[str]:
    out = set()
    for r in refs or []:
        sid = str((r or {}).get("source_id", "")).strip().strip("[]")
        if sid:
            out.add(f"src:{sid}")
            if sid.upper().startswith("F"):
                out.add(f"fid:{sid.upper()}")
    return out


def build_sinks(job: dict, printed: dict[str, str] | None = None) -> list[Sink]:
    sinks: list[Sink] = []
    systems = {s.get("key", ""): s for s in job.get("systems") or []}
    for line in appio.job_lines(job, printed):
        system = systems.get(line.system_key)
        keys = (_system_keys(system) if system else {f"sys:{line.system_key}"}) | _ref_keys(line.refs)
        text = f"{line.text} | {line.name} | {line.slot.replace('_', ' ')}"
        sinks.append(Sink(line.id, "line", line.system_key, line.text, concepts(text), keys, line.quantity,
                          refs=tuple(line.refs)))
    for key, system in systems.items():
        for n, c in enumerate(system.get("clarifications") or [], 1):
            sinks.append(Sink(f"{key}.c{n}", "clarification", key, f"*{c.get('kind', '')}: {c.get('text', '')}",
                              concepts(c.get("text", "")), _system_keys(system)))
        if system.get("no_scope_reason") and not system.get("devices") and not reason_problem(
                system["no_scope_reason"]):
            # a block left out dismisses only what its reason speaks to (and the block's own equipment)
            sinks.append(Sink(f"{key}.left_out", "dismissal", key, f"{system.get('name', key)} left out",
                              concepts(system["no_scope_reason"]) | {"controls"}, _system_keys(system),
                              reason=system["no_scope_reason"]))
    fe = job.get("front_end") or {}
    if fe:
        for n, c in enumerate(fe.get("clarifications") or [], 1):
            sinks.append(Sink(f"FE.c{n}", "clarification", "FE", f"*{c.get('kind', '')}: {c.get('text', '')}",
                              concepts(c.get("text", "")), {"sys:FE"}))
        name = fe.get("existing_system_name") or ""
        sinks.append(Sink("FE.mode", "front_end", "FE", f"Front end: {fe.get('mode', '')} {name}".strip(),
                          {"controls", "integration"}, {"sys:FE"}))
    for n, e in enumerate(job.get("exceptions") or [], 1):
        keys = {f"sys:{e.get('system_key', '')}"} | _ref_keys(e.get("refs")) | {f"tag:{t}" for t in
                                                                               appio.tags_in(e.get("text", ""))}
        if e.get("system_key") in systems:
            keys |= _system_keys(systems[e["system_key"]])
        sinks.append(Sink(f"EXC{n}", "exception", e.get("system_key", ""), e.get("text", ""),
                          concepts(e.get("text", "")), keys))
    for n, (concept, text) in enumerate(STANDARD_EXCLUSIONS, 1):
        sinks.append(Sink(f"STD{n}", "standard_exclusion", "", text, {concept}, {"std:all"}, reason=text))
    for n, q in enumerate(job.get("questions") or [], 1):
        text = q if isinstance(q, str) else json.dumps(q)
        keys = {f"tag:{t}" for t in appio.tags_in(text)}
        keys |= {f"sys:{k}" for k in systems if len(k) >= 2 and re.search(rf"\b{re.escape(k)}\b", text)}
        sinks.append(Sink(f"Q{n}", "question", "", text, concepts(text), keys))
    return sinks


def dismissal_sinks(dismissals: dict[str, str]) -> list[Sink]:
    return [Sink(f"DISMISS.{fid}", "dismissal", "", f"Dismissed by the estimator: {fid}", {ANY}, {f"fid:{fid}"},
                 reason=reason) for fid, reason in dismissals.items()]


def load_dismissals(path) -> dict[str, str]:
    if not path:
        return {}
    data = appio.load_json(path)
    if isinstance(data, dict) and isinstance(data.get("dismissals"), list):
        return {str(d["fact_id"]).upper(): str(d.get("reason", "")) for d in data["dismissals"] if d.get("fact_id")}
    return {str(k).upper(): str(v) for k, v in (data or {}).items()}


# ---- facts --------------------------------------------------------------------------------------------------


def fact_text(fact: dict) -> str:
    return " ".join(str(fact.get(k, "")) for k in ("subject", "value", "quote"))


def fact_keys(fact: dict, job: dict) -> set[str]:
    text = fact_text(fact)
    upper, lower = text.upper(), " ".join(re.sub(r"[^a-z0-9 ]", " ", text.casefold()).split())
    keys = {f"fid:{str(fact.get('id', '')).upper()}", "std:all"}
    if fact.get("source_id"):
        keys.add(f"src:{fact['source_id']}")
    keys |= {f"tag:{t}" for t in appio.tags_in(text)}
    subject = str(fact.get("subject", "")).strip()
    for system in job.get("systems") or []:
        key = system.get("key", "")
        if key and (subject.upper() == key.upper() or (len(key) >= 2 and re.search(
                rf"(?<![A-Z0-9-]){re.escape(key.upper())}(?![A-Z0-9-])", upper))):
            keys.add(f"sys:{key}")
        for fam in system.get("families") or []:
            phrase = _family_phrase(fam.get("name", ""))
            if phrase and re.search(rf"\b{re.escape(phrase)}s?\b", lower):
                keys.add(f"fam:{phrase}")
    if fact.get("kind") == "front_end":
        keys.add("sys:FE")
    return keys


def fact_count(fact: dict) -> int | None:
    value = fact.get("value")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    times = [int(n) for n in _TIMES.findall(str(fact.get("quote", "")))]
    return max(times) if times else None


# ---- the result ---------------------------------------------------------------------------------------------


@dataclass
class Cover:
    concept: str
    sink_id: str
    sink_type: str
    method: str               # linked | concept+count | dismissal | block | ai_judge
    sink_text: str = ""
    reason: str = ""


@dataclass
class Suggestion:
    concept: str
    family_id: str
    line_id: str
    text: str
    score: float
    ruling: str = ""


@dataclass
class FactResult:
    fact_id: str
    kind: str
    subject: str
    value: str
    quote: str
    source_id: str
    citation: str
    concepts: list[str]
    status: str
    severity: str = ""
    covered_by: list[Cover] = field(default_factory=list)
    uncovered: list[str] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)       # sink ids a judge should look at
    suggestions: list[Suggestion] = field(default_factory=list)
    count: int | None = None
    printed_count: int | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class RulingFlag:
    ruling: str
    line_id: str
    text: str
    what: str
    fix: str
    severity: str = MUST_FIX


def ruling_flags(job: dict, printed: dict[str, str] | None = None, library: Library | None = None) -> list[RulingFlag]:
    """Printed lines a decided ruling says are worded or owned wrongly (R2, R3, R4, R6)."""
    by_id = {l.id: l.text for l in (library.lines if library else [])}
    out = []
    for line in appio.job_lines(job, printed):
        found = concepts(f"{line.text} {line.name}")
        mc = "Mechanical Contractor" in (line.furnished_by, line.installed_by) or bool(
            re.search(r"furnished by mechanical contractor", line.text, re.I))
        if mc and "high_water" in found:
            out.append(RulingFlag("R4", line.id, line.text, "a condensate pump float / high water alarm is printed "
                                  "as furnished by the mechanical contractor",
                                  by_id.get("condensate_pump.01", "Tie-in Condensate Pump Float Switch (Furnished by "
                                                                  "Mfr.)")))
        elif mc and "leak" in found:
            out.append(RulingFlag("R3", line.id, line.text, "a leak detector is printed as the mechanical "
                                  "contractor's", by_id.get("leak_detection.01", "Furnish and Install Leak Sensor")))
        elif mc and found & PRIMARY:
            out.append(RulingFlag("R2", line.id, line.text, "a controls item is printed as the mechanical "
                                  "contractor's; controls items by the MC are AME's", "Use the normal AME verb."))
        if "damper" in found and re.search(r"\bper\s+(?:unit|fan)\b", line.assumption or "", re.I):
            out.append(RulingFlag("R6", line.id, line.text, f"the damper count is assumed: {line.assumption}",
                                  "Count every damper shown on the plans, tagged or not; never one per unit."))
    return out


@dataclass
class CoverageResult:
    job_name: str
    passed: bool
    facts: list[FactResult]
    count_gaps: list[dict]
    sinks: int
    library: str
    judge_request: str = ""
    rulings: list[RulingFlag] = field(default_factory=list)

    @property
    def unaccounted(self) -> list[FactResult]:
        return [f for f in self.facts if f.status in (UNACCOUNTED, PARTIAL)]

    def summary(self) -> dict:
        counts = {s: sum(f.status == s for f in self.facts) for s in (ACCOUNTED, DISMISSED, PARTIAL, UNACCOUNTED)}
        return {"relevant_facts": len(self.facts), **counts,
                "must_fix": sum(f.severity == MUST_FIX for f in self.unaccounted),
                "check": sum(f.severity == CHECK for f in self.unaccounted),
                "count_gaps": len(self.count_gaps), "ruling_flags": len(self.rulings), "passed": self.passed}

    def to_dict(self) -> dict:
        return {"job_name": self.job_name, "passed": self.passed, "summary": self.summary(),
                "library": self.library, "judge_request": self.judge_request,
                "unaccounted": [asdict(f) for f in self.unaccounted], "count_gaps": self.count_gaps,
                "ruling_flags": [asdict(r) for r in self.rulings],
                "facts": [asdict(f) for f in self.facts]}


# ---- the gate -----------------------------------------------------------------------------------------------


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", str(text).casefold()) if w not in _STOP and len(w) > 1}


def suggest(concept: str, fact: dict, keys: set[str], library: Library, limit: int = 2) -> list[Suggestion]:
    if not library:
        return []
    systems = {k[4:].upper() for k in keys if k.startswith("sys:")}
    if "FE" in systems:
        systems.add("FRONT_END")
    words = _tokens(fact_text(fact))
    scored = []
    for ln in library.lines:
        if concept not in concepts(f"{ln.text} {ln.id}") and ln.id not in RULING_LINES.get(concept, ("", ()))[1]:
            continue
        score = 1.0
        fam_words = _tokens(f"{ln.family_id.replace('_', ' ')} {ln.family_name}")
        aliases = {a.upper() for a in ln.aliases} | {ln.family_id.upper()}
        if aliases & systems or (fam_words & {s.casefold() for s in systems}):
            score += 2.0
        if concept in concepts(f"{ln.family_id.replace('_', ' ')} {ln.family_name}"):
            score += 1.0      # the family is about this very device (occupancy_sensors, leak_detection, ...)
        if ln.verb == "note" or ln.text.lstrip().startswith("*"):
            score -= 0.75
        score += 0.5 * len(fam_words & words) + 0.25 * len(_tokens(ln.text) & words)
        ruling, ids = RULING_LINES.get(concept, ("", ()))
        if ln.id in ids:
            score += 5.0 - 0.1 * ids.index(ln.id)
        scored.append(Suggestion(concept, ln.family_id, ln.id, ln.text, round(score, 2),
                                 ruling if ln.id in ids else ""))
    scored.sort(key=lambda s: (-s.score, s.line_id))
    return scored[:limit]


def _family_result(fact: dict, ledger: dict, job: dict, sinks: list[Sink]) -> FactResult:
    subject = str(fact.get("subject", ""))
    res = FactResult(fact["id"], "family", subject, str(fact.get("value", "")), str(fact.get("quote", "")),
                     str(fact.get("source_id", "")), appio.where(ledger, str(fact.get("source_id", ""))),
                     ["equipment"], UNACCOUNTED)
    for system in job.get("systems") or []:
        names = {appio.norm_tag(system.get("key", ""))} | {appio.norm_tag(f.get("name", "")) for f in
                                                          system.get("families") or []}
        if appio.norm_tag(subject) in names or appio.norm_tag(str(fact.get("value", ""))) in names:
            if system.get("devices"):
                res.status = ACCOUNTED
                res.covered_by.append(Cover("equipment", system["key"], "block", "block", system.get("name", "")))
            elif system.get("no_scope_reason") and reason_problem(system["no_scope_reason"]):
                res.status = UNACCOUNTED      # "could not be read" / "by the MC" is not a dismissal
                res.covered_by.append(Cover("equipment", system["key"], "dismissal", "rejected dismissal",
                                            system.get("name", ""), f"{system['no_scope_reason']} [REJECTED: "
                                            f"{reason_problem(system['no_scope_reason'])}]"))
            elif system.get("no_scope_reason"):
                res.status = DISMISSED
                res.covered_by.append(Cover("equipment", system["key"], "dismissal", "dismissal",
                                            system.get("name", ""), system["no_scope_reason"]))
            else:
                res.status = UNACCOUNTED
            break
    if res.status == UNACCOUNTED:
        dismissed = [s for s in sinks if s.type == "dismissal" and f"fid:{fact['id'].upper()}" in s.keys]
        if dismissed:
            res.status = DISMISSED
            res.covered_by.append(Cover("equipment", dismissed[0].id, "dismissal", "dismissal", "",
                                        dismissed[0].reason))
        else:
            res.severity = MUST_FIX
            res.uncovered = ["equipment"]
    return res


def check(ledger: dict, job: dict, library: Library | None = None, dismissals: dict[str, str] | None = None,
          printed: dict[str, str] | None = None) -> CoverageResult:
    library = library if library is not None else load_lines()
    sinks = build_sinks(job, printed) + dismissal_sinks(dismissals or {})
    lines = [s for s in sinks if s.type == "line"]
    results: list[FactResult] = []
    gaps: list[dict] = []
    for fact in appio.fact_list(ledger):
        if fact.get("kind") == "family":
            results.append(_family_result(fact, ledger, job, sinks))
            continue
        found = concepts(fact_text(fact)) | subject_concepts(str(fact.get("subject", "")))
        if not found:
            continue
        keys = fact_keys(fact, job)
        linked = [s for s in sinks if s.keys & keys]
        primary = sorted(found & PRIMARY)
        secondary = sorted(found - PRIMARY)
        count = fact_count(fact)
        count_concepts = (subject_concepts(str(fact.get("subject", ""))) & PRIMARY) or set(primary)
        res = FactResult(fact["id"], fact.get("kind", ""), str(fact.get("subject", "")), str(fact.get("value", "")),
                         str(fact.get("quote", "")), str(fact.get("source_id", "")),
                         appio.where(ledger, str(fact.get("source_id", ""))), sorted(found), UNACCOUNTED, count=count)

        def cover(concept: str) -> Cover | None:
            for s in sorted(linked, key=lambda s: s.type != "line"):
                if concept in s.concepts and s.type not in ("dismissal", "standard_exclusion"):
                    return Cover(concept, s.id, s.type, "linked", s.text)
            for s in linked:
                if s.type in ("dismissal", "standard_exclusion") and (ANY in s.concepts or concept in s.concepts):
                    return Cover(concept, s.id, s.type, "dismissal", s.text, s.reason)
            if count is not None and concept in count_concepts:
                # a counted symbol linked to nothing: the job's lines of that concept take it (a count gap shows
                # when they print fewer)
                same = [s for s in lines if concept in s.concepts]
                if same:
                    pick = next((s for s in same if s.quantity == count), same[0])
                    return Cover(concept, pick.id, pick.type, "concept+count", pick.text)
            return None

        if primary:
            for c in primary:
                got = cover(c)
                (res.covered_by.append(got) if got else res.uncovered.append(c))
        else:
            got = None
            for c in secondary:
                got = cover(c)
                if got:
                    res.covered_by.append(got)
                    break
            if got is None:
                # context only (a status point, "BMS connection"): a line citing this very source accounts for it
                fid, sid = str(fact.get("id", "")).upper(), str(fact.get("source_id", ""))
                cited = next((s for s in linked if s.type == "line" and (f"fid:{fid}" in s.keys or any(
                    str(r.get("source_id", "")) == sid and _same_passage(r.get("quote", ""), fact.get("quote", ""))
                    for r in s.refs))), None)
                if cited:
                    got = Cover(secondary[0], cited.id, cited.type, "cites the source", cited.text)
                    res.covered_by.append(got)
            if got is None and "controls" in secondary:
                plain = next((s for s in linked if s.type not in ("dismissal", "standard_exclusion")), None)
                if plain:
                    res.covered_by.append(Cover("controls", plain.id, plain.type, "linked", plain.text))
            if not res.covered_by:
                res.uncovered = list(secondary)
        for system in job.get("systems") or []:
            why = reason_problem(system.get("no_scope_reason") or "") if not system.get("devices") else ""
            if why and (_system_keys(system) & keys):
                res.notes.append(f"{system.get('key')} is left out ({system['no_scope_reason']}), not accepted as a "
                                 f"dismissal: {why}")
        if res.uncovered:
            res.status = PARTIAL if res.covered_by else UNACCOUNTED
            res.severity = MUST_FIX if set(res.uncovered) & PRIMARY else CHECK
            for c in res.uncovered:
                # a context concept (panel, controller, ...) is in almost every family: suggest only a line of
                # the fact's own family, never a guess from an unrelated one
                res.suggestions += [g for g in suggest(c, fact, keys, library) if c in PRIMARY or g.score >= 3]
            res.candidates = sorted({s.id for s in sinks if s.type != "standard_exclusion" and
                                     ((set(res.uncovered) & s.concepts) or s in linked)})
        elif all(c.method == "dismissal" for c in res.covered_by):
            res.status = DISMISSED
        else:
            res.status = ACCOUNTED
        # the count: a covered counted concept whose lines (job-wide) print fewer than the fact counts
        if count is not None:
            for c in sorted(count_concepts):
                if c in res.uncovered or any(cv.concept == c and cv.method == "dismissal" for cv in res.covered_by):
                    continue
                same = [s for s in lines if c in s.concepts]
                known = [s.quantity for s in same if s.quantity is not None]
                total = sum(known) if known else None
                res.printed_count = total
                if same and total is not None and total < count:
                    gaps.append({"fact_id": fact["id"], "concept": c, "label": LABELS.get(c, c), "fact_count": count,
                                 "printed": total, "lines": [s.id for s in same], "citation": res.citation,
                                 "quote": res.quote,
                                 "severity": MUST_FIX if c == "damper" else CHECK,
                                 "ruling": "R6" if c == "damper" else "R1"})
        results.append(res)
    result = CoverageResult(str(job.get("name") or ledger.get("job_name") or ""), False, results, gaps, len(sinks),
                            library.path if library else "", rulings=ruling_flags(job, printed, library))
    result.passed = gate_passes(result)
    return result


def gate_passes(result: "CoverageResult") -> bool:
    """The gate blocks on any must-fix: an unaccounted fact, a damper count gap (R6) or a printed line a decided
    ruling contradicts."""
    return not (any(r.severity == MUST_FIX and r.status in (UNACCOUNTED, PARTIAL) for r in result.facts)
                or any(g.get("severity") == MUST_FIX for g in result.count_gaps)
                or any(f.severity == MUST_FIX for f in result.rulings))


# ---- the AI judge hook (written, never sent) ------------------------------------------------------------------

JUDGE_INSTRUCTIONS = (
    "You are the coverage judge for a BMS/DDC controls proposal. Each item is a fact from the job's documents that "
    "the deterministic gate could not place. For each uncovered concept of each fact, answer one verdict: "
    "'covered' (name the sink_id that already prints or clarifies it), 'missing' (the proposal must add it: name a "
    "line_id from the suggestions when one fits) or 'dismiss' (it needs no line: give the reason an estimator would "
    "accept). Use only the facts, sinks and suggestions given; never invent a source.")

JUDGE_SCHEMA = {
    "type": "object", "required": ["verdicts"], "additionalProperties": False,
    "properties": {"verdicts": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["fact_id", "concept", "verdict", "sink_id", "line_id", "reason"],
        "properties": {"fact_id": {"type": "string"}, "concept": {"type": "string"},
                       "verdict": {"type": "string", "enum": ["covered", "missing", "dismiss"]},
                       "sink_id": {"type": ["string", "null"]}, "line_id": {"type": ["string", "null"]},
                       "reason": {"type": "string"}}}}}}


def judge_request(result: CoverageResult, ledger: dict, job: dict, printed: dict[str, str] | None = None) -> dict:
    sinks = {s.id: s for s in build_sinks(job, printed)}
    items = []
    for f in result.unaccounted:
        items.append({"fact_id": f.fact_id, "kind": f.kind, "subject": f.subject, "value": f.value,
                      "quote": f.quote, "citation": f.citation, "uncovered": f.uncovered,
                      "uncovered_labels": [LABELS.get(c, c) for c in f.uncovered],
                      "already_covered": [asdict(c) for c in f.covered_by],
                      "candidate_sinks": [{"id": s.id, "type": s.type, "system": s.system_key, "text": s.text}
                                          for i in f.candidates if (s := sinks.get(i))],
                      "suggestions": [asdict(s) for s in f.suggestions]})
    return {"task": "harkpro.coverage.judge", "version": 1, "job_name": result.job_name,
            "instructions": JUDGE_INSTRUCTIONS, "answer_schema": JUDGE_SCHEMA, "items": items}


def apply_judge(result: CoverageResult, answer: dict) -> CoverageResult:
    """Fold a judge's answer (shaped as JUDGE_SCHEMA) into the result: 'covered' and 'dismiss' close a concept;
    'missing' keeps it open and records the judge's line pick as the first suggestion."""
    by_id = {f.fact_id: f for f in result.facts}
    for v in (answer or {}).get("verdicts") or []:
        f = by_id.get(str(v.get("fact_id", "")))
        concept = str(v.get("concept", ""))
        if f is None or concept not in f.uncovered:
            continue
        if v.get("verdict") in ("covered", "dismiss"):
            f.uncovered.remove(concept)
            method = "ai_judge" if v["verdict"] == "covered" else "dismissal"
            f.covered_by.append(Cover(concept, str(v.get("sink_id") or ""), "ai_judge", method, "",
                                      str(v.get("reason", ""))))
        elif v.get("line_id"):
            f.suggestions.insert(0, Suggestion(concept, "", str(v["line_id"]), "(judge pick)", 99.0))
        if not f.uncovered:
            f.status = DISMISSED if all(c.method == "dismissal" for c in f.covered_by) else ACCOUNTED
            f.severity = ""
        else:
            f.severity = MUST_FIX if set(f.uncovered) & PRIMARY else CHECK
    result.passed = gate_passes(result)
    return result


# ---- reports ------------------------------------------------------------------------------------------------


def _md_cell(text, limit: int = 140) -> str:
    text = " ".join(str(text or "").split()).replace("|", "/")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def markdown(result: CoverageResult) -> str:
    s = result.summary()
    out = [f"# Coverage gate: {result.job_name}", "",
           f"**{'PASS' if result.passed else 'FAIL'}**: {s['relevant_facts']} controls facts; {s['accounted']} "
           f"accounted, {s['dismissed']} dismissed, {s['partial']} partly covered, {s['unaccounted']} unaccounted "
           f"({s['must_fix']} must fix, {s['check']} to check); {s['count_gaps']} count gaps; "
           f"{s['ruling_flags']} printed lines against the rulings.", ""]
    if result.library:
        out += [f"Line library: `{Path(result.library).name}`", ""]
    else:
        out += ["Line library: none found (suggestions name the concept only).", ""]
    out += ["## Unaccounted", "", "| Fact | Sev | Status | Missing | Fact | Citation | Suggested line |",
            "|---|---|---|---|---|---|---|"]
    for f in result.unaccounted:
        sug = "; ".join(f"{g.line_id} {g.text}" + (f" [{g.ruling}]" if g.ruling else "")
                        for g in f.suggestions[:2]) or "—"
        why = (" — " + " ".join(f.notes) if f.notes else "") + "".join(
            f" — {c.reason}" for c in f.covered_by if c.method == "rejected dismissal")
        out.append(f"| {f.fact_id} | {f.severity} | {f.status} | {', '.join(LABELS.get(c, c) for c in f.uncovered)} "
                   f"| {_md_cell(f'{f.subject} = {f.value}' + why, 260)} | {_md_cell(f.citation, 70)} "
                   f"| {_md_cell(sug, 120)} |")
    out += ["", "## Count gaps", "", "| Fact | Concept | Counted | Printed | Lines | Sev | Citation |",
            "|---|---|---|---|---|---|---|"]
    for g in result.count_gaps:
        out.append(f"| {g['fact_id']} | {g['label']} | {g['fact_count']} | {g['printed']} | {', '.join(g['lines'])} "
                   f"| {g['severity']} ({g['ruling']}) | {_md_cell(g['citation'], 70)} |")
    out += ["", "## Printed lines against the rulings", "", "| Ruling | Line | Printed | What | Fix |",
            "|---|---|---|---|---|"]
    for r in result.rulings:
        out.append(f"| {r.ruling} | {r.line_id} | {_md_cell(r.text, 70)} | {_md_cell(r.what, 120)} "
                   f"| {_md_cell(r.fix, 80)} |")
    out += ["", "## Dismissed (check the reasons)", ""]
    for f in result.facts:
        if f.status == DISMISSED:
            reason = next((c.reason for c in f.covered_by if c.reason), "")
            out.append(f"- {f.fact_id} {_md_cell(f.subject, 60)}: {_md_cell(reason, 160)}")
    out += ["", "## Accounted", ""]
    for f in result.facts:
        if f.status == ACCOUNTED:
            out.append(f"- {f.fact_id} {_md_cell(f.subject, 60)} → " + ", ".join(
                f"{c.concept}:{c.sink_id} ({c.method})" for c in f.covered_by))
    return "\n".join(out) + "\n"


def run(ledger_path, job_path, out_dir, lines_path=None, dismissals_path=None, judge_answer_path=None,
        use_app_render: bool = True) -> CoverageResult:
    ledger, job = appio.load_json(ledger_path), appio.load_json(job_path)
    printed = appio.printed_texts(job) if use_app_render else {}
    result = check(ledger, job, load_lines(lines_path), load_dismissals(dismissals_path), printed)
    if judge_answer_path:
        apply_judge(result, appio.load_json(judge_answer_path))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    name = result.job_name or "job"
    if result.unaccounted:
        req = out / f"{name} coverage judge request.json"
        req.write_text(json.dumps(judge_request(result, ledger, job, printed), indent=2, ensure_ascii=False),
                       encoding="utf-8")
        result.judge_request = str(req)
    (out / f"{name} coverage.json").write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False),
                                               encoding="utf-8")
    (out / f"{name} coverage.md").write_text(markdown(result), encoding="utf-8")
    return result
