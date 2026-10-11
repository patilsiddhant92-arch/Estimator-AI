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

def test_fixture_counts_as_the_code_counts_it_now():
    """Five new air handlers and five exhaust fans are scheduled, each drawn on several plan sheets (the part plans of
    one attic and a demolition plan). A numbered unit tag counts once in the job and the demolition plan is set aside,
    so the plan placements agree with the schedules: 5, 5 and 1. FCU-1, a typical unit drawn 25 times on one floor and
    30 on the next, keeps its 55."""
    counts = _counts(plan_job(fx.ledger(), fx.catalogue(), fx.dossier(), PLAYBOOK))
    # T-005a fixed the per-area overcount of 26-0544; the register pass makes this robust on patterns the rules do
    # not cover
    names = ("Air Handling Unit", "Exhaust Fan", "Energy Recovery Unit", "Fan Coil Unit")
    assert [counts[name].value for name in names] == [5, 5, 1, 55]


def test_fixture_ledger_counts_agree_with_what_the_code_counts_on_the_plans():
    """The "plan placements" of each count fact's quote are what `placements` gives on the fixture's own sheets, so
    the five fixture files cannot drift apart."""
    catalogue, ledger = fx.catalogue(), fx.ledger()
    for prefix, tags, said in (("AHU", [f"AHU-{n}" for n in range(1, 6)], 5),
                               ("EF", [f"EF-{n}" for n in range(1, 6)], 5), ("ERU", ["ERU-1"], 1),
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


# ---- Task 1.3: bms.takeoff ------------------------------------------------------------------------------------------

import copy  # noqa: E402
import dataclasses  # noqa: E402
import json  # noqa: E402

import pytest  # noqa: E402

from bms import ai, takeoff  # noqa: E402
from bms.model import Job  # noqa: E402


class FakeTransport:
    """Answers from a queue, as `tests/bms/test_ai.py`'s does; records every question."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.asked: list[dict] = []
        self.waiting = 0
        self.last_error = None

    def ask(self, kind, name, instructions, system_prompt, prompt, schema, extra=None, images=()):
        self.asked.append(dict(kind=kind, name=name, instructions=instructions, system_prompt=system_prompt,
                               prompt=prompt, schema=schema, extra=extra, images=tuple(images)))
        if not self.answers:
            raise ai.NoAnswer("no answer queued", waiting=True)
        return copy.deepcopy(self.answers.pop(0))


def _take_off(*answers):
    transport = FakeTransport(*answers)
    result = takeoff.take_off(fx.ledger(), fx.catalogue(), fx.reading(), fx.dossier(), PLAYBOOK, transport)
    return result, transport


def _check(answer):
    return takeoff.check_answer(answer, fx.ledger(), fx.catalogue(), fx.reading(), ai.evidence_index(fx.dossier()))


def test_the_request_carries_the_whole_job():
    _, transport = _take_off(fx.answer())
    (asked,) = transport.asked
    assert asked["kind"] == "takeoff_job" == takeoff.TAKEOFF_JOB and asked["extra"] == {"step": "takeoff"}
    assert asked["instructions"] == PLAYBOOK.rules_text
    prompt_file = Path(takeoff.__file__).parent / "prompts" / "takeoff_job.md"
    assert asked["system_prompt"] == prompt_file.read_text(encoding="utf-8").strip()
    assert asked["schema"] == takeoff.answer_schema() and asked["images"] == ()
    text, ledger = asked["prompt"], fx.ledger()
    assert all(fact.line() in text for fact in ledger.facts.values())
    assert all(paragraph in text for paragraph in ledger.understanding.values())
    assert "- plans: The plans show five new air handlers" in text
    sheet_lines = [line for line in text.splitlines() if line.startswith("Mech.pdf | page ")]
    assert [line.split(" | ")[2] for line in sheet_lines] == SHEET_NUMBERS
    assert ("Mech.pdf | page 6 | MD-401 | MECHANICAL DEMOLITION DUCTWORK ATTIC PLAN | code guess: Plans, Demolition | "
            "text: S15 | labels: ") in text
    md401 = next(line for line in sheet_lines if "| MD-401 |" in line)
    # the code's own tally, as it is: "(D)AHU-6" is no label `line_labels` reads, so the AI sees it only in the notes
    assert "AHU-1 x1" in md401 and "EF-5 x1" in md401 and "AHU-6" not in md401
    assert next(line for line in sheet_lines if "| MD-201 |" in line).endswith("labels: none")
    m201 = next(line for line in sheet_lines if "| M-201 |" in line)
    assert m201.endswith("labels: FCU-1 x25") and "code guess: Plans" in m201
    assert "code guess: Control diagrams" in next(line for line in sheet_lines if "| M-701 |" in line)
    for n in range(1, 6):                                            # the M-601 rows
        assert f"AHU-{n}: TAG=AHU-{n}; " in text and f"EF-{n}: TAG=EF-{n}; " in text
    assert "M-601 FAN COIL UNIT SCHEDULE" in text and "FCU-1: TAG=FCU-1; QTY=; CFM=400" in text
    assert "MD-401 KEY NOTES 1: EXISTING AHU-6 AND EF-6 TO BE REMOVED" in text      # the keynote
    for line in ("M-201 Thermostat (T) 14", "M-202 Thermostat (T) 16", "MD-201 Thermostat (T) 9"):
        assert line in text                                          # the thermostat counts
    headings = ["Ledger facts", "What each reading pass understood", "Sheets", "Schedules", "Notes on the sheets",
                "Sequence sections", "Devices counted on the sheets"]
    at = [text.splitlines().index(f"## {h}") for h in headings]
    assert at == sorted(at)                                          # the sections in the plan's order


def test_the_prompt_is_the_same_twice():
    first = takeoff.prompt(fx.ledger(), fx.catalogue(), fx.reading(), fx.dossier())
    assert first == takeoff.prompt(fx.ledger(), fx.catalogue(), fx.reading(), fx.dossier())


def test_a_prompt_over_the_limit_stops_in_words(monkeypatch):
    monkeypatch.setattr(takeoff, "TAKEOFF_LIMIT", 100)
    with pytest.raises(ValueError, match=r"^Stopped: the takeoff request is too long \(\d+ characters\)"):
        takeoff.prompt(fx.ledger(), fx.catalogue(), fx.reading(), fx.dossier())


def test_the_answer_schema_is_the_five_lists():
    schema = takeoff.answer_schema()
    assert schema["type"] == "object" and schema["additionalProperties"] is False
    assert schema["required"] == ["sheets", "units", "set_aside", "future_items", "questions"]
    assert schema["properties"]["units"] == {"type": "array", "items": json_schema(Unit)}
    assert schema["properties"]["sheets"]["items"] == json_schema(SheetClass)
    assert schema["properties"]["set_aside"]["items"] == json_schema(SetAside)
    assert schema["properties"]["future_items"]["items"] == json_schema(FutureItem)
    assert schema["properties"]["questions"] == {"type": "array", "items": {"type": "string"}}
    assert schema_errors(fx.answer(), schema) == []


def test_a_good_answer_loads():
    result, _ = _take_off(fx.answer())
    assert isinstance(result, takeoff.Takeoff)
    # the base fixture (takeoff/s1, Task 1.2) has 14 units: it carries no pump rows yet (plan Task 1.2, amended)
    assert len(result.sheets) == 10 and len(result.units) == len(fx.answer()["units"]) == 14
    assert all(Unit.from_dict(unit.to_dict()) == unit for unit in result.units)
    assert [s.number for s in result.sheets] == SHEET_NUMBERS
    assert len(result.future_items) == 1 and result.set_aside == () and result.questions == ()


def _unit(answer, tag):
    return next(u for u in answer["units"] if u["tag"] == tag)


def _drop_sheet(a):
    a["sheets"] = [s for s in a["sheets"] if s["number"] != "M-402"]


def _twice_sheet(a):
    a["sheets"].append(copy.deepcopy(a["sheets"][2]))


def _unknown_sheet(a):
    a["sheets"].append({**copy.deepcopy(a["sheets"][1]), "page": 11, "number": "M-999"})


def _no_area(a):
    next(s for s in a["sheets"] if s["number"] == "M-403")["area"] = ""


def _no_row(a):
    a["units"] = [u for u in a["units"] if u["tag"] != "AHU-4"]


def _unknown_id(a):
    _unit(a, "AHU-2")["refs"][0]["source_id"] = "F99"


def _wrong_quote(a):
    _unit(a, "AHU-3")["refs"][0]["quote"] = "AHU-9 is scheduled"


def _demolition_counts(a):
    next(s for s in a["sheets"] if s["number"] == "MD-401")["counts_units"] = True


def _two_rows(a):
    a["units"].append(copy.deepcopy(_unit(a, "EF-2")))


def _serves_nothing(a):
    _unit(a, "EF-3")["serves"] = "AHU-12"


def _set_aside_unknown(a):
    a["set_aside"] = [{"family": "AHU", "value": 16, "reason": "demolition sheet", "note": "16 set aside; 5 stay",
                       "ref": {"source_id": "S77", "quote": "plan placements 16", "where": "nowhere"}}]


@pytest.mark.parametrize("spoil, names", [
    (_drop_sheet, "M-402"), (_twice_sheet, "M-402"), (_unknown_sheet, "M-999"), (_no_area, "M-403"),
    (_no_row, "AHU-4"), (_unknown_id, "F99"), (_wrong_quote, "AHU-9 is scheduled"), (_demolition_counts, "MD-401"),
    (_two_rows, "EF-2"), (_serves_nothing, "AHU-12"), (_set_aside_unknown, "S77")])
def test_an_answer_with_a_problem_is_refused(spoil, names):
    answer = fx.answer()
    spoil(answer)
    value, problems = _check(answer)
    assert value is None and problems
    assert any(names in problem for problem in problems), problems


def test_a_demolition_sheet_that_counts_is_kept_with_a_ref():
    answer = fx.answer()
    sheet = next(s for s in answer["sheets"] if s["number"] == "MD-401")
    sheet.update(counts_units=True, refs=[{"source_id": "F13", "quote": "EXISTING AHU-6 AND EF-6 TO BE REMOVED",
                                           "where": "KEY NOTES 1, MD-401, Mech.pdf page 6"}])
    value, problems = _check(answer)
    assert problems == [] and value is not None


def test_a_schema_error_or_a_model_error_is_refused():
    answer = fx.answer()
    del answer["units"]
    value, problems = _check(answer)
    assert value is None and any("units" in p for p in problems)
    answer = fx.answer()
    _unit(answer, "AHU-1")["refs"] = []                               # a Unit with no ref is a ModelError
    value, problems = _check(answer)
    assert value is None and any("units[0]" in p for p in problems), problems    # AHU-1 is the first unit row


def test_the_schedule_is_the_floor():
    answer = fx.answer()
    _unit(answer, "AHU-5").update(status="demolish", reason="")
    value, problems = _check(answer)
    assert value is None and any("AHU-5" in p for p in problems), problems
    _unit(answer, "AHU-5")["reason"] = "Shown for removal."              # a reason, but only the schedule cited
    value, problems = _check(answer)
    assert value is None and any("AHU-5" in p for p in problems), problems
    _unit(answer, "AHU-5").update(
        reason="Shown for removal by the keynote.",
        refs=[{"source_id": "F13", "quote": "EXISTING AHU-6 AND EF-6 TO BE REMOVED", "where": "MD-401"}])
    value, problems = _check(answer)
    assert problems == [] and next(u for u in value.units if u.tag == "AHU-5").status == "demolish"


def test_a_numeric_quantity_column_is_part_of_the_floor():
    reading = fx.reading()
    fcu = reading.schedules[3]
    row = dataclasses.replace(fcu.rows[0], cells={**fcu.rows[0].cells, "QTY": "60"})
    reading.schedules = (*reading.schedules[:3], dataclasses.replace(fcu, rows=(row,)))
    index = ai.evidence_index(fx.dossier())
    answer = fx.answer()
    _, problems = takeoff.check_answer(answer, fx.ledger(), fx.catalogue(), fx.reading(), index)
    assert problems == []                                            # a blank QTY: the floor is the one row
    _unit(answer, "FCU-1")["reason"] = ""
    value, problems = takeoff.check_answer(answer, fx.ledger(), fx.catalogue(), reading, index)
    assert value is None and any("FCU-1" in p and "60" in p for p in problems), problems
    _unit(answer, "FCU-1")["reason"] = "Five of the scheduled sixty are shown for a later phase."
    value, problems = takeoff.check_answer(answer, fx.ledger(), fx.catalogue(), reading, index)
    assert problems == [] and value is not None


def test_a_refused_answer_raises_no_answer():
    answer = fx.answer()
    _no_row(answer)
    with pytest.raises(ai.NoAnswer):
        _take_off(answer)


def _planned() -> Job:
    return plan_job(fx.ledger(), fx.catalogue(), fx.dossier(), PLAYBOOK)


def test_counts_do_not_change():
    job = _planned()
    register, _ = _take_off(fx.answer())
    attached = takeoff.attach(job, register)
    changed = [f.name for f in dataclasses.fields(Job) if getattr(attached, f.name) != getattr(job, f.name)]
    # set_aside is () in this answer, so it equals the planned job's; no other field changes
    assert changed == ["sheets", "units", "future_items"]
    assert attached.sheets == register.sheets and attached.units == register.units
    assert attached.future_items == register.future_items and attached.set_aside == register.set_aside
    assert _counts(attached) == _counts(job)
    assert attached.systems == job.systems


def test_save_and_load(tmp_path):
    register, _ = _take_off(fx.answer())
    path = tmp_path / "00-1111 Takeoff.json"
    takeoff.save(register, path)
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1
    assert takeoff.load(path) == register


def test_save_leaves_a_file_that_holds_the_same_register(tmp_path, monkeypatch):
    """Every later run reads the same cached answer: the file is not written again (a folder another program holds
    does not stop the run for it)."""
    register, _ = _take_off(fx.answer())
    path = tmp_path / "00-1111 Takeoff.json"
    assert takeoff.save(register, path) is True

    def refuse(*_a):
        raise PermissionError(13, "Access is denied (invented)")
    monkeypatch.setattr(ai.os, "replace", refuse)
    assert takeoff.save(register, path) is False
    other = dataclasses.replace(register, questions=("How many AHU units?",))
    with pytest.raises(PermissionError):
        takeoff.save(other, path)


# ---- Task 1.4: the prompt ---------------------------------------------------------------------------------------------

def test_the_takeoff_prompt_carries_the_amended_ruling_list():
    text = (Path(takeoff.__file__).parent / "prompts" / "takeoff_job.md").read_text(encoding="utf-8")
    rulings = text.split("## The estimator's rulings of 2026-10-11", 1)[1].split("## Plain words", 1)[0]
    numbers = [int(line.split(".", 1)[0]) for line in rulings.splitlines() if line[:1].isdigit()]
    assert numbers == [1, 2, 6, 7, 8, 9, 10, 14, 15, 17, 18]
    assert text.startswith("You are the takeoff reader of a building controls (BMS / DDC) estimate for AME.")
    for heading in ("## Sheets", "## Units", "## Counts set aside", "## Future items", "## Questions", "## Citations"):
        assert heading in text
    # the plan's words, with its examples in “ ”: a straight-quoted capitalised phrase in a prompt is a rule citation
    # (`playbook_lint.prompt_rule_names`), and "Demolition Scope" or "Level 2 east" is no Playbook rule
    assert '"' not in text and "“Demolition Scope”" in text and "(“Attic”, “Level 2 east”)" in text


# ---- Task 1.5: the run tests' answerer --------------------------------------------------------------------------------

def test_the_run_tests_answerer_answers_a_takeoff_request_the_checks_keep():
    _, transport = _take_off(fx.answer())
    answer = fx.takeoff_answer({"prompt": transport.asked[0]["prompt"]})
    value, problems = _check(answer)
    assert problems == [] and len(value.sheets) == 10 and all(s.kind == "new_work" for s in value.sheets)
    assert [u.tag for u in value.units] == [*(f"AHU-{n}" for n in range(1, 6)), *(f"EF-{n}" for n in range(1, 6)),
                                            "ERU-1", "FCU-1"]
    assert {u.refs[0].source_id for u in value.units} == {"F3", "F6", "F9", "F12"}


# ---- Stage 2, Task 2.1: count over admissible sheets ------------------------------------------------------------------

def _register() -> takeoff.Takeoff:
    """The fixture's correct register, as the checks keep it."""
    register, problems = _check(fx.answer())
    assert problems == []
    return register


def _registered_job() -> Job:
    """The fixture planned without the register, then the register put on it (the Stage 1 run order)."""
    return takeoff.attach(_planned(), _register())


def _key(number: str) -> tuple[str, int]:
    return ("Mech.pdf", SHEET_NUMBERS.index(number) + 1)


def test_admissible_pages_are_the_sheets_whose_units_count():
    pages = takeoff.admissible_pages(_registered_job().sheets)
    assert pages == frozenset(_key(n) for n in ("M-401", "M-402", "M-403", "M-404", "M-201", "M-202"))


def test_area_groups_map_the_four_attic_sheets_to_one_group():
    groups = takeoff.area_groups(_registered_job().sheets)
    attic = tuple(_key(n) for n in ("M-401", "M-402", "M-403", "M-404"))
    assert all(groups[key] == attic for key in attic)
    # one area per floor; the demolition sheets and the sheets that are no plan are in no group
    assert groups[_key("M-201")] == (_key("M-201"),) and groups[_key("M-202")] == (_key("M-202"),)
    assert not {_key(n) for n in ("MD-401", "MD-201", "M-601", "M-701")} & set(groups)


def test_placements_over_the_admissible_pages_with_the_area_groups():
    job = _registered_job()
    pages, groups = takeoff.admissible_pages(job.sheets), takeoff.area_groups(job.sheets)
    for prefix, tags, total in (("AHU", [f"AHU-{n}" for n in range(1, 6)], 5),
                                ("EF", [f"EF-{n}" for n in range(1, 6)], 5), ("ERU", ["ERU-1"], 1),
                                ("FCU", ["FCU-1"], 55)):
        found = placements(fx.catalogue(), tags, pages=pages, groups=groups)
        assert sum(p.count for p in found.values()) == total, prefix
        # MD-401 is read nowhere: no plan count, no group, nothing left out from it
        assert all("MD-401" not in p.on_plans and "MD-401" not in p.demolition for p in found.values()), prefix
        assert all("MD-401" not in names for p in found.values() for group in p.same_plan for names in group)


def test_the_groups_keyword_replaces_the_code_s_plan_groups():
    """Given groups, `placements` reads them in place of `plan_groups`: two sheets of one type tag in one given group
    count once (the most of one sheet), not added."""
    job = _registered_job()
    pages = takeoff.admissible_pages(job.sheets)
    one = {_key("M-201"): (_key("M-201"), _key("M-202")), _key("M-202"): (_key("M-201"), _key("M-202"))}
    (found,) = placements(fx.catalogue(), ["FCU-1"], pages=pages, groups=one).values()
    assert found.count == 30
    (found,) = placements(fx.catalogue(), ["FCU-1"], pages=pages, groups={}).values()
    assert found.count == 55
    (found,) = placements(fx.catalogue(), ["FCU-1"], pages=pages).values()
    assert found.count == 55


def test_device_tally_keeps_the_thermostats_of_the_new_work_sheets():
    kept, aside = takeoff.device_tally(fx.reading().devices, _registered_job().sheets, "T")
    assert kept == 30
    (one,) = aside
    assert (one.family, one.value, one.reason) == ("T", 9, "demolition sheet")
    assert one.ref.where == "MD-201, Mech.pdf page 9" and one.ref.quote == "T"
    assert one.note == "9 thermostats on MD-201 set aside (demolition sheet); 30 on the new-work sheets"


def test_device_tally_cites_the_sheet_text_when_the_dossier_gives_it():
    pages = fx.dossier().sheet_pages
    kept, (one,) = takeoff.device_tally(fx.reading().devices, _registered_job().sheets, "T", pages)
    assert kept == 30 and one.ref.source_id == "S18"


def test_device_tally_with_no_register_keeps_every_count():
    kept, aside = takeoff.device_tally(fx.reading().devices, (), "T")
    assert (kept, aside) == (39, [])

