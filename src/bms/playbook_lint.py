"""Playbook linter: checks playbook/rules.md, shapes.json and wording.json and reports problems in plain words.

"Lints clean" means the app can load the Playbook (each file goes through the loader's own checks in
`bms.playbook`) and the house style holds: no emoji, no arrows, no source ids, no trailing whitespace, no rule names
that differ only in case. The rule names the code needs come from the code itself: `bms.validate.RULE` and the
rule names quoted in the AI prompts (`src/bms/prompts/*.md`). A Playbook rule no code names is the estimator's to
rename or drop. `python -m bms playbook-lint [ROOT]` prints the problems and exits 1, or exits 0 when clean.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from bms.citations import ONE_ID
from bms.playbook import DEFAULT_ROOT, PlaybookError, load_rules, load_shapes, load_wording
from bms.validate import RULE

PROMPTS = Path(__file__).resolve().parent / "prompts"

# A quoted phrase in a prompt that starts with a capital and has a space is a rule citation (the same reading
# tests/bms/test_rule_names.py uses).
_QUOTED = re.compile(r'"([^"\n]+)"')

# Source ids quoted as examples ("S12", "S40 note 1") are allowed only in this rule.
SOURCE_ID_EXAMPLES_RULE = "Assumption wording has no source ids"
# F and C ids look like equipment tags (fan F1, compressor C2); the Playbook may name those.
TAG_LOOKALIKE_PREFIXES = ("F", "C")

# Arrow characters: the Unicode arrows, single and double, any direction. Checked before emoji, so an arrow from
# the dingbats block (U+2794 to U+27BE) is reported as an arrow, not as an emoji.
ARROW_CHARS = (
    "\\u2190-\\u21FF"        # arrows
    "\\u2794-\\u27AF\\u27B1-\\u27BE"  # dingbat arrows
    "\\u27F0-\\u27FF"        # supplemental arrows-A
    "\\u2900-\\u297F"        # supplemental arrows-B
    "\\u2B00-\\u2B11\\u2B30-\\u2B4F\\u2B5A-\\u2BB7"  # the arrows of miscellaneous symbols and arrows
)
# Arrows: those characters and the ASCII -> and =>. Not <= and not ::.
ARROW_PATTERN = re.compile(rf"->|=>|[{ARROW_CHARS}]")
_ARROW_CHAR = re.compile(rf"[{ARROW_CHARS}]")
EMOJI_PATTERN = re.compile(
    "["
    "\\U0001F000-\\U0001F02F"  # mahjong tiles
    "\\U0001F0A0-\\U0001F0FF"  # playing cards
    "\\U0001F1E0-\\U0001F1FF"  # flags
    "\\U0001F300-\\U0001F5FF"  # symbols and pictographs
    "\\U0001F600-\\U0001F64F"  # emoticons
    "\\U0001F680-\\U0001F6FF"  # transport and map
    "\\U0001F900-\\U0001F9FF"  # supplemental symbols and pictographs
    "\\U0001FA70-\\U0001FAFF"  # symbols and pictographs extended-A
    "\\u2300-\\u23FF"          # miscellaneous technical (watch, hourglass, alarm clock)
    "\\u2600-\\u26FF"          # miscellaneous symbols
    "\\u2700-\\u27BF"          # dingbats (its arrows are reported as arrows first)
    "\\u2B1B\\u2B1C\\u2B50-\\u2B55"  # large squares, stars and circles
    "]"
)

_COMMENT = re.compile(r"<!--.*?-->", re.S)
_FENCE_MARK = re.compile(r" {0,3}(`{3,}|~{3,})")
_BACKTICKS = re.compile(r"`[^`\n]*`")
_DOUBLE_QUOTED = re.compile(r'"[^"\n]*"')


@dataclass(frozen=True)
class LintProblem:
    file: str
    line: int | None
    message: str

    def __str__(self) -> str:
        loc = f"{self.file}:{self.line}" if self.line else self.file
        return f"{loc}: {self.message}"


def prompt_rule_names(folder: Path | None = None) -> set[str]:
    """The rule names the AI prompts quote."""
    names: set[str] = set()
    for prompt in sorted(Path(folder or PROMPTS).glob("*.md")):
        names |= {q for q in _QUOTED.findall(prompt.read_text(encoding="utf-8")) if q[:1].isupper() and " " in q}
    return names


def referenced_rule_names() -> set[str]:
    """The rule names the code needs in rules.md: every validator's rule and every rule a prompt quotes. Read at
    call time, so a new name in `bms.validate.RULE` or a prompt is required at once."""
    return set(RULE.values()) | prompt_rule_names(PROMPTS)


def lint_playbook(root: Path = DEFAULT_ROOT, known_rule_names: set[str] | None = None) -> list[LintProblem]:
    """Lint the Playbook in `root`. Returns the problems (empty: clean). `known_rule_names`: rule names that must
    be in rules.md (the CLI passes `referenced_rule_names()`)."""
    root = Path(root)
    rule_problems, names = _lint_rules(root / "rules.md")
    problems = rule_problems + _lint_shapes(root / "shapes.json") + _lint_wording(root / "wording.json")
    if known_rule_names is not None and names is not None:
        path = root / "rules.md"
        problems += [LintProblem(str(path), None, f"rule {name!r} is used by validators/prompts but missing from "
                                                  "rules.md")
                     for name in sorted(set(known_rule_names) - names)]
    return problems


# ---- shared ------------------------------------------------------------------------------------------------------

def _read(path: Path) -> tuple[str | None, list[LintProblem]]:
    if not path.exists():
        return None, [LintProblem(str(path), None, "file not found")]
    try:
        return path.read_bytes().decode("utf-8-sig"), []
    except UnicodeDecodeError as error:
        return None, [LintProblem(str(path), None, f"is not UTF-8 text (the byte at position {error.start} cannot "
                                                   "be read); save it as UTF-8")]
    except OSError as error:
        return None, [LintProblem(str(path), None, f"cannot be read ({error.strerror or error})")]


def _loader_problem(path: Path, load) -> list[LintProblem]:
    """The loader's own verdict on one file, as a problem (none when the app can load it)."""
    try:
        load(path)
    except (PlaybookError, ValueError, OSError) as error:
        return [LintProblem(str(path), None, f"the app cannot load this file: {error}")]
    return []


def _blank(pattern: re.Pattern, text: str) -> str:
    """`text` with each match of `pattern` removed but its line breaks kept, so line numbers still hold."""
    return pattern.sub(lambda m: "\n" * m.group().count("\n"), text)


# ---- rules.md ----------------------------------------------------------------------------------------------------

def _fenced(lines: list[str]) -> set[int]:
    """Indexes of the lines inside a closed code fence (``` or ~~~, indented 0 to 3 spaces), fence lines included.
    A fence closes on a line of the same character, at least as long, and nothing else; an unclosed fence hides
    nothing. One pass, so linear in the number of lines."""
    inside: set[int] = set()
    start, mark = None, ""
    for i, line in enumerate(lines):
        found = _FENCE_MARK.match(line)
        if start is None:
            if found:
                start, mark = i, found.group(1)
        elif (found and found.group(1)[0] == mark[0] and len(found.group(1)) >= len(mark)
              and not line[found.end():].strip()):
            inside.update(range(start, i + 1))
            start = None
    return inside


def _lint_rules(path: Path) -> tuple[list[LintProblem], set[str] | None]:
    """The loader's structural checks, made over the whole file in the loader's own words (so every defect is
    reported, once, with its line), then the house-style checks. The loader's verdict is added only when the walk
    found nothing the loader refuses, as a safety net."""
    text, problems = _read(path)
    if text is None:
        return problems, None
    refused: list[LintProblem] = []

    def problem(n: int, message: str) -> None:
        problems.append(LintProblem(str(path), n, message))

    def refuse(n: int | None, message: str) -> None:
        where = f"{path.name} line {n}" if n else path.name
        refused.append(LintProblem(str(path), n, f"the app cannot load this file: {where}: {message}"))

    lines = _blank(_COMMENT, text).splitlines()         # comments (the sample mark too) are not rule text
    fenced = _fenced(lines)                             # arrows count outside code fences and backticks

    topics: set[str] = set()
    topic: str | None = None
    rule: str | None = None
    rule_line = 0
    rule_text: list[str] = []
    names: set[str] = set()
    folded: dict[str, str] = {}

    def close() -> None:
        if rule and not "\n".join(rule_text).strip():
            refuse(None, f"rule {rule!r} has no text")

    for n, line in enumerate(lines, start=1):
        where = f"rule {rule!r}" if rule else f"line {n}"
        nameless = False
        if line.startswith("### "):
            close()
            rule, rule_line, rule_text = line[4:].strip(), n, []
            where, nameless = f"rule heading {rule!r}", not rule
            if topic is None:
                refuse(n, f"rule {rule!r} is not under a topic (## heading)")
            elif not rule:
                refuse(n, "a rule with no name")
            elif rule in names:
                refuse(n, f"rule {rule!r} appears twice")
            elif rule.casefold() in folded:
                problem(n, f"rule {rule!r} differs only in case from rule {folded[rule.casefold()]!r}")
            if rule:
                names.add(rule)
                folded.setdefault(rule.casefold(), rule)
        elif line.startswith("## "):
            close()
            rule, topic = None, line[3:].strip()
            where, nameless = f"topic {topic!r}", not topic
            if not topic or topic in topics:
                refuse(n, f"topic {topic!r} is empty or appears twice")
            topics.add(topic)
        elif line.startswith("#### "):
            refuse(n, "only ## topics and ### rules are allowed")
        elif rule is not None:
            rule_text.append(line)

        if line != line.rstrip() and not nameless:      # a nameless heading is already reported
            problem(n, f"{where} has trailing whitespace")
        style = "" if n - 1 in fenced else _blank(_BACKTICKS, line)
        if ARROW_PATTERN.search(style):
            problem(n, f"{where} contains an arrow")
        if EMOJI_PATTERN.search(_ARROW_CHAR.sub("", line)):
            problem(n, f"{where} contains emoji")
        checked = _blank(_DOUBLE_QUOTED, line) if rule == SOURCE_ID_EXAMPLES_RULE else line
        for match in ONE_ID.finditer(checked):
            if not match.group().startswith(TAG_LOOKALIKE_PREFIXES):
                problem(n, f"{where} contains source id {match.group()!r}")
    close()
    if not topics:
        refuse(None, "no topic (## heading)")
    return (refused or _loader_problem(path, load_rules)) + problems, names


# ---- shapes.json -------------------------------------------------------------------------------------------------

def _json(path: Path) -> tuple[dict | None, list[LintProblem]]:
    text, problems = _read(path)
    if text is None:
        return None, problems
    try:
        data = json.loads(text)
    except ValueError as error:
        return None, [LintProblem(str(path), getattr(error, "lineno", None), f"invalid JSON: {error}")]
    if not isinstance(data, dict):
        return None, [LintProblem(str(path), None, "must be a JSON object")]
    return data, []


def _lint_shapes(path: Path) -> list[LintProblem]:
    data, problems = _json(path)
    if data is None:
        return problems

    def problem(message: str) -> None:
        problems.append(LintProblem(str(path), None, message))

    if not isinstance(data.get("shapes"), list):
        problem('"shapes" must be a list')
        return problems
    for idx, shape in enumerate(data["shapes"]):
        if not isinstance(shape, dict):
            problem(f"shapes[{idx}] must be an object")
            continue
        name = shape.get("name", f"<unnamed shape {idx}>")
        line_order, wording, under = shape.get("line_order", []), shape.get("wording", {}), shape.get("under", {})
        if not isinstance(line_order, list) or not all(isinstance(s, str) for s in line_order):
            problem(f"shape {name!r}: line_order must be a list of slot names")
            continue
        if not isinstance(wording, dict):
            problem(f"shape {name!r}: wording must map each slot to its text")
        else:
            for slot in line_order:
                if slot not in wording:
                    problem(f"shape {name!r}: slot {slot!r} in line_order has no wording")
        if not isinstance(under, dict):
            problem(f"shape {name!r}: under must map each sub-line slot to its parent slot")
            continue
        for slot, parent in under.items():
            if slot not in line_order:
                problem(f"shape {name!r}: under slot {slot!r} not in line_order")
            elif not isinstance(parent, str) or parent not in line_order:
                problem(f"shape {name!r}: under parent {parent!r} not in line_order")
            elif line_order.index(parent) >= line_order.index(slot):
                problem(f"shape {name!r}: under parent {parent!r} must come before {slot!r} in line_order")
    return problems or _loader_problem(path, load_shapes)     # the loader's verdict only when it adds something


# ---- wording.json ------------------------------------------------------------------------------------------------

def _lint_wording(path: Path) -> list[LintProblem]:
    """wording.json is judged by the loader alone (its words); the linter adds only the file and JSON checks."""
    data, problems = _json(path)
    return problems if data is None else _loader_problem(path, load_wording)
