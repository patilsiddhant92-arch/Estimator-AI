"""Tests for bms.playbook: loader, encoding checks, and per-file checks (TASK-023)."""
import shutil
from pathlib import Path

import pytest

from bms.playbook import (
    PlaybookError,
    check_file,
    load_playbook,
    load_rules,
    load_shapes,
    load_wording,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE_PLAYBOOK = FIXTURES / "sample_playbook"


def test_load_playbook_raises_playbook_error_on_latin1_rules(tmp_path):
    """TASK-023: Latin-1 bytes in rules.md must raise PlaybookError, not raw UnicodeDecodeError."""
    folder = tmp_path / "pb"
    shutil.copytree(SAMPLE_PLAYBOOK, folder)
    # Write Latin-1 encoded byte 0xe9 (e-acute)
    (folder / "rules.md").write_bytes(b"# AME Playbook\n\n## Topic\n### Rule \xe9\nSome text.\n")
    with pytest.raises(PlaybookError) as exc_info:
        load_playbook(folder)
    msg = str(exc_info.value)
    assert "rules.md" in msg
    assert "UTF-8" in msg


def test_load_playbook_raises_playbook_error_on_latin1_shapes(tmp_path):
    folder = tmp_path / "pb"
    shutil.copytree(SAMPLE_PLAYBOOK, folder)
    (folder / "shapes.json").write_bytes(b'{"$format": {}, "shapes": [\xe9]}')
    with pytest.raises(PlaybookError) as exc_info:
        load_playbook(folder)
    msg = str(exc_info.value)
    assert "shapes.json" in msg
    assert "UTF-8" in msg


def test_load_playbook_raises_playbook_error_on_latin1_wording(tmp_path):
    folder = tmp_path / "pb"
    shutil.copytree(SAMPLE_PLAYBOOK, folder)
    (folder / "wording.json").write_bytes(b'{"$format": {}, "verbs": [\xe9]}')
    with pytest.raises(PlaybookError) as exc_info:
        load_playbook(folder)
    msg = str(exc_info.value)
    assert "wording.json" in msg
    assert "UTF-8" in msg


def test_check_file_accepts_valid_files():
    """check_file validates rules.md, shapes.json, and wording.json without error."""
    for filename in ("rules.md", "shapes.json", "wording.json"):
        check_file(SAMPLE_PLAYBOOK / filename)


def test_check_file_rejects_latin1_file(tmp_path):
    bad = tmp_path / "rules.md"
    bad.write_bytes(b"# Heading\n## Topic\n### Rule\nText \xe9.\n")
    with pytest.raises(PlaybookError, match="rules.md.*UTF-8"):
        check_file(bad)


def test_check_file_rejects_malformed_content(tmp_path):
    orphan_rules = tmp_path / "rules.md"
    orphan_rules.write_text("### Orphan\nNo topic heading.\n", encoding="utf-8")
    with pytest.raises(PlaybookError, match="not under a topic"):
        check_file(orphan_rules)

    bad_json = tmp_path / "shapes.json"
    bad_json.write_text("{ broken json", encoding="utf-8")
    with pytest.raises(PlaybookError, match="not valid JSON"):
        check_file(bad_json)


def test_check_file_rejects_unknown_filename(tmp_path):
    unknown = tmp_path / "unknown.txt"
    unknown.write_text("some text", encoding="utf-8")
    with pytest.raises(PlaybookError, match="not a Playbook file"):
        check_file(unknown)


def test_public_per_file_loaders():
    """load_rules, load_shapes, and load_wording are public functions for individual files."""
    text, topics, rules = load_rules(SAMPLE_PLAYBOOK / "rules.md")
    assert isinstance(text, str)
    assert isinstance(topics, tuple)
    assert "Every line cites this job" in rules

    shapes = load_shapes(SAMPLE_PLAYBOOK / "shapes.json")
    assert "Exhaust Fan" in shapes

    wording = load_wording(SAMPLE_PLAYBOOK / "wording.json")
    assert wording.verbs


# ---- PBK-1: every wording form is checked; PBK-5: a BOM is read through -----------------------------------------

import json  # noqa: E402

from bms.playbook import DEFAULT_ROOT  # noqa: E402


def _shipped_copy(tmp_path) -> Path:
    folder = tmp_path / "pb"
    folder.mkdir()
    for name in ("rules.md", "shapes.json", "wording.json"):
        shutil.copyfile(DEFAULT_ROOT / name, folder / name)
    return folder


def _edit_json(folder: Path, name: str, change) -> None:
    path = folder / name
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _first_slot(data) -> tuple[dict, str]:
    shape = data["shapes"][0]
    slot = next(s for s in shape["line_order"] if "{device}" in shape["wording"][s])
    return shape, slot


def _set_quantity_line(d):
    d["quantity"]["line"] = " (Qty. {count} Total)"


def _set_header_count(d):
    d["header"]["count"] = "{N}"


def _set_unclosed_with_others(d):
    shape, slot = _first_slot(d)
    shape["wording"][slot] = "{verb} {device{owner}{qty}"


def _set_unclosed_alone(d):
    shape, slot = _first_slot(d)
    shape["wording"][slot] = "Interlock with Associated {device Operation"


def _set_misspelt_device(d):
    shape, slot = _first_slot(d)
    shape["wording"][slot] = "{verb} {devcie}{owner}{qty}"


def _set_header_tag(d):
    d["shapes"][0]["header"] = "Qty ({n}) {name} {tag}"


def _set_others_note(d):
    d["quantity"]["others_note"] = "*Qty. {count}."


def _set_bracket_no_space(d):
    d["owner_brackets"]["Others"] = "(Furnished by Others)"


PBK1_EDITS = [
    ("wording.json", _set_quantity_line, "quantity.line"),
    ("wording.json", _set_header_count, "header.count"),
    ("shapes.json", _set_unclosed_with_others, "wording"),
    ("shapes.json", _set_unclosed_alone, "wording"),
    ("shapes.json", _set_misspelt_device, "devcie"),
    ("shapes.json", _set_header_tag, "tag"),
    ("wording.json", _set_others_note, "others_note"),
    ("wording.json", _set_bracket_no_space, "owner_brackets"),
]


@pytest.mark.parametrize("name, change, field", PBK1_EDITS, ids=[e[1].__name__ for e in PBK1_EDITS])
def test_pbk1_a_wrong_wording_form_is_refused_at_load(tmp_path, name, change, field):
    """PBK-1: each of these edits used to load and lint clean, then crash the render or print wrong client text."""
    folder = _shipped_copy(tmp_path)
    _edit_json(folder, name, change)
    with pytest.raises(PlaybookError) as exc_info:
        load_playbook(folder)
    msg = str(exc_info.value)
    assert name in msg
    assert field in msg


def test_pbk1_more_forms_checked(tmp_path):
    """A verb on a sub-line slot, a clarification form with no {text}, a causes form with no {causes}, a
    positional {} and a format spec are all refused."""
    def under_verb(d):
        shape = next(s for s in d["shapes"] if s.get("under"))
        slot = next(iter(shape["under"]))
        shape["wording"][slot] = "{verb} {device}"

    def no_text(d):
        d["clarifications"]["confirm"] = "*Confirm"

    def no_causes(d):
        d["count_causes"]["form"] = "(likely)"

    def positional(d):
        d["clarifications"]["note"] = "**{text} {}"

    def spec(d):
        d["quantity"]["line"] = " (Qty. {n:>3} Total)"

    for name, change in (("shapes.json", under_verb), ("wording.json", no_text), ("wording.json", no_causes),
                         ("wording.json", positional), ("wording.json", spec)):
        folder = tmp_path / change.__name__
        folder.mkdir()
        for file in ("rules.md", "shapes.json", "wording.json"):
            shutil.copyfile(DEFAULT_ROOT / file, folder / file)
        _edit_json(folder, name, change)
        with pytest.raises(PlaybookError, match=name):
            load_playbook(folder)


def test_pbk1_the_shipped_playbook_still_loads():
    playbook = load_playbook(DEFAULT_ROOT)
    assert playbook.shapes and playbook.wording.quantity["line"]


@pytest.mark.parametrize("name", ["rules.md", "shapes.json", "wording.json"])
def test_pbk5_a_file_saved_with_a_bom_loads(tmp_path, name):
    """PBK-5: Windows editors save UTF-8 with a BOM; the loader reads it as the lint does, and no BOM reaches the AI."""
    folder = _shipped_copy(tmp_path)
    path = folder / name
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    playbook = load_playbook(folder)
    assert "\ufeff" not in playbook.rules_text
    check_file(path)


def test_pbk9_the_kind_word_at_the_end_of_the_name_wins():
    """PBK-9: "VAV Air Handling Units" are air handlers; the kind word that ends the name names the equipment, not
    the first shape (file order) whose kind word appears somewhere in it."""
    playbook = load_playbook(DEFAULT_ROOT)
    assert playbook.shape_for("VAV Air Handling Units", []).name == "Air Handling Unit"
    assert playbook.shape_for("VAV Boxes", []).name == "VAV / Fan VAV"


def test_pbk9_of_kind_words_sharing_words_at_the_end_the_first_wins():
    """PBK-9: "kitchen exhaust" and "exhaust fan" share a word in "Kitchen Exhaust Fans"; the one that starts first
    says more (these are kitchen exhaust fans), though only "exhaust fan" ends the name."""
    playbook = load_playbook(DEFAULT_ROOT)
    assert playbook.shape_for("Kitchen Exhaust Fans", []).name == "Kitchen Exhaust Ventilation"
    assert playbook.shape_for("Toilet Exhaust Fans", []).name == "Toilet Exhaust Fan"


def test_pbk9_a_more_specific_kind_word_beats_a_prefix():
    """PBK-9: "Existing Fan Coil Units" tagged FCU take the existing shape (no prefixes of its own): its kind word
    "existing fan coil unit" holds the FCU shape's "fan coil unit" and says more."""
    playbook = load_playbook(DEFAULT_ROOT)
    assert playbook.shape_for("Existing Fan Coil Units", ["FCU"]).name == "Existing Fan Coil Unit (relocated)"
    assert playbook.shape_for("Fan Coil Units", ["FCU"]).name == "Fan Coil Unit"
    assert playbook.shape_for("anything", ["FCU"]).name == "Fan Coil Unit"


def test_pbk9_the_longest_kind_word_wins_when_none_ends_the_name():
    """PBK-9: no kind word ends the name: the longest one that appears wins, then file order."""
    playbook = load_playbook(DEFAULT_ROOT)
    assert playbook.shape_for("Toilet Exhaust Fans Level 2", []).name == "Toilet Exhaust Fan"
    assert playbook.shape_for("Exhaust Fans Level 2", []).name == "Exhaust Fan"
