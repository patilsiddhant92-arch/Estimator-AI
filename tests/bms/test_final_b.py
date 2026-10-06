"""FINAL-B (lead): the family Accept of a line counted from two disputed families, the review card's fix notes,
the evidence of a system named only by a general kind, and the planner's general-kind and condensate-pump guards.
Invented data only."""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import pytest

from bms import ai_evidence, counts, review
from bms.model import Count, Decision, Family, Finding, Job, OtherCount, Ref, System

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TESTS = Path(__file__).resolve().parents[1]
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))


@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


# ---- (1) a line counted from two disputed families ---------------------------------------------------------------


def _two_disputed(job: Job) -> Job:
    system = job.system("EF")
    fans = Family("Exhaust Fan", ("EF-1",), Count(1, (Ref("S1", "EF-1", "x"),), (OtherCount(2, Ref("C1", "q", "y")),)))
    dampers = Family("Motorized Damper", ("MD-1",), Count(1, (Ref("S2", "MD-1", "x"),),
                                                          (OtherCount(2, Ref("C2", "q", "y")),)))
    both = dataclasses.replace(system.devices[0], flag="quantity",
                               quantity=Count(1, (Ref("S1", "EF-1", "x"), Ref("S2", "MD-1", "x"))))
    only_fans = dataclasses.replace(system.devices[1], flag="quantity", quantity=Count(1, (Ref("S1", "EF-1", "x"),)))
    return job.with_system(dataclasses.replace(system, families=(fans, dampers), devices=(both, only_fans)))


def test_accepting_one_of_two_disputed_families_is_honored_while_the_line_keeps_its_flag(job):
    before = _two_disputed(job)
    accept = [Decision("EF", "accept", family_name="Exhaust Fan")]
    after = review.apply_decisions(before, accept)
    assert [d.flag for d in after.system("EF").devices] == ["quantity", "none"]   # only the fans' own line clears
    assert review.unhonored_decisions(before, accept, after) == []


def test_accepting_both_disputed_families_clears_the_line_in_either_order(job):
    before = _two_disputed(job)
    for names in (("Exhaust Fan", "Motorized Damper"), ("Motorized Damper", "Exhaust Fan")):
        decisions = [Decision("EF", "accept", family_name=n) for n in names]
        after = review.apply_decisions(before, decisions)
        assert [d.flag for d in after.system("EF").devices] == ["none", "none"]
        assert review.unhonored_decisions(before, decisions, after) == []
        found = review.unhonored_decisions(before, decisions, before)             # the last write put the flags back
        assert {f.what for f in found} == {f"decision not honored: accept {n}" for n in names}


def test_a_family_that_is_not_disputed_does_not_hold_a_line_back(job):
    before = _two_disputed(job)
    system = before.system("EF")
    settled = dataclasses.replace(system.families[1], count=dataclasses.replace(system.families[1].count, others=()))
    before = before.with_system(dataclasses.replace(system, families=(system.families[0], settled)))
    after = review.apply_decisions(before, [Decision("EF", "accept", family_name="Exhaust Fan")])
    assert [d.flag for d in after.system("EF").devices] == ["none", "none"]


def test_disputed_families_is_the_rule_the_run_flags_by(job):
    before = _two_disputed(job)
    assert [f.name for f in counts.disputed_families(before.system("EF"))] == ["Exhaust Fan", "Motorized Damper"]


# ---- (3) the fix notes of a merged card --------------------------------------------------------------------------


def test_each_findings_fix_stays_next_to_its_own_title_on_a_merged_card(job):
    findings = [Finding("Rule A", "EF", "EF.d1", "check", "A check", "Fix A"),
                Finding("Rule C", "EF", "EF.d1", "check", "Another check", "Fix C"),
                Finding("Rule B", "EF", "EF.d1", "must_fix", "A must fix", "Fix B")]
    card = next(q for q in review._questions(job, findings) if q.device_id == "EF.d1")
    assert card.title == "A must fix"
    assert list(card.notes[:5]) == ["What to do: Fix B", "Finding: A check", "What to do: Fix A",
                                    "Finding: Another check", "What to do: Fix C"]


def test_a_lead_whose_fix_another_finding_shares_still_shows_it_first(job):
    findings = [Finding("Rule A", "EF", "EF.d1", "check", "A check", "Same fix"),
                Finding("Rule B", "EF", "EF.d1", "must_fix", "A must fix", "Same fix")]
    card = next(q for q in review._questions(job, findings) if q.device_id == "EF.d1")
    assert card.notes[0] == "What to do: Same fix"
    assert len(card.notes) == len(set(card.notes))


# ---- (4) the evidence of a system named only by a general kind ---------------------------------------------------

_PUMP_DOSSIER = "\n".join([
    "== 2. SEQUENCE OF OPERATION ==",
    "--- 23 09 93, Specs.pdf page 3 ---",
    "[S1] The sump pump high water alarm reports to the BMS.",
    "[S2] The booster pump package runs on its own controls.",
    "[S3] The circulation pumps run whenever the loop is enabled.",
    "[S4] The sewage ejector pump reports a high level alarm.",
    "[S5] P-1 and P-2 run in lead and lag.",
    "[S6] The pumps of the plant run in lead and lag.",
])


def _pump_system(name: str, tags: tuple[str, ...]) -> System:
    return System(key="P", name=name, shape="", control="field", families=(Family(name, tags, Count(len(tags))),))


def test_a_bare_general_kind_with_tags_gathers_only_the_passages_naming_its_tags():
    text = ai_evidence.evidence(_pump_system("Pump", ("P-1", "P-2")), _PUMP_DOSSIER, {}, {}, ())
    assert "[S5]" in text
    for other in ("[S1]", "[S2]", "[S3]", "[S4]", "[S6]"):
        assert other not in text


def test_a_general_kind_with_no_tags_and_a_specific_kind_keep_their_name_phrase():
    untagged = ai_evidence.evidence(_pump_system("Pumps", ()), _PUMP_DOSSIER, {}, {}, ())
    assert "[S6]" in untagged and "[S1]" in untagged
    sump = ai_evidence.evidence(System(key="SP", name="Sump Pump", shape="", control="field",
                                       families=(Family("Sump Pump", ("SP-1",), Count(1)),)),
                                _PUMP_DOSSIER, {}, {}, ())
    assert "[S1]" in sump and "[S2]" not in sump


# ---- (5a) a block named only by a general kind keeps no tag another family owns ----------------------------------


def test_a_general_kind_block_gives_up_the_tags_of_families_whose_kind_the_ledger_gives():
    from test_plan import _family, _ledger, _plan
    ledger = _ledger()
    _family(ledger, "P", "Pump", "P-1, P-2, SPX-1, BPX-2", 4)
    _family(ledger, "SPX", "Sump Pump", "SPX-1", 1)
    _family(ledger, "BPX", "Booster Pump", "BPX-2", 1)
    job = _plan(ledger)
    systems = {s.key: s for s in job.systems}
    assert set(systems) == {"P", "SPX", "BPX"}
    assert [f.tags for f in systems["P"].families] == [("P-1", "P-2")]
    assert systems["P"].families[0].count.value == 2                 # one row per tag: the two moved rows leave it
    assert [f.tags for f in systems["SPX"].families] == [("SPX-1",)]
    all_tags = [t for s in job.systems for f in s.families for t in f.tags]
    assert len(all_tags) == len(set(all_tags))                         # no tag in two blocks
    asked = [q for q in job.questions if "SPX-1" in q and "BPX-2" in q]
    assert len(asked) == 1 and "Sump Pump" in asked[0] and "Booster Pump" in asked[0]


def test_a_general_kind_block_keeps_a_count_that_is_not_one_per_tag_and_says_so():
    from test_plan import _family, _ledger, _plan
    ledger = _ledger()
    _family(ledger, "P", "Pump", "P-1, SPX-1", 30)
    _family(ledger, "SPX", "Sump Pump", "SPX-1", 1)
    job = _plan(ledger)
    p = next(s for s in job.systems if s.key == "P")
    assert p.families[0].tags == ("P-1",) and p.families[0].count.value == 30
    asked = [q for q in job.questions if "SPX-1" in q and "30" in q]
    assert len(asked) == 1


def test_a_general_kind_block_keeps_a_tag_whose_family_has_no_kind_either():
    from test_plan import _family, _ledger, _plan
    ledger = _ledger()
    _family(ledger, "P", "Pump", "P-1, ZF-1", 2)
    _family(ledger, "ZF", "Fan", "ZF-1", 1)
    p = next(s for s in _plan(ledger).systems if s.key == "P")
    assert p.families[0].tags == ("P-1", "ZF-1")


# ---- (5b) condensate pumps of split units ------------------------------------------------------------------------


def test_condensate_pumps_sharing_the_split_units_tag_numbers_join_the_split_block_and_are_asked():
    from test_plan import _family, _ledger, _plan
    ledger = _ledger()
    _family(ledger, "AC", "Air Conditioning Unit", "AC-21, AC-22", 2)
    _family(ledger, "ACCU", "Air Cooled Condensing Unit", "ACCU-21, ACCU-22", 2)
    _family(ledger, "CP", "Condensate Pump", "CP-21, CP-22", 2)
    job = _plan(ledger)
    (split,) = job.systems
    assert split.key == "Split System"
    assert [(f.name, f.tags, f.count.value) for f in split.families][-1] == ("Condensate Pump", ("CP-21", "CP-22"), 2)
    asked = [q for q in job.questions if "CP-21" in q]
    assert len(asked) == 1 and "float switch" in asked[0] and "Mechanical Contractor" in asked[0]


def test_a_long_condensate_pump_name_is_not_renamed_as_a_condensing_unit():
    from test_plan import _family, _ledger, _plan
    ledger = _ledger()
    _family(ledger, "AC", "Air Conditioning Unit", "AC-21", 1)
    _family(ledger, "ACCU", "Air Cooled Condensing Unit", "ACCU-21", 1)
    _family(ledger, "CP", "Condensate Pump Serving The Split Units", "CP-21", 1)
    (split,) = _plan(ledger).systems
    assert split.families[-1].name == "Condensate Pump Serving The Split Unit"


def test_condensate_pumps_only_partly_matching_a_split_block_stay_apart_and_are_asked():
    from test_plan import _family, _ledger, _plan
    from bms.playbook import load_playbook
    ledger = _ledger()
    _family(ledger, "AC", "Air Conditioning Unit", "AC-21", 1)
    _family(ledger, "ACCU", "Air Cooled Condensing Unit", "ACCU-21", 1)
    _family(ledger, "CP", "Split AC Condensate Pump", "CP-21, CP-98", 2)     # its name says "split ac"
    job = _plan(ledger, load_playbook())
    assert [s.key for s in job.systems] == ["Split System", "CP"]
    assert job.system("Split System").shape == "Split System"
    assert job.system("CP").shape != "Split System"                       # a pump block never takes the split shape
    asked = [q for q in job.questions if "CP-98" in q or "CP-21" in q]
    assert len(asked) == 1 and "Split System" in asked[0]


def test_condensate_pumps_with_no_split_units_are_left_as_they_are():
    from test_plan import _family, _ledger, _plan
    ledger = _ledger()
    _family(ledger, "CP", "Condensate Pump", "CP-21", 1)
    _family(ledger, "EF", "Exhaust Fan", "EF-21", 1)
    job = _plan(ledger)
    assert [s.key for s in job.systems] == ["CP", "EF"]
    assert not any("CP-21" in q for q in job.questions)
