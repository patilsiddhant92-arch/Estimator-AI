"""Bug 4, the count overshoot (bms/counts.py `_located_count`, bms/counts_text.py `family_pattern`):

(a) a unit's tag (one numbered unit, not a type) drawn on several plan sheets that are not one plan group (a riser
    label on every floor, a phase 2 or roof plan reusing the tags) was counted once per sheet, raising the printed
    count. A numbered tag names one unit (`estimator.catalogue.tags.is_type_tag`; rule R1: tagged equipment counts
    from the schedule), so it counts once over the sheets;
(b) a room named after its unit ("AHU-9X", a mechanical room label) matched the family's generic numbered pattern,
    whose numbered part allowed any letter suffix, and was counted as one more AHU. A letter suffix is accepted only
    when the family's own tags carry one.

PROVISIONAL ruling R3: the schedule count wins (a unit tag counts its schedule quantity once over all sheets).
Each positive case has a negative partner that passes before and after the patch. Generic invented tags only."""
from collections import Counter

import pytest

from bms.counts import _located_count, _Sheet
from bms.counts_text import family_pattern, fits, prefix_owners, searcher


def _sheet(n, labels):
    return _Sheet(("Invented.pdf", n), f"X-90{n}, Invented.pdf page {n}", f"X-90{n} whole sheet (picture)",
                  labels=Counter(labels))


def _count(pattern, *sheet_labels, groups=None):
    return _located_count([_sheet(i, l) for i, l in enumerate(sheet_labels, 1)], pattern, groups)


# ---- (a) one unit's tag on several sheets ------------------------------------------------------------------------

ZR = family_pattern(["ZR-7"], {"ZR": 1})
EF = family_pattern(["EF-3"], {"EF": 1})
VAV = family_pattern(["VAV-1", "VAV-2"], {"VAV": 1})


def test_a_riser_label_counted_per_sheet_collapses_to_one():
    assert _count(ZR, {"ZR-7": 1}, {"ZR-7": 1}, {"ZR-7": 1}) == 1


def test_the_same_tag_on_a_phase_plan_and_a_roof_plan_counts_once():
    assert _count(EF, {"EF-3": 1}, {"EF-3": 1}) == 1


def test_a_phase_2_plan_reusing_the_phase_1_tags_counts_each_unit_once():
    assert _count(VAV, {"VAV-1": 1, "VAV-2": 1}, {"VAV-1": 1, "VAV-2": 1}) == 2


def test_the_sheets_in_one_plan_group_still_count_once():          # negative: passes before and after
    groups = {("Invented.pdf", 1): ("g",), ("Invented.pdf", 2): ("g",)}
    assert _count(EF, {"EF-3": 1}, {"EF-3": 1}, groups=groups) == 1


def test_two_different_tags_on_two_sheets_still_count_two():       # negative
    assert _count(VAV, {"VAV-1": 1}, {"VAV-2": 1}) == 2


def test_two_distinct_instance_tags_on_one_sheet_still_count_two():  # negative
    assert _count(VAV, {"VAV-1": 1, "VAV-2": 1}) == 2


def test_a_type_tag_on_two_separate_plans_still_counts_per_plan():  # negative: a type is many units
    ebb = family_pattern(["EBB-A"], {"EBB": 1})
    assert _count(ebb, {"EBB-A": 1}, {"EBB-A": 1}) == 2



# ---- PROVISIONAL ruling R3 (GrokTeam/discussion.md): the schedule count wins ------------------------------------
# A unit tag shown on several plans counts its schedule quantity: once when the schedule lists it once, 2 when the
# schedule says QTY 2. Main-suite CNT-5 (tests/bms/test_counts.py) expects the per-plan-group sum (4) and is
# contradicted on purpose: under R3 its EF-2 counts once, so the located count is 3, the planner's 3.

def _scheduled(pattern, schedule, *sheet_labels):
    return _located_count([_sheet(i, l) for i, l in enumerate(sheet_labels, 1)], pattern, None, schedule)


def test_r3_a_tag_scheduled_qty_2_on_three_plans_counts_2():
    """PROVISIONAL R3: the schedule's QTY 2, not the three plans and not 1."""
    assert _scheduled(EF, {"EF-3": 2}, {"EF-3": 1}, {"EF-3": 1}, {"EF-3": 1}) == 2


def test_r3_a_tag_the_schedule_lists_once_on_three_plans_counts_once():
    """PROVISIONAL R3, negative partner of the QTY 2 case (and of the per-sheet overshoot)."""
    assert _scheduled(EF, {"EF-3": 1}, {"EF-3": 1}, {"EF-3": 1}, {"EF-3": 1}) == 1


def test_r3_a_type_tag_keeps_counting_per_plan_whatever_the_schedule_map_says():
    """PROVISIONAL R3, negative: a type tag (many units) is not a unit tag; its per-plan count is unchanged."""
    ebb = family_pattern(["EBB-A"], {"EBB": 1})
    assert _scheduled(ebb, {"EBB-A": 5}, {"EBB-A": 1}, {"EBB-A": 1}) == 2


def _family(tags, value, quote="EF-3 QTY 2"):
    from bms.model import Count, Family, Ref
    return Family("Exhaust Fan", tuple(tags), Count(value, (Ref("S3", quote, "M-501, Invented.pdf page 6"),)))


def test_r3_a_one_unit_family_s_schedule_quantity_is_its_count():
    """PROVISIONAL R3: where the per-tag quantity comes from (the planner's count of a one-tag family)."""
    family = _family(["EF-3"], 2)
    from bms.counts import schedule_quantities          # proposed (patch 04)
    assert schedule_quantities(family) == {"EF-3": 2}


def test_r3_a_many_unit_family_gives_each_tag_one():
    """PROVISIONAL R3, negative: a total over several tags says nothing per tag (each is 1)."""
    family = _family(["EF-1", "EF-2"], 3, "EF rows 3")
    from bms.counts import schedule_quantities          # proposed (patch 04)
    assert schedule_quantities(family) == {}


def test_r3_a_representative_tag_with_a_total_gives_no_per_tag_quantity():
    """PROVISIONAL R3, negative: "VAV-1" standing for a family of 5 (no stated QTY for VAV-1) is not VAV-1 x 5."""
    family = _family(["VAV-1"], 5, "VAV BOX SCHEDULE")
    from bms.counts import schedule_quantities          # proposed (patch 04)
    assert schedule_quantities(family) == {}


def test_r3_this_check_s_own_located_count_is_no_schedule_quantity():
    """PROVISIONAL R3, negative: a count this check located on the plans is never read back as the schedule's."""
    from bms import counts
    family = _family(["EF-3"], 3, counts.LOCATED_QUOTE)
    from bms.counts import schedule_quantities          # proposed (patch 04)
    assert schedule_quantities(family) == {}


# ---- (b) a room named after its unit -----------------------------------------------------------------------------

OWNERS = prefix_owners([["AHU-1", "AHU-2", "AHU-9"]])
AHU = family_pattern(["AHU-1", "AHU-2", "AHU-9"], OWNERS)


def test_a_room_label_is_not_one_of_the_family_s_tags():
    assert not fits(AHU, "AHU-9X")
    assert not searcher(AHU).search("MECH RM AHU-9X")


def test_a_room_label_on_the_sheet_is_not_counted():
    assert _count(AHU, {"AHU-1": 1, "AHU-2": 1, "AHU-9": 1, "AHU-9X": 1}) == 3


def test_a_scheduled_unit_whose_tag_looks_like_a_room_label_still_counts():   # negative
    pattern = family_pattern(["AHU-9X", "AHU-9Y"], prefix_owners([["AHU-9X", "AHU-9Y"]]))
    assert fits(pattern, "AHU-9X") and fits(pattern, "AHU-9Y")
    assert _count(pattern, {"AHU-9X": 1, "AHU-9Y": 1}) == 2


@pytest.mark.parametrize("tag", ["AHU-1", "AHU-9", "AHU-4", "AHU 12"])
def test_numbered_tags_of_the_family_s_own_prefix_still_fit(tag):            # negative: an unscheduled AHU-4 counts
    assert fits(AHU, tag)


# ---- 1b: new work, existing to remain, existing to be removed (demolition) -----------------------------------------
# A tag is new (counted), existing to remain (not counted as new; its tie-in lines stay where the sequence names it)
# or existing to be removed (out). "(E)" alone means existing, usually to remain: never a demolition mark. Removed is
# "(ER)", "(D)", a REMOVE / EXISTING TO BE REMOVED keynote tied to the tag, or a demolition sheet (DEMOLITION title,
# MD-x / MD### series). Once patch 08 reads the schedule, a tag never counts above its schedule quantity.
# The new names (`tag_state`, `sheet_marks`, `demolition_questions`) are imported inside each test so the rest of
# this file still runs on current code.
from types import SimpleNamespace

AHU = family_pattern(["AHU-9"], {"AHU": 1})
EBB = family_pattern(["EBB-A"], {"EBB": 1})


def _plan(n, labels, number=None, title="FIRST FLOOR MECHANICAL PLAN", marks=None, types=("Plans",)):
    sheet = _sheet(n, labels)
    sheet.sheet = SimpleNamespace(number=number or f"X-90{n}", title=title, types=types)
    if marks:
        sheet.marks = dict(marks)
    return sheet


def _demo(n, labels, number=None, title="FIRST FLOOR DEMOLITION PLAN", marks=None):
    return _plan(n, labels, number or f"X-90{n}", title, marks, types=("Plans", "Demolition"))


def test_1b_1_a_type_tag_on_a_new_plan_and_its_demolition_plan_counts_the_new_plan_only():
    """(1) The same tag on a new-work plan and a demolition plan counts once, from the new-work plan. A type tag is
    used so this is the demolition filter at work, not the R3 once-per-unit rule."""
    sheets = [_plan(1, {"EBB-A": 1}), _demo(2, {"EBB-A": 1})]
    assert _located_count(sheets, EBB) == 1


def test_1b_1_the_md_series_is_a_demolition_sheet_whatever_its_title():
    from bms.counts import demolition_sheet
    assert demolition_sheet(SimpleNamespace(number="MD-101", title="FIRST FLOOR PLAN"))
    assert demolition_sheet(SimpleNamespace(number="MD2", title="SECOND FLOOR"))
    assert not demolition_sheet(SimpleNamespace(number="M-101", title="FIRST FLOOR MECHANICAL PLAN"))  # negative


def test_1b_2_a_tag_only_on_demolition_sheets_counts_0_and_is_asked_about():
    """(2) Only on demolition sheets: 0 new units, and one question naming the tag and the sheet."""
    from bms.counts import demolition_questions
    sheets = [_demo(1, {"AHU-9": 1}, number="MD-101")]
    assert _located_count(sheets, AHU) == 0
    family = _family(["AHU-9"], 1, quote="AHU-9 AIR HANDLING UNIT")
    (ask,) = demolition_questions(family, AHU, sheets)
    assert ask.startswith("AHU-9 appears only on demolition sheet MD-101;"), ask


def test_1b_2_a_d_or_er_prefix_or_a_remove_keynote_marks_the_tag_removed():
    from bms.counts import REMOVED, sheet_marks
    text = "(D) EF-41\n(ER) EF-42\nKEYNOTE 3: EXISTING EF-43 TO BE REMOVED\n(E) EF-44 REMOVE AND CAP DUCT"
    assert sheet_marks(text) == {"EF-41": REMOVED, "EF-42": REMOVED, "EF-43": REMOVED, "EF-44": REMOVED}


def test_1b_er_counts_as_removed():
    """Positive: "(ER)" is existing to be removed, out of the count."""
    from bms.counts import REMOVED, sheet_marks, tag_state
    assert tag_state("(ER) EF-4") == REMOVED
    sheets = [_plan(1, {"EF-4": 1}, marks=sheet_marks("(ER) EF-4"))]
    assert _located_count(sheets, family_pattern(["EF-4"], {"EF": 1})) == 0


def test_1b_negative_e_with_no_remove_keynote_is_existing_to_remain_not_new_not_removed():
    """Negative: "(E) AHU-9" with no remove keynote is existing to remain: not counted as new work, and not dropped
    as removed (no "removed" question; the planner keeps its tie-in lines, guarded below)."""
    from bms.counts import EXISTING, demolition_questions, sheet_marks, tag_state
    assert tag_state("(E) AHU-9") == EXISTING
    assert tag_state("(E) AHU-9", demolition=True) == EXISTING      # on a demolition plan too: (E) is not (ER)
    marks = sheet_marks("(E) AHU-9 TO REMAIN")
    assert marks == {"AHU-9": EXISTING}
    sheets = [_plan(1, {"AHU-9": 1}, marks=marks)]
    assert _located_count(sheets, AHU) == 0
    assert demolition_questions(_family(["AHU-9"], 1, quote="AHU-9 (EXISTING)"), AHU, sheets) == []


def test_1b_negative_a_bare_remove_note_on_a_new_plan_never_drops_a_unit():
    """Negative: "REMOVE AND REPLACE FILTERS" names no existing item going away."""
    from bms.counts import sheet_marks
    assert sheet_marks("KEYNOTE 2: REMOVE AND REPLACE FILTERS AT AHU-9 AFTER STARTUP") == {}


def test_1b_3_existing_to_remain_unit_named_by_the_sequence_keeps_its_system_and_sequence():
    """(3) REGRESSION GUARD (passes on current code): an existing unit the sequence names is still planned with its
    sequence, so the writer keeps its tie-in lines; the demolition filter only takes it out of the new count."""
    from bms.plan import plan_job
    from bms.playbook import load_playbook
    from estimator.ledger.facts import SETTLED, Ledger
    from estimator.writing.dossier import Dossier

    ledger = Ledger({"S3": "X-601, Invented.pdf page 6 (schedule)", "Q1": "sequence section “AHU-9”, Invented.pdf"})
    ledger.job_name = "Invented Job"
    ledger.add("family", "AHU", "Air Handling Unit", "S3", "AHU Air Handling Unit (EXISTING)", "schedules", SETTLED)
    ledger.add("unit", "AHU", "AHU-9", "S3", "Tags: AHU-9 (EXISTING)", "schedules", SETTLED)
    ledger.add("count", "AHU", 1, "S3", "AHU rows 1", "schedules", SETTLED)
    ledger.add("sequence_match", "AHU-9 SEQUENCE OF OPERATION", "AHU", "Q1", "AHU-9 SEQUENCE OF OPERATION",
               "sequence", SETTLED)
    dossier = Dossier(job_name="Invented Job", text="", images=(), sources={}, families=(), device_totals={},
                      counts={}, stats={})
    job = plan_job(ledger, None, dossier, load_playbook())
    (system,) = [s for s in job.systems if any("AHU-9" in f.tags for f in s.families)]
    assert system.sequence_refs


def test_1b_4_three_placements_against_schedule_qty_1_count_1():
    """(4) The schedule cap: a type tag drawn at three places on one plan, scheduled QTY 1, counts 1."""
    sheets = [_plan(1, {"EBB-A": 3})]
    assert _located_count(sheets, EBB, None, {"EBB-A": 1}) == 1


def test_1b_4_negative_a_type_tag_with_no_schedule_quantity_keeps_its_placements():
    """REGRESSION GUARD (negative; passes on current code): no schedule quantity, no cap."""
    assert _located_count([_plan(1, {"EBB-A": 3})], EBB) == 3


def test_1b_5_a_dashed_only_item_no_schedule_lists_is_counted_and_asked_never_dropped():
    """(5) Drawn dashed only (the picture's mark; the sheet text cannot carry line style) and on no schedule: not
    silently dropped. It stays in the count and becomes a question."""
    from bms.counts import UNKNOWN, demolition_questions
    pattern = family_pattern(["EF-9"], {"EF": 1})
    sheets = [_plan(1, {"EF-9": 1}, marks={"EF-9": UNKNOWN})]
    assert _located_count(sheets, pattern) == 1
    (ask,) = demolition_questions(_family(["EF-9"], 1, quote="located on the plans"), pattern, sheets)
    assert ask.startswith("EF-9 appears only drawn dashed, on sheet X-901, and no schedule lists it;"), ask


def test_1b_5_negative_a_dashed_item_the_schedule_lists_is_not_asked():
    from bms.counts import UNKNOWN, demolition_questions
    pattern = family_pattern(["EF-9"], {"EF": 1})
    sheets = [_plan(1, {"EF-9": 1}, marks={"EF-9": UNKNOWN})]
    assert demolition_questions(_family(["EF-9"], 1, quote="EF-9 EXHAUST FAN QTY 1"), pattern, sheets) == []


# ---- follow-ups: the question names the sheet and the reason ------------------------------------------------------

def test_1b_a_removed_question_names_the_sheet_and_the_mark():
    from bms.counts import demolition_questions, mark_reasons, sheet_marks
    text = "(ER) EF-4"
    pattern = family_pattern(["EF-4"], {"EF": 1})
    sheet = _plan(1, {"EF-4": 1}, marks=sheet_marks(text))
    sheet.reasons = mark_reasons(text)
    (ask,) = demolition_questions(_family(["EF-4"], 1, quote="EF-4 EXHAUST FAN"), pattern, [sheet])
    assert ask.startswith('EF-4 appears only as removed: on X-901, marked "(ER)";'), ask


def test_1b_a_removed_question_quotes_the_remove_keynote():
    from bms.counts import demolition_questions, mark_reasons, sheet_marks
    text = "KEYNOTE 3: EXISTING EF-43 TO BE REMOVED"
    pattern = family_pattern(["EF-43"], {"EF": 1})
    sheet = _plan(1, {"EF-43": 1}, marks=sheet_marks(text))
    sheet.reasons = mark_reasons(text)
    (ask,) = demolition_questions(_family(["EF-43"], 1, quote="EF-43 EXHAUST FAN"), pattern, [sheet])
    assert ask.startswith('EF-43 appears only as removed: on X-901, a remove keynote: '
                          '"KEYNOTE 3: EXISTING EF-43 TO BE REMOVED";'), ask


def test_1b_two_demolition_sheets_are_both_named():
    from bms.counts import demolition_questions
    sheets = [_demo(1, {"AHU-9": 1}, number="MD-1"), _demo(2, {"AHU-9": 1}, number="MD-2")]
    (ask,) = demolition_questions(_family(["AHU-9"], 1, quote="AHU-9 AIR HANDLING UNIT"), AHU, sheets)
    assert ask.startswith("AHU-9 appears only on demolition sheets MD-1, MD-2;"), ask


# ---- follow-ups: "MD" and "DEMO" only from the title block --------------------------------------------------------

MDAMP = family_pattern(["MD-1"], {"MD": 1})
NEW_PLAN_TEXT = "FIRST FLOOR MECHANICAL PLAN\nMD-1\nMD-1 MOTORIZED DAMPER, SEE DETAIL 4\nEF-3\nDEMONSTRATION ROOM\nDEMO LAB"


def test_1b_negative_an_md_1_damper_tag_on_a_new_plan_keeps_everything_new_work():
    """Negative: "MD-1" on the plan is a motorized damper's tag, not the sheet number: nothing is marked removed."""
    from bms.counts import demolition_questions, demolition_sheet, sheet_marks
    sheet = _plan(1, {"MD-1": 2, "EF-3": 1}, number="M-101", marks=sheet_marks(NEW_PLAN_TEXT))
    assert sheet.marks == {}
    assert not demolition_sheet(sheet.sheet)
    assert _located_count([sheet], MDAMP) == 1
    assert _located_count([sheet], EF) == 1
    assert demolition_questions(_family(["MD-1"], 1, quote="MD-1 MOTORIZED DAMPER"), MDAMP, [sheet]) == []


def test_1b_negative_md_in_the_title_or_a_longer_number_is_not_the_md_series():
    from bms.counts import demolition_sheet
    assert not demolition_sheet(SimpleNamespace(number="M-101", title="PARTIAL PLAN AT MD-1"))
    assert not demolition_sheet(SimpleNamespace(number="MD-1 MOTORIZED DAMPER", title="FIRST FLOOR PLAN"))
    assert demolition_sheet(SimpleNamespace(number="MD101", title="FIRST FLOOR"))         # positive
    assert demolition_sheet(SimpleNamespace(number="MD-2.1", title="SECOND FLOOR"))       # positive


def test_1b_negative_a_demonstration_room_or_demo_lab_on_a_new_sheet_marks_nothing():
    """Negative: DEMONSTRATION ROOM (a room) and DEMO LAB (a room tag in the plan text, not the title)."""
    from bms.counts import demolition_sheet, sheet_marks
    assert sheet_marks(NEW_PLAN_TEXT) == {}
    assert not demolition_sheet(SimpleNamespace(number="M-102", title="DEMONSTRATION ROOM FIT-OUT PLAN"))
    sheet = _plan(1, {"EF-3": 1}, number="M-102", title="FIRST FLOOR PLAN", marks=sheet_marks(NEW_PLAN_TEXT))
    assert _located_count([sheet], EF) == 1


def test_1b_a_demo_plan_title_still_marks_a_demolition_sheet():
    from bms.counts import demolition_sheet
    assert demolition_sheet(SimpleNamespace(number="M-103", title="DEMO PLAN"))
    assert demolition_sheet(SimpleNamespace(number="M-104", title="SECOND FLOOR DEMOLITION PLAN"))


# ---- follow-ups: the cap reads patch 08's schedule_qty facts (04 and 08 land together) ----------------------------

def _qty_ledger(rows=(), makers=()):
    from estimator.ledger.facts import SETTLED, Ledger
    ledger = Ledger({"S3": "X-601, Invented.pdf page 6 (schedule)"})
    for tag, n in rows:
        ledger.add("schedule_qty", tag, n, "S3", f"{tag} | {n} | ACME AIR", "seed", SETTLED)
    for tag, maker in makers:
        ledger.add("maker", tag, maker, "S3", f"{tag} | {maker}", "seed", SETTLED)
    return ledger


def test_1b_cap_the_schedule_qty_facts_are_read_per_tag():
    from bms.counts import ledger_schedule_quantities
    assert ledger_schedule_quantities(_qty_ledger([("EBB-A", 1), ("AHU-2", 2)])) == {"EBB-A": 1, "AHU-2": 2}


def test_1b_cap_reads_schedule_qty_over_the_count_quote():
    """Three placements of EBB-A, scheduled QTY 1 in its schedule row: 1. The count quote's "QTY 5" is not used
    when the schedule has a qty column."""
    from bms.counts import family_schedule, ledger_schedule_quantities
    scheduled = ledger_schedule_quantities(_qty_ledger([("EBB-A", 1)]))
    family = _family(["EBB-A"], 5, quote="EBB-A QTY 5")
    schedule = family_schedule(family, EBB, scheduled)
    assert schedule == {"EBB-A": 1}
    assert _located_count([_plan(1, {"EBB-A": 3})], EBB, None, schedule) == 1


def test_1b_cap_a_scheduled_unit_tag_counts_its_schedule_qty_once_over_its_plans():
    from bms.counts import family_schedule, ledger_schedule_quantities
    pattern = family_pattern(["AHU-2"], {"AHU": 1})
    scheduled = ledger_schedule_quantities(_qty_ledger([("AHU-2", 2)]))
    schedule = family_schedule(_family(["AHU-2"], 2, quote="AHU-2 AIR HANDLING UNIT"), pattern, scheduled)
    assert _located_count([_plan(1, {"AHU-2": 1}), _plan(2, {"AHU-2": 1}), _plan(3, {"AHU-2": 1})], pattern,
                          None, schedule) == 2


def test_1b_cap_falls_back_to_the_count_quote_when_the_schedule_has_no_qty_column():
    """No qty column: the seed writes no schedule_qty facts (only maker), so the count quote's "QTY 2" is used."""
    from bms.counts import family_schedule, ledger_schedule_quantities
    scheduled = ledger_schedule_quantities(_qty_ledger(makers=[("EF-3", "ACME AIR")]))
    assert scheduled == {}
    schedule = family_schedule(_family(["EF-3"], 2, quote="EF-3 QTY 2"), EF, scheduled)
    assert schedule == {"EF-3": 2}
    assert _located_count([_plan(1, {"EF-3": 1}), _plan(2, {"EF-3": 1})], EF, None, schedule) == 2


def test_1b_cap_the_run_hands_the_ledger_s_quantities_to_the_cross_check():
    """The wiring: `bms.run` calls `cross_check` inside `scheduled_quantities(ledger_schedule_quantities(ledger))`;
    `cross_check` keeps its contract signature (tests/bms/test_contracts.py pins it, and run tests wrap it)."""
    import inspect

    from bms import counts, run
    assert list(inspect.signature(counts.cross_check).parameters) == ["job", "catalogue", "cache", "transport"]
    assert "with scheduled_quantities(ledger_schedule_quantities(ledger)):" in inspect.getsource(run)


def test_1b_cap_cross_check_hands_the_scheduled_quantities_to_the_check(monkeypatch):
    """Inside `scheduled_quantities`, the check is built with them; outside, with none."""
    from bms import counts
    seen = []

    class Spy:
        def __init__(self, *args, scheduled=None, **kwargs):
            self.job = args[0]
            seen.append(scheduled)

        def run(self):
            return self.job

    monkeypatch.setattr(counts, "_Check", Spy)
    with counts.scheduled_quantities({"AHU-2": 2}):
        counts.cross_check("job", None, "/tmp/unused")
    counts.cross_check("job", None, "/tmp/unused")
    assert seen == [{"AHU-2": 2}, None]


# ---- follow-ups: a cap that lowers the count over different new floor plans is asked about -------------------------
# Floor plan vs the rest comes from the catalogue's Sheet (title block): `types` (assets/reading_lists/sheet_types.json
# applied to the title: "Plans", "Details", "Air riser", "Sections and elevations", "Demolition" ...) and the title
# (ENLARGED / PARTIAL / MECHANICAL ROOM ... is an enlarged plan). Invented sheets M-1..M-3, M-501.

FLOORS = ("FIRST FLOOR MECHANICAL PLAN", "SECOND FLOOR MECHANICAL PLAN", "THIRD FLOOR MECHANICAL PLAN")


def test_1b_cap_a_unit_on_three_new_floor_plans_with_qty_1_counts_1_and_is_asked():
    """(a) The same unit on 3 different new floor plans, schedule qty 1: counts 1, and one question."""
    from bms.counts import cap_questions
    sheets = [_plan(i, {"AHU-9": 1}, number=f"M-{i}", title=t) for i, t in enumerate(FLOORS, 1)]
    assert _located_count(sheets, AHU, None, {"AHU-9": 1}) == 1
    (ask,) = cap_questions(AHU, sheets, {"AHU-9": 1})
    assert ask.startswith("AHU-9: 3 new placements on sheets M-1, M-2, M-3; schedule qty 1"), ask


def test_1b_cap_negative_a_floor_plan_and_its_enlarged_mechanical_room_plan_count_1_with_no_question():
    """(b) Negative: a floor plan plus its enlarged mechanical room plan, schedule qty 1: 1, silently."""
    from bms.counts import cap_questions
    sheets = [_plan(1, {"AHU-9": 1}, number="M-1", title=FLOORS[0]),
              _plan(2, {"AHU-9": 1}, number="M-501", title="ENLARGED MECHANICAL ROOM PLAN")]
    assert _located_count(sheets, AHU, None, {"AHU-9": 1}) == 1
    assert cap_questions(AHU, sheets, {"AHU-9": 1}) == []


@pytest.mark.parametrize("title, types", [
    ("MECHANICAL DETAILS", ("Details",)),
    ("AIR RISER DIAGRAM", ("Air riser", "Diagrams")),
    ("BUILDING SECTIONS", ("Sections and elevations",)),
    ("SECOND FLOOR DEMOLITION PLAN", ("Plans", "Demolition")),
    ("PARTIAL SECOND FLOOR PLAN", ("Plans",)),
])
def test_1b_cap_negative_repeats_on_details_risers_sections_demolition_or_partial_plans_are_capped_silently(title, types):
    from bms.counts import cap_questions
    sheets = [_plan(1, {"AHU-9": 1}, number="M-1", title=FLOORS[0]),
              _plan(2, {"AHU-9": 1}, number="M-601", title=title, types=types)]
    assert cap_questions(AHU, sheets, {"AHU-9": 1}) == []


def test_1b_cap_negative_floors_within_the_schedule_qty_are_not_asked():
    from bms.counts import cap_questions
    sheets = [_plan(i, {"AHU-9": 1}, number=f"M-{i}", title=t) for i, t in enumerate(FLOORS[:2], 1)]
    assert cap_questions(AHU, sheets, {"AHU-9": 2}) == []


def test_1b_cap_negative_two_sheets_of_one_plan_group_are_one_floor():
    from bms.counts import cap_questions
    sheets = [_plan(1, {"AHU-9": 1}, number="M-1A", title="FIRST FLOOR MECHANICAL PLAN - PART A"),
              _plan(2, {"AHU-9": 1}, number="M-1B", title="FIRST FLOOR MECHANICAL PLAN - PART B")]
    groups = {sheets[0].key: ("first",), sheets[1].key: ("first",)}
    assert cap_questions(AHU, sheets, {"AHU-9": 1}, groups) == []

