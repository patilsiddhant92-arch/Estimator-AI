"""FINAL-F: an issued id in a where the writer typed is refused, must_fix and cut wherever it stands, sheet word or
not ("S141, Mechanical.pdf page 3", "Mechanical schedule, S141"); tags, known sheets (K) and honest sheet numbers
("M401", an unissued "C2") still pass. The probes run through the real intake, validator and renderer on one job
(`test_review_final3._verdicts`). Invented fixture only."""
from __future__ import annotations

from bms import ai, run
from bms.citations import WHERE_ADVICE, SourceIds, job_ids, job_sheets, job_tags
from bms.model import Ref
from bms.validate import RULE, validate

from test_review_final3 import SAMPLE, _base, _changed, _job, _verdicts, _with_other_count

REFUSED = ("refused", "must_fix", "cut")
ACCEPTED = ("accepted", "none", "prints")
NO_PLACE = ("accepted", "none", "cut")      # a ledger fact, a picture, the equipment counts: no place by design
FULL_S = "\uff33"
ZW = "\u200b"

# (the where on a device quantity's other count, the token looked for in print, K, a tag, the verdict)
PROBES = [
    # an issued id with no sheet word: the gap FINAL-C and FINAL-E left open
    ("S141, Mechanical.pdf page 3", "S141", (), None, REFUSED),
    ("s141, Mechanical.pdf page 3", "s141", (), None, REFUSED),
    ("S141", "S141", (), None, REFUSED),
    ("S141 Mechanical.pdf page 3", "S141", (), None, REFUSED),
    ("S141; Mechanical.pdf page 3", "S141", (), None, REFUSED),
    ("C101, Civil.pdf page 1", "C101", (), None, REFUSED),
    ("F101, Fire.pdf page 2", "F101", (), None, REFUSED),
    ("S2010, Structural.pdf page 4", "S2010", (), None, REFUSED),
    ("S6, Drawings.pdf page 1", "S6", (), None, REFUSED),                       # the job's own schedule line
    (f"{FULL_S}141, Mechanical.pdf page 3", "S141", (), None, REFUSED),         # full-width S
    ("S\uff11\uff14\uff11, Mechanical.pdf page 3", "S141", (), None, REFUSED),                 # full-width digits
    (f"S{ZW}141, Mechanical.pdf page 3", "S141", (), None, REFUSED),            # zero-width space
    ("Mechanical.pdf page 3, S141", "S141", (), None, REFUSED),                 # the id last
    ("Mechanical schedule S141, Mechanical.pdf page 3", "S141", (), None, REFUSED),
    ("Mechanical schedule, S141", "S141", (), None, REFUSED),                   # widening: a part of its own
    ("S141 and S201, Mechanical.pdf page 3", "S201", (), None, REFUSED),
    ("S141-S145, Mechanical.pdf page 3", "S141", (), None, REFUSED),            # S145 unissued, cited
    ("AHU_S141, Mechanical.pdf page 3", "S141", (), None, REFUSED),             # the net cuts it out of the place
    ("Sheet M401 and S141", "S141", (), None, REFUSED),                         # widening: M401 still the place
    ("Sheet C101 and S141", "S141", ("C101",), None, REFUSED),                  # widening: C101 known, S141 not
    ("Sheet S141, Mechanical.pdf page 3", "S141", (), None, REFUSED),           # the sheet-word case, unchanged
    # honest places: no issued id, a known sheet, a tag
    ("M401, Mechanical.pdf page 3", "M401", (), None, ACCEPTED),
    ("M-101, Mechanical.pdf page 3", "M-101", (), None, ACCEPTED),
    ("M-112.00, Mechanical.pdf page 2", "M-112.00", (), None, ACCEPTED),
    ("Mechanical.pdf page 3, M401", "M401", (), None, ACCEPTED),
    ("Sheet M401, Mechanical.pdf page 3", "M401", (), None, ACCEPTED),
    ("C2, Mechanical.pdf page 3", "C2", (), None, ACCEPTED),                    # unissued, the ledger's sheet form
    ("S141A, Mechanical.pdf page 3", "S141A", (), None, ACCEPTED),              # unissued
    ("S141.5, Structural.pdf page 5", "S141.5", (), None, ACCEPTED),            # a decimal is no id
    ("S141, Mechanical.pdf page 3", "S141", ("S141",), None, ACCEPTED),         # the planner's where copied as is
    ("s141, Mechanical.pdf page 3", "s141", ("S141",), None, ACCEPTED),
    ("C101, Civil.pdf page 1", "C101", (), "C101", ACCEPTED),                   # C101 a real tag of the job
    ("Mechanical schedule, Mechanical.pdf page 3", "Mechanical schedule", (), None, ACCEPTED),
    ("Sheets S201 thru S203, Structural.pdf page 4", "S201", ("S201", "S202", "S203"), None, ACCEPTED),
    # no place by design (copied from the evidence, never refused, nothing printed)
    ("Ledger fact S141", "S141", (), None, NO_PLACE),
    ("S141.png", "S141", (), None, NO_PLACE),
    ("Equipment counts S141", "S141", (), None, NO_PLACE),
]


def test_intake_validator_and_render_agree_on_every_where_probe():
    """One test over the whole table, so it fails on rebuild a3e1b1f through the no-sheet-word rows while every
    disagreement is listed."""
    assert len(PROBES) >= 30
    wrong = [(where, sheets, tag, got, want) for where, token, sheets, tag, want in PROBES
             if (got := _verdicts("where", where, token, sheets, tag)) != want]
    assert wrong == []


def test_where_issued_finds_an_issued_id_wherever_the_where_holds_it():
    ids = SourceIds.of(["S141", "S201", "C101"], ["AHU-1"], ["C101"])
    assert ids.where_issued("S141, Mechanical.pdf page 3") == ["S141"]
    assert ids.where_issued("Mechanical schedule, S141") == ["S141"]
    assert ids.where_issued("S141 and S201, Mechanical.pdf page 3") == ["S141", "S201"]
    assert ids.where_issued(f"{FULL_S}141, Mechanical.pdf page 3") == ["S141"]
    assert ids.where_issued("Sheet C101 and S141") == ["S141"]
    assert ids.where_issued("C101, Civil.pdf page 1") == []                     # known
    assert ids.where_issued("M401, Mechanical.pdf page 3") == []
    assert ids.where_issued("Ledger fact S141") == []


def test_the_refusal_and_the_finding_name_the_id_as_the_place_and_give_a_way_out():
    job = _with_other_count(_job(), "S141, Mechanical.pdf page 3")
    system = job.system("EF")
    written, problems = ai._check_system(system.to_dict(), system, None, frozenset(job_ids(job)), (), (), [],
                                         job_tags(job), job_ids(job), tuple(job_sheets(job)))
    assert written is None
    said = " ".join(p for p in problems if "S141" in p)
    assert "as its place" in said and WHERE_ADVICE in said, said
    findings = [f for f in validate(job, SAMPLE) if f.rule == RULE["ids"] and f.severity == "must_fix"]
    assert any("S141" in f.what and "as its place" in f.what and "document and page" in f.fix
               for f in findings), findings
    assert "document and page" in WHERE_ADVICE          # the way out when the evidence's own where leads with it


def test_a_hand_edited_change_whose_where_leads_with_an_issued_id_gets_the_card():
    base = _base()
    device = base.system("EF").devices[0]
    job, decision = _changed(base, refs=device.refs + (Ref("Q2", "q", "S6, Mechanical.pdf page 3"),))
    assert [(device_id, tokens) for _, device_id, tokens in run._ids_in_changes(job, [decision])] \
        == [("EF.d1", ("S6",))]


def test_where_issued_with_no_sheet_word_stays_linear():
    from timing import grows_linearly
    ids = SourceIds.of([f"S{n}" for n in range(1, 400)], [], [f"S{n}" for n in range(1, 400, 2)])
    assert ids.where_issued("S2 and S3, Drawings.pdf page 1") == ["S2"]
    assert grows_linearly(lambda n: ids.where_issued(", ".join(f"S{k % 399 + 1}" for k in range(n))
                                                     + ", Drawings.pdf page 1"), 2000)
