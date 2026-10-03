# tests/test_ledger_passes.py
"""The seven reading passes: what each reads, what it may settle, and how its answer changes the ledger."""
from types import SimpleNamespace

from estimator.ledger.facts import ADDED, CONTRADICTED, SETTLED, Ledger
from estimator.ledger.passes import LEDGER_PROMPT, PASSES, apply, documents, pass_named, prompt, schema
from estimator.ledger.seed import seed
from tests.test_ledger_seed import SOURCES, _dossier

SHEETS = (SimpleNamespace(document="Drawings.pdf", page=3, number="M-201", title="FIRST FLOOR PLAN", discipline="Mechanical",
                          types=("Plans",)),
          SimpleNamespace(document="Drawings.pdf", page=12, number="M-601", title="SCHEDULES", discipline="Mechanical",
                          types=("Schedules",)))
CATALOGUE = SimpleNamespace(sheets=SHEETS)


def test_the_passes_are_in_the_estimators_order():
    assert [p.name for p in PASSES] == ["schedules", "plans", "details", "risers", "network", "sequence", "spec"]
    assert pass_named("risers").settles == ("link", "group", "device")
    assert pass_named("plans").may_add == ("family", "unit", "count")
    assert pass_named("schedules").may_add == ()


def test_each_pass_reads_only_its_own_documents():
    dossier = _dossier()
    assert "[S4] VAV BOX SCHEDULE" in documents(pass_named("schedules"), dossier, CATALOGUE)
    assert "[S2] Each VAV box" not in documents(pass_named("schedules"), dossier, CATALOGUE)
    plans = documents(pass_named("plans"), dossier, CATALOGUE)
    assert "[S8] OCC" in plans and "[S9] M-201 KEY NOTES" in plans and "[S10] M-201" in plans
    assert "[S11] M-601" not in plans                 # a schedule sheet's text is not the plans pass's
    assert documents(pass_named("risers"), dossier, CATALOGUE) == ""     # no riser sheets in this job
    sequence = documents(pass_named("sequence"), dossier, CATALOGUE)
    assert "[Q1] VAV BOXES" in sequence and "No points list" in sequence
    spec = documents(pass_named("spec"), dossier, CATALOGUE)
    assert "[S13]" in spec and "[S1]" in spec


def test_the_prompt_carries_the_understanding_the_ledger_and_the_documents():
    ledger = seed(_dossier())
    ledger.understanding["schedules"] = "Twelve VAV boxes and two exhaust fans."
    text = prompt(pass_named("plans"), ledger, "[S8] OCC (Occupancy sensor): 21 in all — M-201 10, M-202 11")
    assert text.index("Job: 26-9999") < text.index("What the earlier passes understood") < text.index("F1 family VAV")
    assert text.index("F1 family VAV") < text.index("The documents for this pass") < text.index("[S8] OCC")
    assert "Twelve VAV boxes and two exhaust fans." in text
    assert "seen on plans, not scheduled" in text          # the plans pass's own instructions
    assert "You are an HVAC controls estimator at AME" in LEDGER_PROMPT
    assert schema()["required"] == ["facts", "contradictions", "confirmations", "understanding"]


def _answer(**overrides):
    answer = {"facts": [], "contradictions": [], "confirmations": [], "understanding": "A small school."}
    answer.update(overrides)
    return answer


def _known(ledger):
    return frozenset(ledger.sources) | frozenset(ledger.facts)


def test_a_pass_settles_the_kinds_it_owns_and_adds_the_rest():
    ledger = seed(_dossier())
    refused = apply(pass_named("plans"), ledger, _answer(facts=[
        {"kind": "location", "subject": "VAV", "value": "floors 1 and 2", "source_id": "[S10]", "quote": "FIRST FLOOR PLAN: VAV-1 VAV-2"},
        {"kind": "family", "subject": "GD", "value": "Gravity damper", "source_id": "[S10]", "quote": "GD-1 beside EF-1"},
    ]), _known(ledger))

    assert refused == []
    assert ledger.find("location", "VAV").state == SETTLED and ledger.find("location", "VAV").stage == "plans"
    assert ledger.find("family", "GD").state == ADDED          # the plans pass may only add a family


def test_a_kind_the_pass_may_not_touch_is_refused():
    ledger = seed(_dossier())
    refused = apply(pass_named("plans"), ledger, _answer(facts=[
        {"kind": "front_end", "subject": "mode", "value": "new-system", "source_id": "[S10]", "quote": "new BMS"}]),
        _known(ledger))
    assert refused == ["the plans pass may not write a front_end fact (mode = new-system); left out"]
    assert ledger.find("front_end", "mode") is None


def test_a_fact_with_an_unknown_source_or_no_quote_is_refused():
    ledger = seed(_dossier())
    refused = apply(pass_named("plans"), ledger, _answer(facts=[
        {"kind": "location", "subject": "VAV", "value": "floor 1", "source_id": "[S99]", "quote": "VAV-1"},
        {"kind": "location", "subject": "EF", "value": "roof", "source_id": "[S10]", "quote": ""}]), _known(ledger))
    assert refused == ["location VAV = floor 1 cites [S99], which the documents do not have; left out",
                       "location EF = roof has no quote; left out"]


def test_a_different_value_for_a_settled_fact_becomes_a_contradiction():
    ledger = seed(_dossier())
    refused = apply(pass_named("plans"), ledger, _answer(facts=[
        {"kind": "count", "subject": "VAV", "value": 14, "source_id": "[S10]", "quote": "VAV-1 … VAV-14"}]), _known(ledger))
    count = ledger.find("count", "VAV")
    assert refused == []
    assert count.value == 12 and count.state == CONTRADICTED
    assert count.contradictions[0].value == 14 and count.contradictions[0].stage == "plans"
    assert len(ledger.of_kind("count")) == 2       # VAV and EF: no second VAV count was added


def test_contradictions_and_confirmations_by_id():
    ledger = seed(_dossier())
    ef = ledger.find("count", "EF")
    refused = apply(pass_named("schedules"), ledger, _answer(
        contradictions=[{"fact_id": "F1", "value": "Chilled Beam", "source_id": "[S4]", "quote": "VAV BOX SCHEDULE"},
                        {"fact_id": "F99", "value": 3, "source_id": "[S4]", "quote": "three"}],
        confirmations=[ef.id, "F98"]), _known(ledger))
    assert ledger.facts["F1"].state == CONTRADICTED
    assert ledger.find("count", "EF").state == SETTLED
    assert refused == ["a contradiction names F99, which the ledger does not have; left out",
                       "a confirmation names F98, which the ledger does not have; left out"]


def test_the_understanding_is_kept_per_pass():
    ledger = seed(_dossier())
    apply(pass_named("schedules"), ledger, _answer(understanding="  Twelve VAV boxes.  "), _known(ledger))
    assert ledger.understanding == {"schedules": "Twelve VAV boxes."}


# --- a pass's answer to a provisional fact --------------------------------------------------------------------

def test_a_count_the_schedules_pass_corrects_is_settled_with_the_seed_beside_it():
    ledger = seed(_dossier())
    ef = ledger.find("count", "EF")
    assert ef.state == ADDED and ef.value == 2
    refused = apply(pass_named("schedules"), ledger, _answer(facts=[
        {"kind": "count", "subject": "EF", "value": 3, "source_id": "[S4]", "quote": "EF-1, EF-2, EF-3"}]), _known(ledger))
    after = ledger.facts[ef.id]
    assert refused == []
    assert after.value == 3 and after.source_id == "S4" and after.stage == "schedules"
    assert after.state == CONTRADICTED
    assert [(c.value, c.source_id, c.stage) for c in after.contradictions] == [(2, "S6", "seed")]
    assert ledger.printed_count(ef.id) == 3
    assert len(ledger.of_kind("count")) == 2


def test_a_lower_count_from_the_schedules_pass_still_prints_the_higher():
    ledger = seed(_dossier())
    ef = ledger.find("count", "EF")
    apply(pass_named("schedules"), ledger, _answer(facts=[
        {"kind": "count", "subject": "EF", "value": 1, "source_id": "[S4]", "quote": "EF-1"}]), _known(ledger))
    assert ledger.facts[ef.id].value == 1 and ledger.printed_count(ef.id) == 2


def test_a_name_the_schedules_pass_gives_replaces_the_catalogues_guess():
    ledger = seed(_dossier())
    family = ledger.find("family", "EF")
    apply(pass_named("schedules"), ledger, _answer(facts=[
        {"kind": "family", "subject": "EF", "value": "Toilet Exhaust Fan", "source_id": "[S4]", "quote": "TOILET EXHAUST FAN"}]),
        _known(ledger))
    after = ledger.facts[family.id]
    assert after.value == "Toilet Exhaust Fan" and after.state == SETTLED and after.contradictions == ()
    assert len(ledger.of_kind("family")) == 3


def test_a_blank_sequence_heading_is_answered_by_the_sequence_pass():
    ledger = seed(_dossier())
    heading = ledger.find("sequence_match", "VAV BOXES")
    apply(pass_named("sequence"), ledger, _answer(facts=[
        {"kind": "sequence_match", "subject": "VAV BOXES", "value": "VAV", "source_id": "[Q1]", "quote": "VAV BOXES"}]),
        _known(ledger))
    after = ledger.facts[heading.id]
    assert after.value == "VAV" and after.state == SETTLED and after.contradictions == ()


def test_a_provisional_count_a_pass_may_only_add_is_kept_beside_it():
    ledger = seed(_dossier())
    ef = ledger.find("count", "EF")
    apply(pass_named("plans"), ledger, _answer(facts=[
        {"kind": "count", "subject": "EF", "value": 5, "source_id": "[S10]", "quote": "EF-1 … EF-5"}]), _known(ledger))
    after = ledger.facts[ef.id]
    assert after.value == 2 and after.state == CONTRADICTED and after.contradictions[0].value == 5


# --- facts that hold many values ------------------------------------------------------------------------------

def test_notes_front_end_lines_and_locations_are_kept_one_fact_per_value():
    ledger = seed(_dossier())
    apply(pass_named("spec"), ledger, _answer(facts=[
        {"kind": "note", "subject": "question", "value": "Is the existing BMS kept?", "source_id": "[S13]", "quote": "existing BMS"},
        {"kind": "note", "subject": "question", "value": "Who provides the VFDs?", "source_id": "[S13]", "quote": "VFDs"},
        {"kind": "front_end", "subject": "line", "value": "Provide a new Niagara N4 front end", "source_id": "[S13]", "quote": "Niagara N4"},
        {"kind": "front_end", "subject": "line", "value": "Provide one workstation", "source_id": "[S13]", "quote": "workstation"},
        {"kind": "note", "subject": "QUESTION", "value": "Is the existing BMS kept?", "source_id": "[S13]", "quote": "existing BMS"},
    ]), _known(ledger))
    apply(pass_named("plans"), ledger, _answer(facts=[
        {"kind": "location", "subject": "VAV", "value": "floor 1", "source_id": "[S10]", "quote": "FIRST FLOOR PLAN"},
        {"kind": "location", "subject": "VAV", "value": "floor 2", "source_id": "[S10]", "quote": "SECOND FLOOR PLAN"}]),
        _known(ledger))
    assert [f.value for f in ledger.of_kind("note")] == ["Is the existing BMS kept?", "Who provides the VFDs?"]
    assert [f.value for f in ledger.of_kind("front_end")] == ["Provide a new Niagara N4 front end", "Provide one workstation"]
    assert [f.value for f in ledger.of_kind("location")] == ["floor 1", "floor 2"]
    assert all(f.state == SETTLED and f.contradictions == () for f in ledger.of_kind("note") + ledger.of_kind("location"))


def test_the_front_end_mode_is_still_one_value():
    ledger = seed(_dossier())
    apply(pass_named("spec"), ledger, _answer(facts=[
        {"kind": "front_end", "subject": "mode", "value": "new-system", "source_id": "[S13]", "quote": "new BMS"},
        {"kind": "front_end", "subject": "mode", "value": "extend-existing", "source_id": "[S13]", "quote": "extend"}]),
        _known(ledger))
    (mode,) = ledger.of_kind("front_end")
    assert mode.value == "new-system" and mode.state == CONTRADICTED


# --- riser sheets belong to the risers pass -------------------------------------------------------------------

def test_the_details_pass_leaves_riser_sheets_to_the_risers_pass():
    sheets = (SimpleNamespace(document="Drawings.pdf", page=3, number="M-201", title="RISER", discipline="Mechanical",
                              types=("Details", "Air riser")),
              SimpleNamespace(document="Drawings.pdf", page=12, number="M-601", title="DETAILS", discipline="Mechanical",
                              types=("Details",)))
    catalogue = SimpleNamespace(sheets=sheets)
    details = documents(pass_named("details"), _dossier(), catalogue)
    assert "[S11] M-601" in details and "[S10] M-201" not in details
    assert "[S10] M-201" in documents(pass_named("risers"), _dossier(), catalogue)
    assert pass_named("details").not_sheet_types == ("Air riser", "Water riser", "Network riser")
