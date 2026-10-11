"""The Job model (rebuild design 2026-10-04 §4.2 and §4.3): what the planner builds, the AI fills, the validators
check, the review page edits and the renderer prints. Frozen dataclasses; every list is a tuple.

- `to_dict()` / `from_dict()` give a lossless JSON round-trip (tuples become lists and back). `from_dict` is strict:
  an unknown key, a missing required key, a wrong type or a value outside an enumeration raises `ModelError`.
- `json_schema(cls)` gives the JSON Schema the AI steps answer to (Anthropic structured outputs: every property
  required, no additional properties, `null` allowed only where the model allows None, nothing is `$ref`'d).
- `schema_errors(value, schema)` is the small schema check the AI steps run on an answer before `from_dict`
  (`jsonschema` is not a dependency): it understands exactly the keywords `json_schema` produces.

Every Device carries at least one Ref (enforced at construction), and so does every Unit. `Count.value` None means the
count is unknown and prints "Qty (##)". The enumerations below are the only values allowed.

The takeoff register (takeoff pass plan 2026-10-11) sits on the Job: `sheets` (what each drawing sheet is), `units` (the
units the documents show), `set_aside` (the counts set aside, with both numbers) and `future_items`. `bms.takeoff`
fills it. Stage 1 only stores it: no count reads it. A Job saved before the fields loads with all four empty.
"""
from __future__ import annotations

import dataclasses
import json
import types

from dataclasses import dataclass, field
from typing import Literal, Union, get_args, get_origin, get_type_hints

# ---- enumerations (exact values of design §4.2) ------------------------------------------------------------

Verb = Literal["Furnish and Install", "Furnish", "Furnish and Wire", "Install and Wire", "Wire"]
Control = Literal["packaged", "field", "integration", "none"]
Flag = Literal["none", "quantity", "ownership", "assumed"]
ClarificationKind = Literal["confirm", "assumed", "per_drawings", "note"]
AlternateKind = Literal["base", "add", "deduct"]
Party = Literal["AME", "Unit Mfr.", "FA", "Mechanical Contractor", "Electrical Contractor", "Others", "Owner"]
Severity = Literal["must_fix", "check"]
FrontEndMode = Literal["new-system", "extend-existing"]
DecisionAction = Literal["accept", "change", "delete"]
# A device line the estimator must see (T-005 ruling 7): "future" for an item the documents mark FUTURE (it prints with
# "(<mark_note>)" in red font), "notice" for an item to notice (the line prints red); "" for none.
Mark = Literal["", "future", "notice"]
# the takeoff register's enumerations (takeoff pass plan 2026-10-11)
SheetKind = Literal["new_work", "demolition", "part_plan", "enlarged_plan", "riser", "schedule", "detail",
                    "control_diagram", "other"]
UnitStatus = Literal["new", "demolish", "demolish_with_work", "existing_remain", "relocate", "future"]
SetAsideReason = Literal["demolition sheet", "same unit labelled again", "part plan of one area", "future item",
                         "existing to remain", "not a unit of this family"]

# What the proposal prints for an existing BMS the documents do not name (rules.md "Front end mode"; the same fill-in as
# assets/front_end.json existing_systems.unnamed): square brackets, so it reads as a blank to complete. The planner asks
# for the name in a question; the model keeps `existing_system_name` None.
UNNAMED_EXISTING = "[existing BMS name]"

VERBS: tuple[str, ...] = get_args(Verb)
CONTROLS: tuple[str, ...] = get_args(Control)
FLAGS: tuple[str, ...] = get_args(Flag)
CLARIFICATION_KINDS: tuple[str, ...] = get_args(ClarificationKind)
ALTERNATES: tuple[str, ...] = get_args(AlternateKind)
PARTIES: tuple[str, ...] = get_args(Party)
SEVERITIES: tuple[str, ...] = get_args(Severity)
FRONT_END_MODES: tuple[str, ...] = get_args(FrontEndMode)
DECISION_ACTIONS: tuple[str, ...] = get_args(DecisionAction)
MARKS: tuple[str, ...] = get_args(Mark)
SHEET_KINDS: tuple[str, ...] = get_args(SheetKind)
UNIT_STATUSES: tuple[str, ...] = get_args(UnitStatus)
SET_ASIDE_REASONS: tuple[str, ...] = get_args(SetAsideReason)
# the unit statuses whose units count toward a family's number (ruling 17: a unit shown for removal, kept as it is,
# relocated or marked future does not; those print in the Demolition Scope or as future items)
COUNTED_STATUSES: tuple[str, ...] = ("new",)


class ModelError(ValueError):
    """A dict that is not a valid model object; the message names the path ("systems[2].devices[0].verb")."""


def _doc(text: str, **extra) -> dict:
    return {"metadata": {"doc": text, **extra}}


# ---- the model ---------------------------------------------------------------------------------------------


class _Model:
    """Shared JSON round-trip for every model class."""

    def to_dict(self) -> dict:
        return _to_json(self)

    @classmethod
    def from_dict(cls, data: dict):
        return _from_json(cls, data, cls.__name__)

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str):
        return cls.from_dict(json.loads(text))


@dataclass(frozen=True)
class Ref(_Model):
    """A citation from this job: the dossier / ledger source id, the exact words, and where they are."""
    source_id: str = field(**_doc('The source id as the dossier and ledger give it, without brackets: "S41", "I2", '
                                  '"Q7", "F17".'))
    quote: str = field(**_doc("The exact words of the source (copied, never paraphrased)."))
    where: str = field(**_doc('The place: sheet, spec section or page, e.g. "M-201, Drawings.pdf page 3".'))


@dataclass(frozen=True)
class OtherCount(_Model):
    """A count another source gives, different from the printed one; it prints in the quantity note."""
    value: int = field(**_doc("The number this source gives."))
    ref: Ref = field(**_doc("Where that number is."))


@dataclass(frozen=True)
class Count(_Model):
    """A quantity. `value` is the printed count, the highest any source gives (never undershoot); "Qty (##)" prints
    only when it is None and no other count is known (`highest()` is what prints). `sources` back `value`; `others`
    are every different count, each with its source. `added_up` is the plain sum over the plan sheets of one floor and
    area (ruling L1), kept only while it is above the printed count: it is never a count that prints (`highest()`
    ignores it, so it is not one of `others`), and the proposal's "*" note names both numbers."""
    value: int | None = field(**_doc('The printed count (the highest found); null when unknown ("Qty (##)").'))
    sources: tuple[Ref, ...] = field(default=(), **_doc("The citations that give the printed count."))
    others: tuple[OtherCount, ...] = field(default=(), **_doc("Every other, different count, with its source."))
    added_up: OtherCount | None = field(default=None, **_doc(
        'The plain sum over sheets of the same floor and area, when it is higher than the printed count (ruling L1). '
        'It never prints as the count; a "*" note names both numbers.'))

    def highest(self) -> int | None:
        """The highest of `value` and every other count (what must print); None when none is known."""
        numbers = [n for n in (self.value, *(o.value for o in self.others)) if n is not None]
        return max(numbers) if numbers else None


@dataclass(frozen=True)
class Family(_Model):
    """A family of equipment in a system: its name, its tags as printed, and its count."""
    name: str = field(**_doc('The family name, e.g. "Exhaust Fan", "Indoor Unit".'))
    tags: tuple[str, ...] = field(**_doc('The tags as printed, e.g. ["EF-1", "EF-2"]; empty when none.'))
    count: Count = field(**_doc("How many there are."))


@dataclass(frozen=True)
class Assumption(_Model):
    """What was assumed and why (ground rule 6: every assumption says both)."""
    what: str = field(**_doc("What is assumed, in plain words."))
    why: str = field(**_doc("Why: the evidence or the practice rule that led to it."))


@dataclass(frozen=True)
class Device(_Model):
    """One scope line: a device (or point, or interlock) and who furnishes, installs and wires it."""
    id: str = field(**_doc('Unique within the job, e.g. "EF-1.d3".'))
    slot: str = field(**_doc("The Playbook line slot this line fills (a slot of the system's shape)."))
    name: str = field(**_doc("The device in the document's own words."))
    verb: Verb = field(**_doc("The house verb."))
    furnished_by: Party = field(**_doc("Who furnishes it."))
    installed_by: Party = field(**_doc("Who installs it."))
    wired_by: Party = field(**_doc("Who wires it."))
    quantity: Count = field(**_doc("How many."))
    refs: tuple[Ref, ...] = field(**_doc("The citations from this job that call for this line (at least one).",
                                         min_items=1))
    assumption: Assumption | None = field(default=None, **_doc("What was assumed and why; null when nothing was."))
    flag: Flag = field(default="none", **_doc("none, or why the estimator must look: quantity, ownership, assumed."))
    # T-005c: additive, so both are optional in the AI's schema too (`optional`): an answer or a Job saved without them
    # still reads, as ""
    mark: Mark = field(default="", **_doc(
        '"" for none; "future" when the documents mark the item FUTURE (the line prints with "(<mark_note>)" in red); '
        '"notice" for an item the estimator must notice, e.g. one the factory furnishes (the line prints in red).',
        optional=True))
    mark_note: str = field(default="", **_doc(
        'For a "future" mark: the words printed in brackets, e.g. "FUTURE AS PER control schematic on sheet M710.00"; '
        '"" otherwise.', optional=True))

    def __post_init__(self) -> None:
        if not self.refs:
            raise ModelError(f"device {self.id!r} has no ref: every device line rests on a citation from this job")


@dataclass(frozen=True)
class Clarification(_Model):
    """A "*" clarification under a block (one per block)."""
    kind: ClarificationKind = field(**_doc("confirm, assumed, per_drawings or note."))
    text: str = field(**_doc("The clarification in plain words (the form comes from the Playbook wording)."))


@dataclass(frozen=True)
class Served(_Model):
    """A unit duct heaters serve, and the duct heater block that writes those heaters (one place for them)."""
    key: str = field(**_doc("The served unit's system key."))
    name: str = field(**_doc("The served unit's block name."))
    tags: tuple[str, ...] = field(**_doc("The served unit's tags the documents tie to the heaters."))
    heaters: tuple[str, ...] = field(**_doc("The duct heater tags serving it; empty when the documents do not say "
                                            "which."))
    heater_key: str = field(**_doc("The duct heater block's system key."))
    heater_name: str = field(**_doc("The duct heater block's name."))


@dataclass(frozen=True)
class System(_Model):
    """One block of the proposal. The planner fills everything but `devices`, `clarifications` and `tech_hours`;
    `write_system` fills those."""
    key: str = field(**_doc('Unique within the job, e.g. "EF".'))
    name: str = field(**_doc('The block name, e.g. "Exhaust Fans".'))
    shape: str = field(**_doc("The Playbook shape name this block follows."))
    control: Control = field(**_doc("packaged, field, integration or none."))
    families: tuple[Family, ...] = field(**_doc("The equipment families in this block, with their counts."))
    sequence_refs: tuple[Ref, ...] = field(default=(), **_doc("The sequence of operation passages for this system."))
    devices: tuple[Device, ...] = field(default=(), **_doc("The scope lines, in print order."))
    clarifications: tuple[Clarification, ...] = field(default=(), **_doc("At most one per block."))
    tech_hours: float | None = field(default=None, **_doc("The block's tech hours; null when not set."))
    alternate: AlternateKind = field(default="base", **_doc("base, add or deduct."))
    no_scope_reason: str | None = field(default=None, **_doc(
        "When the block has nothing for the BMS to scope (devices empty): why, in plain words; null otherwise."))
    serves: tuple[Served, ...] = field(default=(), **_doc(
        "Duct heaters (the planner's): on the duct heater block, one entry per unit its heaters serve; on a served "
        "unit's block, its own entry, naming the duct heater block that writes its heaters. Empty otherwise."))


@dataclass(frozen=True)
class ScopeException(_Model):
    """A named exception (design §4.2 "Exception"): a system the job names that AME does not do, with why."""
    system_key: str = field(**_doc("The system it is about (may name no planned system)."))
    text: str = field(**_doc("What is excepted, in plain words."))
    refs: tuple[Ref, ...] = field(default=(), **_doc("The citations."))


@dataclass(frozen=True)
class FrontEnd(_Model):
    """The front-end block. `mode` picks the proposal template's opening (as `estimator.scope.FrontEnd.mode`). The
    planner fills `mode`, `existing_system_name`, `lines`, `notes` and `refs` from this job's documents; the front end's
    writer (`bms.ai.write_front_end`, like a system's) fills `devices`, `clarifications`, `tech_hours` and
    `no_scope_reason`."""
    mode: FrontEndMode = field(**_doc("new-system or extend-existing."))
    existing_system_name: str | None = field(default=None, **_doc(
        "The existing BMS, when extending one; null when the documents do not name it (the proposal prints a fill-in "
        "and the planner asks for the name)."))
    devices: tuple[Device, ...] = field(default=(), **_doc("The front-end lines."))
    clarifications: tuple[Clarification, ...] = field(default=(), **_doc("At most one."))
    tech_hours: float | None = field(default=None, **_doc("The front end's tech hours."))
    lines: tuple[str, ...] = field(default=(), **_doc(
        "The planner's: what the reading found this job's documents call for in the front end, one entry each in the "
        "reading's own words (a front-end line, or an item the documents give to another party); the writer writes "
        "the devices from them and the evidence. Empty when the documents call for none."))
    notes: tuple[str, ...] = field(default=(), **_doc(
        "The planner's: the client notes for the front end the reading found, in its words."))
    refs: tuple[Ref, ...] = field(default=(), **_doc(
        "The planner's: the citations of those facts (the passages of this job's documents)."))
    no_scope_reason: str | None = field(default=None, **_doc(
        "When the writer wrote no front-end line: why, in plain words; null otherwise."))


@dataclass(frozen=True)
class Header(_Model):
    """The proposal cover table (mirrors `estimator.scope.Header`; set by the run, not by the planner)."""
    quote_number: str
    reference: str
    mep_engineer: str
    based_on: tuple[str, ...]
    date: str = field(**_doc("ISO date, e.g. 2026-10-04."))
    to: str = "All Bidders"


@dataclass(frozen=True)
class SheetClass(_Model):
    """What one drawing sheet is, as the takeoff reader decided: its kind, the place it shows and whether the units and
    devices drawn on it count for this job (takeoff pass plan 2026-10-11)."""
    document: str = field(**_doc('The drawing file as the dossier names it, e.g. "Mech.pdf".'))
    page: int = field(**_doc("The page of that file, counted from 1."))
    number: str = field(**_doc('The sheet number as listed, e.g. "M-401"; empty when the sheet has none.'))
    kind: SheetKind = field(**_doc("new_work, demolition, part_plan, enlarged_plan, riser, schedule, detail, "
                                   "control_diagram or other."))
    area: str = field(**_doc('The place the sheet shows, in plain words, e.g. "Attic" or "Level 2 east": one area name '
                             "for every sheet of one place; empty for a sheet that is not a plan."))
    counts_units: bool = field(**_doc("True when the units and devices drawn on this sheet count for this job."))
    reason: str = field(**_doc("Why, in one short sentence."))
    refs: tuple[Ref, ...] = field(default=(), **_doc(
        "The citations behind the decision, when it rests on a passage (a demolition sheet that counts, for example)."))


@dataclass(frozen=True)
class Unit(_Model):
    """One unit, or one type tag, the documents show, as the takeoff reader decided: what it is, whether it counts and
    the passages that say so. Like a Device, it rests on at least one Ref (enforced at construction)."""
    family: str = field(**_doc('The ledger family prefix, e.g. "AHU".'))
    tag: str = field(**_doc('The tag as the schedule prints it; a type tag ("FCU-1") for a typical unit.'))
    labels: tuple[str, ...] = field(**_doc("Every label the sheets show for it."))
    status: UnitStatus = field(**_doc("new, demolish, demolish_with_work, existing_remain, relocate or future."))
    count: int = field(**_doc("1 for a numbered unit; for a type tag, the places it is drawn on the counted sheets."))
    sheets: tuple[str, ...] = field(**_doc("The counted sheets it is drawn on."))
    refs: tuple[Ref, ...] = field(**_doc("The citations from this job that show this unit (at least one).",
                                         min_items=1))
    serves: str = field(default="", **_doc('The unit it serves, e.g. "AHU-2" for a control valve; empty when none.'))
    service: str = field(default="", **_doc(
        'The service it is on, e.g. "chilled water" or "hot water"; empty when none.'))
    with_plant: bool = field(default=False, **_doc(
        "True when the pump is drawn and scheduled as part of a plant that is in this job's scope (then serves names "
        "the plant's unit); false for a remote pump or any other unit (ruling 18)."))
    reason: str = field(default="", **_doc("Why, in one short sentence."))

    def __post_init__(self) -> None:
        if not self.refs:
            raise ModelError(f"unit {self.tag!r} has no ref: every unit row rests on a citation from this job")


@dataclass(frozen=True)
class SetAside(_Model):
    """A count in the ledger that the takeoff reader says is not the family's number (it counts a demolition sheet, the
    same unit twice, a future item and so on), with the source of that number and why. Both numbers stay visible."""
    family: str = field(**_doc('The ledger family prefix, e.g. "AHU".'))
    value: int = field(**_doc("The number that is set aside."))
    ref: Ref = field(**_doc("The source of that number."))
    reason: SetAsideReason = field(**_doc(
        "demolition sheet, same unit labelled again, part plan of one area, future item, existing to remain or not a "
        "unit of this family."))
    note: str = field(default="", **_doc(
        'Both numbers in plain words, e.g. "21 plan placements set aside; 5 units on the new-work sheets".'))


@dataclass(frozen=True)
class FutureItem(_Model):
    """A unit or device the documents mark as future work."""
    family: str = field(**_doc('The ledger family prefix, e.g. "AHU".'))
    item: str = field(**_doc('The item in plain words, e.g. "outside airflow measuring station".'))
    refs: tuple[Ref, ...] = field(**_doc("The citations that mark it future."))


@dataclass(frozen=True)
class Job(_Model):
    """The whole job."""
    name: str
    systems: tuple[System, ...] = ()
    front_end: FrontEnd | None = None
    exceptions: tuple[ScopeException, ...] = ()
    questions: tuple[str, ...] = ()
    header: Header | None = None
    # the id-shaped sheet numbers the ledger's sources' wheres name ("S101, Structural.pdf page 3" gives S101), upper
    # case, sorted; the run sets them once (`bms.citations.source_sheets`). A known sheet in a where and right after a
    # sheet word only, never bare in client text (FINAL-J, `citations.SourceIds.source_sheets`); the intake, the
    # validator and the renderer read them alike. () on a Job saved before the field.
    source_sheets: tuple[str, ...] = ()
    # the takeoff register (`bms.takeoff`): what each sheet is, the units the documents show, the counts set aside and
    # the items marked future. Stage 1 of the takeoff pass stores it and no count reads it. () on a Job saved before them.
    sheets: tuple[SheetClass, ...] = ()
    units: tuple[Unit, ...] = ()
    set_aside: tuple[SetAside, ...] = ()
    future_items: tuple[FutureItem, ...] = ()

    def system(self, key: str) -> System:
        for system in self.systems:
            if system.key == key:
                return system
        raise KeyError(key)

    def with_system(self, system: System) -> "Job":
        """This job with the system of the same key replaced."""
        if not any(s.key == system.key for s in self.systems):
            raise KeyError(system.key)
        return dataclasses.replace(self, systems=tuple(system if s.key == system.key else s for s in self.systems))


@dataclass(frozen=True)
class Finding(_Model):
    """A validator's or the QC pass's finding (design §4.3)."""
    rule: str = field(**_doc("The Playbook rule name it enforces (its ### heading in rules.md)."))
    system_key: str = field(**_doc('The system it is about ("" for the whole job or the front end).'))
    device_id: str | None = field(**_doc("The device it is about; null for the whole system."))
    severity: Severity = field(**_doc("must_fix or check."))
    what: str = field(**_doc("What is wrong, in plain words."))
    fix: str = field(**_doc("What to do, in plain words."))


@dataclass(frozen=True)
class Decision(_Model):
    """The estimator's decision on one review-page question (design §4.7), saved in decisions.json.

    What it is about: a device (`device_id` set), a family's count (`family_name` set) or the whole system
    (neither). `accept` keeps it as it is (and clears its flag); `delete` removes the device (or the system);
    `change` replaces the device with `device` (same id) or the family's count with `count`. `finding_rule` names
    the Finding the question came from, when it came from one."""
    system_key: str
    action: DecisionAction
    device_id: str | None = None
    family_name: str | None = None
    device: Device | None = None
    count: Count | None = None
    finding_rule: str | None = None
    reason: str = ""
    was: Device | None = None


MODEL_CLASSES = (Ref, OtherCount, Count, Family, Assumption, Device, Clarification, Served, System, ScopeException,
                 FrontEnd, Header, Job, Finding, Decision, SheetClass, Unit, SetAside, FutureItem)

# ---- JSON round-trip -----------------------------------------------------------------------------------------


def _to_json(value):
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _to_json(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, (tuple, list)):
        return [_to_json(v) for v in value]
    return value


def _is_union(tp) -> bool:
    return get_origin(tp) in (Union, types.UnionType)


def _from_json(tp, data, path: str):
    origin = get_origin(tp)
    if _is_union(tp):
        args = get_args(tp)
        if data is None and type(None) in args:
            return None
        inner = [a for a in args if a is not type(None)]
        if len(inner) != 1:
            raise ModelError(f"{path}: unsupported union {tp}")
        return _from_json(inner[0], data, path)
    if origin is Literal:
        if data not in get_args(tp):
            raise ModelError(f"{path}: {data!r} is not one of {', '.join(map(repr, get_args(tp)))}")
        return data
    if origin is tuple:
        if not isinstance(data, list):
            raise ModelError(f"{path}: expected a list, got {type(data).__name__}")
        (item,) = [a for a in get_args(tp) if a is not Ellipsis]
        return tuple(_from_json(item, v, f"{path}[{n}]") for n, v in enumerate(data))
    if dataclasses.is_dataclass(tp):
        if not isinstance(data, dict):
            raise ModelError(f"{path}: expected an object, got {type(data).__name__}")
        hints = get_type_hints(tp)
        names = {f.name for f in dataclasses.fields(tp)}
        unknown = sorted(set(data) - names)
        if unknown:
            raise ModelError(f"{path}: unknown field(s) {', '.join(unknown)}")
        kwargs = {}
        for f in dataclasses.fields(tp):
            if f.name in data:
                kwargs[f.name] = _from_json(hints[f.name], data[f.name], f"{path}.{f.name}")
            elif f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
                raise ModelError(f"{path}: missing field {f.name}")
        try:
            return tp(**kwargs)
        except ModelError as error:
            raise ModelError(f"{path}: {error}") from None
    if tp is bool:
        if not isinstance(data, bool):
            raise ModelError(f"{path}: expected true or false, got {data!r}")
        return data
    if tp is float:
        if isinstance(data, bool) or not isinstance(data, (int, float)):
            raise ModelError(f"{path}: expected a number, got {data!r}")
        return float(data)
    if tp is int:
        if isinstance(data, bool) or not isinstance(data, int):
            raise ModelError(f"{path}: expected a whole number, got {data!r}")
        return data
    if tp is str:
        if not isinstance(data, str):
            raise ModelError(f"{path}: expected text, got {data!r}")
        return data
    raise ModelError(f"{path}: unsupported type {tp}")


# ---- JSON Schema -------------------------------------------------------------------------------------------


def json_schema(cls) -> dict:
    """The JSON Schema of a model class, for an AI step's structured answer. Every property is required (a field
    with a default still has to be given) except a field added later as optional (metadata `optional`: Device.mark
    and mark_note, T-005c), objects allow no other properties, nested classes are inlined."""
    if not (dataclasses.is_dataclass(cls) and isinstance(cls, type)):
        raise TypeError(f"{cls!r} is not a model class")
    return _schema_of(cls, {})


def _schema_of(tp, meta: dict) -> dict:
    doc = {"description": meta["doc"]} if meta.get("doc") else {}
    if _is_union(tp):
        inner = [a for a in get_args(tp) if a is not type(None)]
        (only,) = inner
        return {"anyOf": [_schema_of(only, {}), {"type": "null"}], **doc}
    origin = get_origin(tp)
    if origin is Literal:
        return {"type": "string", "enum": list(get_args(tp)), **doc}
    if origin is tuple:
        (item,) = [a for a in get_args(tp) if a is not Ellipsis]
        schema = {"type": "array", "items": _schema_of(item, {}), **doc}
        if meta.get("min_items"):
            schema["minItems"] = meta["min_items"]
        return schema
    if dataclasses.is_dataclass(tp):
        hints = get_type_hints(tp)
        fields = dataclasses.fields(tp)
        return {"type": "object",
                "properties": {f.name: _schema_of(hints[f.name], dict(f.metadata))
                               for f in fields},
                "required": [f.name for f in fields if not f.metadata.get("optional")], "additionalProperties": False,
                **({"description": meta["doc"]} if meta.get("doc") else {})}
    if tp is str:
        return {"type": "string", **doc}
    if tp is bool:
        return {"type": "boolean", **doc}
    if tp is int:
        return {"type": "integer", **doc}
    if tp is float:
        return {"type": "number", **doc}
    raise TypeError(f"no schema for {tp}")


_TYPES = {"string": str, "integer": int, "number": (int, float), "object": dict, "array": list,
          "boolean": bool, "null": type(None)}


def schema_errors(value, schema: dict, path: str = "$") -> list[str]:
    """Every way `value` breaks `schema` (empty when it fits). Understands type, enum, properties, required,
    additionalProperties false, items, minItems and anyOf — the keywords `json_schema` produces."""
    if "anyOf" in schema:
        if any(not schema_errors(value, option, path) for option in schema["anyOf"]):
            return []
        return [f"{path}: fits none of the allowed forms"]
    errors: list[str] = []
    kind = schema.get("type")
    if kind is not None:
        kinds = kind if isinstance(kind, list) else [kind]
        ok = any(isinstance(value, _TYPES[k]) and not (k in ("integer", "number") and isinstance(value, bool))
                 for k in kinds)
        if not ok:
            return [f"{path}: expected {' or '.join(kinds)}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} is not one of {schema['enum']}")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{path}: missing {name}")
        if schema.get("additionalProperties") is False:
            errors += [f"{path}: unexpected {name}" for name in value if name not in props]
        for name, sub in props.items():
            if name in value:
                errors += schema_errors(value[name], sub, f"{path}.{name}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: needs at least {schema['minItems']} item(s)")
        if "items" in schema:
            for n, item in enumerate(value):
                errors += schema_errors(item, schema["items"], f"{path}[{n}]")
    return errors


__all__ = ["Verb", "Control", "Flag", "ClarificationKind", "AlternateKind", "Party", "Severity", "FrontEndMode",
           "UNNAMED_EXISTING", "VERBS", "CONTROLS", "FLAGS", "CLARIFICATION_KINDS", "ALTERNATES", "PARTIES", "SEVERITIES",
           "FRONT_END_MODES", "DecisionAction", "DECISION_ACTIONS", "Mark", "MARKS", "ModelError", "Ref", "OtherCount", "Count", "Family", "Assumption", "Device",
           "Clarification", "Served", "System", "ScopeException", "FrontEnd", "Header", "Job", "Finding", "Decision", "MODEL_CLASSES",
           "SheetKind", "UnitStatus", "SetAsideReason", "SHEET_KINDS", "UNIT_STATUSES", "SET_ASIDE_REASONS",
           "COUNTED_STATUSES", "SheetClass", "Unit", "SetAside", "FutureItem",
           "json_schema", "schema_errors"]
