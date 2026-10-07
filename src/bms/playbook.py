"""The Playbook (rebuild design §4.1): the one rule book, read from `playbook/`.

- `rules.md`  — every practice rule in plain words; "## " per topic, "### " per rule (its short name is the rule id
  a Finding names). Loaded whole as the cached instructions of every AI step (`Playbook.rules_text`).
- `shapes.json` — one shape per system type: header form, family names, line order, slot kinds, wording per slot,
  tech-hour rule. Shape only, never content.
- `wording.json` — verbs, owner brackets, integration trio, clarification forms, header and quantity forms, and the
  client words for the likely causes of a high plan count (`count_causes`).

`load_playbook(root)` reads and checks all three; a malformed file raises `PlaybookError` naming the file and the
problem. The format of each file is documented in its own "$format" object (rules.md: its top comment).
"""
from __future__ import annotations

import json
import re
import string
from dataclasses import dataclass, field
from pathlib import Path

from bms.model import CLARIFICATION_KINDS, PARTIES, VERBS

DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "playbook"
TECH_HOUR_BASES = ("unit", "hardware_point", "indoor_unit", "panel", "fan", "fixed", "line")
SLOT_KINDS = ("device", "point", "interlock", "integration", "wiring")
SAMPLE_MARK = "<!-- sample -->"
SAMPLE_PATTERN = re.compile(r"<!--\s*sample\s*-->")              # the mark as written, spaces or none
# a kind word: lower-case words of letters and digits, one space between (as a system kind is compared)
_KIND_WORD = re.compile(r"[a-z0-9]+( [a-z0-9]+)*")


class PlaybookError(ValueError):
    """A Playbook file that cannot be used; the message names the file and what is wrong."""


@dataclass(frozen=True)
class Rule:
    topic: str          # its "## " heading
    name: str           # its "### " heading: the id a Finding.rule names
    text: str           # its plain sentences (the sample marker removed)
    sample: bool = False


@dataclass(frozen=True)
class TechHours:
    per: str                                        # one of TECH_HOUR_BASES
    hours: float | None                             # per item; None: none unless a `when` holds
    when: tuple[tuple[tuple[str, ...], float], ...] = ()   # (slots that must all have a device, hours)


@dataclass(frozen=True)
class Shape:
    name: str
    prefixes: tuple[str, ...]
    kind_words: tuple[str, ...]
    header: str
    family_names: tuple[str, ...]
    line_order: tuple[str, ...]
    slot_kinds: dict[str, str]
    wording: dict[str, str]
    tech_hours: TechHours
    under: dict[str, str] = field(default_factory=dict)    # sub-line slot -> its parent slot (prints one level in)
    order: int = 10                                        # block order in the scope: lower prints first (DEFAULT_ORDER)

    def parent_of(self, slot: str) -> str | None:
        """The slot a sub-line slot prints under, or None for a line of its own."""
        return self.under.get(slot)

    def slots_of_kind(self, kind: str) -> tuple[str, ...]:
        return tuple(s for s in self.line_order if self.slot_kinds[s] == kind)


# wording.json "count_causes": the quantity note's form for the likely causes of a high plan count ({causes}), the
# joiner between causes, and each cause's client words (bms.render reads the cause from the counts line's head)
COUNT_CAUSE_KEYS = ("form", "joiner", "typical", "labelled_twice")


@dataclass(frozen=True)
class Wording:
    verbs: tuple[str, ...]
    owner_brackets: dict[str, str]                  # party -> " (Furnished by …)"
    integration_trio: tuple[str, ...]               # the three lines; {what} names the equipment
    integration_depths: tuple[int, ...]
    clarifications: dict[str, str]                  # kind -> "*{text} …"
    header: dict[str, str]                          # count, unknown_count, tags_joiner (generic)
    quantity: dict[str, str]                        # line, unknown, others_note (unlabelled, per, and, joiner)
    draft: tuple[str, ...] = ()
    count_causes: dict[str, str] = field(default_factory=dict)   # form, joiner and each cause's client words
    alternate_label: str = ""                       # optional "ALT #{k}: {name}" form; "" = the renderer's own
    # the optional keys below: each one left out keeps the renderer's own words (bms.render), so the text is unchanged
    quantity_labels: dict[str, str] = field(default_factory=dict)  # quantity.labels: what a count's quote counted
    assumption: dict = field(default_factory=dict)  # because (text), leads (texts): an assumption's reason words
    casing: dict = field(default_factory=dict)      # acronyms, small_words, not_plural (texts); acronym_before


@dataclass(frozen=True)
class Playbook:
    rules_text: str                                 # rules.md whole: the cached instructions of every AI step
    topics: tuple[str, ...]
    rules: dict[str, Rule]                          # by name, in file order
    shapes: dict[str, Shape]                        # by name, in file order
    wording: Wording
    root: Path

    def rule(self, name: str) -> Rule:
        try:
            return self.rules[name]
        except KeyError:
            raise KeyError(f"no Playbook rule named {name!r}") from None

    def shape(self, name: str) -> Shape:
        try:
            return self.shapes[name]
        except KeyError:
            raise KeyError(f"no Playbook shape named {name!r}") from None

    def shape_for(self, system_kind: str, prefixes) -> Shape | None:
        """The shape for a system: the first shape (file order) one of whose prefixes is one of `prefixes`
        (compared upper case, without dashes or spaces); else the first whose kind words appear in `system_kind`
        (lower case, whole words, a plural s / es allowed); else None (an untemplated system — it is still written, from its evidence)."""
        wanted = {_plain_prefix(p) for p in prefixes or () if p}
        for shape in self.shapes.values():
            if wanted & set(shape.prefixes):
                return shape
        kind = " ".join(re.findall(r"[a-z0-9]+", (system_kind or "").lower()))
        for shape in self.shapes.values():
            if any(re.search(rf"\b{re.escape(w)}(?:s|es)?\b", kind) for w in shape.kind_words):
                return shape
        return None


def _plain_prefix(prefix: str) -> str:
    return re.sub(r"[\s\-_]", "", str(prefix)).upper()


def load_playbook(root: Path = DEFAULT_ROOT) -> Playbook:
    """The Playbook in `root` (default: the repo's `playbook/`). Raises PlaybookError on a malformed file."""
    root = Path(root)
    rules_text, topics, rules = load_rules(root / "rules.md")
    shapes = load_shapes(root / "shapes.json")
    wording = load_wording(root / "wording.json")
    return Playbook(rules_text, topics, rules, shapes, wording, root)


def check_file(path: Path) -> None:
    """Check one Playbook file (`rules.md`, `shapes.json` or `wording.json`).
    Raises PlaybookError naming the file and what is wrong."""
    path = Path(path)
    if path.name == "rules.md":
        load_rules(path)
    elif path.name == "shapes.json":
        load_shapes(path)
    elif path.name == "wording.json":
        load_wording(path)
    else:
        raise PlaybookError(f"{path.name}: not a Playbook file (expected rules.md, shapes.json, or wording.json)")


check_playbook_file = check_file


# ---- rules.md ------------------------------------------------------------------------------------------------

def load_rules(path: Path) -> tuple[str, tuple[str, ...], dict[str, Rule]]:
    """Load and check rules.md. Raises PlaybookError on a malformed file."""
    path = Path(path)
    text = _read(path)
    body = strip_comments(text)
    topics: list[str] = []
    rules: dict[str, Rule] = {}
    topic: str | None = None
    current: tuple[str, list[str]] | None = None

    def close() -> None:
        if current is None:
            return
        name, lines = current
        joined = "\n".join(lines).strip()
        sample = SAMPLE_PATTERN.search(joined) is not None
        joined = SAMPLE_PATTERN.sub("", joined).strip()
        if not joined:
            raise PlaybookError(f"{path.name}: rule {name!r} has no text")
        rules[name] = Rule(topic or "", name, joined, sample)

    for n, line in enumerate(body.splitlines(), start=1):
        if line.startswith("### "):
            close()
            name = line[4:].strip()
            if topic is None:
                raise PlaybookError(f"{path.name} line {n}: rule {name!r} is not under a topic (## heading)")
            if not name:
                raise PlaybookError(f"{path.name} line {n}: a rule with no name")
            if name in rules:
                raise PlaybookError(f"{path.name} line {n}: rule {name!r} appears twice")
            current = (name, [])
        elif line.startswith("## "):
            close()
            current = None
            topic = line[3:].strip()
            if not topic or topic in topics:
                raise PlaybookError(f"{path.name} line {n}: topic {topic!r} is empty or appears twice")
            topics.append(topic)
        elif line.startswith("#### "):
            raise PlaybookError(f"{path.name} line {n}: only ## topics and ### rules are allowed")
        elif current is not None:
            current[1].append(line)
    close()
    if not topics:
        raise PlaybookError(f"{path.name}: no topic (## heading)")
    return text, tuple(topics), rules


def strip_comments(text: str) -> str:
    """rules.md as the loader reads it: comments out, sample marks kept. A comment's line breaks stay, so a line
    number still names the line of the file (bms.playbook_lint reads the file the same way)."""
    return re.sub(r"<!--(?!\s*sample\s*-->).*?-->", lambda m: "\n" * m.group().count("\n"), text, flags=re.S)


_load_rules = load_rules


# ---- shapes.json ---------------------------------------------------------------------------------------------

def _strings(value, where: str, path: Path, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise PlaybookError(f"{path.name}: {where} must be a list of non-empty texts")
    if not allow_empty and not value:
        raise PlaybookError(f"{path.name}: {where} must not be empty")
    return tuple(value)


def _form(text, where: str, path: Path, allowed, required=()) -> str:
    """A wording form checked against what bms.render fills it with: only the placeholders in `allowed`, by name,
    with no format spec or conversion, every one in `required` present, and every brace closed ("{{" and "}}"
    print a brace). A typo here would otherwise crash the render or drop words from client text."""
    if not isinstance(text, str):
        raise PlaybookError(f"{path.name}: {where} must be a text")
    try:
        parts = list(string.Formatter().parse(text))
    except ValueError as error:
        raise PlaybookError(f"{path.name}: {where}: a brace is not closed or not doubled ({error}): {text!r}") from None
    names = set()
    for _, name, spec, conversion in parts:
        if name is None:
            continue
        if not name or name not in allowed:
            shown = ", ".join("{" + a + "}" for a in sorted(allowed)) or "none"
            raise PlaybookError(f"{path.name}: {where}: unknown placeholder {{{name}}} (allowed: {shown}): {text!r}")
        if spec or conversion:
            raise PlaybookError(f"{path.name}: {where}: the placeholder {{{name}}} must be plain, with no ! or : "
                                f"part: {text!r}")
        names.add(name)
    missing = [r for r in required if r not in names]
    if missing:
        raise PlaybookError(f"{path.name}: {where} must hold " + ", ".join("{" + m + "}" for m in missing)
                            + f": {text!r}")
    return text


# wording.json's optional keys (RND-14): bms.render keeps its own words for each one left out
HEADER_OPTIONAL = ("generic",)                                  # the header of a system with no shape
QUANTITY_OPTIONAL = ("unlabelled", "per", "and", "joiner")      # the count note's words and joiners
COUNT_LABEL_KEYS = ("plan_placements", "schedule_rows", "schedule", "riser", "sheet_pictures")   # quantity.labels
ASSUMPTION_KEYS = ("because", "leads")
CASING_KEYS = ("acronyms", "small_words", "not_plural", "acronym_before")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9]*")
_LOWER_WORD = re.compile(r"[a-z]+")

# what bms.render fills each form with (its `_fill` / `format` calls)
HEADER_FIELDS = ("n", "name", "tags")
LINE_FIELDS = ("verb", "device", "owner", "qty", "what")


def _text_map(value, where: str, path: Path) -> dict[str, str]:
    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise PlaybookError(f"{path.name}: {where} must map names to texts")
    return dict(value)


_SHAPE_KEYS = {"name", "applies_to", "header", "family_names", "line_order", "slot_kinds", "wording", "tech_hours"}
_OPTIONAL_SHAPE_KEYS = {"under", "order"}
DEFAULT_ORDER = 10          # a shape with no "order": the equipment blocks


def load_shapes(path: Path) -> dict[str, Shape]:
    """Load and check shapes.json. Raises PlaybookError on a malformed file."""
    path = Path(path)
    data = _json(path)
    if not isinstance(data.get("$format"), dict):
        raise PlaybookError(f"{path.name}: the \"$format\" object is missing")
    raw = data.get("shapes")
    if not isinstance(raw, list):
        raise PlaybookError(f"{path.name}: \"shapes\" must be a list")
    shapes: dict[str, Shape] = {}
    prefix_owner: dict[str, str] = {}               # prefix -> the shape it names
    word_owner: dict[str, str] = {}                 # kind word -> the shape it names
    for n, entry in enumerate(raw):
        where = f"shapes[{n}]"
        if not isinstance(entry, dict):
            raise PlaybookError(f"{path.name}: {where} must be an object")
        missing, extra = _SHAPE_KEYS - set(entry), set(entry) - _SHAPE_KEYS - _OPTIONAL_SHAPE_KEYS
        if missing or extra:
            raise PlaybookError(f"{path.name}: {where} " + "; ".join(
                part for part in (f"is missing {', '.join(sorted(missing))}" if missing else "",
                                  f"has unknown {', '.join(sorted(extra))}" if extra else "") if part))
        name = entry["name"]
        if not isinstance(name, str) or not name.strip():
            raise PlaybookError(f"{path.name}: {where}.name must be a non-empty text")
        where = f"shape {name!r}"
        if name in shapes:
            raise PlaybookError(f"{path.name}: {where} appears twice")
        applies = entry["applies_to"]
        if not isinstance(applies, dict) or set(applies) != {"prefixes", "kind_words"}:
            raise PlaybookError(f"{path.name}: {where}.applies_to must have exactly prefixes and kind_words")
        prefixes = _strings(applies["prefixes"], f"{where}.applies_to.prefixes", path)
        if any(p != _plain_prefix(p) for p in prefixes):
            raise PlaybookError(f"{path.name}: {where}.applies_to.prefixes must be upper case with no dash or space")
        kind_words = _strings(applies["kind_words"], f"{where}.applies_to.kind_words", path)
        if not all(_KIND_WORD.fullmatch(w) for w in kind_words):
            raise PlaybookError(f"{path.name}: {where}.applies_to.kind_words must be lower case letters and digits, "
                                "one space between words (no dash or other mark; a system kind is compared so)")
        for label, values, seen in (("prefix", prefixes, prefix_owner), ("kind word", kind_words, word_owner)):
            for value in values:
                if seen.setdefault(value, name) != name:
                    raise PlaybookError(f"{path.name}: {where}: the {label} {value!r} is already shape "
                                        f"{seen[value]!r}'s (each names one shape)")
        header = _form(entry["header"], f"{where}.header", path, HEADER_FIELDS, required=("n",))
        family_names = _strings(entry["family_names"], f"{where}.family_names", path, allow_empty=False)
        line_order = _strings(entry["line_order"], f"{where}.line_order", path, allow_empty=False)
        if len(set(line_order)) != len(line_order):
            raise PlaybookError(f"{path.name}: {where}.line_order names a slot twice")
        slot_kinds = _text_map(entry["slot_kinds"], f"{where}.slot_kinds", path)
        wording = _text_map(entry["wording"], f"{where}.wording", path)
        for label, mapping in (("slot_kinds", slot_kinds), ("wording", wording)):
            if set(mapping) != set(line_order):
                raise PlaybookError(f"{path.name}: {where}.{label} must cover exactly the slots of line_order")
        bad = sorted(k for k, v in slot_kinds.items() if v not in SLOT_KINDS)
        if bad:
            raise PlaybookError(f"{path.name}: {where}.slot_kinds: {', '.join(bad)} not one of {SLOT_KINDS}")
        under = _under(entry.get("under", {}), where, path, line_order)
        for slot, form in wording.items():
            # a sub-line prints with no verb, one level in under its parent
            allowed = tuple(f for f in LINE_FIELDS if f != "verb" or slot not in under)
            _form(form, f"{where}.wording.{slot}", path, allowed)
        order = entry.get("order", DEFAULT_ORDER)
        if isinstance(order, bool) or not isinstance(order, int) or order < 0:
            raise PlaybookError(f"{path.name}: {where}.order must be a whole number, 0 or more")
        shapes[name] = Shape(name, prefixes, kind_words, header, family_names, line_order, slot_kinds, wording,
                             _tech_hours(entry["tech_hours"], where, path, set(line_order)), under, order)
    return shapes


_load_shapes = load_shapes


def _under(raw, where: str, path: Path, line_order: tuple[str, ...]) -> dict[str, str]:
    """The optional sub-line map: slot -> the parent slot it prints one level in under. Both are slots of the shape
    and the parent comes earlier in line_order (so a chain never loops)."""
    under = _text_map(raw, f"{where}.under", path)
    position = {slot: n for n, slot in enumerate(line_order)}
    for slot, parent in under.items():
        if slot not in position or parent not in position:
            raise PlaybookError(f"{path.name}: {where}.under: {slot!r} -> {parent!r} names a slot not in line_order")
        if position[parent] >= position[slot]:
            raise PlaybookError(f"{path.name}: {where}.under: the parent {parent!r} must come before {slot!r} in "
                                "line_order")
    return under


def _tech_hours(raw, where: str, path: Path, slots: set[str]) -> TechHours:
    if not isinstance(raw, dict) or set(raw) != {"per", "hours", "when"}:
        raise PlaybookError(f"{path.name}: {where}.tech_hours must have exactly per, hours and when")
    if raw["per"] not in TECH_HOUR_BASES:
        raise PlaybookError(f"{path.name}: {where}.tech_hours.per must be one of {TECH_HOUR_BASES}")
    hours = raw["hours"]
    if hours is not None and (isinstance(hours, bool) or not isinstance(hours, (int, float)) or hours < 0):
        raise PlaybookError(f"{path.name}: {where}.tech_hours.hours must be a number or null")
    when = []
    if not isinstance(raw["when"], list):
        raise PlaybookError(f"{path.name}: {where}.tech_hours.when must be a list")
    for cond in raw["when"]:
        if (not isinstance(cond, dict) or set(cond) != {"if", "hours"}
                or isinstance(cond["hours"], bool) or not isinstance(cond["hours"], (int, float))
                or cond["hours"] < 0):
            raise PlaybookError(f"{path.name}: {where}.tech_hours.when entries must be {{\"if\": [...], \"hours\": n}}, "
                                "n a number, 0 or more")
        named = _strings(cond["if"], f"{where}.tech_hours.when.if", path, allow_empty=False)
        if not set(named) <= slots:
            raise PlaybookError(f"{path.name}: {where}.tech_hours.when names a slot not in line_order")
        when.append((named, float(cond["hours"])))
    return TechHours(raw["per"], None if hours is None else float(hours), tuple(when))


# ---- wording.json --------------------------------------------------------------------------------------------

def load_wording(path: Path) -> Wording:
    """Load and check wording.json. Raises PlaybookError on a malformed file."""
    path = Path(path)
    data = _json(path)
    if not isinstance(data.get("$format"), dict):
        raise PlaybookError(f"{path.name}: the \"$format\" object is missing")
    for key in ("verbs", "owner_brackets", "integration_trio", "clarifications", "header", "quantity", "count_causes"):
        if key not in data:
            raise PlaybookError(f"{path.name}: {key} is missing")
    verbs = _strings(data["verbs"], "verbs", path)
    if verbs != VERBS:
        raise PlaybookError(f"{path.name}: verbs must be exactly {list(VERBS)}")
    brackets = _text_map(data["owner_brackets"], "owner_brackets", path)
    wanted = set(PARTIES) - {"AME"}
    if set(brackets) != wanted:
        raise PlaybookError(f"{path.name}: owner_brackets must name exactly {sorted(wanted)}")
    for party, bracket in brackets.items():
        if not bracket.startswith(" ("):
            raise PlaybookError(f"{path.name}: owner_brackets.{party} must start with \" (\" (it prints right after "
                                f"the device): {bracket!r}")
    trio = data["integration_trio"]
    if not isinstance(trio, dict) or set(trio) != {"lines", "depths"}:
        raise PlaybookError(f"{path.name}: integration_trio must have exactly lines and depths")
    lines = _strings(trio["lines"], "integration_trio.lines", path)
    depths = trio["depths"]
    if len(lines) != 3 or not isinstance(depths, list) or len(depths) != 3 or any(d not in (1, 2) for d in depths):
        raise PlaybookError(f"{path.name}: integration_trio needs three lines and three depths of 1 or 2")
    for n, line in enumerate(lines):
        _form(line, f"integration_trio.lines[{n}]", path, ("what",))
    forms = _text_map(data["clarifications"], "clarifications", path)
    if set(forms) != set(CLARIFICATION_KINDS) or not all(f.startswith("*") for f in forms.values()):
        raise PlaybookError(f"{path.name}: clarifications must give a \"*…{{text}}…\" form for each of "
                            f"{list(CLARIFICATION_KINDS)}")
    for kind, form in forms.items():
        _form(form, f"clarifications.{kind}", path, ("text",), required=("text",))
    header = _text_map(data["header"], "header", path)
    if not {"count", "unknown_count", "tags_joiner"} <= set(header) <= {"count", "unknown_count", "tags_joiner",
                                                                         *HEADER_OPTIONAL}:
        raise PlaybookError(f"{path.name}: header must have exactly count, unknown_count and tags_joiner "
                            "(and, optionally, generic)")
    _form(header["count"], "header.count", path, ("n",), required=("n",))
    _form(header["unknown_count"], "header.unknown_count", path, ())
    if "generic" in header:               # the header of a system with no shape (bms.render.GENERIC_HEADER)
        _form(header["generic"], "header.generic", path, HEADER_FIELDS, required=("n",))
    raw_quantity, labels = data["quantity"], {}
    if isinstance(raw_quantity, dict) and "labels" in raw_quantity:
        raw_quantity = dict(raw_quantity)
        labels = _count_labels(raw_quantity.pop("labels"), path)
    quantity = _text_map(raw_quantity, "quantity", path)
    if not {"line", "unknown", "others_note"} <= set(quantity) <= {"line", "unknown", "others_note",
                                                                    *QUANTITY_OPTIONAL}:
        raise PlaybookError(f"{path.name}: quantity must have exactly line, unknown and others_note "
                            "(and, optionally, unlabelled, per, and, joiner and labels)")
    _form(quantity["line"], "quantity.line", path, ("n",), required=("n",))
    _form(quantity["unknown"], "quantity.unknown", path, ())
    _form(quantity["others_note"], "quantity.others_note", path, ("counts",), required=("counts",))
    for key in QUANTITY_OPTIONAL:         # the count note's words (bms.render.UNLABELLED, COUNT_PER, ...)
        if key in quantity:
            _form(quantity[key], f"quantity.{key}", path, ())
            if key != "unlabelled" and not quantity[key].strip():
                raise PlaybookError(f"{path.name}: quantity.{key} must not be blank (it joins the count note)")
    causes = _text_map(data["count_causes"], "count_causes", path)
    if set(causes) != set(COUNT_CAUSE_KEYS):
        raise PlaybookError(f"{path.name}: count_causes must have exactly {', '.join(COUNT_CAUSE_KEYS)}")
    _form(causes["form"], "count_causes.form", path, ("causes",), required=("causes",))
    if not all(causes[k].strip() for k in COUNT_CAUSE_KEYS if k != "joiner"):
        raise PlaybookError(f"{path.name}: count_causes: the form must hold {{causes}} and every cause needs its words")
    draft = _strings(data.get("$draft", []), "$draft", path)
    alternate_label = data.get("alternate_label", "")          # optional: the renderer keeps its own form without it
    if not isinstance(alternate_label, str) or (alternate_label and "{k}" not in alternate_label):
        raise PlaybookError(f"{path.name}: alternate_label must be a text holding {{k}}")
    return Wording(verbs, brackets, lines, tuple(depths), forms, header, quantity, draft, causes, alternate_label,
                   labels, _assumption(data.get("assumption", {}), path), _casing(data.get("casing", {}), path))


def _count_labels(raw, path: Path) -> dict[str, str]:
    """quantity.labels (optional): the count note's words for what a count's quote counted, by kind; a kind left
    out keeps the renderer's own words (bms.render.COUNT_LABELS)."""
    labels = _text_map(raw, "quantity.labels", path)
    extra = sorted(set(labels) - set(COUNT_LABEL_KEYS))
    if extra:
        raise PlaybookError(f"{path.name}: quantity.labels: unknown {', '.join(extra)} "
                            f"(allowed: {', '.join(COUNT_LABEL_KEYS)})")
    for key, text in labels.items():
        _form(text, f"quantity.labels.{key}", path, ())
        if not text.strip():
            raise PlaybookError(f"{path.name}: quantity.labels.{key} must not be blank")
    return labels


def _assumption(raw, path: Path) -> dict:
    """assumption (optional): `because`, the words put before an assumption's reason ("<what>, because <why>"), and
    `leads`, the words a reason may already start with (then nothing is put before it)."""
    if not isinstance(raw, dict):
        raise PlaybookError(f"{path.name}: assumption must be an object")
    extra = sorted(set(raw) - set(ASSUMPTION_KEYS))
    if extra:
        raise PlaybookError(f"{path.name}: assumption: unknown {', '.join(extra)} "
                            f"(allowed: {', '.join(ASSUMPTION_KEYS)})")
    out: dict = {}
    if "because" in raw:
        _form(raw["because"], "assumption.because", path, ())
        if not raw["because"].strip():
            raise PlaybookError(f"{path.name}: assumption.because must not be blank")
        out["because"] = raw["because"]
    if "leads" in raw:
        out["leads"] = _strings(raw["leads"], "assumption.leads", path, allow_empty=False)
        for n, lead in enumerate(out["leads"]):
            _form(lead, f"assumption.leads[{n}]", path, ())
    return out


def _casing(raw, path: Path) -> dict:
    """casing (optional): the house casing of names. acronyms: the words printed in their own spelling (BMS,
    BACnet); small_words: the lower-case joining words left lower case after the first word; not_plural: the
    lower-case words ending in s that are not plurals; acronym_before: a lower-case word that is also an ordinary
    word -> the words it must come before to print upper case ("co" before "sensor" -> CO)."""
    if not isinstance(raw, dict):
        raise PlaybookError(f"{path.name}: casing must be an object")
    extra = sorted(set(raw) - set(CASING_KEYS))
    if extra:
        raise PlaybookError(f"{path.name}: casing: unknown {', '.join(extra)} (allowed: {', '.join(CASING_KEYS)})")
    out: dict = {}
    for key, pattern, kind in (("acronyms", _WORD, "one word of letters and digits"),
                               ("small_words", _LOWER_WORD, "one lower-case word"),
                               ("not_plural", _LOWER_WORD, "one lower-case word")):
        if key in raw:
            words = _strings(raw[key], f"casing.{key}", path)
            if not all(pattern.fullmatch(w) for w in words):
                raise PlaybookError(f"{path.name}: casing.{key}: each entry must be {kind}")
            out[key] = words
    if "acronym_before" in raw:
        before = raw["acronym_before"]
        if not isinstance(before, dict):
            raise PlaybookError(f"{path.name}: casing.acronym_before must map a word to the words it comes before")
        out["acronym_before"] = {}
        for word, following in before.items():
            words = _strings(following, f"casing.acronym_before.{word}", path, allow_empty=False)
            if not _LOWER_WORD.fullmatch(word) or not all(_LOWER_WORD.fullmatch(w) for w in words):
                raise PlaybookError(f"{path.name}: casing.acronym_before: {word!r} and the words it comes before "
                                    "must be lower-case words")
            out["acronym_before"][word] = words
    return out


_load_wording = load_wording


# ---- files ---------------------------------------------------------------------------------------------------

def _read(path: Path) -> str:
    path = Path(path)
    try:
        return path.read_text(encoding="utf-8-sig")      # a BOM (Windows editors) is read through, never kept
    except UnicodeDecodeError as error:
        raise PlaybookError(f"{path.name}: not valid UTF-8 text ({error})") from None
    except OSError as error:
        raise PlaybookError(f"{path}: cannot be read ({error.strerror or error})") from None


def _json(path: Path) -> dict:
    text = _read(path)
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as error:
        raise PlaybookError(f"{path.name}: not valid JSON ({error})") from None
    if not isinstance(data, dict):
        raise PlaybookError(f"{path.name}: must be a JSON object")
    return data
