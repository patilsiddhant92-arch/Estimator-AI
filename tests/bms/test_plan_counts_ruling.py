"""PLAN-1..5 and the estimator's count ruling (2026-10-09): the equipment schedule is the working count; the plans,
risers, sheet text and sheet picture verify it, and any difference is a flag (DISCREPANCY beside a schedule,
CONFLICT where no schedule gives the count) that never raises or lowers the printed count. Every ledger, sheet and
tag here is invented."""
from __future__ import annotations

import dataclasses
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

from estimator.catalogue.tags import label_keys, line_labels, unread_counts
from estimator.ledger.facts import SETTLED
from estimator.writing.dossier import Dossier

from bms import counts
from bms.counts_text import family_pattern, prefix_owners
from bms import evidence
from bms.evidence import count_flag, quantity
from bms.model import CONFLICT, DISCREPANCY, Count, Family, Job, OtherCount, Ref, System
from bms.plan import plan_job
from bms.plan_read import times_form

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pdfs import FILLER, Page, make_pdf  # noqa: E402
from test_counts import FakeVision, _catalogue  # noqa: E402
from test_plan import PLAYBOOK, _family, _ledger, _plan  # noqa: E402

SAMPLE_JOB = Path(__file__).resolve().parent / "fixtures" / "sample_job.json"


def _one_family_job(name: str, tags: tuple[str, ...], count: Count, key: str = "X") -> Job:
    system = System(key=key, name=name, shape="", control="field", families=(Family(name, tags, count),))
    return Job(name="Invented Job", systems=(system,))


# ---- PLAN-1: a typical floor plan's located count is its labels times its floors -------------------------------

def _typical_plan(tmp_path: Path, labels: int = 6, title: str = "TYPICAL FLOOR PLAN - FLOORS 2-10"):
    texts = [(200, 200, FILLER, 10)] + [(150 + 200 * n, 500, "EBB-A", 14) for n in range(labels)]
    pdf = make_pdf(tmp_path / "job" / "Drawings.pdf", Page(1728, 1152, tuple(texts)))
    text = "\n".join(t for _, _, t, _ in texts)
    return _catalogue(pdf, [(1, "M-102", title, text)])


def test_plan1_a_typical_sheet_located_count_is_multiplied_by_its_floors(tmp_path):
    """r8: EBB-A at 6 places on a typical plan of floors 2 to 10, the count unknown: 54 prints, never 6."""
    catalogue = _typical_plan(tmp_path)
    job = _one_family_job("Electric Baseboard", ("EBB-A",), Count(None), key="EBB")
    checked = counts.cross_check(job, catalogue, tmp_path / "cache")
    count = checked.system("EBB").families[0].count
    assert count.value == 54
    assert [r.quote for r in count.sources] == [counts.LOCATED_QUOTE]
    [proof] = counts.proofs_for(tmp_path / "cache", "EBB", "Electric Baseboard")
    assert proof["located_text"] == 54


def test_plan1_one_floor_plan_is_not_multiplied(tmp_path):
    catalogue = _typical_plan(tmp_path, title="FIRST FLOOR PLAN")
    job = _one_family_job("Electric Baseboard", ("EBB-A",), Count(None), key="EBB")
    count = counts.cross_check(job, catalogue, tmp_path / "cache").system("EBB").families[0].count
    assert count.value == 6


def test_plan1_the_located_count_reads_each_sheets_floors():
    pattern = family_pattern(["EBB-A"], prefix_owners([["EBB-A"]]))
    sheet = counts._Sheet(("M.pdf", 3), "M-102", "M-102 picture")
    sheet.labels = Counter({"EBB-A": 6})
    assert counts._located_count([sheet], pattern) == 6
    sheet.floors = frozenset(str(n) for n in range(2, 11))
    assert counts._located_count([sheet], pattern) == 54


# ---- PLAN-2: the picture count counts placements, not distinct tag names -----------------------------------------

def test_plan2_the_picture_count_counts_every_place_a_type_tag_is_drawn():
    """r7: two raster plans, CUH-A at 3 places on each, the count unknown: 6 prints, never 1."""
    tags = ["CUH-A"]
    pattern = family_pattern(tags, prefix_owners([tags]))
    family = Family("Cabinet Unit Heater", tuple(tags), Count(None))
    system = System(key="CUH", name="CUH", shape="", control="field", families=(family,))
    check = counts._Check(Job(name="J", systems=(system,)), None, Path("/nonexistent"), transport=object())
    check.patterns[("CUH", family.name)] = pattern
    sheets = []
    for page in (1, 2):
        sheet = counts._Sheet(("M.pdf", page), f"M-10{page}", f"M-10{page} picture")
        sheet.seen = [("CUH-A", (n * 100, 0, 50, 20)) for n in range(3)]
        sheet.counted = frozenset({pattern})
        sheets.append(sheet)
    new, _ids = check._check_family(system, family, pattern, sheets)
    assert new.families[0].count.value == 6


def test_plan2_count_sheet_keeps_one_box_per_place_and_one_per_tag(tmp_path):
    from PIL import Image
    picture = tmp_path / "p.png"
    Image.new("RGB", (3600, 2400), "white").save(picture)
    seen = [("CUH-A", 100, 100, 80, 30), ("CUH-A", 900, 300, 80, 30), ("CUH-A", 1500, 200, 80, 30),   # in an overlap
            ("CUH-A", 3000, 2000, 80, 30)]
    result = counts.count_sheet(picture, ["CUH-A"], transport=FakeVision(seen))["CUH-A"]
    assert result.value == 1 and len(result.boxes) == 1          # one distinct tag, as the contract says
    assert len(result.places) == 4                               # four places drawn, the overlap's twin folded


def test_plan2_a_unit_tag_seen_twice_on_one_sheet_is_one_unit():
    tags = ["EF-1"]
    pattern = family_pattern(tags, prefix_owners([tags]))
    sheet = counts._Sheet(("M.pdf", 1), "M-101", "M-101 picture")
    sheet.seen = [("EF-1", (0, 0, 10, 10)), ("EF-1", (500, 0, 10, 10))]
    assert counts._seen_count([sheet], pattern) == 1


# ---- PLAN-3: a tag list longer than the schedule's count is a DISCREPANCY, never silently dropped ----------------

def test_plan3_a_longer_unit_tag_list_than_the_schedule_is_a_discrepancy():
    """"VAV-1 thru 5" with a schedule count of 3: 3 prints (the schedule's), 5 is a DISCREPANCY beside it, asked."""
    ledger = _ledger()
    _family(ledger, "VAV", "Variable Air Volume Box", "VAV-1 thru 5", 3)
    job = _plan(ledger)
    family = job.systems[0].families[0]
    assert family.tags == ("VAV-1", "VAV-2", "VAV-3", "VAV-4", "VAV-5")
    assert family.count.value == 3 == family.count.printed() and family.count.basis == "schedule"
    assert [o.value for o in family.count.others] == [5] and family.count.flag() == DISCREPANCY
    [asked] = [q for q in job.questions if "VAV" in q]
    assert asked.startswith("DISCREPANCY") and "3" in asked and "5" in asked
    if hasattr(evidence, "count_rows"):     # the Counts tab is part of the evidence-ui redesign (hark/ref-evidence-ui)
        row = next(r for r in evidence.count_rows(job) if r[1] == family.name)
        assert row[3] == 3 and row[7].startswith("DISCREPANCY: the schedule's 3 prints; 5 per")


def test_plan3_with_no_schedule_the_tag_list_count_prints_flagged():
    ledger = _ledger()
    _family(ledger, "VAV", "Variable Air Volume Box", "VAV-1 thru 5", 3, source="S2", state="added", stage="plans")
    family = _plan(ledger).systems[0].families[0]
    assert family.count.value == 5 and family.count.basis == "highest"
    assert [o.value for o in family.count.others] == [3] and family.count.flag() == CONFLICT


def test_a_duplicate_tag_on_the_schedule_is_a_discrepancy_never_a_silent_count():
    """Quantity rules R7: FCU-7-1 listed twice on the schedule. The schedule's 3 stays the working count, the 2
    distinct tags are a DISCREPANCY beside it, and the planner asks."""
    ledger = _ledger()
    _family(ledger, "FCU", "Fan Coil Unit", "FCU-7-1, FCU-7-1, FCU-7-2", 3)
    job = _plan(ledger)
    family = job.systems[0].families[0]
    assert family.tags == ("FCU-7-1", "FCU-7-2")
    assert family.count.value == 3 and 2 in {o.value for o in family.count.others}
    assert family.count.flag() == DISCREPANCY
    assert any(q.startswith("DISCREPANCY - duplicate tag on the schedule") and "FCU-7-1" in q for q in job.questions)


# ---- PLAN-4 / PLAN-5: stated counts in every common form ------------------------------------------------------------

KEYS = label_keys(["CUH-A", "CUH-B", "VAV-1", "VAV-2X1", "EF-1"])


@pytest.mark.parametrize("text", [
    "CUH-A (TYP. OF 4)", "CUH-A (TYP. OF 4 PLACES)", "CUH-A (TYP. 4)", "CUH-A TYP. (4)", "CUH-A TYP. OF 4",
    "CUH-A, TYP. OF 4", "CUH-A - TYP OF 4", "CUH-A (TYP OF 4) 300W", "CUH-A (4)", "CUH-A (4 PLACES)",
    "CUH-A 4 PLACES", "CUH-A (4 TOTAL)", "CUH-A (4X)", "CUH-A x4", "CUH-A (QTY 4)", "CUH-A QTY 4", "CUH-A QTY. 4",
    "CUH-A(4)", "CUH-Ax4", "4x CUH-A", "4 x CUH-A", "(4) CUH-A", "CUH-A\n(TYP. OF 4)",
])
def test_plan4_5_a_stated_count_is_that_many_places(text):
    assert line_labels(text, KEYS) == Counter({"CUH-A": 4})


@pytest.mark.parametrize("text, expected", [
    ("CUH-A", {"CUH-A": 1}),
    ("CUH-A (TYP. OF 60)", {"CUH-A": 1}),          # over STATED_MOST: one place, said (unread_counts)
    ("CUH-A (QTY 60)", {"CUH-A": 1}),
    ("VAV-2X1", {"VAV-2X1": 1}),                    # a tag with an X in it stays whole
    ("VAV-1 450 CFM", {"VAV-1": 1}),                # a size is no count
    ("CUH-A\nCUH-B", {"CUH-A": 1, "CUH-B": 1}),
    ("TO CUH-A", {}),
    ("2-VAV-1", {"VAV-1": 1}),                      # a dash before a tag is no count (FINAL-N)
])
def test_plan4_5_what_is_no_stated_count_is_read_as_before(text, expected):
    assert dict(line_labels(text, KEYS)) == expected


def test_plan4_an_unread_stated_count_is_listed():
    assert unread_counts("CUH-A (QTY 60)\nCUH-A, TYP. OF FOUR", KEYS) == [
        ("CUH-A", "CUH-A (QTY 60)"), ("CUH-A", "CUH-A, TYP. OF FOUR")]


@pytest.mark.parametrize("text", ["CUH-A (TYP. OF 4 PLACES)", "CUH-A (TYP. 4)", "CUH-A, TYP. OF 4",
                                  "CUH-A (4 TOTAL)", "CUH-A (QTY 4)", "CUH-A QTY. 4", "4x CUH-A", "CUH-A(4)",
                                  "CUH-Ax4"])
def test_plan4_5_the_planner_reads_the_same_forms(text):
    assert times_form(text, ["CUH-A"]) == "CUH-A ×4"


def test_plan4_a_type_family_counts_its_stated_places_on_the_sheets():
    """A schedule of types with no quantity (CUH rows 1): the sheets' stated places are the quantity (R8)."""
    ledger = _ledger()
    _family(ledger, "CUH", "Cabinet Unit Heater", "CUH-A", 1)
    dossier = Dossier(job_name="J", text="[S2] CUH-A (TYP. OF 4 PLACES)\n[S5] CUH-A (QTY 3)\n", images=(),
                      sources={}, families=(), device_totals={}, counts={}, stats={})
    count = plan_job(ledger, None, dossier, PLAYBOOK).systems[0].families[0].count
    assert count.value == 7 and count.basis == "highest"


# ---- the ruling in the cross-check, the evidence and the written lines -------------------------------------------

def test_a_plan_count_never_changes_a_schedules_count(tmp_path):
    texts = ((200, 200, FILLER, 10), (300, 400, "EF-1", 14), (900, 300, "EF-2", 14), (1500, 900, "EF-3", 14),
             (600, 1000, "EF-4", 14), (1580, 1100, "M-101", 30))
    pdf = make_pdf(tmp_path / "job" / "Drawings.pdf", Page(1728, 1152, texts))
    catalogue = _catalogue(pdf, [(1, "M-101", "FIRST FLOOR PLAN", "\n".join(t for _, _, t, _ in texts))])
    schedule = Ref("S3", "EF rows 3", "M-501, Drawings.pdf page 6")
    job = _one_family_job("Exhaust Fan", ("EF-1", "EF-2", "EF-3"), Count(3, (schedule,), basis="schedule"), "EF")
    count = counts.cross_check(job, catalogue, tmp_path / "cache").system("EF").families[0].count
    assert count.value == 3 and count.sources == (schedule,) and count.basis == "schedule"
    assert [(o.value, o.ref.quote) for o in count.others] == [(4, counts.LOCATED_QUOTE)]
    assert count.flag() == DISCREPANCY and quantity(count) == 3
    assert count_flag(count).startswith("DISCREPANCY: the schedule's 3 prints; 4 per M-101")


def test_a_plan_count_that_agrees_confirms_the_schedule(tmp_path):
    texts = ((200, 200, FILLER, 10), (300, 400, "EF-1", 14), (900, 300, "EF-2", 14), (1580, 1100, "M-101", 30))
    pdf = make_pdf(tmp_path / "job" / "Drawings.pdf", Page(1728, 1152, texts))
    catalogue = _catalogue(pdf, [(1, "M-101", "FIRST FLOOR PLAN", "\n".join(t for _, _, t, _ in texts))])
    job = _one_family_job("Exhaust Fan", ("EF-1", "EF-2"), Count(2, (Ref("S3", "EF rows 2", "M-501"),),
                                                                   basis="schedule"), "EF")
    count = counts.cross_check(job, catalogue, tmp_path / "cache").system("EF").families[0].count
    assert count.value == 2 and count.others == () and len(count.sources) == 2 and count_flag(count) is None


def test_printed_is_the_schedules_count_and_the_highest_without_one():
    other = (OtherCount(5, Ref("S5", "x5", "M-601")),)
    assert Count(3, (), other, basis="schedule").printed() == 3
    assert Count(3, (), other).printed() == 5
    assert Count(None, (), other).printed() == 5
    assert Count(None).printed() is None and Count(None).flag() == ""


def test_a_count_round_trips_with_its_basis():
    count = Count(3, (Ref("S3", "q", "w"),), (OtherCount(5, Ref("S5", "q", "w")),), basis="schedule")
    assert Count.from_dict(count.to_dict()) == count and count.to_dict()["basis"] == "schedule"
    assert Count.from_dict({"value": 1, "sources": [], "others": []}).basis == "highest"


def test_a_written_line_counted_from_a_schedules_family_takes_its_basis():
    job = Job.from_dict(json.loads(SAMPLE_JOB.read_text(encoding="utf-8")))
    system = next(s for s in job.systems if s.families and s.devices)
    ref = system.devices[0].refs[0]
    other = OtherCount(5, Ref("C1", "located on the sheet text", "M-101"))
    family = dataclasses.replace(system.families[0], count=Count(3, (ref,), (other,), basis="schedule"))
    # the writer copied the count but left the basis out: the line would print 5
    device = dataclasses.replace(system.devices[0], flag="none", quantity=Count(3, (ref,), (other,)))
    assert device.quantity.printed() == 5
    written = dataclasses.replace(system, devices=(device,), families=(family,))
    fixed = counts.flag_written_devices(written).devices[0]
    assert fixed.quantity.basis == "schedule" and fixed.quantity.printed() == 3 and fixed.flag == "quantity"
