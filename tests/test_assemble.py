"""The whole-job path after the judge: the cross-checks and the assembly, against fakes of the
dossier (Part A) and the judge's plan and scope (Part B)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from types import SimpleNamespace

from estimator.price_sheet.write import check_fit
from estimator.reading.inventory import FamilyTotal, InventoryItem
from estimator.scope import Job
from estimator.writing.judge import TechHoursHint
from estimator.writing.assemble import (assemble_job, check_plan, check_scope, checklist_text, cited_text,
                                        expand_tags, plan_checks, quote_in_dossier, system_evidence, system_images,
                                        template_options, tech_hours)
from estimator.writing.templates import load_templates
from test_front_end import _catalogue as front_end_catalogue, _overview as front_end_overview, \
    _warranty as front_end_warranty

TEMPLATES = load_templates()


# --- the shapes of Parts A and B (docs/superpowers/plans/2026-09-26-whole-job-writing.md) -------------------
# After the merge these become:
#   from estimator.writing.dossier import Dossier, DossierImage
#   from estimator.writing.whole_job import JobPlan, PlannedSystem, WrittenLine, WrittenScope

@dataclass(frozen=True)
class DossierImage:
    path: str
    what: str
    sheet: str | None
    document: str
    page: int


@dataclass(frozen=True)
class Dossier:
    job_name: str
    text: str
    images: tuple = ()
    sources: dict = field(default_factory=dict)
    families: tuple = ()
    device_totals: dict = field(default_factory=dict)
    counts: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PlannedSystem:
    key: str
    header: str
    kind: str
    tags: tuple = ()
    quantity: int | None = None
    quantity_source: str = ""
    quantity_quote: str = ""
    sequence_sources: tuple = ()
    schedule_sources: tuple = ()
    group: str = ""
    alternate: str = ""
    exception: str = ""
    why: str = ""
    facts: tuple = ()
    count_note: str = ""


@dataclass(frozen=True)
class JobPlan:
    systems: tuple
    front_end: dict = field(default_factory=dict)
    unresolved: tuple = ()
    model: str = "fake"
    dropped: tuple = ()


@dataclass(frozen=True)
class WrittenLine:
    text: str
    depth: int = 1
    quantity: int | None = None
    quote: str = ""
    source_id: str = ""
    why: str = ""
    confidence: float = 0.9


@dataclass(frozen=True)
class WrittenScope:
    lines: tuple
    client_notes: tuple = ()
    tech_hours_hint: object = None
    review_notes: tuple = ()
    model: str = "fake"
    refused: tuple = ()
    explanation: str = ""


class FakeJudge:
    """write_system answers from canned objects; counts like the real Judge."""

    def __init__(self, plan, scopes, mode="api"):
        self.plan, self.scopes, self.mode = plan, dict(scopes), mode
        self.asked: list[str] = []
        self.calls = self.cached = self.answered_in_chat = self.waiting = 0
        self.available, self.model, self.last_error = True, "fake-model", None
        self.requests_dir = "requests"
        self.old_requests_dir = "requests/old"
        self.qc_calls = 0

    def retire_requests(self, sources=None):
        return 0

    def stale_requests(self):
        return 0

    def write_system(self, system, evidence_text, images, options, examples, style_text, hours_rule="", image_ids=None,
                     ledger_text="", facts=(), counts=(), brief="", klass="", owned_elsewhere=(), heater_class="",
                     heater_home=("", ""), heater_assignment=("", "")):
        self.asked.append(system.key)
        self.calls += 1
        return self.scopes.get(system.key)

    def qc_job(self, name, system_prompt, prompt, schema, extra=None):
        """A canned QC answer: one ownership must-fix finding on the VAV block's sensor line and one block note."""
        self.qc_calls += 1
        return ({"findings": [{"system": "VAV", "line": "Furnish and Install Space Temperature / CO2 Sensor",
                               "kind": "ownership", "say": "The sensor ships loose with the box; AME installs it.",
                               "fix": "Install and Wire Space Temperature / CO2 Sensor", "severity": "must-fix",
                               "quote": "space temperature and CO2 setpoints"}],
                 "block_notes": [{"system": "VAV", "note": "Nearly right; the sensor's verb is wrong."}],
                 "job_note": "A small job, written in the house shape."}, "fake-model")


# --- a small job ------------------------------------------------------------------------------------------

SEQ_VAV = ("[S1] A. VAV boxes: each VAV box shall maintain the space temperature and CO2 setpoints. "
           "The hot water reheat valve shall modulate to hold the discharge air temperature.")
SEQ_EF = "[S2] B. Exhaust fans EF-1 and EF-2 shall be interlocked with the space line-voltage thermostat."
TEXT = "\n".join([
    "1. Job", "[S9] Job 26-9999, 1 Test Street", "",
    "2. Sequence of operation", SEQ_VAV, "", SEQ_EF, "",
    "4. Schedules", "[S3] M-601 VAV BOX SCHEDULE (see image I1)",
    "[S4] VAV-1 | OFFICE 101 | 600 | HW GPM 1.5", "[S5] VAV-2 | OFFICE 102 | 700 | HW GPM 1.5",
    "[S6] VAV-3 | OFFICE 103 | 500 | HW GPM 1.0", "",
    "[S7] M-602 CABINET UNIT HEATER SCHEDULE: CUH-1 | QUANTITY 12", "",
    "[S8] Provide two fire pumps, each with its own controller.", "",
])
SOURCES = {"S1": "23 09 93 SEQUENCE OF OPERATIONS, Specs.pdf page 44", "S2": "23 09 93, Specs.pdf page 45",
           "S3": "M-601 VAV BOX SCHEDULE, Mech.pdf page 5", "S4": "M-601, VAV-1", "S5": "M-601, VAV-2",
           "S6": "M-601, VAV-3", "S7": "M-602 CABINET UNIT HEATER SCHEDULE", "S9": "the job folder"}
FAMILIES = (FamilyTotal("Variable Air Volume Box", "VAV", 3, "VAV-1 thru VAV-3", ()),
            FamilyTotal("Exhaust Fan", "EF", 2, "EF-1, EF-2", ()),
            FamilyTotal("Cabinet Unit Heater", "CUH", 1, "CUH-1", ()))
COUNTS = {"VAV": {"schedule_rows": 3, "quantity_column": None, "plan_placements": 3, "riser": None, "distinct_tags": 3},
          "EF": {"schedule_rows": 2, "quantity_column": None, "plan_placements": 2, "riser": None, "distinct_tags": 2},
          "CUH": {"schedule_rows": 1, "quantity_column": 12, "plan_placements": 12, "riser": None, "distinct_tags": 1}}
IMAGE = DossierImage("C:/cache/dossier-images/m601.png", "M-601 VAV BOX SCHEDULE — picture schedule", "M-601",
                     "Mech.pdf", 5)


def _dossier(**kw):
    values = dict(job_name="26-9999", text=TEXT, images=(IMAGE,), sources=SOURCES, families=FAMILIES,
                  device_totals={"T": 3}, counts=COUNTS, stats={})
    values.update(kw)
    return Dossier(**values)


def _vav(**kw):
    values = dict(key="VAV", header="Variable Air Volume Box VAV-1 thru 3", kind="Variable Air Volume Box",
                  tags=("VAV-1", "VAV-2", "VAV-3"), quantity=3, quantity_source="[S3]",
                  quantity_quote="VAV-1 | OFFICE 101", sequence_sources=("S1",), schedule_sources=("S3", "S4"),
                  why="three rows on the VAV schedule")
    values.update(kw)
    return PlannedSystem(**values)


def _ef(**kw):
    values = dict(key="EF", header="Exhaust Fan EF-1, 2", kind="Exhaust Fan", tags=("EF-1", "EF-2"), quantity=2,
                  quantity_source="S2", quantity_quote="Exhaust fans EF-1 and EF-2", sequence_sources=("S2",))
    values.update(kw)
    return PlannedSystem(**values)


def _cuh(**kw):
    values = dict(key="CUH", header="Cabinet Unit Heater CUH-1", kind="Cabinet Unit Heater", tags=("CUH-1",),
                  quantity=12, quantity_source="S7", quantity_quote="CUH-1 | QUANTITY 12", schedule_sources=("S7",))
    values.update(kw)
    return PlannedSystem(**values)


READING = type("Reading", (), {"inventory": ()})()


def _check(system, dossier=None):
    [check], _ = plan_checks(JobPlan((system,)), dossier or _dossier(), READING)
    return check


# --- tags, ids and quotes ---------------------------------------------------------------------------------

def test_tags_are_expanded_one_by_one():
    assert expand_tags("VAV-101 thru VAV-103, VAV-114") == ["VAV-101", "VAV-102", "VAV-103", "VAV-114"]
    assert expand_tags(("RTU-1 thru 3",)) == ["RTU-1", "RTU-2", "RTU-3"]
    assert expand_tags("AHU-1, 2") == ["AHU-1", "AHU-2"]
    assert expand_tags("VAV-21-01 thru 03") == ["VAV-21-01", "VAV-21-02", "VAV-21-03"]


def test_a_continued_letter_list_is_expanded():
    assert expand_tags("SPXF-A, B, C") == ["SPXF-A", "SPXF-B", "SPXF-C"]
    assert expand_tags(("TXF-A", "B")) == ["TXF-A", "TXF-B"]
    assert expand_tags("CAC-1.5, 6") == ["CAC-1.5", "CAC-1.6"]


def test_a_cited_paragraph_is_found_by_its_id():
    assert cited_text(_dossier(), "S1") == SEQ_VAV
    assert cited_text(_dossier(), "S4") == "[S4] VAV-1 | OFFICE 101 | 600 | HW GPM 1.5"
    assert cited_text(_dossier(), "S99") == ""


def test_a_quote_is_found_ignoring_whitespace_and_most_of_it_in_order():
    d = _dossier()
    assert quote_in_dossier("each VAV box shall   maintain the space\ntemperature", d)
    # 60 % of the words, in order, is enough: a word or two changed by the AI
    assert quote_in_dossier("each VAV box will maintain the room temperature and CO2 setpoints", d)
    assert not quote_in_dossier("each unit ventilator shall run on a time schedule from the BMS", d)
    assert not quote_in_dossier("VAV boxes shall", _dossier(text="nothing here"))


# --- C1: the plan against the counts ----------------------------------------------------------------------

def test_a_quantity_the_counts_agree_with_is_confirmed():
    check = _check(_vav())
    assert check.category == "CONFIRMED" and check.review == ()
    assert check.counts == {"distinct tags": 3, "placements on the plans": 3}


def test_a_quantity_the_counts_disagree_with_is_a_discrepancy_with_both_numbers():
    check = _check(_vav(quantity=4))
    assert check.category == "DISCREPANCY"
    [item] = check.review
    assert item.category == "DISCREPANCY"
    assert "4" in item.decide and "3 by distinct tags" in item.decide
    assert "kept" in item.action                                   # never changed silently


def test_a_type_row_with_a_quantity_column_is_that_many_units_never_one():
    assert _check(_cuh()).category == "CONFIRMED"
    one = _check(_cuh(quantity=1))
    assert one.category == "DISCREPANCY"
    assert "12 by the schedule's QUANTITY column" in one.review[0].decide


def test_no_quantity_is_pending_with_the_counts_as_the_alternatives():
    check = _check(_vav(quantity=None, quantity_quote="", quantity_source=""), _dossier(counts={}))
    assert check.category == "PENDING"               # nothing counts it (round 4: a count the dossier gives is printed)
    [item] = check.review
    assert item.category == "PENDING" and "no count" in item.evidence
    assert check.goes == "the base bid, Qty (##)"


def test_a_system_with_no_tag_is_confirmed_by_its_quote():
    pump = PlannedSystem("FP", "Fire Pump", "Fire Pump", (), 1, "S9", "Job 26-9999", ("S9",))
    assert _check(pump).category == "ASSUMPTION"          # the quote is there but does not state the count
    stated = PlannedSystem("FP", "Fire Pump", "Fire Pump", (), 2, "S8", "Provide two fire pumps", ("S8",))
    assert _check(stated).category == "CONFIRMED"
    tag_only = PlannedSystem("FP", "Fire Pump", "Fire Pump", (), 2, "S2", "EF-1 and EF-2", ("S2",))
    assert _check(tag_only).category == "ASSUMPTION"          # a tag number is not a count


def test_a_split_family_is_checked_against_its_own_tags():
    part = _vav(key="VAV-A", tags=("VAV-1", "VAV-2"), quantity=2)
    assert _check(part).category == "CONFIRMED"
    assert _check(_vav(key="VAV-A", tags=("VAV-1", "VAV-2"), quantity=3)).category == "DISCREPANCY"


def test_a_system_with_no_source_is_reviewed():
    check = _check(_vav(quantity_source="", sequence_sources=(), schedule_sources=()))
    assert not check.sourced
    assert any("cites no source" in item.decide for item in check.review)


def test_a_family_no_planned_system_covers_is_reviewed_not_added():
    review = check_plan(JobPlan((_vav(), _ef())), _dossier(), READING)
    [item] = [i for i in review if i.decide.startswith("Equipment on the drawings the plan didn't write")]
    assert "Cabinet Unit Heater CUH-1" in item.decide
    assert "VAV" not in item.decide and "EF-1" not in item.decide


def test_part_of_a_family_left_out_is_reviewed_and_existing_units_are_not():
    existing = type("Reading", (), {"inventory": (InventoryItem("VAV-3", "Variable Air Volume Box", "EXISTING", 1,
                                                                None, (), "", ""),)})()
    plan = JobPlan((_vav(tags=("VAV-1",), quantity=1), _ef(), _cuh()))
    review = check_plan(plan, _dossier(), READING)
    assert any("Variable Air Volume Box VAV-2, 3" in i.decide for i in review)
    review = check_plan(plan, _dossier(), existing)
    assert any("Variable Air Volume Box VAV-2" in i.decide and "3" not in i.decide.split("VAV-2")[1]
               for i in review)


# --- C1: the scope against its quotes, the house style and the Master Template --------------------------------

VAV_LINES = (
    WrittenLine("Furnish DDC Controller to the Factory for Installation", quote="each VAV box shall maintain",
                source_id="S1"),
    WrittenLine("Furnish and Install Space Temperature / CO2 Sensor", quote="space temperature and CO2 setpoints",
                source_id="S1"),
    WrittenLine("Furnish and Install Discharge Air Temperature Sensor", quote="hold the discharge air temperature",
                source_id="S1"),
    WrittenLine("Furnish and Wire Hot Water Control Valve and Actuator", quote="The hot water reheat valve shall "
                "modulate", source_id="S1"),
    WrittenLine("Furnish and Install VAV Transformer", quote="each VAV box shall maintain", source_id="S1",
                confidence=0.6),
)


def test_a_line_whose_quote_is_not_in_the_dossier_is_capped_and_reviewed():
    lines = VAV_LINES + (WrittenLine("Furnish and Install Occupancy Sensor", quantity=5,
                                     quote="occupancy sensors in every office"),)
    kept, review = check_scope(_vav(), WrittenScope(lines), _dossier(), TEMPLATES)
    occ = next(k for k in kept if k.text == "Furnish and Install Occupancy Sensor")
    assert not occ.quoted and occ.confidence == 0.5 and occ.quantity == 5     # a count given with a quote is kept
    assert any("Occupancy Sensor" in i.decide and "not in the job's documents" in i.decide for i in review)
    valve = next(k for k in kept if "Hot Water" in k.text)
    assert valve.quoted and valve.confidence == 0.9 and valve.source_id == "S1"


def test_lines_naming_prices_hours_confidence_or_a_category_are_dropped_and_listed():
    lines = VAV_LINES + (WrittenLine("Furnish Fan Enable at $200", quote="each VAV box"),
                         WrittenLine("Furnish Graphics (4 hours)", quote="each VAV box"),
                         WrittenLine("Furnish Sensor — CONFIRMED", quote="each VAV box"),
                         WrittenLine("Space sensors everywhere", quote="each VAV box"))
    kept, review = check_scope(_vav(), WrittenScope(lines), _dossier(), TEMPLATES)
    # the GEM round: a line with no house verb is kept in the GEM's words; only what the client must never see goes
    assert [k.text for k in kept] == [line.text for line in VAV_LINES] + ["Space sensors everywhere"]
    [item] = [i for i in review if "dropped" in i.decide]
    for text in ("$200", "4 hours", "CONFIRMED"):
        assert text in item.evidence


def test_the_master_template_is_a_checklist_of_what_the_ai_left_out():
    lines = VAV_LINES[1:3]          # no DDC controller, no valve, no transformer
    kept, review = check_scope(_vav(), WrittenScope(lines), _dossier(), TEMPLATES)
    [item] = [i for i in review if i.decide.startswith("Usually present")]
    assert "Furnish DDC Controller to the Factory for Installation" in item.decide
    assert "Furnish and Wire Hot Water Control Valve and Actuator" in item.decide   # the evidence names hot water reheat
    assert "Furnish Fan Enable" not in item.decide                                   # nothing says fan powered
    assert "Furnish and Install VAV Transformer" in item.decide                      # a choice with none written
    _, review = check_scope(_vav(), WrittenScope(VAV_LINES), _dossier(), TEMPLATES)
    assert not any(i.decide.startswith("Usually present") for i in review)


def test_every_line_of_an_unsourced_system_is_at_most_point_four():
    kept, _ = check_scope(_vav(), WrittenScope(VAV_LINES), _dossier(), TEMPLATES, sourced=False)
    assert max(k.confidence for k in kept) == 0.4


def test_the_ais_own_notes_reach_the_review_list():
    _, review = check_scope(_vav(), WrittenScope(VAV_LINES, review_notes=("Check VAV-3's heating coil",)),
                            _dossier(), TEMPLATES)
    assert any(i.decide == "Check VAV-3's heating coil" for i in review)


# --- C1: tech hours ---------------------------------------------------------------------------------------------

def test_tech_hours_follow_the_master_template_when_it_fits_the_kind():
    evidence = system_evidence(_vav(), _dossier())
    hours, note = tech_hours(_vav(), 3, [], None, TEMPLATES, evidence)
    assert (hours, note) == (12.0, None)                   # 4 h per hot-water reheat VAV
    hours, _ = tech_hours(_vav(), 3, [], None, TEMPLATES, "cooling only")
    assert hours == 9.0


def test_tech_hours_per_hardware_point_count_the_hardware_lines():
    ahu = PlannedSystem("AHU", "Air Handling Unit AHU-1", "Air Handling Unit", ("AHU-1",), 1)
    lines = [("Furnish and Install Supply Air Temperature Sensor", 1), ("Furnish and Wire Supply Fan Start/Stop", 1),
             ("Map Available Points", None)]
    hours, _ = tech_hours(ahu, 1, lines, None, TEMPLATES)
    assert hours == 4.0


def test_without_its_own_template_the_nearest_entrys_rule_is_an_assumption_and_the_ais_hint_never_counts():
    pump = PlannedSystem("FP", "Fire Pump", "Fire Pump", (), 1)
    lines = [("Furnish and Install Current Switch for Pump Status", 1)]
    hours, note = tech_hours(pump, 1, lines, None, TEMPLATES)       # the nearest: 2 h a hardware point
    assert hours == 2.0 and note.category == "ASSUMPTION" and "nearest Master Template entry" in note.decide
    hours, note = tech_hours(pump, 1, [], TechHoursHint("unit", 2.0, "Fuel Oil Pump System"), TEMPLATES)
    assert hours is None and "enter them" in note.decide           # nothing counted, and never the AI's hours
    odd = PlannedSystem("ZC", "Zamboni Charger", "Zamboni Charger", (), 1)
    hours, note = tech_hours(odd, 1, [], TechHoursHint("unit", 2.0, "Fuel Oil Pump System"), TEMPLATES)
    assert hours is None and "enter them" in note.decide


# --- what the judge is asked ---------------------------------------------------------------------------------

def test_the_request_pieces():
    evidence = system_evidence(_vav(), _dossier())
    assert SEQ_VAV in evidence and "[S4] VAV-1 | OFFICE 101" in evidence
    assert "Counts for VAV" in evidence and "T: 3" in evidence
    assert system_images(_vav(), _dossier()) == [IMAGE]                 # S3 says "see image I1"
    assert "Furnish and Wire Hot Water Control Valve and Actuator" in template_options(_vav(), TEMPLATES)
    checklist = checklist_text(TEMPLATES)
    assert "- VAV / Fan VAV (tags VAV" in checklist
    assert "tech hour" not in checklist.lower()


# --- C2: the job from the plan ---------------------------------------------------------------------------------

TODAY = dt.date(2026, 9, 26)
JOB_READING = SimpleNamespace(inventory=(), versions=(), schedules=(), backbone=(), notes=(), devices=(), flags=())
EF_SCOPE = WrittenScope((WrittenLine("Furnish and Wire Fan Start/Stop", quote="Exhaust fans EF-1 and EF-2",
                                     source_id="S2"),))


def _job_catalogue(**kw):
    catalogue = front_end_catalogue(folder="26-9999, 1 Test Street", **kw)
    catalogue.tags, catalogue.bid = (), None
    return catalogue


def _assemble(systems, scopes, catalogue=None, front_end=None, unresolved=(), dossier=None):
    plan = JobPlan(tuple(systems), front_end or {}, tuple(unresolved))
    return assemble_job(catalogue or _job_catalogue(), JOB_READING, dossier or _dossier(), plan, scopes, TODAY,
                        TEMPLATES)


def _headers(job):
    return [b.header for b in job.blocks]


def test_the_job_has_the_planned_blocks_in_order_and_fits_the_price_sheet():
    job, systems, review = _assemble([_vav(), _ef()], {"VAV": WrittenScope(VAV_LINES), "EF": EF_SCOPE})
    assert isinstance(job, Job)
    check_fit(job)
    assert _headers(job) == ["Qty (3) Variable Air Volume Box VAV-1 thru 3", "Qty (2) Exhaust Fan EF-1, 2"]
    vav = job.blocks[0]
    # the GEM's SOW order: the controller and its transformer, the sensors, then the valve
    assert [i.text for i in vav.items] == [VAV_LINES[0].text, VAV_LINES[4].text, VAV_LINES[1].text,
                                           VAV_LINES[2].text, VAV_LINES[3].text]
    assert all(i.quantity == 3 for i in vav.items)                 # one per unit when the quote states no count
    assert vav.tech_hours == 12.0
    assert systems[0].bundle_key == "Front end"
    valve = next(line for s in systems for line in s.lines if "Hot Water Control Valve" in line.text)
    assert valve.source == "AI (whole job) [S1]" and valve.category == "CONFIRMED" and valve.client
    assert "23 09 93 SEQUENCE OF OPERATIONS" in valve.evidence
    assert any(i.decide.startswith("Equipment on the drawings the plan didn't write") for i in review)


def test_a_pending_quantity_is_printed_as_qty_hash_hash_with_a_count_to_give():
    job, systems, _ = _assemble([_vav(quantity=None, quantity_quote=""), _ef()],
                                {"VAV": WrittenScope(VAV_LINES), "EF": EF_SCOPE}, dossier=_dossier(counts={}))
    assert _headers(job) == ["Qty (##) Variable Air Volume Box VAV-1 thru 3", "Qty (2) Exhaust Fan EF-1, 2"]
    vav = next(s for s in systems if s.bundle_key == "VAV")
    assert vav.printed and all(line.quantity is None for line in vav.lines)
    assert any(i.decide == "Give the count for Qty (##) Variable Air Volume Box VAV-1 thru 3" for i in vav.review)


def test_a_system_the_ai_has_not_written_yet_is_left_out_with_no_master_template_lines_and_reviewed():
    job, systems, _ = _assemble([_vav(), _ef()], {"VAV": WrittenScope(VAV_LINES), "EF": None})
    assert _headers(job) == ["Qty (3) Variable Air Volume Box VAV-1 thru 3"]
    ef = next(s for s in systems if s.bundle_key == "EF")
    assert not ef.printed and not ef.lines
    assert ef.review[0].decide.startswith("Left out of the proposal: the AI wrote no scope line for")
    assert ef.review[0].evidence == "the AI has not written it yet" and ef.review[0].tier == 1


def test_a_block_the_ai_left_empty_on_purpose_is_left_out_with_its_reason():
    scope = WrittenScope((), explanation="TX is the toilet exhaust riser tag, not a fan.",
                         review_notes=("Fold it into TXF-R-1.",))
    job, systems, _ = _assemble([_vav(), _ef()], {"VAV": WrittenScope(VAV_LINES), "EF": scope})
    assert _headers(job) == ["Qty (3) Variable Air Volume Box VAV-1 thru 3"]
    ef = next(s for s in systems if s.bundle_key == "EF")
    assert not ef.printed
    assert ef.review[0].evidence == ("The AI's reason: TX is the toilet exhaust riser tag, not a fan. — "
                                     "Fold it into TXF-R-1.")


def test_exceptions_and_alternates_go_where_the_plan_puts_them():
    fans = _ef(exception="EXCEPTION TO ANY WORK WITH Qty (2) EF-1, 2 - LINE-VOLTAGE THERMOSTAT")
    heaters = _cuh(alternate="add")
    scopes = {"VAV": WrittenScope(VAV_LINES),
              "CUH": WrittenScope((WrittenLine("Furnish and Install Space Temperature Sensor",
                                               quote="CABINET UNIT HEATER SCHEDULE", source_id="S7"),))}
    job, systems, _ = _assemble([_vav(), fans, heaters], scopes)
    check_fit(job)
    assert _headers(job) == ["Qty (3) Variable Air Volume Box VAV-1 thru 3"]
    assert job.named_exceptions == ("EXCEPTION TO ANY WORK WITH Qty (2) EF-1, 2 - LINE-VOLTAGE THERMOSTAT",)
    [alt] = job.add_alternates
    assert alt.label == "ALT #1: Cabinet Unit Heater CUH-1"
    assert [b.header for b in alt.blocks] == ["Qty (12) Cabinet Unit Heater CUH-1"]
    assert job.deduct_alternates == ()
    fan = next(s for s in systems if s.bundle_key == "EF")
    assert fan.blocks == () and fan.lines[0].text.startswith("EXCEPTION TO ANY WORK")


def test_a_group_stacks_its_headers_over_the_lines_they_share():
    chillers = PlannedSystem("CH", "Chiller CH-1, 2", "Chiller", ("CH-1", "CH-2"), 2, "S9", "Job", ("S9",),
                             group="Chilled Water System")
    pumps = PlannedSystem("CHWP", "Chilled Water Pump CHWP-1, 2", "Chilled Water Pump", ("CHWP-1", "CHWP-2"), 2,
                          "S9", "Job", ("S9",), group="Chilled Water System")
    shared = WrittenLine("Furnish and Install Chilled Water Supply Temperature Sensor", quantity=1, quote="Job 26-9999")
    scopes = {"CH": WrittenScope((WrittenLine("Furnish and Wire Chiller Enable", quote="Job 26-9999"), shared)),
              "CHWP": WrittenScope((WrittenLine("Furnish and Wire Pump Start/Stop", quote="Job 26-9999"), shared))}
    job, systems, _ = _assemble([chillers, _vav(), pumps], scopes | {"VAV": WrittenScope(VAV_LINES)})
    assert _headers(job)[:2] == ["Qty (2) Chiller CH-1, 2", "Qty (2) Chilled Water Pump CHWP-1, 2"]
    first, second = job.blocks[:2]
    assert second.joined and not first.joined and first.items == ()
    texts = [i.text for i in second.items]
    assert texts.count(shared.text) == 1
    assert next(i for i in second.items if i.text == shared.text).quantity == 1      # one sensor, named by both
    group = next(s for s in systems if s.bundle_key == "Chilled Water System")
    assert group.template == "Chilled Water System"


def test_the_front_end_keeps_the_spec_overviews_reading_and_adds_only_a_sourced_line():
    plan_front = {"mode": "extend-existing", "existing_name": "Siemens", "lines": ["Furnish BMS Server"],
                  "notes": [], "sources": ["S9"]}
    job, systems, _ = _assemble([_vav()], {"VAV": WrittenScope(VAV_LINES)}, front_end=plan_front)
    assert job.front_end.mode == "new-system"
    texts = [i.text for i in job.front_end.items]
    assert "Furnish BMS Server" in texts
    front = systems[0]
    assert any("reads the front end as extend existing" in i.decide for i in front.review)
    assert any(line.text == "Furnish BMS Server" and line.source == "AI (whole job) [S9]" for line in front.lines)
    assert any("leaves out front-end lines" in i.decide for i in front.review)

    unsourced = dict(plan_front, sources=[])
    job, systems, _ = _assemble([_vav()], {"VAV": WrittenScope(VAV_LINES)}, front_end=unsourced)
    assert "Furnish BMS Server" not in [i.text for i in job.front_end.items]
    assert any("cites no source" in i.decide for i in systems[0].review)


def test_global_points_and_the_extended_warranty_come_from_the_job_and_move_the_warranty_lines():
    services = (front_end_warranty("The warranty is one year, then extend the maintenance service for four (4) "
                                   "additional years.", "one year"),)
    catalogue = _job_catalogue(overview=front_end_overview(services=services),
                               texts=["Furnish an outside air temperature sensor for the BMS."])
    job, systems, _ = _assemble([_vav()], {"VAV": WrittenScope(VAV_LINES)}, catalogue=catalogue)
    check_fit(job)
    assert _headers(job) == ["Qty (1) Global Points", "Qty (3) Variable Air Volume Box VAV-1 thru 3",
                             "Qty (1) Extended Warranty"]
    assert not any("arrant" in i.text for i in job.front_end.items)
    assert [s.bundle_key for s in systems] == ["Front end", "Global Points", "VAV", "Extended Warranty"]
    assert not any("arrant" in line.text for line in systems[0].lines)


def test_the_plans_questions_reach_the_review_list():
    _, _, review = _assemble([_vav()], {"VAV": WrittenScope(VAV_LINES)},
                             unresolved=("Are the kitchen hoods by others?",))
    assert any(i.decide == "Are the kitchen hoods by others?" for i in review)


def test_what_the_judge_threw_away_reaches_the_review_list():
    plan = JobPlan((_vav(),), dropped=("AHU-1: a quantity with no quote",))
    scope = WrittenScope(VAV_LINES, refused=("“Furnish Sensor $40” — it names “$”",))
    _, systems, review = assemble_job(_job_catalogue(), JOB_READING, _dossier(), plan, {"VAV": scope}, TODAY,
                                      TEMPLATES)
    assert any("AHU-1: a quantity with no quote" in i.evidence for i in review)
    vav = next(s for s in systems if s.bundle_key == "VAV")
    assert any("Furnish Sensor $40" in i.evidence for i in vav.review)


def test_a_client_note_the_evidence_does_not_bear_out_is_reviewed_not_printed():
    scope = WrittenScope(VAV_LINES, client_notes=("**Space sensors by others", "**Maintain the CO2 setpoints"))
    job, systems, _ = _assemble([_vav()], {"VAV": scope})
    notes = [i.text for i in job.blocks[0].items if i.kind == "note"]
    assert "**Maintain the CO2 setpoints" not in notes            # borne out, but the controls contractor's own work
    vav = next(s for s in systems if s.bundle_key == "VAV")
    assert any(l.text == "**Maintain the CO2 setpoints" and not l.client for l in vav.lines)
    assert any("Space sensors by others" in i.decide for i in vav.review)


def test_the_fakes_have_the_real_parts_field_names():
    """The fakes above stand in for Parts A and B; their field names must stay those of the real classes."""
    import dataclasses
    from estimator.writing import dossier as real_dossier, whole_job as real_whole_job
    pairs = [(Dossier, real_dossier.Dossier), (DossierImage, real_dossier.DossierImage),
             (PlannedSystem, real_whole_job.PlannedSystem), (JobPlan, real_whole_job.JobPlan),
             (WrittenLine, real_whole_job.WrittenLine), (WrittenScope, real_whole_job.WrittenScope)]
    for fake, real in pairs:
        fake_names = {f.name for f in dataclasses.fields(fake)}
        real_names = {f.name for f in dataclasses.fields(real)}
        assert fake_names <= real_names, (fake.__name__, fake_names - real_names)


def test_a_contradicted_count_prints_its_note_and_a_review_row():
    from estimator.writing.assemble import count_notes
    from estimator.writing.write import ScopeLine, WrittenSystem
    from estimator.scope import Block, Item, Run
    from types import SimpleNamespace
    block = Block(header="Qty (14) Variable Air Volume Box VAV-1 thru 14", items=(Item(kind="line", runs=(Run(text="Furnish x"),)),))
    written = WrittenSystem("VAV", (block,), (), ())
    part = SimpleNamespace(system=SimpleNamespace(header="Variable Air Volume Box VAV-1 thru 14",
                                                  count_note="*Qty. (14) per M-201, Drawings.pdf page 3; equipment counts for VAV lists (12)."))

    noted = count_notes(written, [part])

    assert noted.blocks[0].items[-1].kind == "note"
    assert noted.blocks[0].items[-1].text == "*Qty. (14) per M-201, Drawings.pdf page 3; equipment counts for VAV lists (12)."
    row = noted.review[-1]
    assert row.category == "DISCREPANCY" and row.tier == 2
    assert row.decide == "Two counts for Variable Air Volume Box VAV-1 thru 14: *Qty. (14) per M-201, Drawings.pdf page 3; equipment counts for VAV lists (12)."
    assert count_notes(written, [SimpleNamespace(system=SimpleNamespace(header="x", count_note=""))]) == written


def test_a_ledger_system_keeps_its_count_when_the_dossier_counts_disagree():
    check = _check(_vav(quantity=4, facts=("F1", "F2")))
    assert check.category == "CONFIRMED" and check.quantity == 4
    assert not any(item.category == "DISCREPANCY" for item in check.review)


def test_a_ledger_system_with_no_count_is_pending_not_counted_from_the_plans():
    plain = _check(_vav(quantity=None, quantity_quote="", quantity_source=""))
    assert plain.category == "CONFIRMED-on-plans" and plain.quantity == 3                     # the old plan: counted from the plans
    ledger = _check(_vav(quantity=None, quantity_quote="", quantity_source="", facts=("F1",)))
    assert ledger.category == "PENDING" and ledger.quantity is None


# --- one clarification per block, sequence-only systems, integration hours (2026-10-03) ----------------------

def test_one_clarification_per_block():
    from estimator.writing.assemble import block_clarifications, _Row
    from types import SimpleNamespace
    def row(text, after):
        return _Row(SimpleNamespace(text=text, flag="", source_id="", quote="", quantity=None, depth=1, origin=""), None, True, frozenset(), None, "S", after=list(after))
    rows = [row("Furnish and Install Sensor A", ["*Confirm quantity: Sensor A"]),
            row("Wire Relay B", ["*Assumed: the relay comes with the unit", "*RELAY B BY UNIT MFR."]),
            row("Furnish and Install Sensor C", ["*Confirm quantity: Sensor C"])]
    kept, notes = block_clarifications(rows)
    assert [r.after for r in kept] == [[], ["*RELAY B BY UNIT MFR."], []]
    assert notes == ["*Confirm quantities: Sensor A, Sensor C", "*Assumed: the relay comes with the unit"]


def test_a_sequence_only_system_prints_in_the_base_bid_with_its_note():
    from estimator.writing.assemble import _check_one
    from estimator.writing.whole_job import PlannedSystem
    system = PlannedSystem("EG", "Emergency Generator EG", "Emergency Generator", ("EG",), None, "", "", ("[Q21]",), (), "", "", "",
                           "Named in the sequence of operation; no drawing shows it.", sequence_section="[Q21]", facts=("F171",))
    check = _check_one(system, _dossier())
    assert check.held is False and check.category == "PENDING"
    assert any("Named only in the sequence" in r.evidence for r in check.review)


def test_integration_only_systems_get_four_hours():
    from estimator.writing.assemble import tech_hours
    from estimator.writing.whole_job import PlannedSystem
    system = PlannedSystem("HT", "Heat Tracing HT", "Heat Tracing", ("HT",), None, "", "", ("[Q24]",), (), "", "", "",
                           "Named in the sequence of operation; no drawing shows it.", facts=("F170",))
    hours, row = tech_hours(system, None, [("Integrate Heat Tracing Control Panel to the BMS via Serial Interface", None),
                                           ("Map Available Points Via Mfr. Provided BMS Interface", None)], None)
    assert hours == 4.0 and "4 h per integration" in row.decide


def test_the_left_out_list_suggests_the_template_line():
    _, review = check_scope(_vav(), WrittenScope(VAV_LINES[1:3]), _dossier(), TEMPLATES)
    [item] = [i for i in review if i.decide.startswith("Usually present")]
    assert "Add it: Furnish DDC Controller to the Factory for Installation" in item.action.split("\n")


def test_a_sequence_only_system_prints_qty_hash_with_its_note_and_four_hours():
    from estimator.writing.whole_job import PlannedSystem
    from test_gem_round2 import FANS, _assemble as _gem_assemble, _gl, _scope
    eg = PlannedSystem("EG", "Emergency Generator EG", "Emergency Generator", ("EG",), None, "", "", ("[S1]",), (), "",
                       "", "", "Named in the sequence of operation; no drawing shows it.", sequence_section="[S1]",
                       facts=("F171",))
    job, _, _, _ = _gem_assemble([FANS, eg], {"EF": _scope(_gl("Furnish Fan Start/Stop and Status")),
                                              "EG": _scope(_gl("Furnish Generator Run Status"))})
    block = next(b for b in job.blocks if b.header == "Qty (##) Emergency Generator EG")
    assert block.tech_hours == 4.0
    assert [i.text for i in block.items][-1] == "*Quantity per electrical drawings"     # a generator's count


def test_each_family_note_of_a_group_is_its_own_note():
    from types import SimpleNamespace
    from estimator.writing.assemble import count_notes
    from estimator.writing.write import WrittenSystem
    from estimator.scope import Block, Item, Run
    block = Block(header="Chilled Water Plant", items=(Item(kind="line", runs=(Run(text="Furnish x"),)),))
    note = "CH: *Qty. (3) per M-201; schedule rows 2.\nCHWP: *Qty. (4) per M-201; schedule rows 2."
    part = SimpleNamespace(system=SimpleNamespace(header="Chilled Water Plant", count_note=note))
    written = count_notes(WrittenSystem("Chilled Water Plant", (block,), (), ()), [part])
    assert [i.text for i in written.blocks[-1].items][-2:] == ["CH: *Qty. (3) per M-201; schedule rows 2.",
                                                                "CHWP: *Qty. (4) per M-201; schedule rows 2."]


def test_the_per_drawings_note_follows_the_kind_of_system():
    from estimator.writing.assemble import per_drawings_note
    from estimator.writing.style import load_house_style
    from estimator.writing.whole_job import PlannedSystem
    style = load_house_style()

    def system(key, kind):
        return PlannedSystem(key, f"{kind} {key}", kind, (key,), None, "", "", ("[Q1]",), (), "", "", "",
                             "Named in the sequence of operation; no drawing shows it.", facts=("F1",))

    assert per_drawings_note(system("OAF", "Outdoor Air Fan"), style) == "*Quantity per mechanical drawings"
    assert per_drawings_note(system("DWH", "Domestic Water Heater"), style) == "*Quantity per plumbing drawings"
    assert per_drawings_note(system("EG", "Emergency Generator"), style) == "*Quantity per electrical drawings"
