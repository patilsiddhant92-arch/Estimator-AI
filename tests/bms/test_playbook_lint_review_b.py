"""REVIEW-020b: gaps left in the corrected Playbook linter (lead/correct-020 3bcaf28). Invented playbooks only.

Each test fails on 3bcaf28.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from bms.playbook_lint import lint_playbook

REPO_PLAYBOOK = Path(__file__).resolve().parents[2] / "playbook"


def _playbook(tmp_path: Path, rules: str) -> Path:
    root = tmp_path / "playbook"
    shutil.copytree(REPO_PLAYBOOK, root)
    (root / "rules.md").write_text(rules, encoding="utf-8")
    return root


# One defect in rules.md is one problem: today the loader's verdict and the linter's own check both print it.
ONE_DEFECT = {
    "a rule name twice": "# P\n\n## Topic\n\n### A\nx.\n\n### A\ny.\n",
    "a rule with no text": "# P\n\n## Topic\n\n### A\n\n### B\ny.\n",
    "a rule before any topic": "# P\n\n### A\nx.\n\n## Topic\n\n### B\ny.\n",
    "a level-four heading": "# P\n\n## Topic\n\n### A\nx.\n#### deeper\n",
}


@pytest.mark.parametrize("case", sorted(ONE_DEFECT))
def test_one_defect_is_reported_once(tmp_path, case):
    problems = lint_playbook(_playbook(tmp_path, ONE_DEFECT[case]))
    assert len(problems) == 1, [str(p) for p in problems]


def test_a_tilde_code_fence_is_a_code_fence(tmp_path):
    # Ruling: arrows count outside backticks and code fences. ~~~ opens a code fence as ``` does (CommonMark).
    rules = "# P\n\n## Topic\n\n### A\nThe form is:\n~~~\nA -> B\n~~~\n"
    assert [str(p) for p in lint_playbook(_playbook(tmp_path, rules))] == []
