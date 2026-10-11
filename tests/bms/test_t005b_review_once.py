"""T-005b, ruling 11: the review page asks each question once. A count question is asked once per family: a line
flagged only because it was counted from that family, with the family's own count, folds into the family card. Two
cards with no line of their own that ask the same thing in one block are one card. Invented data only."""
from __future__ import annotations

from bms import review
from bms.model import Assumption, Count, Device, Family, Finding, FrontEnd, Job, OtherCount, Ref, System

SCHEDULE = Ref("S1", "AHU rows 5", "M-501, Drawings.pdf page 6")
PLANS = Ref("C1", "plan placements 21", "M-101, Drawings.pdf page 2")
OWN = Ref("S9", "valve schedule", "M-502, Drawings.pdf page 7")


def _count() -> Count:
    return Count(21, (PLANS,), (OtherCount(5, SCHEDULE),))


def _device(i: int, name: str, count: Count, flag: str = "quantity", assumption=None) -> Device:
    return Device(id=f"AHU.d{i}", slot="other_device", name=name, verb="Furnish and Install", furnished_by="AME",
                  installed_by="AME", wired_by="AME", quantity=count, refs=(PLANS,), flag=flag,
                  assumption=assumption)


def _job(*devices: Device, families=None) -> Job:
    families = families or (Family("Air Handling Unit", ("AHU-1", "AHU-2"), _count()),)
    system = System(key="AHU", name="Air Handling Unit", shape="Air Handling Unit", control="field",
                    families=families, devices=devices)
    return Job(name="Invented", systems=(system,), front_end=FrontEnd(mode="new-system"))


def test_lines_that_only_repeat_the_family_count_fold_into_the_family_card():
    job = _job(_device(1, "DDC Controller", _count()), _device(2, "Discharge Air Sensor", _count()),
               _device(3, "Freezestat", _count()))
    questions = review._questions(job, ())
    assert [q.level for q in questions] == ["family"]
    (card,) = questions
    assert card.title == "How many Air Handling Unit units?"
    assert any("DDC Controller (Furnish and Install)" in n and "Freezestat (Furnish and Install)" in n
               for n in card.notes)


def test_a_line_with_its_own_count_or_an_assumption_keeps_its_card():
    own = Count(42, (PLANS,), (OtherCount(10, SCHEDULE),))                  # two valves per unit: not the family's
    assumed = _device(3, "Low Limit", _count(), assumption=Assumption("one per unit", "the sequence"))
    unflagged = _device(4, "Smoke Detector", Count(2, (OWN,)), flag="none")
    job = _job(_device(1, "DDC Controller", _count()), _device(2, "Control Valve", own), assumed, unflagged)
    questions = review._questions(job, ())
    assert [(q.level, q.device_id) for q in questions] == [("family", None), ("device", "AHU.d2"),
                                                            ("device", "AHU.d3")]


def test_a_line_counted_from_two_disputed_families_keeps_its_card():
    second = Family("Energy Recovery Unit", ("ERV-1",), Count(3, (PLANS,), (OtherCount(1, SCHEDULE),)))
    job = _job(_device(1, "DDC Controller", _count()), families=(Family("Air Handling Unit", (), _count()), second))
    assert [q.level for q in review._questions(job, ())] == ["family", "family", "device"]


def test_a_finding_on_a_line_still_shows_with_the_line():
    job = _job(_device(1, "DDC Controller", _count()))
    finding = Finding(rule="quote", severity="must_fix", system_key="AHU", device_id="AHU.d1",
                      what="The quote is not in the source.", fix="Cite the source.")
    questions = review._questions(job, (finding,))
    assert {q.level for q in questions} == {"device", "family"}


def test_the_same_question_twice_in_one_block_is_one_card():
    job = _job()
    twice = [Finding(rule="shape", severity="check", system_key="AHU", device_id=None,
                     what="The block has no tech hours.", fix=fix) for fix in ("Pick a shape.", "Set the hours.")]
    other = Finding(rule="shape", severity="check", system_key="", device_id=None, what="The block has no tech hours.",
                    fix="")
    questions = review._questions(job, (*twice, other))
    system_cards = [q for q in questions if q.level == "system"]
    assert [q.system_key for q in system_cards] == ["AHU", ""]
    assert system_cards[0].notes == ("What to do: Pick a shape.", "What to do: Set the hours.")


def test_the_page_shows_one_card_per_question(tmp_path):
    job = _job(*(_device(i, f"Line {i}", _count()) for i in range(1, 23)))
    page = review.review_page(job, (), tmp_path).read_text(encoding="utf-8")
    assert page.count('class="qtitle"') == 1
    assert "1 of 1 question(s) shown" in page
