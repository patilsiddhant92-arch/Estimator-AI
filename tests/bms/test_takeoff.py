"""The takeoff pass (plan 2026-10-11): the invented fixture of `takeoff_fixture` ("Invented Hall", 00-1111) and, from
the next tasks on, `bms.takeoff`. Every name and number here is invented."""
from __future__ import annotations

from pathlib import Path

import takeoff_fixture as fx
from bms.model import FutureItem, SetAside, SheetClass, Unit, json_schema, schema_errors
from bms.plan import plan_job
from bms.playbook import load_playbook
from estimator.ledger.facts import Ledger
from estimator.reading.inventory import placements

PLAYBOOK = load_playbook(Path(__file__).parent / "fixtures" / "sample_playbook")

SHEET_NUMBERS = ["M-601", "M-401", "M-402", "M-403", "M-404", "MD-401", "M-201", "M-202", "MD-201", "M-701"]


def _counts(job) -> dict:
    return {family.name: family.count for system in job.systems for family in system.families}


# ---- the fixture ----------------------------------------------------------------------------------------------

def test_fixture_reproduces_the_defect():
    """Five new air handlers and five exhaust fans are scheduled, and the plan placements, which add up the part
    plans and the demolition plan, count more: the higher count prints, as it did for 26-0544."""
    counts = _counts(plan_job(fx.ledger(), fx.catalogue(), fx.dossier(), PLAYBOOK))
    air, fans = counts["Air Handling Unit"], counts["Exhaust Fan"]
    assert air.value > 5 and fans.value > 5
    # characterisation of the 26-0544 defect: the plan placements print, the schedule count of 5 stays beside them
    assert (air.value, [other.value for other in air.others]) == (16, [5])
    assert (fans.value, [other.value for other in fans.others]) == (16, [5])
    assert (air.sources[0].source_id, air.sources[0].quote) == ("S5", "plan placements 16")
    assert (counts["Energy Recovery Unit"].value, counts["Fan Coil Unit"].value) == (2, 55)   # schedule rows: 1 and 1


def test_fixture_ledger_counts_agree_with_what_the_code_counts_on_the_plans():
    """The "plan placements" of each count fact's quote are what `placements` gives on the fixture's own sheets, so
    the five fixture files cannot drift apart."""
    catalogue, ledger = fx.catalogue(), fx.ledger()
    for prefix, tags, said in (("AHU", [f"AHU-{n}" for n in range(1, 6)], 16),
                               ("EF", [f"EF-{n}" for n in range(1, 6)], 16), ("ERU", ["ERU-1"], 2),
                               ("FCU", ["FCU-1"], 55)):
        assert sum(found.count for found in placements(catalogue, tags).values()) == said, prefix
        assert f"plan placements {said} (" in ledger.find("count", prefix).quote
    assert [ledger.find("count", p).value for p in ("AHU", "EF", "ERU", "FCU")] == [5, 5, 1, 1]


def test_fixture_has_the_ten_sheets_and_every_label_but_t():
    catalogue = fx.catalogue()
    assert [s.number for s in catalogue.sheets] == SHEET_NUMBERS
    assert [s.page for s in catalogue.sheets] == list(range(1, 11))
    assert {s.document for s in catalogue.sheets} == {"Mech.pdf"}
    assert {s.number: s.types for s in catalogue.sheets}["MD-401"] == ("Plans", "Demolition")
    assert [p.page for p in catalogue.pages] == list(range(1, 11))
    assert [t.tag for t in catalogue.tags] == [*(f"AHU-{n}" for n in range(1, 7)), *(f"EF-{n}" for n in range(1, 7)),
                                              "ERU-1", "FCU-1"]
    text = {s["number"]: s["text"].splitlines() for s in fx.sheets()}
    assert text["M-201"].count("FCU-1") == 25 and text["M-201"].count("T") == 14
    assert text["M-202"].count("FCU-1") == 30 and text["M-202"].count("T") == 16 and text["MD-201"] == ["T"] * 9
    assert "(D)AHU-6" in text["MD-401"] and "(D)EF-6" in text["MD-401"]


def test_fixture_reading_holds_the_schedules_the_thermostats_and_the_keynote():
    reading = fx.reading()
    assert [(s.sheet, s.title, [row.tag for row in s.rows]) for s in reading.schedules] == [
        ("M-601", "AIR HANDLING UNIT SCHEDULE", [f"AHU-{n}" for n in range(1, 6)]),
        ("M-601", "EXHAUST FAN SCHEDULE", [f"EF-{n}" for n in range(1, 6)]),
        ("M-601", "ENERGY RECOVERY UNIT SCHEDULE", ["ERU-1"]),
        ("M-601", "FAN COIL UNIT SCHEDULE", ["FCU-1"])]
    assert reading.schedules[3].rows[0].cells["QTY"] == ""                       # a blank QUANTITY: a typical unit
    assert [(d.sheet, d.page, d.label, d.device, d.count) for d in reading.devices] == [
        ("M-201", 7, "T", "Thermostat", 14), ("M-202", 8, "T", "Thermostat", 16), ("MD-201", 9, "T", "Thermostat", 9)]
    (note,) = reading.notes
    assert (note.sheet, note.text, note.controls) == ("MD-401", "EXISTING AHU-6 AND EF-6 TO BE REMOVED", False)
    assert reading.typicals == () and reading.totals == ()


def test_fixture_ledger_and_dossier_agree():
    ledger, dossier = fx.ledger(), fx.dossier()
    assert ledger.complete and ledger.job_name == dossier.job_name == "Invented Hall"
    assert Ledger.from_dict(ledger.to_dict()).to_dict() == ledger.to_dict()
    assert dossier.sources == ledger.sources
    assert sorted(dossier.sheet_pages.values()) == [("Mech.pdf", n) for n in range(1, 11)]   # one 7c id per sheet
    assert all(ledger.sources[sid].endswith("(sheet text)") for sid in dossier.sheet_pages)
    assert all(ledger.knows(fact.source_id) for fact in ledger.facts.values())
    assert set(ledger.understanding) == {"plans"} and "five new air handlers" in ledger.understanding["plans"]
    assert [f.subject for f in ledger.of_kind("note")] == ["AHU", "FCU", "question"]


def test_fixture_answer_is_the_register_of_this_job():
    answer, ledger = fx.answer(), fx.ledger()
    assert set(answer) == {"sheets", "units", "set_aside", "future_items", "questions"}
    sheets = [SheetClass.from_dict(s) for s in answer["sheets"]]
    units = [Unit.from_dict(u) for u in answer["units"]]
    assert [s.number for s in sheets] == SHEET_NUMBERS and len(units) == 14
    assert {s.number: s.area for s in sheets} == {
        "M-601": "", "M-401": "Attic", "M-402": "Attic", "M-403": "Attic", "M-404": "Attic", "MD-401": "Attic",
        "M-201": "Level 1", "M-202": "Level 2", "MD-201": "Level 1", "M-701": ""}
    assert [s.number for s in sheets if s.counts_units] == ["M-401", "M-402", "M-403", "M-404", "M-201", "M-202"]
    assert {s.number for s in sheets if s.kind == "demolition"} == {"MD-401", "MD-201"}
    by_tag = {u.tag: u for u in units}
    assert [by_tag[f"AHU-{n}"].status for n in range(1, 7)] == ["new"] * 5 + ["demolish"]
    assert [by_tag[f"EF-{n}"].status for n in range(1, 7)] == ["new"] * 5 + ["demolish"]
    assert (by_tag["ERU-1"].status, by_tag["FCU-1"].status, by_tag["FCU-1"].count) == ("new", "new", 55)
    assert answer["set_aside"] == [] and answer["questions"] == []
    (future,) = [FutureItem.from_dict(x) for x in answer["future_items"]]
    assert (future.family, future.item) == ("AHU", "outside airflow measuring station")
    # every unit and the future item cite a ledger fact by its id, in that fact's own words
    for ref in [r for u in units for r in u.refs] + list(future.refs):
        fact = ledger.facts[ref.source_id]
        assert ref.quote in f"{fact.quote} {fact.value}", (ref.source_id, ref.quote)
    assert future.refs[0].source_id == ledger.find("note", "question").id
    # the answer fits the schemas the AI's answer is checked against, and no scheduled tag is left without a row
    for key, cls in (("sheets", SheetClass), ("units", Unit), ("set_aside", SetAside), ("future_items", FutureItem)):
        assert all(schema_errors(row, json_schema(cls)) == [] for row in answer[key]), key
    scheduled = {row.tag for schedule in fx.reading().schedules for row in schedule.rows}
    assert scheduled <= set(by_tag)
