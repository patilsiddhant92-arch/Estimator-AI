"""REVIEW-019b: review-of-record tests for lead/task-019b (counts.counted_from, the family Accept, the I8 card
merge). Invented data only. A strict xfail is an open finding of the review: it passes once the finding is fixed."""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import pytest

from bms import counts, review
from bms.model import Assumption, Count, Decision, Family, Finding, Job, OtherCount, Ref

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TESTS = Path(__file__).resolve().parents[1]
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))


@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


def _disputed_ef(job: Job, first_flag: str) -> Job:
    """EF with a disputed Exhaust Fan count; EF.d1 is counted from it (S6, a known count) and carries `first_flag`."""
    system = job.system("EF")
    family = dataclasses.replace(system.families[0], count=dataclasses.replace(
        system.families[0].count, others=(OtherCount(2, Ref("C1", "located on the sheet text", "invented")),)))
    first = dataclasses.replace(system.devices[0], flag=first_flag,
                                assumption=Assumption("One per fan.", "The schedule lists one per fan.")
                                if first_flag == "assumed" else None)
    return job.with_system(dataclasses.replace(system, families=(family,), devices=(first, *system.devices[1:])))


# ---- finding F1: a family Accept is "not honored" whenever a counted line keeps a flag Accept never clears ---------


@pytest.mark.xfail(strict=True, reason="REVIEW-019b F1: _family_holds counts an 'assumed' or 'ownership' flag "
                                       "as the last write undoing a family Accept, which clears only 'quantity'")
@pytest.mark.parametrize("flag", ["assumed", "ownership"])
def test_a_family_accept_is_honored_when_a_counted_line_keeps_a_flag_accept_does_not_clear(job, flag):
    before = _disputed_ef(job, flag)
    decision = Decision("EF", "accept", family_name="Exhaust Fan")
    after = review.apply_decisions(before, [decision])
    assert after.system("EF").devices[0].flag == flag                 # Accept leaves it, as it should
    assert review.unhonored_decisions(before, [decision], after) == []


def test_a_family_accept_whose_quantity_flag_came_back_is_still_not_honored(job):
    """The guard the F1 fix must keep: a known-count line counted from the family, flagged "quantity" again by the
    last write, still makes the Accept "not honored"."""
    before = _disputed_ef(job, "quantity")
    decision = Decision("EF", "accept", family_name="Exhaust Fan")
    expected = review.apply_decisions(before, [decision])
    assert expected.system("EF").devices[0].flag == "none"
    found = review.unhonored_decisions(before, [decision], before)    # the last write put the flag back
    assert [f.what for f in found] == ["decision not honored: accept Exhaust Fan"]


@pytest.mark.xfail(strict=True, reason="REVIEW-019b F1, through the real run: a false must_fix on every run")
def test_a_family_accept_with_an_assumed_counted_line_gives_no_must_fix_through_the_run(tmp_path, monkeypatch):
    from test_run import JOB, _answer, _reach, _schedule_sheet, PLAN, SEQUENCE  # noqa: F401
    from pdfs import make_pdf
    from bms.run import estimate

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    root = tmp_path / f"{JOB}, 1 Invented Street"
    base = root / "2. Takeoffs" / "1. Base Takeoff"
    make_pdf(base / "Mech.pdf", _schedule_sheet(), PLAN)
    make_pdf(base / "230993.pdf", SEQUENCE)
    out, cache = tmp_path / "out", tmp_path / "cache"
    _reach(root, out, cache, "write")
    planned = json.loads(next(out.glob("* Job.json")).read_text(encoding="utf-8"))
    [vav] = [s for s in planned["systems"] if s["key"] == "VAV"]
    [family] = vav["families"]
    assert family["count"]["others"]                                  # the invented plan disputes the count
    source = family["count"]["sources"][0]
    count = {"value": family["count"]["value"], "others": [],
             "sources": [{"source_id": source["source_id"], "quote": "schedule rows", "where": "invented"}]}

    def plant():
        for path in sorted((cache / "judge-chat" / "requests").glob("*.json")):
            request = json.loads(path.read_text(encoding="utf-8"))
            answer = _answer(request)
            if request.get("kind") == "write_system" and request.get("plan_key") == "VAV":
                line = dict(answer["devices"][0], id="VAV.d1", name="Damper Actuator", quantity=count,
                            flag="assumed", assumption={"what": "One actuator per box.",
                                                        "why": "The schedule shows one damper per box."})
                answer["devices"] = [line]
            dest = Path(request["answer_file"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(answer), encoding="utf-8")

    (out / "decisions.json").write_text(json.dumps([{"system_key": "VAV", "action": "accept",
                                                     "family_name": family["name"], "reason": "invented"}]),
                                        encoding="utf-8")
    result = None
    for _ in range(25):
        plant()
        result = estimate(root, out, cache, "chat")
        if result.status == "done":
            break
    assert result.status == "done"
    # the finding is this last assert (seen with --runxfail): "decision not honored: accept Variable Air Volume Box"
    assert not [f.what for f in result.findings if f.rule == "decision not honored"]


# ---- counted_from: the shared-source tie -------------------------------------------------------------------------


def test_counted_from_ties_by_a_disagreeing_count_and_ignores_brackets_and_quotes(job):
    family = job.system("VRF").families[2]                            # Branch Selector: I1, other S11
    line = job.system("VRF").devices[0]
    by_other = dataclasses.replace(line, quantity=Count(1, (Ref("[S11]", "a trimmed quote", "elsewhere"),)))
    by_tag_only = dataclasses.replace(line, quantity=Count(1, (Ref("S99", "BS-1 BS-2", "M-002"),)))
    no_sources = dataclasses.replace(line, quantity=Count(1))
    assert counts.counted_from(by_other, family)
    assert not counts.counted_from(by_tag_only, family)
    assert not counts.counted_from(no_sources, family)
    empty = Family("Nothing", (), Count(1, (Ref("", "no id", "x"),)))
    assert not counts.counted_from(dataclasses.replace(line, quantity=Count(1, (Ref("", "no id", "x"),))), empty)


def test_a_family_accept_leaves_a_lines_own_count_disagreement_on_the_page(job):
    """Accept clears the quantity flag of a line counted from the family, but the line's own disagreeing counts
    still give it a card: the Accept does not hide a dispute that is not the family's."""
    system = job.system("EF")
    own = Count(3, system.devices[0].quantity.sources, (OtherCount(1, Ref("S20", "one keynote", "invented")),))
    first = dataclasses.replace(system.devices[0], flag="quantity", quantity=own)
    job2 = job.with_system(dataclasses.replace(system, devices=(first, *system.devices[1:])))
    after = review.apply_decisions(job2, [Decision("EF", "accept", family_name="Exhaust Fan")])
    assert after.system("EF").devices[0].flag == "none"
    assert any(q.device_id == "EF.d1" for q in review._questions(after, []))


@pytest.mark.xfail(strict=True, reason="REVIEW-019b F3 (low): a line counted from two disputed families is "
                                       "cleared by the Accept of either one")
def test_a_line_counted_from_two_disputed_families_keeps_its_flag_until_both_are_accepted(job):
    system = job.system("EF")
    fans = Family("Exhaust Fan", ("EF-1",), Count(1, (Ref("S1", "EF-1", "x"),), (OtherCount(2, Ref("C1", "q", "y")),)))
    dampers = Family("Motorized Damper", ("MD-1",), Count(1, (Ref("S2", "MD-1", "x"),),
                                                          (OtherCount(2, Ref("C2", "q", "y")),)))
    both = dataclasses.replace(system.devices[0], flag="quantity",
                               quantity=Count(1, (Ref("S1", "EF-1", "x"), Ref("S2", "MD-1", "x"))))
    job2 = job.with_system(dataclasses.replace(system, families=(fans, dampers), devices=(both,)))
    assert counts.flag_written_devices(dataclasses.replace(job2.system("EF"), devices=(
        dataclasses.replace(both, flag="none"),))).devices[0].flag == "quantity"
    one = review.apply_decisions(job2, [Decision("EF", "accept", family_name="Exhaust Fan")])
    assert one.system("EF").devices[0].flag == "quantity"


@pytest.mark.xfail(strict=True, reason="REVIEW-019b F4 (low): cross_check ties a line to the family by the whole "
                                       "citation, flag_written_devices by source id (counted_from)")
def test_cross_check_flags_the_lines_flag_written_devices_would_flag(tmp_path):
    from test_counts import _plan, _sample_job
    _, catalogue = _plan(tmp_path)
    job = _sample_job()
    system = job.system("EF")
    trimmed = dataclasses.replace(system.devices[1], flag="none",
                                  quantity=Count(3, (Ref("[S6]", "EF-1", "M-001"),)))   # same source, shorter quote
    job = job.with_system(dataclasses.replace(system, devices=(system.devices[0], trimmed, *system.devices[2:])))
    checked = counts.cross_check(job, catalogue, tmp_path / "cache")
    assert checked.system("EF").families[0].count.others                 # the plan disputes the count
    by_run = counts.flag_written_devices(dataclasses.replace(
        checked.system("EF"), devices=job.system("EF").devices))
    assert [d.flag for d in checked.system("EF").devices] == [d.flag for d in by_run.devices]


# ---- the I8 card merge --------------------------------------------------------------------------------------------


def test_three_findings_on_one_line_give_one_card_led_by_the_must_fix_with_each_other_once(job):
    findings = [Finding("Rule A", "EF", "EF.d1", "check", "A check", "Fix A"),
                Finding("Rule B", "EF", "EF.d1", "must_fix", "A must fix", "Fix B"),
                Finding("Rule C", "EF", "EF.d1", "check", "Another check", "Fix C"),
                Finding("Rule A", "EF", "EF.d1", "check", "A check", "Fix A"),
                Finding("Rule D", "EF", "EF.d1", "must_fix", "A second must fix", "Fix D")]
    cards = [q for q in review._questions(job, findings) if q.device_id == "EF.d1"]
    assert len(cards) == 1
    card = cards[0]
    assert (card.rank, card.title, card.finding_rule) == (review.RANK_MUST_FIX, "A must fix", "Rule B")
    finding_notes = [n for n in card.notes if n.startswith("Finding:")]
    assert finding_notes == ["Finding: A check", "Finding: Another check", "Finding: A second must fix"]
    assert len(card.notes) == len(set(card.notes))
    assert not any("A must fix" in n for n in card.notes)            # the lead is never repeated as a note


@pytest.mark.xfail(strict=True, reason="REVIEW-019b F2 (low, the author's concern 3): when a must_fix takes the lead "
                                       "the check's 'What to do' stays the first note, so it reads as the lead's fix")
def test_the_leading_findings_fix_is_the_first_note(job):
    findings = [Finding("Rule A", "EF", "EF.d1", "check", "A check", "Fix A"),
                Finding("Rule B", "EF", "EF.d1", "must_fix", "A must fix", "Fix B")]
    card = next(q for q in review._questions(job, findings) if q.device_id == "EF.d1")
    assert card.title == "A must fix"
    assert card.notes[0] == "What to do: Fix B"
