"""REVIEW-020: gaps in the Playbook linter, found by the primary review. Invented playbooks only.

Each test names a defect the review found; they fail on opencode/work 147ff61.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from bms.__main__ import main
from bms.playbook import PlaybookError, load_playbook
from bms.playbook_lint import lint_playbook

REPO_PLAYBOOK = Path(__file__).resolve().parents[2] / "playbook"
GOOD_RULES = "# P\n\n## Topic\n\n### Rule one\nPlain words.\n"


def _copy_playbook(tmp_path: Path) -> Path:
    root = tmp_path / "playbook"
    shutil.copytree(REPO_PLAYBOOK, root)
    return root


# A playbook the app's own loader refuses must never lint clean, and the linter must not crash on it.
REJECTED = {
    "empty rules file": ("rules.md", ""),
    "no topic heading": ("rules.md", "# P\n\nJust a sentence.\n"),
    "rule heading with no name": ("rules.md", "# P\n\n## Topic\n\n### \nText.\n"),
    "the same topic twice": ("rules.md", "# P\n\n## Topic\n\n### A\nx.\n\n## Topic\n\n### B\ny.\n"),
    "shapes file is a list": ("shapes.json", "[]"),
    "wording file is a list": ("wording.json", "[]"),
}


@pytest.mark.parametrize("case", sorted(REJECTED))
def test_a_playbook_the_loader_rejects_does_not_lint_clean(tmp_path, case):
    root = _copy_playbook(tmp_path)
    (root / "rules.md").write_text(GOOD_RULES, encoding="utf-8")
    name, text = REJECTED[case]
    (root / name).write_text(text, encoding="utf-8")
    with pytest.raises(PlaybookError):
        load_playbook(root)
    problems = lint_playbook(root)
    assert problems, f"{case}: the loader refuses this playbook but the linter reports nothing"


def test_the_sample_marker_is_not_reported_as_an_arrow(tmp_path):
    # rebuild-interfaces.md: "<!-- sample -->" right under a rule heading is a documented marker.
    root = _copy_playbook(tmp_path)
    (root / "rules.md").write_text("# P\n\n## Topic\n\n### Rule one\n<!-- sample -->\nPlain words.\n",
                                   encoding="utf-8")
    load_playbook(root)
    assert [p for p in lint_playbook(root) if "arrow" in p.message] == []


def test_the_estimator_may_rename_a_rule_no_code_names(tmp_path):
    # "Warranty lines" is not named by bms.validate.RULE or by any prompt; renaming it is the estimator's call.
    root = _copy_playbook(tmp_path)
    rules = (root / "rules.md").read_text(encoding="utf-8")
    assert "### Warranty lines\n" in rules
    (root / "rules.md").write_text(rules.replace("### Warranty lines\n", "### Warranty terms\n"), encoding="utf-8")
    load_playbook(root)
    assert main(["playbook-lint", str(root)]) == 0
