"""Every assumption gives its reason (2026-10-04): "*Assumed: <what>, because <why>"; none without a reason, none hidden."""
from __future__ import annotations

from estimator.writing.assemble import _plain_assumption, block_clarifications, _Row, flag_review
from estimator.writing.style import load_house_style
from test_gem_round2 import FANS, _assemble, _gl, _items, _scope

STYLE = load_house_style()
HEADER = "Qty (2) Exhaust Fan EF-1, 2"
SENSOR = ("Furnish and Install Duct Static Sensor", "ASSUMED: duct static sensor shipped loose — because the schedule "
                                                    "shows no factory sensor")


def _notes(*lines):
    job, systems, general, ranked = _assemble([FANS], {"EF": _scope(*lines)})
    return [t for k, t in _items(job, HEADER) if k == "note" and t.startswith("*Assumed")], ranked


def test_an_assumption_prints_with_its_reason():
    notes, _ = _notes(_gl(SENSOR[0], flag="orange", flag_text=SENSOR[1]))
    assert notes == ["*Assumed: Duct static sensor shipped loose, because the schedule shows no factory sensor"]


def test_two_assumptions_in_a_block_give_one_note_with_both_and_none_hidden():
    notes, _ = _notes(_gl(SENSOR[0], flag="orange", flag_text=SENSOR[1]),
                      _gl("Furnish and Install Wire Guard", flag="orange",
                          flag_text="Wire guards furnished by AME, because the specification requires them in "
                                    "gymnasiums"),
                      _gl("Furnish and Install Relay", flag="orange",
                          flag_text="Relay furnished by AME because the sequence calls for a start relay"))
    assert len(notes) == 1
    for part in ("Duct static sensor shipped loose, because the schedule shows no factory sensor",
                 "Wire guards furnished by AME, because the specification requires them in gymnasiums",
                 "Relay furnished by AME, because the sequence calls for a start relay"):
        assert part in notes[0]
    assert "more" not in notes[0] and notes[0].count("; ") == 2


def test_a_flag_without_a_reason_prints_no_note_and_its_review_row_says_so():
    notes, ranked = _notes(_gl(SENSOR[0], flag="orange", flag_text="ASSUMED: duct static sensor shipped loose"))
    assert notes == []
    row = next(r for r in ranked if "Duct Static Sensor" in r.decide)
    assert "no reason to print" in row.action


def test_the_reason_keeps_client_words_only():
    assert _plain_assumption("ASSUMED: sensor by AME — because rule C5 applies", STYLE) is None
    assert _plain_assumption("ASSUMED: sensor by AME — because the plan sheet M-101 shows no sensor",
                             STYLE) == "Sensor by AME, because the plan sheet M-101 shows no sensor"
    assert _plain_assumption("ASSUMED: sensor by AME — confirm with the engineer", STYLE) is None


def test_one_assumption_stays_within_160_characters_and_never_cuts_mid_reason():
    long_reason = "because " + "the schedule shows no factory sensor and " * 6
    assert _plain_assumption(f"ASSUMED: duct static sensor shipped loose, {long_reason}", STYLE) is None


def test_confirm_quantities_keeps_its_short_list():
    from types import SimpleNamespace
    rows = [_Row(SimpleNamespace(text=f"Furnish X{n}", flag="", source_id="", quote="", quantity=None, depth=1,
                                 origin=""), None, True, frozenset(), None, "S",
                 after=[f"*Confirm quantity: Sensor Number {n}"]) for n in range(5)]
    _, notes = block_clarifications(rows)
    assert notes[0].endswith("more") and "and 2 more" in notes[0]
