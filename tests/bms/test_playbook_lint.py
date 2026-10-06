"""Playbook linter tests — invented playbooks in a temp folder. No real job data."""
from __future__ import annotations

import json
from pathlib import Path

from bms.playbook_lint import lint_playbook


def _write_playbook(tmp: Path, rules: str, shapes: dict, wording: dict) -> Path:
    root = tmp / "playbook"
    root.mkdir()
    (root / "rules.md").write_text(rules, encoding="utf-8")
    (root / "shapes.json").write_text(json.dumps(shapes, indent=2), encoding="utf-8")
    (root / "wording.json").write_text(json.dumps(wording, indent=2), encoding="utf-8")
    return root


MINIMAL_SHAPES = {
    "$format": {},
    "shapes": [{
        "name": "Test Shape",
        "applies_to": {"prefixes": ["TS"], "kind_words": ["test"]},
        "header": "Qty ({n}) {name} {tags}",
        "family_names": ["Test"],
        "line_order": ["device"],
        "slot_kinds": {"device": "device"},
        "wording": {"device": "{verb} {device}{owner}{qty}"},
        "tech_hours": {"per": "unit", "hours": 1, "when": []}
    }]
}

MINIMAL_WORDING = {
    "$format": {},
    "verbs": ["Furnish and Install", "Furnish", "Furnish and Wire", "Install and Wire", "Wire"],
    "owner_brackets": {
        "Unit Mfr.": " (Furnished by Unit Mfr.)",
        "FA": " (Relay Furnished by FA)",
        "Others": " (Furnished by Others)",
        "Mechanical Contractor": " (Furnished by Mechanical Contractor)",
        "Electrical Contractor": " (Furnished by Electrical Contractor)",
        "Owner": " (Furnished by Owner)"
    },
    "integration_trio": {
        "lines": [
            "Furnish BMS Communication Wiring to {what} Factory Controls",
            "Map Available Points Via Mfr. Provided BMS Interface",
            "AME requires mfr. Rep to assist in integration, cost to be incurred by mech contractor"
        ],
        "depths": [1, 1, 2]
    },
    "clarifications": {
        "confirm": "*Confirm {text}",
        "assumed": "*Assumed: {text}",
        "per_drawings": "*Quantity per {text} drawings",
        "note": "**{text}"
    },
    "header": {"count": "{n}", "unknown_count": "##", "tags_joiner": ", "},
    "quantity": {"line": " (Qty. {n} Total)", "unknown": " (Qty. ##)", "others_note": "*Qty. {counts}."},
    "count_causes": {"form": "({causes})", "joiner": ", ", "typical": "likely a typical unit at each place",
                     "labelled_twice": "likely one unit labelled more than once on a sheet"}
}


def test_clean_playbook_passes(tmp_path):
    rules = """# AME Playbook

## Topic One

### Rule One
This is a valid rule with text.

### Rule Two
Another valid rule.
"""
    root = _write_playbook(tmp_path, rules, MINIMAL_SHAPES, MINIMAL_WORDING)
    problems = lint_playbook(root)
    assert problems == []


def test_duplicate_rule_names_fails(tmp_path):
    rules = """# AME Playbook

## Topic One

### Same Name
First rule.

### Same Name
Duplicate rule name.
"""
    root = _write_playbook(tmp_path, rules, MINIMAL_SHAPES, MINIMAL_WORDING)
    problems = lint_playbook(root)
    # In the loader's own words (REVIEW-020b: one defect, one problem, the loader's wording).
    assert any("appears twice" in p.message.lower() and "same name" in p.message.lower() for p in problems)


def test_rule_with_no_sentence_fails(tmp_path):
    rules = """# AME Playbook

## Topic One

### Empty Rule

"""
    root = _write_playbook(tmp_path, rules, MINIMAL_SHAPES, MINIMAL_WORDING)
    problems = lint_playbook(root)
    assert any("no sentence" in p.message.lower() or "no text" in p.message.lower() for p in problems)


def test_emoji_in_rule_fails(tmp_path):
    rules = """# AME Playbook

## Topic One

### Rule With Emoji
This rule has an emoji 😀 in it.
"""
    root = _write_playbook(tmp_path, rules, MINIMAL_SHAPES, MINIMAL_WORDING)
    problems = lint_playbook(root)
    assert any("emoji" in p.message.lower() for p in problems)


def test_arrow_in_rule_fails(tmp_path):
    rules = """# AME Playbook

## Topic One

### Rule With Arrow
This rule has an arrow -> in it.
"""
    root = _write_playbook(tmp_path, rules, MINIMAL_SHAPES, MINIMAL_WORDING)
    problems = lint_playbook(root)
    assert any("arrow" in p.message.lower() for p in problems)


def test_source_id_in_rule_fails(tmp_path):
    rules = """# AME Playbook

## Topic One

### Rule With Source ID
This rule references S12 and Q3 in the text.
"""
    root = _write_playbook(tmp_path, rules, MINIMAL_SHAPES, MINIMAL_WORDING)
    problems = lint_playbook(root)
    assert any("source id" in p.message.lower() and ("s12" in p.message.lower() or "q3" in p.message.lower()) for p in problems)


def test_heading_outside_topic_fails(tmp_path):
    rules = """# AME Playbook

### Rule Before Topic
This rule is not under any topic.

## Topic One

### Valid Rule
This is under a topic.
"""
    root = _write_playbook(tmp_path, rules, MINIMAL_SHAPES, MINIMAL_WORDING)
    problems = lint_playbook(root)
    assert any("outside" in p.message.lower() or "not under" in p.message.lower() for p in problems)


def test_shape_line_order_slot_missing_wording_fails(tmp_path):
    shapes = {
        "$format": {},
        "shapes": [{
            "name": "Bad Shape",
            "applies_to": {"prefixes": ["BS"], "kind_words": ["bad"]},
            "header": "Qty ({n}) {name} {tags}",
            "family_names": ["Bad"],
            "line_order": ["device", "missing_wording"],
            "slot_kinds": {"device": "device", "missing_wording": "device"},
            "wording": {"device": "{verb} {device}{owner}{qty}"},
            "tech_hours": {"per": "unit", "hours": 1, "when": []}
        }]
    }
    root = _write_playbook(tmp_path, "# AME Playbook\n\n## Topic\n\n### Rule\nText.\n", shapes, MINIMAL_WORDING)
    problems = lint_playbook(root)
    assert any("missing wording" in p.message.lower() or "no wording" in p.message.lower() for p in problems)


def test_validator_rule_missing_from_playbook_fails(tmp_path, monkeypatch):
    """A rule name used by validators but missing from rules.md should be flagged."""
    # We need to mock the validator rule names. The linter should check against
    # a known set of rule names that validators/prompts reference.
    # For the test, we'll check that the linter has a way to know about these.
    rules = """# AME Playbook

## Topic One

### Rule One
Valid rule.
"""
    root = _write_playbook(tmp_path, rules, MINIMAL_SHAPES, MINIMAL_WORDING)
    # The linter should know about rule names from validators/prompts
    # We'll test this by checking the linter's behavior with a known missing rule
    problems = lint_playbook(root, known_rule_names={"Rule One", "Missing Rule"})
    assert any("missing" in p.message.lower() and "missing rule" in p.message.lower() for p in problems)


def test_trailing_whitespace_fails(tmp_path):
    rules = """# AME Playbook

## Topic One

### Rule With Trailing Space
This rule has trailing spaces.   
"""
    root = _write_playbook(tmp_path, rules, MINIMAL_SHAPES, MINIMAL_WORDING)
    problems = lint_playbook(root)
    assert any("trailing whitespace" in p.message.lower() for p in problems)


def test_repo_playbook_lints_clean():
    """The repo playbook lints clean, through the function and through the CLI (with the code's rule names)."""
    from bms.__main__ import main
    repo_playbook = Path(__file__).resolve().parents[2] / "playbook"
    assert (repo_playbook / "rules.md").exists()
    problems = lint_playbook(repo_playbook)
    assert problems == [], f"Repo playbook has problems: {[str(p) for p in problems]}"
    assert main(["playbook-lint", str(repo_playbook)]) == 0


# Additional edge case tests

def test_multiple_emojis_flagged(tmp_path):
    rules = """# AME Playbook

## Topic One

### Rule With Multiple Emojis
Has 😀 and 🎉 and 🚀 here.
"""
    root = _write_playbook(tmp_path, rules, MINIMAL_SHAPES, MINIMAL_WORDING)
    problems = lint_playbook(root)
    emoji_problems = [p for p in problems if "emoji" in p.message.lower()]
    assert len(emoji_problems) >= 1


def test_source_id_variants_flagged(tmp_path):
    rules = """# AME Playbook

## Topic One

### Rule With Various Source IDs
References S1, Q99, I5, F100, C3, S12a, Q3b.
"""
    root = _write_playbook(tmp_path, rules, MINIMAL_SHAPES, MINIMAL_WORDING)
    problems = lint_playbook(root)
    source_problems = [p for p in problems if "source id" in p.message.lower()]
    assert len(source_problems) >= 1


def test_shape_under_references_valid_parent(tmp_path):
    """Sub-line 'under' references must point to a valid earlier slot."""
    shapes = {
        "$format": {},
        "shapes": [{
            "name": "Bad Under Shape",
            "applies_to": {"prefixes": ["BUS"], "kind_words": ["bad under"]},
            "header": "Qty ({n}) {name} {tags}",
            "family_names": ["Bad Under"],
            "line_order": ["parent", "child"],
            "slot_kinds": {"parent": "device", "child": "device"},
            "wording": {"parent": "{verb} {device}{owner}{qty}", "child": "{device}{owner}{qty}"},
            "under": {"child": "parent"},
            "tech_hours": {"per": "unit", "hours": 1, "when": []}
        }]
    }
    root = _write_playbook(tmp_path, "# AME Playbook\n\n## Topic\n\n### Rule\nText.\n", shapes, MINIMAL_WORDING)
    problems = lint_playbook(root)
    # This should pass - valid under reference
    under_problems = [p for p in problems if "under" in p.message.lower()]
    assert len(under_problems) == 0


def test_shape_under_references_invalid_parent_fails(tmp_path):
    """Sub-line 'under' referencing non-existent or later slot should fail."""
    shapes = {
        "$format": {},
        "shapes": [{
            "name": "Bad Under Shape",
            "applies_to": {"prefixes": ["BUS"], "kind_words": ["bad under"]},
            "header": "Qty ({n}) {name} {tags}",
            "family_names": ["Bad Under"],
            "line_order": ["parent", "child"],
            "slot_kinds": {"parent": "device", "child": "device"},
            "wording": {"parent": "{verb} {device}{owner}{qty}", "child": "{device}{owner}{qty}"},
            "under": {"child": "nonexistent"},
            "tech_hours": {"per": "unit", "hours": 1, "when": []}
        }]
    }
    root = _write_playbook(tmp_path, "# AME Playbook\n\n## Topic\n\n### Rule\nText.\n", shapes, MINIMAL_WORDING)
    problems = lint_playbook(root)
    assert any("under" in p.message.lower() and ("nonexistent" in p.message.lower() or "not in line_order" in p.message.lower()) for p in problems)


def test_shape_under_cycle_fails(tmp_path):
    """Sub-line 'under' where parent comes after child should fail."""
    shapes = {
        "$format": {},
        "shapes": [{
            "name": "Cycle Shape",
            "applies_to": {"prefixes": ["CS"], "kind_words": ["cycle"]},
            "header": "Qty ({n}) {name} {tags}",
            "family_names": ["Cycle"],
            "line_order": ["parent", "child"],
            "slot_kinds": {"parent": "device", "child": "device"},
            "wording": {"parent": "{verb} {device}{owner}{qty}", "child": "{device}{owner}{qty}"},
            "under": {"parent": "child"},  # parent under child - cycle
            "tech_hours": {"per": "unit", "hours": 1, "when": []}
        }]
    }
    root = _write_playbook(tmp_path, "# AME Playbook\n\n## Topic\n\n### Rule\nText.\n", shapes, MINIMAL_WORDING)
    problems = lint_playbook(root)
    assert any("under" in p.message.lower() and ("cycle" in p.message.lower() or "before" in p.message.lower() or "after" in p.message.lower()) for p in problems)