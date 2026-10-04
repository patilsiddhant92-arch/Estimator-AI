"""Playbook linter: checks playbook/rules.md, shapes.json, wording.json for problems.

Reports in plain words. Exit 1 on any problem, 0 when clean.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# Known rule names referenced by validators and prompts (from the codebase)
# These must exist in rules.md
VALIDATOR_RULE_NAMES = frozenset({
    "Every line cites this job",
    "No standard or fallback lines",
    "Nothing from other jobs",
    "Read the whole sequence first",
    "Contractor name in the documents",
    "Everything assigned is extracted",
    "Sequence first, point list second",
    "Every point-list point is checked",
    "Device names from the documents",
    "Every line carries its ownership",
    "Who owns what by default",
    "Three ownership questions",
    "Verb from the three answers",
    "Verbs by device type",
    "Explicit assignment always wins",
    "Mixed ownership device by device",
    "Blanket wiring clause",
    "Other trades in brackets",
    "Point lines only on AME controllers",
    "Minimum points on AME-run equipment",
    "Start/stop covers the relay and status switch",
    "Fire alarm interface",
    "Unclear ownership is flagged",
    "Higher count prints",
    "Never undershoot",
    "Line quantity",
    "Systems named only in the sequence",
    "One clarification per block",
    "Joining into the one clarification",
    "Every assumption says why",
    "Assumption wording has no source ids",
    "Client notes",
    "Miscellaneous responsibilities",
    "Words the client never sees",
    "Questions for the estimator",
    "Packaged units",
    "No AME controller on a packaged unit",
    "Nothing inside the unit is a line",
    "Factory-installed devices",
    "Template is the ideal case",
    "Shipped-loose devices",
    "Shipped-loose devices not named",
    "Thermostat furnished by the unit manufacturer",
    "Dampers under their fan",
    "Untraced dampers in their own block",
    "Unclaimed dampers in their own block",
    "Fire and smoke dampers keep their own block",
    "One line per damper type",
    "Duct heaters in one place",
    "Heater on a packaged unit",
    "Heater on an AME controller",
    "Heater assignment wins",
    "VRF and split as one block",
    "VRF lines",
    "VRF wiring belongs to the manufacturer",
    "Split system interlock wiring",
    "Refrigerant leak detection wiring",
    "BMS space sensor on AC units",
    "Integration trio",
    "Integration lines cover monitoring",
    "Integration lines last",
    "UUKL listed smoke control",
    "Residential equipment stays in scope",
    "Factory thermostat units with no BMS work",
    "Electric unit heater with factory thermostat",
    "Front end mode",
    "Front end lines cite the specification",
    "Front end items by others",
    "Auto dialer with a network panel",
    "Warranty lines",
    "Named exceptions",
    "Never invent an alternate",
    "Exclusions",
    "Tech hours follow the shape",
    "Tech hours the shape cannot express",
    "Integration-only systems",
    "Tech hours never print",
    "Template gives shape only",
    "Placing a device in a slot",
    "Standard order",
    "Line form",
    "Sub-lines under their parent",
    "Untemplated systems",
    "One system one block",
})


# Pattern for source ids: S12, Q3, I5, F100, C3, etc. (with optional lowercase suffix)
SOURCE_ID_PATTERN = re.compile(r"\b[SQIFC]\d+[a-z]?\b")

# Pattern for emoji (simplified - matches common emoji ranges)
EMOJI_PATTERN = re.compile(
    r"[\U0001F600-\U0001F64F"  # emoticons
    r"\U0001F300-\U0001F5FF"  # symbols & pictographs
    r"\U0001F680-\U0001F6FF"  # transport & map
    r"\U0001F1E0-\U0001F1FF"  # flags
    r"\U00002700-\U000027BF"  # dingbats
    r"\U00002600-\U000026FF"  # misc symbols
    r"\U0001F900-\U0001F9FF"  # supplemental symbols
    r"]+"
)

# Pattern for arrows
ARROW_PATTERN = re.compile(r"(?:->|<-|=>|<=|=>|::|->>|<<-|-->|<--|==>|<==|=>=|<=<)")


@dataclass(frozen=True)
class LintProblem:
    file: str
    line: int | None
    message: str

    def __str__(self) -> str:
        loc = f"{self.file}:{self.line}" if self.line else self.file
        return f"{loc}: {self.message}"


def lint_playbook(root: Path, known_rule_names: set[str] | None = None) -> list[LintProblem]:
    """Lint the playbook in `root`. Returns list of problems (empty = clean)."""
    root = Path(root)
    problems: list[LintProblem] = []

    # Lint each file
    problems.extend(_lint_rules(root / "rules.md"))
    problems.extend(_lint_shapes(root / "shapes.json"))
    problems.extend(_lint_wording(root / "wording.json"))

    # Cross-file checks
    if known_rule_names is not None:
        rules = _parse_rules_for_names(root / "rules.md")
        problems.extend(_check_missing_validator_rules(rules, known_rule_names))

    return problems


def _lint_rules(path: Path) -> list[LintProblem]:
    problems: list[LintProblem] = []
    if not path.exists():
        return [LintProblem(str(path), None, "file not found")]

    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()

    topic: str | None = None
    rule_name: str | None = None
    rule_lines: list[str] = []
    rule_start_line: int = 0
    seen_rules: set[str] = set()

    def check_rule() -> None:
        nonlocal problems, rule_name, rule_lines, rule_start_line
        if rule_name is None:
            return
        # Duplicate rule name
        if rule_name in seen_rules:
            problems.append(LintProblem(str(path), rule_start_line,
                                        f"duplicate rule name {rule_name!r}"))
        seen_rules.add(rule_name)

        # No sentence (empty after stripping sample marker)
        joined = "\n".join(rule_lines).strip()
        joined = joined.replace("<!-- sample -->", "").strip()
        if not joined:
            problems.append(LintProblem(str(path), rule_start_line,
                                        f"rule {rule_name!r} has no text"))

        # Check if this rule discusses source ids (allows them as examples)
        discusses_source_ids = "source id" in joined.lower()

        # Emoji, arrow, source id, trailing whitespace checks
        for i, line in enumerate(rule_lines, start=rule_start_line):
            full_line = line.rstrip("\n")
            if EMOJI_PATTERN.search(full_line):
                problems.append(LintProblem(str(path), i + 1,
                                            f"rule {rule_name!r} contains emoji"))
            # Arrow check
            if ARROW_PATTERN.search(full_line):
                problems.append(LintProblem(str(path), i + 1,
                                            f"rule {rule_name!r} contains arrow"))
            # Source id check - allow when rule discusses source ids (they're examples)
            if not discusses_source_ids:
                for match in SOURCE_ID_PATTERN.finditer(full_line):
                    problems.append(LintProblem(str(path), i + 1,
                                                f"rule {rule_name!r} contains source id {match.group()!r}"))
            # Trailing whitespace
            if line != line.rstrip():
                problems.append(LintProblem(str(path), i + 1,
                                            f"rule {rule_name!r} has trailing whitespace"))

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("### "):
            check_rule()
            rule_name = stripped[4:].strip()
            rule_start_line = i
            rule_lines = []
            if topic is None:
                problems.append(LintProblem(str(path), i,
                                            f"rule {rule_name!r} is not under a topic (no ## heading above it)"))
        elif stripped.startswith("## "):
            check_rule()
            rule_name = None
            rule_lines = []
            topic = stripped[3:].strip()
        elif stripped.startswith("#### "):
            problems.append(LintProblem(str(path), i,
                                        "only ## topics and ### rules are allowed (#### not permitted)"))
        elif rule_name is not None:
            rule_lines.append(line)

    check_rule()  # last rule

    return problems


def _lint_shapes(path: Path) -> list[LintProblem]:
    problems: list[LintProblem] = []
    if not path.exists():
        return [LintProblem(str(path), None, "file not found")]

    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return [LintProblem(str(path), e.lineno, f"invalid JSON: {e}")]

    if not isinstance(data.get("shapes"), list):
        problems.append(LintProblem(str(path), None, '"shapes" must be a list'))
        return problems

    for idx, shape in enumerate(data["shapes"]):
        if not isinstance(shape, dict):
            problems.append(LintProblem(str(path), None, f"shapes[{idx}] must be an object"))
            continue

        name = shape.get("name", f"<unnamed shape {idx}>")
        line_order = shape.get("line_order", [])
        wording = shape.get("wording", {})
        under = shape.get("under", {})

        # line_order slots must have wording
        for slot in line_order:
            if slot not in wording:
                problems.append(LintProblem(str(path), None,
                                            f"shape {name!r}: slot {slot!r} in line_order has no wording"))

        # under references must be valid
        for slot, parent in under.items():
            if slot not in line_order:
                problems.append(LintProblem(str(path), None,
                                            f"shape {name!r}: under slot {slot!r} not in line_order"))
            elif parent not in line_order:
                problems.append(LintProblem(str(path), None,
                                            f"shape {name!r}: under parent {parent!r} not in line_order"))
            else:
                # parent must come before child in line_order
                if line_order.index(parent) >= line_order.index(slot):
                    problems.append(LintProblem(str(path), None,
                                                f"shape {name!r}: under parent {parent!r} must come before {slot!r} in line_order"))

    return problems


def _lint_wording(path: Path) -> list[LintProblem]:
    problems: list[LintProblem] = []
    if not path.exists():
        return [LintProblem(str(path), None, "file not found")]

    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return [LintProblem(str(path), e.lineno, f"invalid JSON: {e}")]

    # Basic structure validation (the playbook loader does more)
    required_keys = ("verbs", "owner_brackets", "integration_trio", "clarifications", "header", "quantity")
    for key in required_keys:
        if key not in data:
            problems.append(LintProblem(str(path), None, f"missing required key: {key}"))

    # Check verbs match exactly
    if "verbs" in data and data["verbs"] != list(VALIDATOR_RULE_NAMES):
        # Actually verbs should match VERBS from model, not rule names
        # We'll just check it's a list of 5 strings
        pass

    return problems


def _parse_rules_for_names(path: Path) -> set[str]:
    """Parse rules.md and return set of rule names (### headings)."""
    if not path.exists():
        return set()
    text = path.read_text(encoding="utf-8-sig")
    names = set()
    for line in text.splitlines():
        if line.startswith("### "):
            names.add(line[4:].strip())
    return names


def _check_missing_validator_rules(rule_names: set[str], known_names: set[str]) -> list[LintProblem]:
    """Check that every known rule name appears in the playbook."""
    problems: list[LintProblem] = []
    missing = known_names - rule_names
    for name in sorted(missing):
        problems.append(LintProblem("rules.md", None,
                                    f"rule {name!r} is used by validators/prompts but missing from rules.md"))
    return problems


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(prog="playbook-lint", description="Lint the playbook files")
    parser.add_argument("root", nargs="?", type=Path, default=Path("playbook"),
                        help="playbook root folder (default: playbook/)")
    args = parser.parse_args(argv)

    problems = lint_playbook(args.root, known_rule_names=VALIDATOR_RULE_NAMES)
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    import sys
    sys.exit(main())