"""T-005b regression tests from an invented copy of the 26-0544 planning defects (NOTES 2026-10-11 rule 4), read
from tests/bms/fixtures/t005b_blocks.json:

- control valves printed as a block of their own: they go under the unit the valve schedule's SERVES column names;
- pumps of two services in one block: one block per service, from the sequence section titles;
- one count question asked many times: once per family on the plan side, one card per family on the review page.
Invented fixtures only."""
from __future__ import annotations

import json
from pathlib import Path

from estimator.ledger.facts import SETTLED, Ledger

from bms import review
from bms.model import Count, Device, Family, FrontEnd, Job, OtherCount, Ref, System
from bms.plan import one_count_question_per_family
from test_t005b_plan_blocks import PLANT, _dossier, _family, _plan

FIXTURE = json.loads((Path(__file__).resolve().parent / "fixtures" / "t005b_blocks.json").read_text("utf-8"))


def _ledger() -> Ledger:
    ledger = Ledger(FIXTURE["sources"])
    ledger.job_name = "Invented Job"
    ledger.add("front_end", "mode", "new-system", "S3", "provide a new building automation system", "spec", SETTLED)
    for u in FIXTURE["units"]:
        _family(ledger, u["prefix"], u["name"], u["tags"], u["count"], source="S2")
    return ledger


def _valve_schedule():
    vs = FIXTURE["valve_schedule"]
    lines = ["== 4. SCHEDULES ==",
             f"[{vs['id']}] {vs['title']} — {vs['sheet']}, Mech.pdf page {vs['page']} ({len(vs['rows'])} rows)",
             "    Columns: " + " | ".join(vs["columns"])]
    sources = {}
    for sid, *cells in vs["rows"]:
        lines.append(f"[{sid}] " + " | ".join(cells))
        sources[sid] = f"{vs['title']} row {cells[0]}, {vs['sheet']}, Mech.pdf page {vs['page']}"
    return _dossier("\n".join(lines), sources)


# ---- control valves under the unit they serve ---------------------------------------------------------------------

def test_fixture_valves_go_under_the_unit_their_schedule_serves_column_names():
    ledger = _ledger()
    v = FIXTURE["valves"]
    _family(ledger, v["prefix"], v["name"], v["tags"], v["count"], source="S1")
    job = _plan(ledger, PLANT, _valve_schedule())
    systems = {s.key: s for s in job.systems}
    assert "CV" not in systems                                      # no block of valves of their own
    for key, tags in FIXTURE["valve_schedule"]["expected"].items():
        valves = next(f for f in systems[key].families if f.name == v["name"])
        assert list(valves.tags) == tags and valves.count.value == len(tags)
    assert not any("CV-3" in q for q in job.questions)


# ---- pumps split by service ---------------------------------------------------------------------------------------

def test_fixture_pumps_split_into_one_block_per_service():
    ledger = _ledger()
    p = FIXTURE["pumps"]
    _family(ledger, p["prefix"], p["name"], p["tags"], p["count"], source="S2")
    for s in p["sequences"]:
        ledger.add("sequence_match", s["title"], p["prefix"], s["id"], s["title"], "sequence", SETTLED)
    job = _plan(ledger, PLANT)
    pumps = {s.name: s for s in job.systems if s.name.endswith("Pump")}
    assert {name: list(s.families[0].tags) for name, s in pumps.items()} == p["expected"]
    chw, hw = pumps["Chilled Water Pump"], pumps["Hot Water Pump"]
    assert (chw.shape, hw.shape) == ("Chilled Water System", "Hot Water System")
    assert [r.source_id for r in chw.sequence_refs] == ["Q1", "Q2"]
    assert [r.source_id for r in hw.sequence_refs] == ["Q3", "Q4"]
    assert not any("P-4" in q for q in job.questions)


# ---- one question per family --------------------------------------------------------------------------------------

def test_fixture_count_questions_on_one_family_are_asked_once():
    questions = FIXTURE["count_questions"]
    merged = one_count_question_per_family(questions)
    assert len(merged) == len(questions) - 1
    ahu = [q for q in merged if q.startswith("Air Handling Unit (AHU)")]
    assert len(ahu) == 1 and ahu[0].count("confirm the count") == 1
    assert "lists 3" in ahu[0] and "13 if every sheet" in ahu[0]           # both reasons kept


def test_fixture_review_page_shows_one_card_for_lines_that_repeat_the_family_count(tmp_path):
    plans = Ref("C1", "plan placements 13", "M118.00, Mech.pdf page 4")
    schedule = Ref("S2", "AHU rows 3", "M622.00, Mech.pdf page 27")
    count = Count(13, (plans,), (OtherCount(3, schedule),))
    devices = tuple(Device(id=f"AHU.d{i}", slot="other_device", name=name, verb="Furnish and Install",
                           furnished_by="AME", installed_by="AME", wired_by="AME", quantity=count, refs=(plans,),
                           flag="quantity")
                    for i, name in enumerate(FIXTURE["repeated_lines"], 1))
    system = System(key="AHU", name="Air Handling Unit", shape="Air Handling Unit", control="field",
                    families=(Family("Air Handling Unit", ("AHU-21", "AHU-22", "AHU-23"), count),), devices=devices)
    job = Job(name="Invented", systems=(system,), front_end=FrontEnd(mode="new-system"))
    questions = review._questions(job, ())
    assert [q.level for q in questions] == ["family"]
    page = review.review_page(job, (), tmp_path).read_text(encoding="utf-8")
    assert page.count('class="qtitle"') == 1
