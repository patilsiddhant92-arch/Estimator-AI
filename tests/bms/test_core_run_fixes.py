"""Regression tests for the core and run fixes of the 2026-10-09 audit: CORE-1 (an unnamed existing BMS), CORE-2
(sub-line ownership), CORE-3 (one clarification of each kind), CORE-4 (the D3 rep-assist line in a block with no
shape), RUN-1 (the estimator's line decisions kept through the revise), RUN-2 (an older decisions.json copied in
again), RUN-4 (must_fix questions never hidden behind the cap) and RUN-11 (the revise may correct a count or the
alternate a must_fix finding asks for, checked against the evidence).

Every job here is invented; the Playbook is the repo's own (`playbook/`), the sample job the test fixture."""
from __future__ import annotations

import copy
import dataclasses
import json
import re
from pathlib import Path

import pytest

from bms import ai, render as render_mod, review, run
from bms.model import (Clarification, Count, Decision, Device, Family, Finding, FrontEnd, Header, Job, OtherCount,
                       Ref, System)
from bms.playbook import load_playbook
from bms.render import EXISTING_PLACEHOLDER, existing_name_given, existing_system_name, render
from bms.validate import RULE, validate

FIXTURES = Path(__file__).parent / "fixtures"
PB = load_playbook()
REF = Ref("S1", "invented words", "M-1, Invented.pdf page 1")
HEADER = Header("Q-1", "Invented Ref", "Invented Engineer", ("M-1",), "2026-10-09")


def dev(id_, slot, name="Invented Device", verb="Furnish and Install", f="AME", i="AME", w="AME", qty=None, **kw):
    return Device(id_, slot, name, verb, f, i, w, qty or Count(1, (REF,)), (REF,), **kw)


def job_of(*systems, front_end=None) -> Job:
    return Job("Invented job", tuple(systems), front_end=front_end, header=HEADER)


def rules(findings):
    return [(f.rule, f.system_key, f.device_id, f.severity) for f in findings]


@pytest.fixture
def sample() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


# ---- CORE-1: an existing BMS the documents do not name -------------------------------------------------------------

@pytest.mark.parametrize("name", [None, "", "  ", "base building controls (vendor not named)", "unknown",
                                  "Existing BMS", EXISTING_PLACEHOLDER])
def test_an_unnamed_existing_bms_prints_the_placeholder_and_asks_to_confirm_the_vendor(name):
    j = job_of(front_end=FrontEnd("extend-existing", name))
    draft = render(j, PB)                                   # no crash (it raised a RenderError before)
    assert draft.scope.front_end.existing_system_name == EXISTING_PLACEHOLDER
    notes = [i.runs[0].text for i in draft.scope.front_end.items if i.kind == "note"]
    assert any(n.startswith("*Confirm") and "vendor" in n for n in notes), notes
    found = [f for f in validate(j, PB) if f.rule == "Front end mode"]
    assert found and found[0].severity == "check" and EXISTING_PLACEHOLDER in found[0].what


def test_the_word_proposal_heading_carries_the_placeholder_not_the_description():
    from estimator.proposal.layout import front_end_heading
    j = job_of(front_end=FrontEnd("extend-existing", "base building controls (vendor not named)"))
    heading = front_end_heading(render(j, PB).scope.front_end)
    assert heading.endswith(f"{EXISTING_PLACEHOLDER} BMS") and "vendor not named" not in heading


def test_a_named_existing_bms_prints_as_given_with_no_finding():
    j = job_of(front_end=FrontEnd("extend-existing", "Honeywell / Niagara N4"))
    draft = render(j, PB)
    assert draft.scope.front_end.existing_system_name == "Honeywell / Niagara N4"
    assert not any(i.kind == "note" for i in draft.scope.front_end.items)
    assert [f for f in validate(j, PB) if f.rule == "Front end mode"] == []


def test_a_vendor_confirm_the_front_end_already_has_is_not_printed_twice():
    fe = FrontEnd("extend-existing", None, clarifications=(Clarification("confirm", "existing BMS vendor"),))
    notes = [i.runs[0].text for i in render(job_of(front_end=fe), PB).scope.front_end.items if i.kind == "note"]
    assert notes == ["*Confirm existing BMS vendor"]


def test_a_new_system_with_a_name_renders_and_is_a_check():
    j = job_of(front_end=FrontEnd("new-system", "Metasys"))
    assert render(j, PB).scope.front_end.existing_system_name is None      # it raised before
    assert ("Front end mode", "", None, "check") in rules(validate(j, PB))


def test_existing_name_given():
    assert existing_name_given("Siemens Apogee") and existing_name_given("Existing Johnson Controls Metasys")
    assert not existing_name_given("base building controls") and not existing_name_given("TBD")
    assert existing_system_name(FrontEnd("new-system")) is None and existing_system_name(None) is None


# ---- CORE-2: a sub-line carries its parent's ownership ------------------------------------------------------------

def _gas(sensor_owners):
    f, i, w = sensor_owners
    verb = "Furnish and Install" if f == "AME" else "Wire"
    return System("GD", "Gas Detection", "Gas Detection", "field",
                  (Family("Gas Detection Panel", ("GDP-1",), Count(1, (REF,))),),
                  devices=(dev("GD.d1", "panel", "Gas Detection Panel"),
                           dev("GD.d2", "sensor", "CO Sensor", verb, f, i, w)))


def test_a_sub_line_owned_otherwise_than_its_parent_is_a_must_fix():
    found = validate(job_of(_gas(("Others", "Others", "AME"))), PB)
    assert ("Sub-lines under their parent", "GD", "GD.d2", "must_fix") in rules(found)


def test_a_sub_line_with_its_parents_ownership_passes():
    found = validate(job_of(_gas(("AME", "AME", "AME"))), PB)
    assert [r for r in rules(found) if r[0] == "Sub-lines under their parent"] == []


def test_the_integration_rep_assist_sub_line_is_exempt_from_the_match():
    """Ruling D3: the rep-assist sub-line is the mechanical contractor's under an AME Map Available Points line."""
    trio = (dev("EF.d1", "comm_wiring", "BMS Communication Wiring", "Furnish"),
            dev("EF.d2", "map_points", "Map Available Points Via Mfr. Provided BMS Interface", "Furnish"),
            dev("EF.d3", "rep_assist", "AME requires mfr. Rep to assist in integration, cost to be incurred by mech "
                "contractor", "Furnish", "Mechanical Contractor", "Mechanical Contractor", "Mechanical Contractor"))
    ef = System("EF", "Exhaust Fans", "Exhaust Fan", "packaged", (Family("Exhaust Fan", ("EF-1",), Count(1, (REF,))),),
                devices=trio)
    assert [r for r in rules(validate(job_of(ef), PB)) if r[0] == "Sub-lines under their parent"] == []


# ---- CORE-3: one clarification of each kind -----------------------------------------------------------------------

def _ef(*clarifications):
    return System("EF", "Exhaust Fans", "Exhaust Fan", "field", (Family("Exhaust Fan", ("EF-1",), Count(1, (REF,))),),
                  devices=(dev("EF.d1", "start_stop_status", "Exhaust Fan Start/Stop and Status", "Furnish"),),
                  clarifications=clarifications)


def test_a_confirm_and_a_client_note_in_one_block_pass_and_print_as_two_lines():
    j = job_of(_ef(Clarification("confirm", "quantity: 1 per schedule"),
                   Clarification("note", "Start/Stop via Fire Alarm System")))
    assert [r for r in rules(validate(j, PB)) if r[0] == "One clarification per block"] == []
    notes = [line.text for line in render(j, PB).lines if line.kind == "note"]
    assert notes == ["*Confirm quantity: 1 per schedule", "**Start/Stop via Fire Alarm System"]


def test_two_clarifications_of_one_kind_are_a_must_fix():
    j = job_of(_ef(Clarification("confirm", "a"), Clarification("confirm", "b")))
    assert ("One clarification per block", "EF", None, "must_fix") in rules(validate(j, PB))


def _answer(system: System, **changes) -> dict:
    return dict(system.to_dict(), **changes)


def test_the_writer_intake_takes_one_clarification_of_each_kind():
    system = _ef()
    ok = _answer(system, clarifications=[{"kind": "confirm", "text": "quantity"}, {"kind": "note", "text": "a note"}])
    written, problems = ai._check_system(ok, system, PB.shapes["Exhaust Fan"], frozenset({"S1"}))
    assert problems == [] and len(written.clarifications) == 2
    two = _answer(system, clarifications=[{"kind": "confirm", "text": "a"}, {"kind": "confirm", "text": "b"}])
    written, problems = ai._check_system(two, system, PB.shapes["Exhaust Fan"], frozenset({"S1"}))
    assert written is None and any("'confirm'" in p for p in problems)


# ---- CORE-4: the D3 rep-assist line in a block with no shape ------------------------------------------------------

def _untemplated(rep_owner="Mechanical Contractor"):
    trio = (dev("G.d1", "comm_wiring", "BMS Communication Wiring", "Furnish"),
            dev("G.d2", "map_points", "Map Available Points Via Mfr. Provided BMS Interface", "Furnish"),
            dev("G.d3", "rep_assist", "AME requires mfr. Rep to assist in integration, cost to be incurred by mech "
                "contractor", "Furnish", rep_owner, rep_owner, rep_owner))
    return System("G", "Generator", "", "integration", (Family("Generator", ("GEN-1",), Count(1, (REF,))),),
                  devices=trio)


def test_the_house_rep_assist_line_in_an_untemplated_block_is_no_ownership_must_fix():
    found = validate(job_of(_untemplated()), PB)
    assert [r for r in rules(found) if r[0] == "Every line carries its ownership"] == []


def test_a_real_line_of_another_trade_in_an_untemplated_block_still_is():
    other = System("G", "Generator", "", "field", (Family("Generator", ("GEN-1",), Count(1, (REF,))),),
                   devices=(dev("G.d1", "relay", "Invented Relay", "Furnish", "Others", "Others", "Others"),))
    assert ("Every line carries its ownership", "G", "G.d1", "must_fix") in rules(validate(job_of(other), PB))


# ---- RUN-1: the estimator's deletes and changes hold through the revise --------------------------------------------

class Rewrites:
    """A writer that answers the revise with the block as it first wrote it (the deleted line back, the change
    undone)."""
    waiting = 0
    last_error = None

    def __init__(self, answer: System):
        self.answer = answer.to_dict()
        self.prompts: list[str] = []

    def ask(self, kind, name, instructions, system_prompt, prompt, schema, extra=None, images=()):
        self.prompts.append(prompt)
        return copy.deepcopy(self.answer)


EVIDENCE = ("[Q2] exhaust fans shall start and stop on the BMS schedule\n\n[S6] EF-1 EF-2 EF-3\n\n"
            "[S7] MD-1 interlocked with EF-1\n\n[S8] MD-2 interlocked with EF-2")
WHOLE = Finding("Every line cites this job", "EF", None, "must_fix", "the block's clarification is wrong", "fix it")


def test_a_deleted_line_does_not_come_back_after_a_whole_block_revise(sample):
    written = sample.system("EF")
    d3 = next(d for d in written.devices if d.id == "EF.d3")
    delete = Decision("EF", "delete", device_id="EF.d3", was=d3)
    decided = review.apply_decisions(sample, [delete])
    writer = Rewrites(written)
    revised = run._revised(decided.system("EF"), [WHOLE], EVIDENCE, PB, writer, decided, lines=[delete])
    final = decided.with_system(revised)
    assert [d.id for d in final.system("EF").devices] == ["EF.d1", "EF.d2"]
    assert review.unhonored_decisions(sample, [delete], final) == []
    assert "Lines the estimator deleted" in writer.prompts[0] and d3.name in writer.prompts[0]


def test_a_changed_line_keeps_the_estimators_words_after_a_whole_block_revise(sample):
    written = sample.system("EF")
    d1 = written.devices[0]
    mine = dataclasses.replace(d1, name="Invented Estimator Name")
    change = Decision("EF", "change", device_id=d1.id, device=mine, was=d1)
    decided = review.apply_decisions(sample, [change])
    writer = Rewrites(written)
    revised = run._revised(decided.system("EF"), [WHOLE], EVIDENCE, PB, writer, decided, lines=[change])
    final = decided.with_system(revised)
    assert any(d.name == "Invented Estimator Name" for d in final.system("EF").devices)
    assert not any(d.name == d1.name for d in final.system("EF").devices)
    assert review.unhonored_decisions(sample, [change], final) == []
    assert "The estimator's lines" in writer.prompts[0]


def test_a_finding_on_the_estimators_own_line_is_not_sent_to_the_writer(sample):
    written = sample.system("EF")
    d1 = written.devices[0]
    mine = dataclasses.replace(d1, name="Invented Estimator Name")
    decided = review.apply_decisions(sample, [Decision("EF", "change", device_id=d1.id, device=mine, was=d1)])
    finding = Finding("Every line carries its ownership", "EF", d1.id, "must_fix", "wrong verb", "fix")
    writer = Rewrites(written)
    system = decided.system("EF")
    assert ai.revise_system(system, [finding], EVIDENCE, PB, writer, estimators=(d1.id,)) is system
    assert writer.prompts == []


# ---- RUN-2: an older decisions.json copied in again ------------------------------------------------------------------

def _count(sample, n):
    family = sample.system("EF").families[0]
    return Decision("EF", "change", family_name=family.name, count=Count(n, family.count.sources, ()))


def test_an_older_save_copied_in_again_does_not_roll_back_newer_answers(sample):
    a, b = [_count(sample, 5)], [_count(sample, 6)]
    history = review.merge_decisions([], a, job=sample)
    history = review.merge_decisions(history, b, job=sample)
    again = review.merge_decisions(history, a, job=sample)
    assert again == history
    assert review.stale_save(history, a) and not review.stale_save(history, b)
    applied = review.apply_decisions(sample, [e.decision for e in again])
    assert applied.system("EF").families[0].count.value == 6


def test_the_same_answers_saved_from_a_newer_page_are_a_new_round(sample):
    a, b = [_count(sample, 5)], [_count(sample, 6)]
    history = review.merge_decisions([], a, job=sample, page="p1")
    history = review.merge_decisions(history, b, job=sample, page="p2")
    assert review.stale_save(history, a, "p1")
    newer = review.merge_decisions(history, a, job=sample, page="p3")
    assert max(e.round for e in newer) == 3
    assert review.apply_decisions(sample, [e.decision for e in newer]).system("EF").families[0].count.value == 5


def test_the_history_remembers_its_saves_across_a_save_and_load(sample, tmp_path):
    history = review.merge_decisions([], [_count(sample, 5)], job=sample, page="p1")
    history = review.merge_decisions(history, [_count(sample, 6)], job=sample, page="p2")
    review.save_history(tmp_path, history)
    loaded = review.load_history(tmp_path)
    assert loaded == history and review.stale_save(loaded, [_count(sample, 5)], "p1")


def test_the_page_saves_its_id_and_the_run_reads_both_forms(sample, tmp_path):
    page = review.review_page(sample, [], tmp_path).read_text(encoding="utf-8")
    page_id = re.search(r'var PAGE_ID = "([0-9a-f]+)";', page).group(1)
    assert "decisions: out" in page
    decision = _count(sample, 7)
    (tmp_path / "decisions.json").write_text(json.dumps({"page": page_id, "decisions": [decision.to_dict()]}),
                                             encoding="utf-8")
    assert review.load_decisions(tmp_path) == [decision] and review.decisions_page(tmp_path) == page_id
    (tmp_path / "decisions.json").write_text(json.dumps([decision.to_dict()]), encoding="utf-8")
    assert review.load_decisions(tmp_path) == [decision] and review.decisions_page(tmp_path) is None


# ---- RUN-4: must_fix questions are never hidden behind the cap ------------------------------------------------------

def test_every_must_fix_question_shows_whatever_the_cap(sample, tmp_path):
    findings = [Finding("Every line cites this job", "EF", None, "must_fix", f"must fix {n}", "fix")
                for n in range(review.MAX_QUESTIONS + 2)]
    page = review.review_page(sample, findings, tmp_path).read_text(encoding="utf-8")
    assert re.findall(r'<div class="q extra" id="q\d+" data-rank="0">', page) == []
    assert all(f"must fix {n}" in page for n in range(review.MAX_QUESTIONS + 2))


def test_a_card_with_some_questions_behind_the_cap_says_how_many(sample, tmp_path):
    findings = [Finding("Every line cites this job", "EF", None, "check", f"check {n}", "fix")
                for n in range(review.MAX_QUESTIONS + 3)]
    page = review.review_page(sample, findings, tmp_path).read_text(encoding="utf-8")
    card = re.search(r'data-system="EF">(.*?)</section>', page, re.S).group(1)
    hidden = len(re.findall(r'class="q extra"', card))
    assert 0 < hidden < card.count('class="q') and f"{hidden} more question(s)" in card


# ---- RUN-11: the revise corrects a count or the alternate a must_fix finding asks for -------------------------------

VEVIDENCE = ("[S2] EF (Exhaust Fan): schedule rows 2; distinct tags 2; plan placements 4 (M-1 2; M-2 2)\n\n"
             "[S3] EXHAUST FAN SCHEDULE (ADD ALTERNATE) EF-1 EF-2\n\n[S4] exhaust fans start and stop on the BMS")
R_ROWS = Ref("S2", "schedule rows 2; distinct tags 2", "equipment counts for EF")
R_PLACED = Ref("S2", "plan placements 4 (M-1 2; M-2 2)", "equipment counts for EF")


def _planned(alternate="base") -> System:
    """As the planner left it: the plan placements (each fan shown on two plans) carried as the count."""
    family = Family("Exhaust Fan", ("EF-1", "EF-2"), Count(4, (R_PLACED,), (OtherCount(2, R_ROWS),)))
    line = Device("EF.d1", "start_stop_status", "Exhaust Fan Start/Stop and Status", "Furnish", "AME", "AME", "AME",
                  Count(4, (R_PLACED,)), (Ref("S4", "exhaust fans start and stop on the BMS", "M-1"),))
    return System("EF", "Exhaust Fans", "Exhaust Fan", "field", (family,), devices=(line,), tech_hours=8.0,
                  alternate=alternate)


COUNT_FINDING = Finding("The schedule count prints", "EF", None, "must_fix",
                        "The EF count of 4 counts EF-1 and EF-2 twice, once on M-1 and once on M-2.",
                        "Set the EF count to 2 per the fan schedule, and name the plan figure in the note.")
ALT_FINDING = Finding("Never invent an alternate", "EF", None, "must_fix",
                      "The schedule titles this equipment an add alternate, but the block is carried as base.",
                      "Set the block's alternate to add alternate, as the schedule titles it.")


def _corrected(system: System, value=2, sources=(R_ROWS,), others=(OtherCount(4, R_PLACED),),
               alternate=None) -> dict:
    answer = system.to_dict()
    answer["families"][0]["count"] = Count(value, tuple(sources), tuple(others)).to_dict()
    for d in answer["devices"]:
        d["quantity"]["value"] = value
    answer["tech_hours"] = 4.0
    if alternate:
        answer["alternate"] = alternate
    return answer


def test_the_revise_carries_a_count_correction_the_finding_asks_for():
    system = _planned()
    revised = ai.revise_system(system, [COUNT_FINDING], VEVIDENCE, PB, Rewrites(System.from_dict(_corrected(system))))
    family = revised.families[0]
    assert family.count.value == 2 and family.count.highest() == 2
    assert family.count.sources == (R_ROWS,) and family.count.others == ()     # the double-counted figure is gone
    assert family.tags == ("EF-1", "EF-2") and family.name == "Exhaust Fan"
    assert revised.devices[0].quantity.value == 2 and revised.alternate == "base"


def test_the_corrected_count_reaches_job_json_the_proposal_and_the_price_sheet():
    system = _planned()
    revised = run._revised(system, [COUNT_FINDING], VEVIDENCE, PB, Rewrites(System.from_dict(_corrected(system))))
    j = job_of(revised)
    assert Job.from_json(j.to_json()).system("EF").families[0].count.value == 2
    assert [f for f in validate(j, PB) if f.severity == "must_fix"] == []
    draft = render(j, PB)
    headers = [line.text for line in draft.lines if line.kind == "header"]
    assert headers and headers[0].startswith("Qty (2)")
    assert draft.scope.blocks[0].header.startswith("Qty (2)")
    cards = run.revise_corrections(system, revised, [COUNT_FINDING], VEVIDENCE)
    assert [(c.rule, c.severity) for c in cards] == [("The schedule count prints", "check")]
    assert "from 4 to 2" in cards[0].what and "S2" in cards[0].what


def test_a_count_correction_without_a_finding_that_asks_for_it_is_not_taken():
    system = _planned()
    other = Finding("Every line cites this job", "EF", None, "must_fix", "the clarification is wrong", "Fix it.")
    revised = ai.revise_system(system, [other], VEVIDENCE, PB, Rewrites(System.from_dict(_corrected(system))))
    assert revised.families == system.families                        # the planner's count still wins


def test_a_count_correction_the_evidence_does_not_hold_is_refused():
    system = _planned()
    made_up = Ref("S2", "schedule rows 3", "equipment counts for EF")
    answer = _corrected(system, value=3, sources=(made_up,), others=(OtherCount(4, R_PLACED),))
    with pytest.raises(ai.NoAnswer) as refused:
        ai.revise_system(system, [COUNT_FINDING], VEVIDENCE, PB, Rewrites(System.from_dict(answer)))
    assert "Exhaust Fan count" in str(refused.value.reason)


def test_a_count_correction_that_keeps_a_new_higher_count_is_refused():
    system = _planned()
    higher = OtherCount(6, Ref("S3", "EXHAUST FAN SCHEDULE", "M-3"))
    answer = _corrected(system, others=(OtherCount(4, R_PLACED), higher))
    with pytest.raises(ai.NoAnswer) as refused:
        ai.revise_system(system, [COUNT_FINDING], VEVIDENCE, PB, Rewrites(System.from_dict(answer)))
    assert "higher count 6" in str(refused.value.reason)


def test_an_estimators_count_is_not_corrected_by_the_revise():
    system = _planned()
    revised = ai.revise_system(system, [COUNT_FINDING], VEVIDENCE, PB, Rewrites(System.from_dict(_corrected(system))),
                               counts_decided=True)
    assert revised.families == system.families


def test_the_revise_carries_an_alternate_the_documents_name_into_the_add_alternates():
    system = _planned()
    answer = _corrected(system, alternate="add")
    answer["families"] = system.to_dict()["families"]                  # only the alternate is corrected here
    revised = run._revised(system, [ALT_FINDING], VEVIDENCE, PB, Rewrites(System.from_dict(answer)))
    assert revised.alternate == "add" and revised.families == system.families
    draft = render(job_of(revised), PB)
    assert draft.scope.add_alternates and not draft.scope.blocks
    cards = run.revise_corrections(system, revised, [ALT_FINDING], VEVIDENCE)
    assert [(c.rule, c.severity) for c in cards] == [("Never invent an alternate", "check")]
    assert "S3" in cards[0].what


def test_an_alternate_no_document_names_is_refused():
    system = _planned()
    answer = _corrected(system, alternate="deduct")
    answer["families"] = system.to_dict()["families"]
    with pytest.raises(ai.NoAnswer) as refused:
        ai.revise_system(system, [ALT_FINDING], VEVIDENCE, PB, Rewrites(System.from_dict(answer)))
    assert "deduct" in str(refused.value.reason)


def test_the_revise_prompt_lets_the_writer_correct_a_count_or_the_alternate():
    text = (Path(ai.__file__).parent / "prompts" / "revise_system.md").read_text(encoding="utf-8")
    assert "families, sequence_refs and alternate exactly as given." not in text
    assert "a count:" in text and "the alternate:" in text
    assert ai._revisions([COUNT_FINDING]) == {"count"} and ai._revisions([ALT_FINDING]) == {"alternate"}
    assert ai._revisions([dataclasses.replace(COUNT_FINDING, device_id="EF.d1")]) == set()


def test_a_corrected_count_gets_a_count_card_the_estimator_can_change(tmp_path):
    system = _planned()
    revised = run._revised(system, [COUNT_FINDING], VEVIDENCE, PB, Rewrites(System.from_dict(_corrected(system))))
    cards = run.revise_corrections(system, revised, [COUNT_FINDING], VEVIDENCE)
    page = review.review_page(job_of(revised), cards, tmp_path).read_text(encoding="utf-8")
    assert "How many Exhaust Fan units?" in page and "The revise corrected this count" in page
    assert "the revise corrected the Exhaust Fan count from 4 to 2" in page
