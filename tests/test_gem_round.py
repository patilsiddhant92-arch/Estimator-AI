"""The GEM round (.superpowers/sdd/2026-09-26-whole-job-writing/gem-round-brief.md): systems are the sequence's
sections, the write step runs the estimator's GEM, and the assembly follows the GEM instead of the trimming rules."""
from __future__ import annotations

import json

from estimator.reading.sequences import POINTS, SEQUENCE
from estimator.writing.dossier import build_dossier, is_section_heading, sections_in
from estimator.writing.whole_job import PLAN_PROMPT, Family, parse_plan, plan_schema
from estimator.writing.style import load_house_style
from test_dossier import SPEC, _backbone, _catalogue, _doc, _job, _page, _reading

STYLE = load_house_style()


# --- Part 1: the dossier marks the sequence's headings --------------------------------------------------------------

def test_a_lettered_or_numbered_title_is_a_section_heading_and_a_sentence_is_not():
    for heading in ("C. DRYER EXHAUST AND MAKE-UP AIR FANS", "1. RTU-1 AND RTU-2", "3.1 AIR HANDLING UNITS",
                    "D. Outdoor Air Fan:", "B. VRF Split System Units.", "A. Energy Recovery Ventilation Unit",
                    "I. Parking Garage Fans and Associated CO Control System",
                    "C. Rooftop Units with Heat Recovery (Heat Recovery where indicated on schedules):"):
        assert is_section_heading(heading), heading
    for sentence in ("A. AHU-1 shall run continuously in the occupied mode.", "4. Warm-up:", "1. DDC points:",
                     "a. Outdoor air temperature", "H. E/P: Electric to pneumatic.", "12. Bill of materials.",
                     "F. Provide surge protection for wiring and all system components.",
                     "A. The BMS contractor to provide the following global points to be available to all ddc "
                     "controllers on the BMS.", "SECTION 23 09 93 - SEQUENCE OF OPERATIONS"):
        assert not is_section_heading(sentence), sentence


DRYER_PAGE = """C. DRYER EXHAUST AND MAKE-UP AIR FANS

1. The dryer exhaust fans DXF-1 and DXF-2 shall run with the dryers.

2. The make-up air fans MUAF-1 and MUAF-2 shall be interlocked with the dryer exhaust fans.

D. EMERGENCY GENERATOR

1. The BMS shall monitor the generator run status and common alarm.
"""


def _sectioned_job():
    catalogue, reading = _job()
    catalogue.job.documents += (_doc("Specs/Seq2.pdf", "specs", 1),)
    catalogue.pages += (_page("Specs/Seq2.pdf", 1, DRYER_PAGE),)
    reading.backbone += (_backbone(SEQUENCE, "23 09 93 SEQUENCE PART 2 (Seq2.pdf, page 1)", "Specs/Seq2.pdf", 1, 1),)
    return catalogue, reading


def test_each_heading_of_the_sequence_starts_a_section_block_with_a_stable_id(tmp_path):
    d = build_dossier(*_sectioned_job(), tmp_path)
    sequence = d.text.split("== 2. SEQUENCE OF OPERATION ==")[1].split("== 3.")[0]
    assert "--- [Q1] 3.1 AIR HANDLING UNITS ---" in sequence
    assert "--- [Q2] 3.2 EXHAUST FANS ---" in sequence
    assert "--- [Q3] C. DRYER EXHAUST AND MAKE-UP AIR FANS ---" in sequence
    assert "--- [Q4] D. EMERGENCY GENERATOR ---" in sequence
    heading, ids = d.sections["Q3"]
    assert heading == "C. DRYER EXHAUST AND MAKE-UP AIR FANS"
    assert len(ids) == 3                                   # the heading's paragraph and the two under it
    texts = [sequence.split(f"[{i}]", 1)[1].split("\n", 1)[0] for i in ids]
    assert "DRYER EXHAUST" in texts[0] and "DXF-1" in texts[1] and "MUAF-1" in texts[2]
    assert all(i.startswith("S") for i in ids)            # every paragraph keeps its own [S..] id
    assert d.sections["Q4"][0] == "D. EMERGENCY GENERATOR" and len(d.sections["Q4"][1]) == 2
    # the section of the first heading holds its paragraphs up to the next heading, and no further
    first = d.sections["Q1"][1]
    assert any("AHU-1 shall run" in sequence.split(f"[{i}]", 1)[1].split("\n", 1)[0] for i in first)
    assert not any("EF-1 and EF-2" in sequence.split(f"[{i}]", 1)[1].split("\n", 1)[0] for i in first)


def test_the_sections_are_read_back_from_the_text(tmp_path):
    d = build_dossier(*_sectioned_job(), tmp_path)
    assert sections_in(d.text) == d.sections
    assert "Q3" in d.sources and "DRYER EXHAUST" in d.sources["Q3"]


def test_a_points_list_with_per_system_headings_gets_sections_too(tmp_path):
    catalogue, reading = _job()
    points = "A. AHU-1 POINTS\n\n1. Supply fan status.\n\n2. Discharge air temperature.\n\nB. EF-1 POINTS\n\n1. Fan status.\n"
    catalogue.pages = tuple(p if (p.document, p.page) != (SPEC, 3) else _page(SPEC, 3, points) for p in catalogue.pages)
    d = build_dossier(catalogue, reading, tmp_path)
    listed = d.text.split("== 3. POINTS LISTS ==")[1].split("== 4.")[0]
    assert "] A. AHU-1 POINTS" in listed
    q = next(k for k, (heading, _) in d.sections.items() if heading == "A. AHU-1 POINTS")
    assert f"--- [{q}] A. AHU-1 POINTS ---" in listed and len(d.sections[q][1]) == 3


def test_a_job_with_no_headings_has_no_sections(tmp_path):
    documents = [_doc(SPEC, "specs", 1)]
    catalogue = _catalogue(documents, [_page(SPEC, 1, "The fans shall run.\n\nThe pumps shall run.")])
    reading = _reading(backbone=[_backbone(SEQUENCE, "SEQ (Specs.pdf, page 1)", SPEC, 1, 1)])
    d = build_dossier(catalogue, reading, tmp_path)
    assert d.sections == {} and "[Q" not in d.text


# --- Part 1: the plan names each system's sequence section and its families ----------------------------------------

def test_the_plan_prompt_makes_one_system_per_sequence_section_with_one_header_per_family():
    for words in ("One system per sequence section.",
                  "A section that describes several equipment families together (dryer exhaust fans and their "
                  "make-up air fans; a fan and its damper; a chiller plant) is ONE system with one header per family.",
                  "Give each system its `Q` id(s), and every equipment family it covers with the family's count.",
                  "A family that no sequence section covers becomes its own system, citing its schedule row or plan "
                  "count."):
        assert words in PLAN_PROMPT, words
    system = plan_schema()["properties"]["systems"]["items"]
    assert {"sequence_section", "families"} <= set(system["required"])
    family = system["properties"]["families"]["items"]
    assert set(family["required"]) == {"header", "tags", "quantity", "quantity_source", "quantity_quote"}


def _dryer_answer(**families):
    fams = families.get("families", [
        {"header": "Dryer Exhaust Fan DXF-1-1, 2", "tags": ["DXF-1-1", "DXF-1-2"], "quantity": 2,
         "quantity_source": "[S5]", "quantity_quote": "DXF-1-1 | DXF-1-2"},
        {"header": "Make-up Air Fan MUAF-1-1, 2", "tags": ["MUAF-1-1", "MUAF-1-2"], "quantity": 2,
         "quantity_source": "[S6]", "quantity_quote": "MUAF-1-1 | MUAF-1-2"}])
    return {"systems": [{
        "key": "DXF-MUAF", "header": "Dryer Exhaust and Make-up Air Fans", "kind": "Exhaust Fan",
        "tags": ["DXF-1-1", "DXF-1-2", "MUAF-1-1", "MUAF-1-2"], "quantity": 2, "quantity_source": "[S5]",
        "quantity_quote": "DXF-1-1 | DXF-1-2", "sequence_sources": ["[S2]"], "schedule_sources": ["[S5]", "[S6]"],
        "group": "", "alternate": "", "exception": "", "why": "One sequence section runs them together.",
        "sequence_section": "[Q3]", "families": fams}],
        "front_end": {"mode": "new-system", "existing_name": "", "lines": [], "notes": [], "sources": []},
        "unresolved": []}


KNOWN = frozenset({"S2", "S5", "S6", "Q3"})


def test_a_system_of_several_families_keeps_its_section_and_each_family_with_its_count():
    plan = parse_plan(_dryer_answer(), "m", STYLE, KNOWN)
    (system,) = plan.systems
    assert system.sequence_section == "Q3"
    assert system.families == (
        Family("Dryer Exhaust Fan DXF-1-1, 2", ("DXF-1-1", "DXF-1-2"), 2, "[S5]", "DXF-1-1 | DXF-1-2"),
        Family("Make-up Air Fan MUAF-1-1, 2", ("MUAF-1-1", "MUAF-1-2"), 2, "[S6]", "MUAF-1-1 | MUAF-1-2"))


def test_a_family_count_with_no_words_stating_it_is_cleared_and_asked_but_the_system_stays():
    answer = _dryer_answer()
    answer["systems"][0]["families"][1]["quantity_quote"] = ""
    plan = parse_plan(answer, "m", STYLE, KNOWN)
    (system,) = plan.systems
    assert system.families[1].quantity is None
    assert any("Make-up Air Fan" in q for q in plan.unresolved)


def test_one_family_is_the_system_itself():
    answer = _dryer_answer(families=[{"header": "Dryer Exhaust Fan DXF-1-1, 2", "tags": ["DXF-1-1", "DXF-1-2"],
                                      "quantity": 2, "quantity_source": "[S5]", "quantity_quote": "DXF-1-1 | DXF-1-2"}])
    (system,) = parse_plan(answer, "m", STYLE, KNOWN).systems
    assert system.families == ()
    assert system.header == "Dryer Exhaust Fan DXF-1-1, 2" and system.tags == ("DXF-1-1", "DXF-1-2")


def test_an_old_plan_answer_without_sections_or_families_still_reads():
    answer = _dryer_answer()
    for key in ("sequence_section", "families"):
        del answer["systems"][0][key]
    (system,) = parse_plan(json.loads(json.dumps(answer)), "m", STYLE, KNOWN).systems
    assert system.sequence_section == "" and system.families == ()
