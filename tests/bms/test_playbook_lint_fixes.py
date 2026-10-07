"""CORRECT-020: the Playbook linter fixes asked for by REVIEW-020 (primary and secondary) and the lead's rulings.

Invented playbooks in temp folders, built from a copy of the repo Playbook. No job data. Only names that exist on
the original commit are imported at the top, so each test fails on its assertion when its fix is reverted.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import bms.validate
from bms.__main__ import main
from bms.playbook import PlaybookError, load_playbook
from bms.playbook_lint import lint_playbook

REPO = Path(__file__).resolve().parents[2]
REPO_PLAYBOOK = REPO / "playbook"


def _copy(tmp_path: Path) -> Path:
    root = tmp_path / "playbook"
    shutil.copytree(REPO_PLAYBOOK, root)
    return root


def _with_rules(tmp_path: Path, rules: str) -> Path:
    root = _copy(tmp_path)
    (root / "rules.md").write_text(rules, encoding="utf-8")
    return root


def _shapes(root: Path) -> dict:
    return json.loads((root / "shapes.json").read_text(encoding="utf-8"))


def _write_json(root: Path, name: str, data) -> None:
    (root / name).write_text(json.dumps(data, indent=2), encoding="utf-8")


def _messages(root: Path) -> list[str]:
    return [p.message for p in lint_playbook(root)]


# ---- ruling 1: the rule names come from the code, never from a copy ----------------------------------------------

def test_a_rule_name_newly_used_by_a_validator_is_required(tmp_path, monkeypatch, capsys):
    root = _copy(tmp_path)
    monkeypatch.setitem(bms.validate.RULE, "invented_check", "An invented rule no Playbook has")
    assert main(["playbook-lint", str(root)]) == 1
    assert "An invented rule no Playbook has" in capsys.readouterr().out


def test_a_rule_name_newly_quoted_by_a_prompt_is_required(tmp_path, monkeypatch, capsys):
    root = _copy(tmp_path)
    prompts = tmp_path / "prompts"
    shutil.copytree(REPO / "src" / "bms" / "prompts", prompts)
    (prompts / "invented.md").write_text('Follow "An invented quoted rule" always.\n', encoding="utf-8")
    import bms.playbook_lint
    monkeypatch.setattr(bms.playbook_lint, "PROMPTS", prompts, raising=False)
    assert main(["playbook-lint", str(root)]) == 1
    assert "An invented quoted rule" in capsys.readouterr().out


# ---- ruling 3: lints clean means the app can load it --------------------------------------------------------------

def _wording_verbs(root: Path) -> None:
    data = json.loads((root / "wording.json").read_text(encoding="utf-8"))
    data["verbs"] = ["Furnish"]
    _write_json(root, "wording.json", data)


def _extra_wording_slot(root: Path) -> None:
    data = _shapes(root)
    data["shapes"][0]["wording"]["invented_slot"] = "{device}"
    _write_json(root, "shapes.json", data)


def _missing_tech_hours(root: Path) -> None:
    data = _shapes(root)
    del data["shapes"][0]["tech_hours"]
    _write_json(root, "shapes.json", data)


def _empty_topic(root: Path) -> None:
    (root / "rules.md").write_text("# P\n\n## \n\n### A\nx.\n", encoding="utf-8")


LOADER_REFUSES = {"wording verbs are not the house verbs": _wording_verbs,
                  "a wording slot not in line_order": _extra_wording_slot,
                  "a shape with no tech hours": _missing_tech_hours,
                  "an empty topic heading": _empty_topic}


@pytest.mark.parametrize("case", sorted(LOADER_REFUSES))
def test_lint_clean_means_the_app_can_load_it(tmp_path, case):
    root = _copy(tmp_path)
    LOADER_REFUSES[case](root)
    with pytest.raises(PlaybookError):
        load_playbook(root)
    assert any("app" in m and "load" in m for m in _messages(root)), _messages(root)


# ---- ruling 2: topics as the loader reads them (no second list) ---------------------------------------------------

def test_a_topic_twice_is_reported_in_the_loaders_words(tmp_path):
    root = _with_rules(tmp_path, "# P\n\n## Topic\n\n### A\nx.\n\n## Topic\n\n### B\ny.\n")
    assert any("appears twice" in m for m in _messages(root)), _messages(root)


# ---- malformed input is a plain problem, never a traceback --------------------------------------------------------

def test_a_latin1_rules_file_is_a_problem_not_a_crash(tmp_path):
    root = _copy(tmp_path)
    (root / "rules.md").write_bytes("# P\n\n## Topic\n\n### Café rule\nPlain words.\n".encode("latin-1"))
    problems = lint_playbook(root)
    assert any(p.file.endswith("rules.md") and "UTF-8" in p.message for p in problems), problems


def _shape_field(field: str, value):
    def change(root: Path) -> None:
        data = _shapes(root)
        data["shapes"][0][field] = value
        _write_json(root, "shapes.json", data)
    return change


def _slot_is_a_list(root: Path) -> None:
    data = _shapes(root)
    data["shapes"][0]["line_order"].append(["a"])
    _write_json(root, "shapes.json", data)


MALFORMED_SHAPES = {"wording is null": _shape_field("wording", None),
                    "under is a list": _shape_field("under", ["a"]),
                    "a line_order slot is a list": _slot_is_a_list}


@pytest.mark.parametrize("case", sorted(MALFORMED_SHAPES))
def test_a_malformed_shape_is_a_problem_not_a_crash(tmp_path, case):
    root = _copy(tmp_path)
    MALFORMED_SHAPES[case](root)
    problems = lint_playbook(root)
    assert problems and all(p.file.endswith("shapes.json") for p in problems), problems


def test_a_line_order_text_is_not_walked_letter_by_letter(tmp_path):
    root = _copy(tmp_path)
    _shape_field("line_order", "abc")(root)
    assert not any("'a'" in m or "'b'" in m for m in _messages(root)), _messages(root)


def test_a_missing_rules_file_is_one_problem(tmp_path):
    root = _copy(tmp_path)
    (root / "rules.md").unlink()
    problems = lint_playbook(root, known_rule_names={"Every line cites this job", "Never undershoot"})
    assert len(problems) == 1 and "not found" in problems[0].message, problems


# ---- ruling 5: arrows and emoji -----------------------------------------------------------------------------------

def _one_rule(text: str, name: str = "Rule one") -> str:
    return f"# P\n\n## Topic\n\n### {name}\n{text}\n"


def test_unicode_and_ascii_arrows_are_reported(tmp_path):
    arrows = ["→", "←", "⇒", "⇐", "->", "=>"]
    text = "\n".join(f"The fan {arrow} the damper." for arrow in arrows)
    root = _with_rules(tmp_path, _one_rule(text))
    lines = [p.line for p in lint_playbook(root) if "arrow" in p.message]
    assert lines == [6, 7, 8, 9, 10, 11]


def test_less_or_equal_and_double_colon_are_not_arrows(tmp_path):
    root = _with_rules(tmp_path, _one_rule("Counts <= 3 print as written. Name:: value."))
    assert _messages(root) == []


def test_arrows_in_backticks_and_code_fences_are_not_reported(tmp_path):
    root = _with_rules(tmp_path, _one_rule("Write `a -> b` as code.\n```\nfan -> damper => unit\n```\nPlain."))
    assert _messages(root) == []


@pytest.mark.parametrize("emoji", ["⭐", "\U0001fa75"])
def test_more_emoji_are_reported(tmp_path, emoji):
    root = _with_rules(tmp_path, _one_rule(f"A star {emoji} here."))
    assert any("emoji" in m for m in _messages(root)), _messages(root)


# ---- ruling 4: source ids -----------------------------------------------------------------------------------------

def test_a_rule_that_talks_about_source_ids_is_still_checked(tmp_path):
    root = _with_rules(tmp_path, _one_rule('Each line carries its source id, never "S12" in the text.'))
    assert any("source id" in m and "S12" in m for m in _messages(root)), _messages(root)


def test_quoted_examples_only_in_the_source_id_rule(tmp_path):
    rules = _one_rule('Never write a source id ("S12", "S40 note 1") in wording; not Q3 either.',
                      name="Assumption wording has no source ids")
    root = _with_rules(tmp_path, rules)
    messages = _messages(root)
    assert any("Q3" in m for m in messages), messages
    assert not any("S12" in m or "S40" in m for m in messages), messages


def test_equipment_tag_lookalikes_are_never_flagged(tmp_path):
    root = _with_rules(tmp_path, _one_rule("Fan F1 and compressor C2 are equipment tags."))
    assert _messages(root) == []


# ---- headings, comments and line numbers --------------------------------------------------------------------------

def test_a_source_id_in_a_heading_is_reported(tmp_path):
    root = _with_rules(tmp_path, _one_rule("Plain words.", name="Rule S12"))
    assert any("S12" in m for m in _messages(root)), _messages(root)


def test_trailing_whitespace_on_a_heading_is_reported(tmp_path):
    root = _with_rules(tmp_path, "# P\n\n## Topic\n\n### Rule one   \nPlain words.\n")
    assert any("trailing whitespace" in m for m in _messages(root)), _messages(root)


def test_a_heading_inside_a_comment_is_ignored(tmp_path):
    root = _with_rules(tmp_path, "# P\n\n<!--\n### Not a rule\n-->\n\n## Topic\n\n### Rule one\nPlain words.\n")
    assert _messages(root) == []


def test_rule_names_that_differ_only_in_case_are_reported(tmp_path):
    root = _with_rules(tmp_path, "# P\n\n## Topic\n\n### Same name\nOne.\n\n### Same Name\nTwo.\n")
    assert any("case" in m for m in _messages(root)), _messages(root)


def test_an_indented_heading_is_rule_text_as_the_loader_reads_it(tmp_path):
    root = _with_rules(tmp_path, "# P\n\n## Topic\n\n### A\nOne.\n   ### A\nTwo.\n")
    load_playbook(root)
    assert _messages(root) == []


def test_line_numbers_after_a_level_four_heading(tmp_path):
    root = _with_rules(tmp_path, "# P\n\n## Topic\n\n### A\n#### x\nOne.\nTwo.   \n")
    lines = [p.line for p in lint_playbook(root) if "trailing whitespace" in p.message]
    assert lines == [8]


# ---- the command line ---------------------------------------------------------------------------------------------

def test_the_cli_default_folder_is_the_repo_playbook(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["playbook-lint"]) == 0


def test_the_cli_reports_in_plain_words_and_exits_1(tmp_path, capsys):
    root = _copy(tmp_path)
    (root / "rules.md").write_bytes("# P\n\n## Topic\n\n### Café\nx.\n".encode("latin-1"))
    assert main(["playbook-lint", str(root)]) == 1
    out = capsys.readouterr().out
    assert "rules.md" in out and "UTF-8" in out and "Traceback" not in out


def test_the_cli_says_clean_and_exits_0(tmp_path, capsys):
    root = _copy(tmp_path)
    assert main(["playbook-lint", str(root)]) == 0
    assert "clean" in capsys.readouterr().out


# ---- ruling 6: one dispatch table for the subcommands ------------------------------------------------------------

def test_subcommands_go_through_one_dispatch_table(monkeypatch):
    import bms.__main__ as cli
    commands = getattr(cli, "COMMANDS", None)
    assert isinstance(commands, dict) and {"estimate", "playbook-lint"} <= set(commands)
    called = []
    monkeypatch.setitem(commands, "playbook-lint", lambda args: called.append(args.root) or 7)
    assert main(["playbook-lint", "somewhere"]) == 7
    assert called == [Path("somewhere")]


# ---- REVIEW-020b ------------------------------------------------------------------------------------------------

def test_a_missing_wording_key_is_reported_once(tmp_path):
    root = _copy(tmp_path)
    data = json.loads((root / "wording.json").read_text(encoding="utf-8"))
    del data["quantity"]
    _write_json(root, "wording.json", data)
    assert len(lint_playbook(root)) == 1, _messages(root)


def test_two_duplicate_topics_are_both_reported_once(tmp_path):
    rules = "# P\n\n## T\n\n### A\nx.\n\n## U\n\n### B\ny.\n\n## T\n\n### C\nz.\n\n## U\n\n### D\nw.\n"
    root = _with_rules(tmp_path, rules)
    problems = lint_playbook(root)
    assert [p.line for p in problems] == [13, 18], [str(p) for p in problems]


@pytest.mark.parametrize("fence", ["```", "   ```", "~~~", "  ~~~~"])
def test_indented_and_tilde_fences_are_code_fences(tmp_path, fence):
    root = _with_rules(tmp_path, _one_rule(f"The form is:\n{fence}\nA -> B\n{fence}\nPlain."))
    assert _messages(root) == []


def test_an_unclosed_fence_does_not_hide_what_follows(tmp_path):
    root = _with_rules(tmp_path, _one_rule("Plain.\n~~~\nA -> B"))
    assert any("arrow" in m for m in _messages(root)), _messages(root)


def test_a_fence_closes_only_with_its_own_marker(tmp_path):
    root = _with_rules(tmp_path, _one_rule("Plain.\n```\nA\n~~~\nB -> C"))
    assert any("arrow" in m for m in _messages(root)), _messages(root)


@pytest.mark.slow
def test_many_unclosed_fences_lint_in_linear_time(tmp_path):
    from timing import grows_linearly
    roots: dict[int, object] = {}

    def lint(n):                      # the playbook folder is made once per size; only the lint is timed
        lint_playbook(roots[n])

    def work(n):
        if n not in roots:
            roots[n] = _with_rules(tmp_path / str(n), _one_rule("Plain.\n" + "~~~x\n" * n))
        lint(n)
    assert grows_linearly(work, 2000)  # growth, not a wall-clock limit (it flaked under load)


@pytest.mark.parametrize("arrow", ["➔", "➡", "⬅", "⮕"])
def test_dingbat_and_supplemental_arrows_are_arrows_not_emoji(tmp_path, arrow):
    root = _with_rules(tmp_path, _one_rule(f"The fan {arrow} the damper."))
    assert _messages(root) == ["rule 'Rule one' contains an arrow"], _messages(root)


@pytest.mark.parametrize("emoji", ["⏰", "\U0001f004", "\U0001f0cf"])
def test_technical_mahjong_and_card_emoji_are_reported(tmp_path, emoji):
    root = _with_rules(tmp_path, _one_rule(f"A clock {emoji} here."))
    assert any("emoji" in m for m in _messages(root)), _messages(root)


def test_a_nameless_rule_heading_is_one_problem(tmp_path):
    root = _with_rules(tmp_path, "# P\n\n## Topic\n\n### \nText.\n")
    problems = lint_playbook(root)
    assert len(problems) == 1 and "no name" in problems[0].message, [str(p) for p in problems]


# ---- PBK-8: a heading with no space after its marks ------------------------------------------------------------

@pytest.mark.parametrize("heading", ["###Second rule", "##Topic two", "###\tSecond rule"])
def test_a_heading_with_no_space_is_one_problem_at_its_line(tmp_path, heading):
    root = _with_rules(tmp_path, f"# P\n\n## Topic\n\n### A\nOne.\n{heading}\nTwo.\n")
    load_playbook(root)                 # the loader reads it as rule text of A
    problems = lint_playbook(root)
    assert [p.line for p in problems] == [7], [str(p) for p in problems]
    assert "heading" in problems[0].message


def test_a_heading_like_line_inside_a_code_fence_is_rule_text(tmp_path):
    root = _with_rules(tmp_path, "# P\n\n## Topic\n\n### A\nThe form:\n```\n###Second\n```\n")
    assert _messages(root) == []
