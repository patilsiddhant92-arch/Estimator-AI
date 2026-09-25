"""The house style as data: it agrees with the Master Template file, and it tells good lines from bad."""
import json

from estimator.writing.style import STYLE_FILE, load_house_style
from estimator.writing.templates import TEMPLATES_FILE, load_templates

STYLE = load_house_style()
TEMPLATES_RAW = json.loads(TEMPLATES_FILE.read_text(encoding="utf-8"))


def test_the_verbs_and_the_trio_are_the_master_templates_own():
    assert list(STYLE.verbs) == TEMPLATES_RAW["verbs"]
    assert list(STYLE.trio) == TEMPLATES_RAW["integration_trio"]
    assert list(STYLE.trio_depths) == TEMPLATES_RAW["integration_trio_depths"]


def test_each_opening_without_a_verb_is_one_the_template_writes():
    no_verb = [line.text.lower() for t in load_templates() for line in t.lines if line.no_verb]
    for start in STYLE.no_verb_starts:
        assert any(text.startswith(start.lower() + " ") for text in no_verb), start


def test_the_file_holds_every_part_the_brief_asks_for():
    raw = json.loads(STYLE_FILE.read_text(encoding="utf-8"))
    for key in ("verbs", "trailing_forms", "integration_trio", "notes", "forbidden", "guide"):
        assert raw[key], key
    for form in ("(Furnished by Unit Mfr.)", "(Furnished by Others)", "(Qty. N Total)", "(as per sequence)"):
        assert form in STYLE.trailing_forms
    assert any("guidance" in line for line in STYLE.guide)       # the "How to use this template" section
    assert any("Qty (#) System Header" in line for line in STYLE.guide)


def test_the_templates_own_lines_pass_the_check():
    for template in load_templates():
        for line in template.lines:
            if line.no_verb or "{" in line.text or line.depth > 1:   # a sub-line takes its parent's verb
                continue
            assert STYLE.check_line(line.text) is None, (template.name, line.text)


def test_bad_lines_and_notes_are_named_in_plain_words():
    assert STYLE.check_line("Furnish and Install Occupancy Sensor") is None
    assert STYLE.check_line("Interlock with Associated AHU Operation") is None
    assert STYLE.check_line("Map Available Points Via Mfr. Provided BMS Interface") is None
    assert "verb" in STYLE.check_line("Occupancy Sensor")
    assert "tech hours" in STYLE.check_line("Furnish and Install Sensor (4 hours)")
    assert STYLE.check_line("Furnish and Install Sensor $120") is not None
    assert STYLE.check_line("Furnish and Install " + "Sensor " * 30) is not None
    assert STYLE.check_line("Furnish and Install Sensor (ASSUMPTION)") is not None
    assert STYLE.check_note("**Start/Stop via Fire Alarm System") is None
    assert STYLE.check_note("Start/Stop via Fire Alarm System") is not None
    assert STYLE.check_note("**Allow 8 hrs for the programming") is not None


def test_the_prompt_text_carries_the_rules():
    text = STYLE.prompt_text()
    for verb in STYLE.verbs:
        assert verb in text
    assert STYLE.trio[1] in text and "(Furnished by Unit Mfr.)" in text
    assert "Never write prices, tech hours" in text


def test_a_line_under_another_line_may_be_a_noun_phrase():
    style = load_house_style()
    assert style.check_line("Damper Actuator", depth=2) is None
    assert style.check_line("Damper Actuator") is not None
