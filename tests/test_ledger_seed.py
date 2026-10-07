"""The ledger's seed: what the readers already know, before the AI reads a pass."""
from types import SimpleNamespace

from estimator.ledger.facts import ADDED, SETTLED
from estimator.ledger.seed import dossier_sections, seed, sheet_text_lines
from estimator.writing.dossier import Dossier

TEXT = """JOB DOSSIER — 26-9999
Everything controls-relevant.

== 1. JOB ==
[S1] 26-9999 Example HS. Controls: new BACnet system.

== 2. SEQUENCE OF OPERATION ==
--- [Q1] VAV BOXES ---
[S2] Each VAV box shall maintain space temperature.
--- [Q2] EXHAUST FANS ---
[S3] EF-1 shall run with RTU-1.

== 3. POINTS LISTS ==
(No points list found in the documents.)

== 4. SCHEDULES ==
[S4] VAV BOX SCHEDULE (M-601, page 12): VAV-1 | 500 CFM ; VAV-2 | 500 CFM

== 5. EQUIPMENT COUNTS ==
[S5] VAV (Variable Air Volume Box): schedule rows 12; QUANTITY column total 12; distinct tags 12; plan placements 14 (M-201 6, M-202 8); riser —. Tags: VAV-1 thru 12.
[S6] EF (Exhaust Fan): schedule rows 0; QUANTITY column total —; distinct tags 2; plan placements 2 (M-201 2); riser —. Tags: EF-1, EF-2.
[S7] T (type code on a schedule): schedule rows 0; QUANTITY column total —; distinct tags 0; plan placements 0; riser —.

== 6. DEVICES ON PLANS ==
[S8] OCC (Occupancy sensor): 21 in all — M-201 10, M-202 11

== 7. NOTES ==
[S9] M-201 KEY NOTES 3: Provide damper actuator by ATC.
--- 7c PLAN SHEET TEXT ---
(Each sheet's own text.)
[S10] M-201, Drawings.pdf page 3 FIRST FLOOR PLAN: VAV-1 VAV-2 OCC
[S11] M-601, Drawings.pdf page 12 SCHEDULES: VAV BOX SCHEDULE
[S12] Drawings.pdf page 30: no sheet number here

== 8. CONTROLS SPEC HIGHLIGHTS ==
[S13] 23 09 00 1.2: Honeywell WEBs.
"""
SOURCES = {f"S{n}": f"place {n}" for n in range(1, 14)} | {"Q1": "sequence section “VAV BOXES”", "Q2": "sequence section “EXHAUST FANS”"}
FAMILIES = (SimpleNamespace(kind="Variable Air Volume Box", prefix="VAV", scheduled=12, tags="VAV-1 thru 12", flags=()),
            SimpleNamespace(kind="Exhaust Fan", prefix="EF", scheduled=0, tags="EF-1, EF-2", flags=()))
COUNTS = {"VAV": {"schedule_rows": 12, "quantity_column": 12, "plan_placements": 14, "riser": 0, "distinct_tags": 12},
          "EF": {"schedule_rows": 0, "quantity_column": None, "plan_placements": 2, "riser": 0, "distinct_tags": 2},
          "T": {"schedule_rows": 0, "quantity_column": None, "plan_placements": 0, "riser": 0, "distinct_tags": 0}}


def _dossier(**kw):
    values = dict(job_name="26-9999", text=TEXT, images=(), sources=SOURCES, families=FAMILIES, device_totals={"OCC": 21},
                  counts=COUNTS, stats={}, sections={"Q1": ("VAV BOXES", ("S2",)), "Q2": ("EXHAUST FANS", ("S3",))})
    values.update(kw)
    return Dossier(**values)


def test_the_sections_are_split_by_their_headings():
    sections = dossier_sections(TEXT)
    assert sorted(sections) == [1, 2, 3, 4, 5, 6, 7, 8]
    assert sections[5].startswith("== 5. EQUIPMENT COUNTS ==")
    assert "[S7] T" in sections[5] and "[S8] OCC" not in sections[5]


def test_sheet_text_lines_carry_their_sheet_numbers():
    lines = sheet_text_lines(TEXT)
    assert [(sid, number) for sid, number, _ in lines] == [("S10", "M-201"), ("S11", "M-601"), ("S12", "")]
    assert lines[0][2].startswith("[S10] M-201, Drawings.pdf page 3")


def test_a_scheduled_family_seeds_a_settled_family_and_count():
    ledger = seed(_dossier())
    family = ledger.find("family", "VAV")
    count = ledger.find("count", "VAV")
    assert family.value == "Variable Air Volume Box" and family.state == ADDED and family.source_id == "S5"   # the name is the catalogue's guess
    assert family.quote == "VAV (Variable Air Volume Box): schedule rows 12; QUANTITY column total 12; distinct tags 12; plan placements 14 (M-201 6, M-202 8); riser —"
    assert count.value == 12 and count.state == SETTLED and count.stage == "seed"
    assert ledger.find("unit", "VAV").value == "VAV-1 thru 12"


def test_a_plan_only_family_seeds_added_facts_with_the_plan_count():
    ledger = seed(_dossier())
    assert ledger.find("family", "EF").state == ADDED
    count = ledger.find("count", "EF")
    assert count.value == 2 and count.state == ADDED


def test_a_family_with_nothing_counted_gets_no_count_fact():
    ledger = seed(_dossier())
    assert ledger.find("family", "T") is not None
    assert ledger.find("count", "T") is None
    assert ledger.find("unit", "T") is None


def test_devices_and_sequence_headings_are_seeded_as_added():
    ledger = seed(_dossier())
    occ = ledger.find("device", "OCC")
    assert occ.value == 21 and occ.source_id == "S8" and occ.state == ADDED
    heading = ledger.find("sequence_match", "VAV BOXES")
    assert heading.value == "" and heading.source_id == "Q1" and heading.state == ADDED


def test_the_seed_keeps_the_dossier_sources_and_names_the_job():
    ledger = seed(_dossier())
    assert ledger.sources == SOURCES and ledger.job_name == "26-9999"
    assert ledger.understanding == {} and ledger.complete is False


def test_a_family_the_readers_did_not_name_takes_the_kind_from_its_count_line():
    ledger = seed(_dossier(families=()))
    assert ledger.find("family", "VAV").value == "Variable Air Volume Box"
    assert ledger.find("family", "EF").value == "Exhaust Fan"


def test_every_seeded_family_waits_for_the_schedules_pass():
    ledger = seed(_dossier())
    assert {f.subject: f.state for f in ledger.of_kind("family")} == {"VAV": ADDED, "EF": ADDED, "T": ADDED}
    assert ledger.find("count", "VAV").state == SETTLED and ledger.find("count", "EF").state == ADDED


def test_a_counts_line_quote_keeps_sheet_numbers_with_a_period():
    text = TEXT.replace("plan placements 14 (M-201 6, M-202 8)", "plan placements 14 (M-201.00 6; M-202.00 8)")
    family = seed(_dossier(text=text)).find("family", "VAV")
    assert family.quote == ("VAV (Variable Air Volume Box): schedule rows 12; QUANTITY column total 12; distinct tags 12; "
                            "plan placements 14 (M-201.00 6; M-202.00 8); riser —")


def test_a_device_name_with_brackets_is_still_seeded():
    text = TEXT.replace("[S8] OCC (Occupancy sensor): 21 in all — M-201 10, M-202 11",
                        "[S8] TB (Thermostat (by others?)): 21 in all — M-201 10, M-202 11")
    ledger = seed(_dossier(text=text))
    assert [f.value for f in ledger.of_kind("device") if f.subject == "TB"] == [21]
    assert not ledger.refused.get("seed")


def test_a_device_line_that_cannot_be_read_is_recorded_not_dropped():
    text = TEXT.replace("[S8] OCC (Occupancy sensor): 21 in all — M-201 10, M-202 11",
                        "[S8] OCC Occupancy sensor: 21 in all — M-201 10, M-202 11")
    ledger = seed(_dossier(text=text))
    assert not ledger.of_kind("device")
    assert any("[S8]" in note for note in ledger.refused.get("seed", []))


def test_a_full_stop_inside_a_sheet_label_does_not_cut_the_counts_quote():
    from bms.plan_read import counts_clauses
    line = ("[S5] VAV (Variable Air Volume Box): schedule rows 12; QUANTITY column total 12; distinct tags 12; "
            "plan placements 14 (M-101 (Bldg. A.pdf) 6, M-102 8); riser 7. Tags: VAV-1 thru 12.")
    ledger = seed(_dossier(text=TEXT.split("[S5]")[0] + line + "\n" + "\n== 6." + TEXT.split("\n== 6.")[1]))
    fact = next(f for f in ledger.of_kind("count") if f.subject == "VAV")
    assert "riser 7" in fact.quote
    assert ("riser 7", 7) in counts_clauses(fact.quote)
