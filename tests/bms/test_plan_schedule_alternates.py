"""HP 23: a bid alternate named in a schedule's title ("ADD ALTERNATE", "ADD ALT. NO. 2", "DEDUCT ALTERNATE") makes the
families that schedule lists an add or a deduct alternate, as an alternate note of the ledger does (`Reader.alternate`
is the one reading the planner makes of it). The schedule is the one that lists a tag of the family in a row, or that a
fact of the family cites. A note wins over a title; a family on schedules that disagree stays base. Every ledger and
dossier here is invented."""
from __future__ import annotations

import pytest

from estimator.ledger.facts import SETTLED, Ledger
from estimator.writing.dossier import Dossier

from bms.plan import plan_job
from bms.plan_read import _schedules_of, alternate_in

from test_plan import PLAYBOOK, SOURCES, _by_key, _family, _ledger


def _schedules(*blocks, one_column: bool = False) -> str:
    """The dossier's schedule part as `build_dossier` writes it: for each (source id, title, first cells of the rows) the
    title line "[S1] TITLE — M-401, Drawings.pdf page 7 (2 rows)", its column line and one line per row (a schedule of
    one column writes its rows with no "|")."""
    lines, n = ["== 4. SCHEDULES =="], 30
    for sid, title, firsts in blocks:
        lines.append(f"[{sid}] {title} — M-401, Drawings.pdf page 7 ({len(firsts)} rows)")
        lines.append("    Columns: TAG" if one_column else "    Columns: TAG | SERVES")
        for first in firsts:
            n += 1
            lines.append(f"[S{n}] {first}" if one_column else f"[S{n}] {first} | AHU-1")
    return "\n".join(lines) + "\n"


def _dossier(text: str = "", sources=None) -> Dossier:
    return Dossier(job_name="Invented Job", text=text, images=(), sources=dict(sources or SOURCES), families=(),
                   device_totals={}, counts={}, stats={})


def _plan(ledger, text: str = ""):
    return plan_job(ledger, None, _dossier(text), PLAYBOOK)


def _purifiers(title: str):
    """A job whose air purifiers (AP-1, AP-2) are listed by a schedule of this title and whose exhaust fan (EF-1) is on a
    schedule of its own."""
    ledger = _ledger()
    _family(ledger, "AP", "Air Purifier", "AP-1, 2", 2)
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    return _plan(ledger, _schedules(("S40", title, ["AP-1", "AP-2"]), ("S41", "EXHAUST FAN SCHEDULE", ["EF-1"])))


# ---- the words of a title ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("title, kind", [
    ("AIR PURIFIER SCHEDULE (ADD ALTERNATE)", "add"),
    ("ADD ALTERNATE - AIR PURIFIER SCHEDULE", "add"),
    ("AIR PURIFIER SCHEDULE - ADD ALT. NO. 2", "add"),
    ("ADD ALT #1 AIR PURIFIERS", "add"),
    ("ADD ALTERNATE NO. 3: AIR PURIFIERS", "add"),
    ("ADDITIVE ALTERNATE 3 AIR PURIFIER SCHEDULE", "add"),
    ("air purifier schedule (add alternate)", "add"),
    ("AIR PURIFIER SCHEDULE (DEDUCT ALTERNATE)", "deduct"),
    ("DEDUCT ALT. NO. 4 AIR PURIFIERS", "deduct"),
    ("DEDUCTIVE ALTERNATE AIR PURIFIER SCHEDULE", "deduct"),
])
def test_a_title_that_names_a_bid_alternate_says_which(title, kind):
    assert alternate_in(title) == kind


@pytest.mark.parametrize("title", [
    "AIR PURIFIER SCHEDULE", "AIR PURIFIER SCHEDULE (ALTERNATING LEAD / LAG)", "ALTERNATOR SCHEDULE",
    "ADDRESSABLE ALT PANEL SCHEDULE", "AIR PURIFIER SCHEDULE - NO ADD ALTERNATE",
    "AIR PURIFIER SCHEDULE - NOT AN ADD ALTERNATE", "ALTERNATE #1 AIR PURIFIERS",
    "ADD ALTERNATE 1 / DEDUCT ALTERNATE 2 AIR PURIFIERS", "",
])
def test_a_title_that_names_no_one_alternate_says_none(title):
    assert alternate_in(title) == ""


# ---- the plan --------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("title, kind", [
    ("AIR PURIFIER SCHEDULE (ADD ALTERNATE)", "add"),
    ("AIR PURIFIER SCHEDULE - ADD ALT. NO. 2", "add"),
    ("ADD ALTERNATE - AIR PURIFIER SCHEDULE", "add"),
    ("AIR PURIFIER SCHEDULE (DEDUCT ALTERNATE)", "deduct"),
])
def test_the_families_a_schedule_of_an_alternate_title_lists_are_that_alternate(title, kind):
    systems = _by_key(_purifiers(title))
    assert systems["AP"].alternate == kind
    assert systems["EF"].alternate == "base"                     # its own schedule names none


@pytest.mark.parametrize("title", ["AIR PURIFIER SCHEDULE", "AIR PURIFIER SCHEDULE (ALTERNATING LEAD / LAG)",
                                   "AIR PURIFIER SCHEDULE - NO ADD ALTERNATE"])
def test_a_schedule_whose_title_names_no_alternate_leaves_its_families_base(title):
    assert _by_key(_purifiers(title))["AP"].alternate == "base"


def test_a_job_with_no_dossier_text_reads_no_title_and_asks_nothing_new():
    ledger = _ledger()
    _family(ledger, "AP", "Air Purifier", "AP-1, 2", 2)
    job = _plan(ledger)
    assert job.systems[0].alternate == "base" and job.questions == ()


def test_the_schedule_a_fact_of_the_family_cites_is_found_even_when_no_row_names_a_tag():
    sources = {**SOURCES, "S8": "M-401 AIR PURIFIER (ADD ALTERNATE), Drawings.pdf page 7"}
    ledger = Ledger(sources)
    ledger.job_name = "Invented Job"
    ledger.add("front_end", "mode", "new-system", "S4", "provide a new building automation system", "spec", SETTLED)
    _family(ledger, "AP", "Air Purifier", "AP-1, 2", 2, source="S8")
    text = _schedules(("S8", "AIR PURIFIER (ADD ALTERNATE)", ["TYPE A", "TYPE B"]))
    assert _by_key(plan_job(ledger, None, _dossier(text, sources), PLAYBOOK))["AP"].alternate == "add"


def test_a_row_of_the_schedule_that_a_fact_cites_finds_the_schedule_too():
    sources = {**SOURCES, "S31": "AIR PURIFIER (DEDUCT ALTERNATE) row TYPE A, M-401, Drawings.pdf page 7"}
    ledger = Ledger(sources)
    ledger.job_name = "Invented Job"
    ledger.add("front_end", "mode", "new-system", "S4", "provide a new building automation system", "spec", SETTLED)
    _family(ledger, "AP", "Air Purifier", "AP-1, 2", 2, source="S31")
    text = _schedules(("S40", "AIR PURIFIER (DEDUCT ALTERNATE)", ["TYPE A", "TYPE B"]))      # its rows are S31 and S32
    assert _by_key(plan_job(ledger, None, _dossier(text, sources), PLAYBOOK))["AP"].alternate == "deduct"


def test_a_row_of_an_existing_unit_names_its_tag_without_the_mark():
    ledger = _ledger()
    _family(ledger, "AP", "Air Purifier", "AP-1, 2", 2)
    text = _schedules(("S40", "AIR PURIFIER SCHEDULE (ADD ALTERNATE)", ["AP-1 (EXISTING)", "AP-2"]))
    assert _by_key(_plan(ledger, text))["AP"].alternate == "add"


def test_a_tag_written_without_its_dash_on_the_schedule_is_the_same_tag():
    ledger = _ledger()
    _family(ledger, "AP", "Air Purifier", "AP-1, 2", 2)
    text = _schedules(("S40", "AIR PURIFIER SCHEDULE (ADD ALTERNATE)", ["AP1", "AP 2"]))
    assert _by_key(_plan(ledger, text))["AP"].alternate == "add"


def test_a_note_of_the_ledger_wins_over_a_schedule_title():
    ledger = _ledger()
    _family(ledger, "AP", "Air Purifier", "AP-1, 2", 2)
    ledger.add("note", "alternate", "deduct: AP", "S4", "AP as a deduct", "spec", SETTLED)
    text = _schedules(("S40", "AIR PURIFIER SCHEDULE (ADD ALTERNATE)", ["AP-1", "AP-2"]))
    assert _by_key(_plan(ledger, text))["AP"].alternate == "deduct"


def test_a_family_on_a_base_schedule_and_an_alternate_schedule_stays_base():
    """Nothing says which of its units are the alternate, so no part of the base bid is taken out of it."""
    ledger = _ledger()
    _family(ledger, "AP", "Air Purifier", "AP-1, 2", 2)
    text = _schedules(("S40", "AIR PURIFIER SCHEDULE", ["AP-1"]),
                      ("S42", "AIR PURIFIER SCHEDULE - ADD ALTERNATE", ["AP-2"]))
    assert _by_key(_plan(ledger, text))["AP"].alternate == "base"


def test_two_schedules_that_both_name_the_alternate_agree():
    ledger = _ledger()
    _family(ledger, "AP", "Air Purifier", "AP-1, 2", 2)
    text = _schedules(("S40", "AIR PURIFIER SCHEDULE - ADD ALTERNATE", ["AP-1"]),
                      ("S42", "AIR PURIFIER SCHEDULE 2 - ADD ALT. NO. 2", ["AP-2"]))
    assert _by_key(_plan(ledger, text))["AP"].alternate == "add"


def test_a_title_is_read_only_in_the_schedule_part_of_the_dossier():
    ledger = _ledger()
    _family(ledger, "AP", "Air Purifier", "AP-1, 2", 2)
    text = ("== 7. PLAN NOTES ==\n[D7] M-101, Drawings.pdf page 3 ADD ALTERNATE AIR PURIFIER PLAN: AP-1 AP-2\n"
            "== 4. SCHEDULES ==\n[S40] AIR PURIFIER SCHEDULE — M-401, Drawings.pdf page 7 (2 rows)\n"
            "[S41] AP-1 | AHU-1\n")
    assert _by_key(_plan(ledger, text))["AP"].alternate == "base"


@pytest.mark.parametrize("one_column", [False, True])
def test_a_schedule_is_its_title_without_its_id_and_its_rows_in_either_layout(one_column):
    text = _schedules(("S40", "AIR PURIFIER SCHEDULE (ADD ALTERNATE)", ["AP-1", "AP-2 (EXISTING)"]),
                      ("S50", "EXHAUST FAN SCHEDULE", ["EF-1"]), one_column=one_column)
    first, second = _schedules_of(text)
    assert first.title == "AIR PURIFIER SCHEDULE (ADD ALTERNATE)" and first.ids == {"S40", "S31", "S32"}
    assert first.firsts == {"AP1", "AP2"}
    assert second.title == "EXHAUST FAN SCHEDULE" and second.ids == {"S50", "S33"} and second.firsts == {"EF1"}


def test_a_title_with_a_bar_in_it_is_still_a_title_and_never_takes_the_next_schedules_rows():
    text = ("== 4. SCHEDULES ==\n[S40] AIR PURIFIERS | ADD ALTERNATE — M-401, Drawings.pdf page 7 (1 row)\n"
            "[S31] AP-1 | AHU-1\n[S50] EXHAUST FAN SCHEDULE | NORTH — M-402, Drawings.pdf page 8 (1 row)\n"
            "[S32] EF-1 | AHU-2\n")
    first, second = _schedules_of(text)
    assert (first.title, first.firsts) == ("AIR PURIFIERS | ADD ALTERNATE", {"AP1"})
    assert (second.title, second.firsts) == ("EXHAUST FAN SCHEDULE | NORTH", {"EF1"})


@pytest.mark.parametrize("columns", [("TAG",), ("TAG", "SERVES")])
@pytest.mark.parametrize("title, kind", [("AIR PURIFIER SCHEDULE (ADD ALTERNATE)", "add"),
                                         ("DEDUCT ALT. NO. 2 AIR PURIFIERS", "deduct"),
                                         ("AIR PURIFIER SCHEDULE", "base")])
def test_the_rule_reads_the_schedule_lines_the_dossier_builder_writes(tmp_path, title, kind, columns):
    """The line shape `_schedules_of` reads is the one `build_dossier` writes, not only the one these tests invent. The
    family's facts cite the counts line, as the seed's do, so only the rows' tags find its schedule."""
    import sys
    from pathlib import Path

    from bms.plan_read import Reader
    from estimator.reading.schedules import Schedule, ScheduleRow

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from estimator.writing.dossier import build_dossier
    from test_dossier_plan_areas import DWG, _catalogue, _page, _reading, _sheet

    rows = tuple(ScheduleRow(t, {h: (t if h == "TAG" else "AHU-1") for h in columns}, None, None, False)
                 for t in ("AP-1", "AP-2"))
    schedule = Schedule(DWG, 1, "M-601", title, columns, rows, False, (), (), False)
    pages = [_page(DWG, 1, f"{title}\nAP-1\nAP-2")]
    built = build_dossier(_catalogue(pages, [_sheet(1, "M-601", "SCHEDULES", types=("Schedules",))], ["AP-1", "AP-2"]),
                          _reading([schedule]), tmp_path)
    counts_line = next(sid for sid, where in built.sources.items() if where.startswith("equipment counts for AP"))
    assert f"] {title} — M-601, " in built.text                      # the title line the rule reads
    ledger = Ledger(dict(built.sources))
    _family(ledger, "AP", "Air Purifier", "AP-1, 2", 2, source=counts_line)
    assert Reader(ledger, built.sources, built.text).alternate("AP") == kind


# ---- a group, and the blocks the planner gathers by alternate ----------------------------------------------------------

def _vrf(indoor_title: str, outdoor_title: str):
    ledger = _ledger()
    _family(ledger, "AC", "Indoor Unit", "AC-1", 1, source="S5")
    _family(ledger, "ACCU", "Outdoor Unit", "ACCU-1", 1, source="S5")
    ledger.add("group", "VRF-ALT", "AC, ACCU", "S5", "VRF-ALT riser", "risers", SETTLED)
    return _plan(ledger, _schedules(("S40", indoor_title, ["AC-1"]), ("S42", outdoor_title, ["ACCU-1"])))


def test_a_group_whose_families_are_all_on_alternate_schedules_is_that_alternate():
    (vrf,) = _vrf("INDOOR UNIT SCHEDULE - ADD ALTERNATE", "OUTDOOR UNIT SCHEDULE - ADD ALTERNATE").systems
    assert vrf.key == "VRF-ALT" and vrf.alternate == "add"


def test_a_group_with_a_family_on_a_base_schedule_stays_base():
    (vrf,) = _vrf("INDOOR UNIT SCHEDULE - ADD ALTERNATE", "OUTDOOR UNIT SCHEDULE").systems
    assert vrf.alternate == "base"


def test_split_units_on_an_alternate_schedule_are_one_alternate_block_apart_from_the_base_ones():
    ledger = _ledger()
    _family(ledger, "AC", "Indoor Unit", "AC-1", 1)
    _family(ledger, "ACCU", "Outdoor Unit", "ACCU-1", 1)
    _family(ledger, "SS", "Indoor Unit", "SS-1", 1)
    _family(ledger, "CU", "Condensing Unit", "CU-1", 1)
    text = _schedules(("S40", "SPLIT SYSTEM SCHEDULE", ["AC-1", "ACCU-1"]),
                      ("S42", "SPLIT SYSTEM SCHEDULE - ADD ALT. NO. 1", ["SS-1", "CU-1"]))
    base, add = _plan(ledger, text).systems
    assert base.key == "Split System" and base.alternate == "base"
    assert add.key == "Split System (add alternate)" and add.alternate == "add"
    assert [f.tags for f in add.families] == [("SS-1",), ("CU-1",)]
