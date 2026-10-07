"""PBK-2, 4, 6, 10: the Playbook loader and linter fixes. Invented playbooks in temp folders, built from copies of
the invented sample Playbook or the repo Playbook. No job data."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from bms import ai
from bms.model import Count, Device, Family, Job, Ref, System
from bms.playbook import PlaybookError, load_playbook, load_rules, load_shapes
from bms.playbook_lint import lint_playbook, referenced_rule_names
from bms.validate import RULE

HERE = Path(__file__).resolve().parent
SAMPLE = HERE / "fixtures" / "sample_playbook"
REPO_PLAYBOOK = HERE.parents[1] / "playbook"
REF = Ref("S1", "invented words", "M-1, Invented.pdf page 1")


def _copy(tmp_path: Path, source: Path = SAMPLE) -> Path:
    root = tmp_path / "playbook"
    shutil.copytree(source, root)
    return root


def _uncited_job() -> Job:
    device = Device(id="EF.d1", slot="controller", name="Invented Controller", verb="Furnish and Install",
                    furnished_by="AME", installed_by="AME", wired_by="AME", quantity=Count(1, (REF,)), refs=(REF,))
    system = System(key="EF", name="Invented Exhaust Fan", shape="Exhaust Fan", control="field",
                    families=(Family("Exhaust Fan", ("EF-1",), Count(1, (REF,))),), devices=(device,))
    return Job(name="Invented job", systems=(system,))


# ---- PBK-2: the citation rule is found by its name, not by where it sits ----------------------------------------

def test_the_mechanical_citation_check_names_the_cites_rule_whatever_rule_comes_first(tmp_path):
    root = _copy(tmp_path)
    rules = (root / "rules.md").read_text(encoding="utf-8")
    first = "## Evidence and citations\n\n"
    assert first in rules
    (root / "rules.md").write_text(rules.replace(first, first + "### No standard or fallback lines\n"
                                                 "A line is never added because systems of this kind have it.\n\n"),
                                   encoding="utf-8")
    playbook = load_playbook(root)
    assert next(iter(playbook.rules)) == "No standard or fallback lines"
    found = ai.quote_findings(_uncited_job(), {}, playbook)
    assert found and {f.rule for f in found} == {RULE["cites"]}


def test_the_mechanical_citation_check_does_not_depend_on_the_topic_name(tmp_path):
    # The check looks the rule up by name, so no topic name is fixed: renaming the topic changes nothing.
    root = _copy(tmp_path)
    rules = (root / "rules.md").read_text(encoding="utf-8")
    (root / "rules.md").write_text(rules.replace("## Evidence and citations", "## Sources"), encoding="utf-8")
    found = ai.quote_findings(_uncited_job(), {}, load_playbook(root))
    assert found and {f.rule for f in found} == {RULE["cites"]}


# ---- PBK-4: a kind word with punctuation can never match ------------------------------------------------------

def test_a_kind_word_with_punctuation_is_refused(tmp_path):
    root = _copy(tmp_path)
    data = json.loads((root / "shapes.json").read_text(encoding="utf-8"))
    data["shapes"][0]["applies_to"]["kind_words"] = ["make-up air unit"]
    (root / "shapes.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PlaybookError, match="kind_words"):
        load_shapes(root / "shapes.json")


def test_the_shipped_kind_words_load():
    load_shapes(REPO_PLAYBOOK / "shapes.json")


# ---- PBK-6: line numbers after a multi-line comment ------------------------------------------------------------

def test_a_duplicate_rule_after_a_long_comment_names_its_own_line(tmp_path):
    text = "# P\n<!--\none\ntwo\nthree\n-->\n## Topic\n\n### A\nx.\n\n### A\ny.\n"
    line = text.splitlines().index("### A", 9) + 1
    path = tmp_path / "rules.md"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(PlaybookError, match=rf"line {line}:"):
        load_rules(path)


# ---- PBK-10a: a prefix or kind word in two shapes -------------------------------------------------------------

def test_a_prefix_in_two_shapes_is_refused(tmp_path):
    root = _copy(tmp_path)
    data = json.loads((root / "shapes.json").read_text(encoding="utf-8"))
    ef = next(s for s in data["shapes"] if "EF" in s["applies_to"]["prefixes"])
    other = next(s for s in data["shapes"] if s is not ef)
    other["applies_to"]["prefixes"] = [*other["applies_to"]["prefixes"], "EF"]
    (root / "shapes.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PlaybookError, match="'EF'"):
        load_shapes(root / "shapes.json")


def test_a_kind_word_in_two_shapes_is_refused(tmp_path):
    root = _copy(tmp_path)
    data = json.loads((root / "shapes.json").read_text(encoding="utf-8"))
    word = data["shapes"][0]["applies_to"]["kind_words"][0]
    data["shapes"][1]["applies_to"]["kind_words"] = [*data["shapes"][1]["applies_to"]["kind_words"], word]
    (root / "shapes.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PlaybookError, match=repr(word)):
        load_shapes(root / "shapes.json")


# ---- PBK-10b: negative hours in a tech-hour condition -----------------------------------------------------------

def test_negative_hours_in_a_tech_hour_condition_are_refused(tmp_path):
    root = _copy(tmp_path)
    data = json.loads((root / "shapes.json").read_text(encoding="utf-8"))
    shape = data["shapes"][0]
    shape["tech_hours"]["when"] = [{"if": [shape["line_order"][0]], "hours": -2}]
    (root / "shapes.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PlaybookError, match="when"):
        load_shapes(root / "shapes.json")


# ---- PBK-10c: the sample Playbook has every rule the code names -------------------------------------------------

def test_the_sample_playbook_lints_clean_with_the_rule_names_the_code_needs():
    assert [str(p) for p in lint_playbook(SAMPLE, referenced_rule_names())] == []


# ---- PBK-10f: a leftover sample rule or draft value is reported --------------------------------------------------

def test_a_leftover_sample_rule_is_reported_at_its_heading(tmp_path):
    root = _copy(tmp_path, REPO_PLAYBOOK)
    (root / "rules.md").write_text("# P\n\n## Topic\n\n### Rule one\n<!-- sample -->\nPlain words.\n",
                                   encoding="utf-8")
    problems = lint_playbook(root)
    assert [(p.line, "sample" in p.message) for p in problems] == [(5, True)], [str(p) for p in problems]


def test_a_non_empty_draft_is_reported(tmp_path):
    root = _copy(tmp_path, REPO_PLAYBOOK)
    data = json.loads((root / "wording.json").read_text(encoding="utf-8"))
    data["$draft"] = ["quantity"]
    (root / "wording.json").write_text(json.dumps(data), encoding="utf-8")
    problems = lint_playbook(root)
    assert len(problems) == 1 and "$draft" in problems[0].message and "quantity" in problems[0].message, \
        [str(p) for p in problems]
