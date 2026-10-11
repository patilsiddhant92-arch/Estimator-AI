"""ws5, HP 17: a revise can correct a family count or the alternate when a must_fix finding about the whole block asks
for it, checked against the evidence. The highest count prints and no count is dropped (an unlisted count stays in
`others` with its source, so the "*" note names both numbers). Invented data only: tests/bms/fixtures."""
from __future__ import annotations

import copy
import dataclasses

import pytest

from bms import ai
from bms.model import Count, Finding, OtherCount, Ref
from test_ai import FakeTransport
from test_ai import dossier, job, playbook, raw  # noqa: F401  (fixtures)

S6 = Ref("S6", "EF-1 EF-2 EF-3", "M-001, Drawings.pdf page 1")           # the planner's count source, in the fixture
S44_QUOTE = "roof plan placements 4"
S44 = Ref("S44", S44_QUOTE, "M-101, Drawings.pdf page 2")


@pytest.fixture
def held(dossier):
    """The invented dossier with one more passage about the exhaust fans: the roof plan shows 4 (a count) and the bid
    form calls them an add alternate."""
    text = dossier.text.replace(
        "== 6. DEVICES ON PLANS ==",
        "[S44] EF (exhaust fan): roof plan placements 4 (M-101 4). Tags: EF-1 EF-2 EF-3 EF-4.\n\n"
        "== 6. DEVICES ON PLANS ==")
    text = text.replace("== 8. CONTROLS SPEC HIGHLIGHTS ==",
                        "[S45] BID FORM: add alternate 2: exhaust fans EF-1 thru EF-3.\n\n"
                        "== 8. CONTROLS SPEC HIGHLIGHTS ==")
    assert "[S44]" in text and "[S45]" in text
    sources = {**dossier.sources, "S44": "equipment counts for EF (roof plan)", "S45": "BID FORM, E-001, Drawings.pdf page 6"}
    return dataclasses.replace(dossier, text=text, sources=sources)


def _count_finding(rule="Higher count prints", fix="Set the Exhaust Fan count to 4, the roof plan's count.", **kw):
    return Finding(rule, "EF", None, "must_fix", "The roof plan shows 4 exhaust fans; the block carries 3.", fix)


def _answer(raw, count=None, alternate=None):
    answer = copy.deepcopy(raw["systems"][1])                       # the EF block as the fixture writes it
    if count is not None:
        answer["families"][0]["count"] = count
    if alternate is not None:
        answer["alternate"] = alternate
    return answer


def _count(value, sources=(), others=()):
    return {"value": value, "sources": [s.to_dict() for s in sources],
            "others": [{"value": n, "ref": r.to_dict()} for n, r in others], "added_up": None}


def _revise(job, held, playbook, answer, findings, **kw):
    system = job.system("EF")
    transport = FakeTransport(answer)
    revised = ai.revise_system(system, findings, ai.evidence_for(system, held), playbook, transport, **kw)
    return revised, transport


# ---- a count --------------------------------------------------------------------------------------------------------

def test_a_finding_about_the_count_lets_the_revise_raise_it(job, raw, held, playbook):
    revised, transport = _revise(job, held, playbook, _answer(raw, _count(4, [S44])), [_count_finding()])
    (family,) = revised.families
    assert family.count.value == 4 and family.count.sources == (S44,) and family.count.highest() == 4
    assert family.count.others == (OtherCount(3, S6),)               # the earlier count stays, with its source
    assert (family.name, family.tags) == ("Exhaust Fan", ("EF-1", "EF-2", "EF-3"))
    assert "may correct" in transport.asked[0]["prompt"]             # the writer is told it may


def test_the_corrected_system_keeps_the_planners_other_fields(job, raw, held, playbook):
    answer = _answer(raw, _count(4, [S44]))
    answer["key"], answer["name"], answer["control"], answer["sequence_refs"] = "XX", "Renamed", "none", []
    revised, _ = _revise(job, held, playbook, answer, [_count_finding()])
    system = job.system("EF")
    assert (revised.key, revised.name, revised.control, revised.sequence_refs, revised.alternate) == (
        system.key, system.name, system.control, system.sequence_refs, system.alternate)


def test_a_revise_never_drops_a_count_the_block_already_has(job, raw, held, playbook):
    other = Ref("S7", "MD-1 interlocked with EF-1", "M-101, Drawings.pdf page 2")
    system = job.system("EF")
    system = dataclasses.replace(system, families=(dataclasses.replace(
        system.families[0], count=Count(3, (S6,), (OtherCount(2, other),))),))
    transport = FakeTransport(_answer(raw, _count(4, [S44])))        # the answer leaves both earlier counts out
    revised = ai.revise_system(system, [_count_finding()], ai.evidence_for(system, held), playbook, transport)
    count = revised.families[0].count
    assert count.value == 4 and count.sources == (S44,)
    assert set(count.others) == {OtherCount(3, S6), OtherCount(2, other)}


def test_a_revise_never_lowers_the_count(job, raw, held, playbook):
    """An answer that sets the count below the one the block carries: the highest still prints, and the lower count
    is named beside it with its source (the "*" note names both numbers)."""
    low = Ref("S28", "EF-1 | 500", "M-001, Drawings.pdf page 1")
    revised, _ = _revise(job, held, playbook, _answer(raw, _count(2, [low])),
                         [_count_finding(fix="Set the Exhaust Fan count to 2.")])
    count = revised.families[0].count
    assert count.value == 3 and count.sources == (S6,)                # the highest prints
    assert count.others == (OtherCount(2, low),)                     # the lower count is named with its source


def test_an_unknown_count_takes_the_number_the_evidence_gives(job, raw, held, playbook):
    system = job.system("EF")
    system = dataclasses.replace(system, families=(dataclasses.replace(system.families[0], count=Count(None)),))
    transport = FakeTransport(_answer(raw, _count(4, [S44])))
    finding = Finding("Never undershoot", "EF", None, "must_fix", "The count is unknown but the roof plan gives 4.",
                      "Carry 4 with its source.")
    revised = ai.revise_system(system, [finding], ai.evidence_for(system, held), playbook, transport)
    assert revised.families[0].count == Count(4, (S44,))


def test_a_value_below_the_highest_other_count_is_set_to_the_highest(job, raw, held, playbook):
    """The answer keeps the earlier count as the value and puts the new, higher one among the others: the highest
    prints, so it is the value."""
    system = job.system("EF")
    answer = _answer(raw, _count(3, [S6], [(4, S44)]))
    transport = FakeTransport(answer)
    revised = ai.revise_system(system, [_count_finding()], ai.evidence_for(system, held), playbook, transport)
    count = revised.families[0].count
    assert (count.value, count.sources) == (4, (S44,)) and count.others == (OtherCount(3, S6),)


@pytest.mark.parametrize("count, words", [
    (_count(4, [Ref("S999", "roof plan", "M-1")]), "S999"),
    (_count(4, [Ref("S44", "the roof plan shows twenty fans", "M-101")]), "the roof plan shows twenty fans"),
    (_count(4, []), "no source"),
    (_count(4, [S44], [(5, Ref("S998", "x", "y"))]), "S998"),
])
def test_a_count_the_evidence_does_not_support_is_refused(job, raw, held, playbook, count, words):
    system = job.system("EF")
    with pytest.raises(ai.NoAnswer) as refused:
        ai.revise_system(system, [_count_finding()], ai.evidence_for(system, held), playbook,
                         FakeTransport(_answer(raw, count)))
    assert words in refused.value.reason and "Exhaust Fan" in refused.value.reason


def test_a_count_below_one_is_refused(job, raw, held, playbook):
    system = job.system("EF")
    with pytest.raises(ai.NoAnswer) as refused:
        ai.revise_system(system, [_count_finding()], ai.evidence_for(system, held), playbook,
                         FakeTransport(_answer(raw, _count(0, [S44]))))
    assert "1 or more" in refused.value.reason


def test_a_finding_about_one_line_never_opens_the_count(job, raw, held, playbook):
    finding = Finding("Higher count prints", "EF", "EF.d1", "must_fix", "The controller quantity is 3.", "Make it 4.")
    revised, transport = _revise(job, held, playbook, _answer(raw, _count(4, [S44])), [finding])
    assert revised.families == job.system("EF").families
    assert "may correct" not in transport.asked[0]["prompt"]


def test_a_finding_about_something_else_leaves_the_count_to_the_planner(job, raw, held, playbook):
    finding = Finding("Every line cites this job", "EF", None, "must_fix", "The start/stop line has no source.",
                      "Remove it.")
    revised, transport = _revise(job, held, playbook, _answer(raw, _count(4, [S44])), [finding])
    assert revised.families == job.system("EF").families               # the skeleton's counts win, no refusal
    assert "may correct" not in transport.asked[0]["prompt"]


def test_a_count_the_estimator_set_is_never_changed_by_a_revise(job, raw, held, playbook):
    revised, transport = _revise(job, held, playbook, _answer(raw, _count(4, [S44])), [_count_finding()],
                                 hold_counts=("Exhaust Fan",))
    assert revised.families == job.system("EF").families
    assert "may correct" not in transport.asked[0]["prompt"]


class _Logging(FakeTransport):
    """A transport with an intake log, as the real ones have (`note_intake`)."""

    def __init__(self, *answers):
        super().__init__(*answers)
        self.log: list[tuple[str, str]] = []

    def note_intake(self, system: str, change: str) -> None:
        self.log.append((system, change))


def test_the_intake_log_names_a_corrected_count_and_a_corrected_alternate(job, raw, held, playbook):
    transport = _Logging(_answer(raw, _count(4, [S44]), alternate="add"))
    system = job.system("EF")
    findings = [_count_finding(), _alternate_finding()]
    ai.revise_system(system, findings, ai.evidence_for(system, held), playbook, transport)
    changes = [change for _, change in transport.log]
    assert any("Exhaust Fan count" in c and "corrected to 4" in c for c in changes), changes
    assert any("alternate" in c and "'add'" in c for c in changes), changes


# ---- the alternate --------------------------------------------------------------------------------------------------

def _alternate_finding(key="EF", fix="Make the block an add alternate, as the bid form says."):
    return Finding("Never invent an alternate", key, None, "must_fix", "The alternate does not follow the documents.",
                   fix)


def test_a_finding_about_the_alternate_lets_the_revise_take_an_alternate_off(job, raw, held, playbook):
    system = job.system("DH")
    assert system.alternate == "add"
    answer = copy.deepcopy(raw["systems"][3])
    answer["alternate"] = "base"
    finding = Finding("Never invent an alternate", "DH", None, "must_fix", "No document calls the duct heaters an "
                      "alternate.", "Make the block base bid.")
    transport = FakeTransport(answer)
    revised = ai.revise_system(system, [finding], ai.evidence_for(system, held), playbook, transport)
    assert revised.alternate == "base" and "may correct" in transport.asked[0]["prompt"]


def test_an_alternate_the_evidence_says_is_taken(job, raw, held, playbook):
    revised, _ = _revise(job, held, playbook, _answer(raw, alternate="add"), [_alternate_finding()])
    assert revised.alternate == "add"


def test_an_alternate_no_passage_says_is_refused(job, raw, dossier, playbook):
    """The invented dossier has no passage that says the exhaust fans are an alternate."""
    system = job.system("EF")
    with pytest.raises(ai.NoAnswer) as refused:
        ai.revise_system(system, [_alternate_finding()], ai.evidence_for(system, dossier), playbook,
                         FakeTransport(_answer(raw, alternate="deduct")))
    assert "deduct" in refused.value.reason and "keep" in refused.value.reason


def test_an_alternate_answer_with_no_finding_about_it_is_ignored(job, raw, held, playbook):
    finding = Finding("Every line cites this job", "EF", None, "must_fix", "w", "Remove the start/stop line.")
    revised, _ = _revise(job, held, playbook, _answer(raw, alternate="add"), [finding])
    assert revised.alternate == "base"


# ---- the run: lines counted from the family take the new count; the estimator's count stands -----------------------------

def test_the_run_carries_the_corrected_count_to_the_lines_counted_from_the_family(job, raw, held, playbook):
    from bms import run
    system = job.system("EF")
    answer = _answer(raw, _count(4, [S44]))
    # the writer left every line at the old count; the controller line cites the family's count source
    revised = run._revised(system, [_count_finding()], ai.evidence_for(system, held), playbook, FakeTransport(answer),
                           job)
    by_id = {d.id: d for d in revised.devices}
    assert revised.families[0].count.value == 4
    assert by_id["EF.d1"].quantity.value == 4                           # counted from the family: carried
    assert by_id["EF.d3"].quantity.value == 2                           # counted from other sources: left


def test_the_run_keeps_the_count_the_estimator_set(job, raw, held, playbook):
    from bms import run
    system = job.system("EF")
    revised = run._revised(system, [_count_finding()], ai.evidence_for(system, held), playbook,
                           FakeTransport(_answer(raw, _count(4, [S44]))), job, hold_counts=("Exhaust Fan",))
    assert revised.families[0].count.value == 3
