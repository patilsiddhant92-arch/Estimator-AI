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
    assert pass_named("plans").may_add == ("family", "unit", "count", "note")
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
    refused = apply(pass_named("plans"), ledger, _answer(
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


def test_two_sequence_sections_with_one_heading_each_keep_their_own_match():
    from bms.plan_read import Reader
    ledger = seed(_dossier(sections={"Q1": ("1. OCCUPIED MODE", ("S2",)), "Q2": ("1. OCCUPIED MODE", ("S3",))}))
    refused = apply(pass_named("sequence"), ledger, _answer(facts=[
        {"kind": "sequence_match", "subject": "1. OCCUPIED MODE", "value": "VAV", "source_id": "[Q1]",
         "quote": "1. OCCUPIED MODE"},
        {"kind": "sequence_match", "subject": "1. OCCUPIED MODE", "value": "EF", "source_id": "[Q2]",
         "quote": "1. OCCUPIED MODE"}]), _known(ledger))
    assert refused == []
    by_section = {f.source_id: f for f in ledger.of_kind("sequence_match")}
    assert len(ledger.of_kind("sequence_match")) == 2
    assert by_section["Q1"].value == "VAV" and by_section["Q1"].state == SETTLED and by_section["Q1"].contradictions == ()
    assert by_section["Q2"].value == "EF" and by_section["Q2"].state == SETTLED and by_section["Q2"].contradictions == ()
    assert [f.source_id for f in Reader(ledger).matches("EF")] == ["Q2"]
    assert [f.source_id for f in Reader(ledger).matches("VAV")] == ["Q1"]


def test_a_provisional_count_a_pass_may_only_add_is_kept_beside_it():
    ledger = seed(_dossier())
    ef = ledger.find("count", "EF")
    apply(pass_named("plans"), ledger, _answer(facts=[
        {"kind": "count", "subject": "EF", "value": 5, "source_id": "[S10]", "quote": "EF-1 … EF-5"}]), _known(ledger))
    after = ledger.facts[ef.id]
    assert after.value == 2 and after.state == CONTRADICTED and after.contradictions[0].value == 5


def test_a_contradiction_from_the_owning_pass_resolves_a_provisional_name():
    ledger = seed(_dossier())
    family = ledger.find("family", "EF")
    refused = apply(pass_named("schedules"), ledger, _answer(contradictions=[
        {"fact_id": family.id, "value": "Exhaust Fan (roof)", "source_id": "[S6]", "quote": "EF (Exhaust Fan)"}]),
        _known(ledger))
    after = ledger.facts[family.id]
    assert refused == []
    assert after.value == "Exhaust Fan (roof)" and after.state == SETTLED and after.contradictions == ()


def test_a_contradiction_from_the_owning_pass_resolves_a_provisional_count():
    ledger = seed(_dossier())
    ef = ledger.find("count", "EF")
    apply(pass_named("schedules"), ledger, _answer(contradictions=[
        {"fact_id": ef.id, "value": 3, "source_id": "[S6]", "quote": "EF (Exhaust Fan)"}]), _known(ledger))
    after = ledger.facts[ef.id]
    assert after.value == 3 and after.state == CONTRADICTED
    assert [(c.value, c.stage) for c in after.contradictions] == [(2, "seed")]
    assert ledger.printed_count(ef.id) == 3


def test_a_contradiction_from_a_pass_that_may_only_add_stays_a_contradiction():
    ledger = seed(_dossier())
    family = ledger.find("family", "EF")
    apply(pass_named("plans"), ledger, _answer(contradictions=[
        {"fact_id": family.id, "value": "Exhaust Fan (roof)", "source_id": "[S6]", "quote": "EF (Exhaust Fan)"}]),
        _known(ledger))
    after = ledger.facts[family.id]
    assert after.value == family.value and after.state == CONTRADICTED and after.contradictions[0].value == "Exhaust Fan (roof)"


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


def test_the_plans_pass_may_settle_a_damper_link():
    ledger = seed(_dossier())
    refused = apply(pass_named("plans"), ledger, _answer(facts=[
        {"kind": "link", "subject": "MD-1", "value": "EF-1", "source_id": "[S10]", "quote": "MD-1 EF-1"}]), _known(ledger))
    assert refused == [] and ledger.find("link", "MD-1").state == SETTLED


# --- counts are numbers, groups are plants, a sequence match names a live system -------------------------------

def test_a_count_given_in_words_keeps_its_leading_number():
    ledger = seed(_dossier())
    ef = ledger.find("count", "EF")
    refused = apply(pass_named("plans"), ledger, _answer(contradictions=[
        {"fact_id": ef.id, "value": "55 placements on the plans", "source_id": "[S10]", "quote": "EF-1 x55"}]),
        _known(ledger))
    after = ledger.facts[ef.id]
    assert refused == []
    assert after.contradictions[0].value == 55 and ledger.printed_count(ef.id) == 55


def test_a_count_with_no_number_is_refused():
    ledger = seed(_dossier())
    ef = ledger.find("count", "EF")
    refused = apply(pass_named("plans"), ledger, _answer(
        facts=[{"kind": "count", "subject": "EF", "value": "many", "source_id": "[S10]", "quote": "EF everywhere"}],
        contradictions=[{"fact_id": ef.id, "value": "lots more", "source_id": "[S10]", "quote": "EF everywhere"}]),
        _known(ledger))
    assert len(refused) == 2
    assert all("a count must be a number; the words go in the quote; left out" in r for r in refused)
    assert ledger.facts[ef.id].contradictions == ()


def test_a_device_count_in_words_keeps_its_number_and_a_device_name_stays_text():
    ledger = seed(_dossier())
    apply(pass_named("plans"), ledger, _answer(facts=[
        {"kind": "device", "subject": "T-STAT", "value": "4 thermostats", "source_id": "[S10]", "quote": "T x4"},
        {"kind": "device", "subject": "keynote 3", "value": "damper actuator by ATC", "source_id": "[S10]", "quote": "KEY NOTES 3"}]),
        _known(ledger))
    assert ledger.find("device", "T-STAT").value == 4
    assert ledger.find("device", "keynote 3").value == "damper actuator by ATC"


def test_the_plans_and_risers_passes_ask_for_whole_number_counts():
    for name in ("plans", "risers"):
        assert "a count's value is a whole number; put the words in the quote" in pass_named(name).instructions


def test_the_risers_pass_asks_for_plants_not_risers():
    words = pass_named("risers").instructions
    assert "never a riser, a shaft or a drain route" in words and "at most five words" in words


def test_a_group_named_in_more_than_six_words_is_refused():
    ledger = seed(_dossier())
    refused = apply(pass_named("risers"), ledger, _answer(facts=[
        {"kind": "group", "subject": "toilet exhaust riser one with branch per floor", "value": "EF, VAV",
         "source_id": "[S10]", "quote": "TX 1"}]), _known(ledger))
    assert len(refused) == 1 and "toilet exhaust riser one" in refused[0] and "left out" in refused[0]
    assert ledger.of_kind("group") == []


def test_a_sequence_match_naming_no_system_is_refused():
    ledger = seed(_dossier())
    ledger.add("group", "Air Plant", "VAV, EF", "[S10]", "AIR PLANT", "risers", SETTLED)
    refused = apply(pass_named("sequence"), ledger, _answer(facts=[
        {"kind": "sequence_match", "subject": "VAV BOXES", "value": "vav", "source_id": "[Q1]", "quote": "VAV BOXES"},
        {"kind": "sequence_match", "subject": "EXHAUST FANS", "value": "AHU", "source_id": "[Q2]", "quote": "EXHAUST FANS"},
        {"kind": "sequence_match", "subject": "PLANT", "value": "Air Plant", "source_id": "[Q2]", "quote": "PLANT"},
        {"kind": "sequence_match", "subject": "OTHER", "value": "", "source_id": "[Q2]", "quote": "OTHER"}]),
        _known(ledger))
    assert refused == ["sequence_match EXHAUST FANS = AHU names no system the ledger holds; left out"]
    assert ledger.find("sequence_match", "VAV BOXES").value == "vav"
    assert ledger.find("sequence_match", "PLANT").value == "Air Plant"


def test_the_sequence_prompt_lists_the_match_values_and_asks_for_general_rules():
    ledger = seed(_dossier())
    ledger.add("group", "Air Plant", "VAV, EF", "[S10]", "AIR PLANT", "risers", SETTLED)
    text = prompt(pass_named("sequence"), ledger, "[S2] Each VAV box")
    assert "Match values you may use: VAV, EF, T, Air Plant" in text
    assert ('notes with subject "general" for rules the sequence sets for the whole job (fire/smoke damper control, '
            'who wires non-FSD actuators, global points)') in text
    assert "Match values you may use" not in prompt(pass_named("plans"), ledger, "[S8] OCC")


def test_a_sequence_match_must_equal_a_live_name_not_merely_contain_it():
    ledger = seed(_dossier())
    refused = apply(pass_named("sequence"), ledger, _answer(facts=[
        {"kind": "sequence_match", "subject": "VAV BOXES", "value": "VAV-1 boxes", "source_id": "[Q1]", "quote": "VAV BOXES"},
        {"kind": "sequence_match", "subject": "OTHER", "value": "vav", "source_id": "[Q1]", "quote": "OTHER"}]),
        _known(ledger))
    assert refused == ["sequence_match VAV BOXES = VAV-1 boxes names no system the ledger holds; left out"]
    assert ledger.find("sequence_match", "OTHER").value == "vav"


def test_a_float_count_is_read_as_a_whole_number_only_when_whole():
    from estimator.ledger.passes import _value
    assert _value(16.0, "count") == 16 and isinstance(_value(16.0, "count"), int)
    assert _value(16.5, "count") is None


def test_the_sequence_pass_adds_a_family_for_a_system_no_family_covers():
    text = pass_named("sequence").instructions
    assert ("When a section gives the BMS work on a system that no family in the live list covers (plumbing pumps, "
            "domestic water heaters, heat tracing, a gas booster, glycol feed, a generator), add a family fact for it "
            "(kind and name, with a short subject; no count fact), citing the section; add a count fact only when "
            "the section itself states one, quoting it." in text)


def test_plans_and_risers_ask_for_short_names_and_a_note_for_the_reasons():
    for name in ("plans", "risers"):
        pass_ = pass_named(name)
        assert "short kind name" in pass_.instructions and "note fact" in pass_.instructions
        assert ("the family's prefix as the note's subject (never \"question\" or \"general\")"
                in pass_.instructions)
        assert "note" in pass_.kinds


def test_an_id_only_written_in_document_text_is_refused_not_a_crash():
    """A bracketed id inside a document's own words ("per detail [M5]") is in the prompt but is not a source the
    ledger holds: an answer citing it is refused, and the ledger is left as it was."""
    ledger = seed(_dossier())
    before = (dict(ledger.facts), dict(ledger.sources))
    refused = apply(pass_named("plans"), ledger, _answer(
        facts=[{"kind": "location", "subject": "VAV", "value": "floor 1", "source_id": "[M5]", "quote": "per detail [M5]"}],
        contradictions=[{"fact_id": "F1", "value": "2", "source_id": "[M5]", "quote": "per detail [M5]"}]),
        _known(ledger) | {"M5"})
    assert len(refused) == 2 and all("[M5]" in r for r in refused)
    assert (dict(ledger.facts), dict(ledger.sources)) == before


# --- a 7c line is read by its own (document, page), never by a number parsed from the line (LDG-7) --------------

def _built(sheets, pages, documents=(("Drawings/Mech.pdf", "drawings", "base"),), supersessions=()):
    """A dossier built from an invented catalogue, and the catalogue."""
    from pathlib import Path
    from estimator.catalogue.documents import Document
    from estimator.catalogue.overview import SpecOverview
    from estimator.writing.dossier import build_dossier
    job = SimpleNamespace(name="26-9999", root=Path("."),
                          documents=tuple(Document(Path(d), d, kind, rev, 3) for d, kind, rev in documents))
    catalogue = SimpleNamespace(job=job, pages=tuple(pages), sheets=tuple(sheets), sections=(), tags=(),
                                overview=SpecOverview(), bid=None, flags=())
    reading = SimpleNamespace(schedules=(), totals=(), devices=(), typicals=(), notes=(), backbone=(), versions=(),
                              supersessions=tuple(supersessions), inventory=(), legend=(), flags=())
    import tempfile
    return build_dossier(catalogue, reading, Path(tempfile.mkdtemp())), catalogue


def test_the_plans_pass_reads_a_spaced_sheet_number_and_an_unnumbered_plans_sheet():
    from estimator.catalogue.register import PageRecord
    from estimator.catalogue.sheet_types import Sheet
    dwg = "Drawings/Mech.pdf"
    sheets = [Sheet(dwg, 1, "M 201", "SECOND FLOOR PLAN", "Mechanical", ("Plans",)),
              Sheet(dwg, 2, None, "THIRD FLOOR PLAN", "Mechanical", ("Plans",))]
    pages = [PageRecord(dwg, 1, "text", "SECOND FLOOR PLAN KEYED NOTE 2 PROVIDE A LEAK CHIME AT WH-2.", 0, True, ()),
             PageRecord(dwg, 2, "text", "THIRD FLOOR PLAN KEYED NOTE 5 PROVIDE A CO2 SENSOR IN ROOM 301.", 0, True, ())]
    dossier, catalogue = _built(sheets, pages)
    assert "LEAK CHIME AT WH-2" in dossier.text and "CO2 SENSOR IN ROOM 301" in dossier.text   # both 7c lines written
    plans = documents(pass_named("plans"), dossier, catalogue)
    assert "LEAK CHIME AT WH-2" in plans
    assert "CO2 SENSOR IN ROOM 301" in plans


def test_a_tag_list_the_schedules_pass_shortens_keeps_the_seeds_list_beside_it():
    # LDG-4: the seed's tags are the counts line's (scheduled and on the plans); a shorter schedule list must not
    # erase VAV-11 and VAV-12 with no record
    ledger = seed(_dossier())
    unit = ledger.find("unit", "VAV")
    assert unit.state == ADDED and unit.value == "VAV-1 thru 12"
    refused = apply(pass_named("schedules"), ledger, _answer(facts=[
        {"kind": "unit", "subject": "VAV", "value": "VAV-1 thru 10", "source_id": "[S4]", "quote": "VAV-1 thru VAV-10"}]),
        _known(ledger))
    after = ledger.facts[unit.id]
    assert refused == []
    assert after.value == "VAV-1 thru 10" and after.stage == "schedules"
    assert [(c.value, c.source_id, c.stage) for c in after.contradictions] == [("VAV-1 thru 12", unit.source_id, "seed")]
    assert [f.id for f in ledger.of_kind("unit") if f.subject == "VAV"] == [unit.id]   # no second unit fact


# --- a pass that may only add never takes away the "confirm it exists" flag ------------------------------------

def test_a_pass_may_confirm_only_the_kinds_it_settles():
    ledger = seed(_dossier())
    ef = ledger.find("count", "EF")
    assert ef.state == ADDED
    refused = apply(pass_named("spec"), ledger, _answer(confirmations=[ef.id]), _known(ledger))
    assert ledger.facts[ef.id].state == ADDED
    assert refused == [f"the spec pass may not confirm {ef.id}, a count fact; left out"]


def test_a_plans_count_for_a_plan_only_family_keeps_it_plan_only():
    from bms.plan_read import Reader
    from estimator.ledger.to_plan import PLAN_ONLY_WHY, ledger_plan
    ledger = seed(_dossier())
    apply(pass_named("plans"), ledger, _answer(facts=[
        {"kind": "count", "subject": "EF", "value": 3, "source_id": "[S10]", "quote": "EF-1, EF-2, EF-3"}]), _known(ledger))
    assert ledger.find("count", "EF").contradictions          # the other count is still kept beside it
    reader = Reader(ledger)
    assert reader.family(ledger.find("family", "EF")).plan_only
    assert next(s for s in ledger_plan(ledger).systems if s.key == "EF").why.startswith(PLAN_ONLY_WHY)


def test_a_scheduled_count_the_plans_contradict_is_not_plan_only():
    from bms.plan_read import Reader
    from estimator.ledger.to_plan import PLAN_ONLY_WHY, ledger_plan
    ledger = seed(_dossier())
    apply(pass_named("plans"), ledger, _answer(facts=[
        {"kind": "count", "subject": "VAV", "value": 14, "source_id": "[S10]", "quote": "VAV-1 … VAV-14"}]), _known(ledger))
    assert ledger.find("count", "VAV").state == CONTRADICTED
    assert not Reader(ledger).family(ledger.find("family", "VAV")).plan_only
    assert not next(s for s in ledger_plan(ledger).systems if s.key == "VAV").why.startswith(PLAN_ONLY_WHY)
