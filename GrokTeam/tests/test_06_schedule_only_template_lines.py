"""Bug 6: a schedule-only job (no sequence of operation, no BMS) gets no Master Template floor.

Fixture: an invented job whose only documents are equipment schedules (no sequence passage, no front_end fact, no
BMS anywhere). Generic tags. Line wording is read from HarkPro/doctrine/lines.json (read-only; the Master Template
as data).

Owner ruling 2026-10-09: the Master Template is the ideal-case checklist only (rules.md "Template is the ideal
case", "No standard or fallback lines"): nothing prints by default. Tests marked REGRESSION GUARD pass on current
code; they pin the behaviour, they are not bug proofs. Parts with a design note and no patch (6a's planner
question, 6c, 6e) are xfail(strict=True). 6b's and 6d's planner questions have a patch
(`06-schedule-only-questions.patch`).
"""
import json
import re
from pathlib import Path

import pytest

from estimator.ledger.facts import SETTLED, Ledger
from estimator.writing.dossier import Dossier

import dataclasses

from bms.model import Count, Device, Family, FrontEnd, Header, Job, ModelError, Ref, System
from bms.plan import plan_job
from bms.playbook import load_playbook
from bms.render import render
from bms.validate import validate

ROOT = Path(__file__).resolve().parents[2]
LINES = json.loads((ROOT / "HarkPro" / "doctrine" / "lines.json").read_text(encoding="utf-8"))
PLAYBOOK = load_playbook()
SOURCES = {"S3": "M-501, Invented.pdf page 6 (schedule)", "S5": "M-502, Invented.pdf page 7 (schedule)"}
REF = Ref("S3", "invented quote", "M-501, Invented.pdf page 6")

# (prefix, family name, tags, count): schedules only
SCHEDULE = (
    ("IDU", "VRF Indoor Unit", "IDU-1, IDU-2", 2),
    ("VAV", "VAV Box", "VAV-1, VAV-2", 2),
    ("UH", "Electric Unit Heater", "UH-1", 1),
    ("EF", "Exhaust Fan", "EF-1", 1),
    ("ACU", "Air Curtain", "ACU-1", 1),
    ("MD", "Motorized Damper", "MD-1", 1),
)


def _template(line_id: str) -> str:
    for family in LINES["families"]:
        for line in family["lines"]:
            if line["id"] == line_id:
                return line["text"]
    raise KeyError(line_id)


def _dossier():
    return Dossier(job_name="Invented Job", text="", images=(), sources={}, families=(), device_totals={},
                   counts={}, stats={})


def _schedule_only_ledger(extra=()):
    ledger = Ledger(dict(SOURCES))
    ledger.job_name = "Invented Job"
    for prefix, name, tags, n in (*SCHEDULE, *extra):
        ledger.add("family", prefix, name, "S3", f"{prefix} {name}", "schedules", SETTLED)
        ledger.add("unit", prefix, tags, "S3", f"Tags: {tags}", "schedules", SETTLED)
        ledger.add("count", prefix, n, "S3", f"{prefix} rows {n}", "schedules", SETTLED)
    return ledger


def _job(extra=()):
    return plan_job(_schedule_only_ledger(extra), None, _dossier(), PLAYBOOK)


def _plain(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


# ---- 6a (revised by owner ruling 2026-10-09): the template is the ideal-case checklist, never default lines -------
# rules.md "Template is the ideal case" and "No standard or fallback lines": a template device the documents support
# prints with its schedule quantity and owner; one they do not support does not print and becomes a planner question.

def _header():
    return Header(quote_number="Q-0000", reference="Invented Job", mep_engineer="Invented Engineer",
                  based_on=("Invented drawings",), date="2026-10-09")


def _printed(job):
    return [(it.runs[0].text, it.quantity) for b in render(job, PLAYBOOK).scope.blocks for it in b.items
            if it.kind == "line"]


def test_6a_a_supported_template_device_prints_with_its_schedule_quantity_and_owner():
    """REGRESSION GUARD (passes on current code): the schedule row gives the thermostat to the unit maker."""
    sched = Ref("S3", "UH-1, UH-2 unit controls by: thermostat furnished by unit mfr", "M-501, Invented.pdf page 6")
    line = Device("UH.d1", "space_temperature", "Space Thermostat", "Install and Wire", "Unit Mfr.", "AME", "AME",
                  Count(2, (sched,)), (sched,))
    uh = System("UH", "Unit Heaters", "EUH / CUH / UH", "field",
                (Family("Unit Heater", ("UH-1", "UH-2"), Count(2, (sched,))),), devices=(line,))
    job = Job("Invented Job", (uh,), front_end=FrontEnd(mode="new-system"), header=_header())
    assert _printed(job) == [("Install and Wire Space Thermostat (Furnished by Unit Mfr.)", 2)]


def test_6a_no_template_line_prints_by_default_on_a_schedule_only_job():
    """REGRESSION GUARD (negative, passes on current code): the planner writes no line of its own, and a line with
    no citation from this job cannot be made at all."""
    job = _job()
    assert all(not s.devices for s in job.systems)
    with pytest.raises(ModelError):
        Device("X.d1", "controller", "DDC Controller", "Furnish", "AME", "AME", "AME", Count(1), ())


def _asks_about(job, tag, device):
    return [q for q in job.questions if tag in q and device.lower() in q.lower()]


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="6a design note: the planner has no ideal-case checklist to compare the "
                                       "documents against (shapes.json slots carry no 'template device' list); "
                                       "needs a checklist source the owner approves")
def test_6a_an_unsupported_template_device_becomes_a_question_and_does_not_print():
    # the schedule names the VAV boxes only: nothing shows their space sensors
    job = _job()
    assert _asks_about(job, "VAV-1", "Space Temperature Sensor"), job.questions
    printed = [t for t, _q in _printed(dataclasses.replace(job, header=_header()))]
    assert not [t for t in printed if "space temperature sensor" in t.lower()], printed


def test_6a_a_supported_template_device_raises_no_question():
    """REGRESSION GUARD (negative, passes on current code): a schedule column that names the thermostat."""
    ledger = _schedule_only_ledger()
    ledger.add("provider", "UH-1", "thermostat furnished by unit mfr", "S3", "Unit controls by: unit mfr",
               "schedules", SETTLED)
    job = plan_job(ledger, None, _dossier(), PLAYBOOK)
    assert not _asks_about(job, "UH-1", "Thermostat"), job.questions


# ---- 6b (revision 2): who furnishes a damper actuator is open; documents silent -> a question, no line ----------
# No wording or furnisher is asserted ('Wire Motorized Damper (Furnished by Others)' is acceptable).

def _damper_job(provider=None):
    ledger = _schedule_only_ledger()
    if provider:
        ledger.add("provider", "MD-1", provider, "S5", provider, "schedules", SETTLED)
    return plan_job(ledger, None, _dossier(), PLAYBOOK)


def test_6b_documents_silent_on_who_furnishes_the_actuator_raise_a_question():
    job = _damper_job()
    asks = [q for q in job.questions if "MD-1" in q and "actuator" in q.lower()]
    assert len(asks) == 1, job.questions


def test_6b_documents_silent_print_no_damper_line():
    """Negative (passes before and after): the planner writes no damper line of its own."""
    job = dataclasses.replace(_damper_job(), header=_header())
    assert not [t for t, _q in _printed(job) if "damper" in t.lower()]


def test_6b_documents_naming_the_furnisher_raise_no_actuator_question():
    """Negative (passes before and after): a provider fact names who furnishes the dampers' controls."""
    job = _damper_job("damper actuators furnished and installed by controls contractor")
    assert not [q for q in job.questions if "MD-1" in q and "actuator" in q.lower()], job.questions


# ---- 6c: a sensor symbol attaches to the unit it is drawn next to ------------------------------------------------

def _attach(symbols, units):
    from bms.counts import attach_symbols                # proposed; does not exist yet
    return attach_symbols(symbols, units)


@pytest.mark.xfail(strict=True, raises=ImportError, reason="6c design note: no symbol-to-unit attachment by drawing position exists "
                                       "(counts read tags only)")
def test_6c_a_humidity_sensor_next_to_a_dehumidifier_attaches_to_it():
    units = [("DH-1", (100, 100)), ("VAV-1", (400, 120))]               # same floor plan, invented positions
    assert _attach([("TH", (110, 105))], units) == {"TH@110,105": "DH-1"}


@pytest.mark.xfail(strict=True, raises=ImportError, reason="6c design note: negative partner of the attachment test (same API)")
def test_6c_a_sensor_next_to_a_vav_stays_with_the_vav():
    units = [("DH-1", (100, 100)), ("VAV-1", (400, 120))]
    assert _attach([("TH", (395, 118))], units) == {"TH@395,118": "VAV-1"}


# ---- 6d: equipment with no template family is never dropped silently (patched) -----------------------------------

LEAK = (("RLD", "Refrigerant Leak Detector", "RLD-1, RLD-2", 2),)


def test_6d_an_unmatched_family_raises_a_question():
    job = _job(LEAK)
    asks = [q for q in job.questions if "RLD-1" in q and "Master Template" in q]
    assert len(asks) == 1, job.questions


def test_6d_the_unmatched_family_is_still_planned_never_dropped():          # negative: before and after
    job = _job(LEAK)
    assert any("RLD-1" in f.tags for s in job.systems for f in s.families)


def test_6d_a_family_with_a_template_shape_raises_no_such_question():      # negative: before and after
    job = _job()
    assert not [q for q in job.questions if "Master Template" in q], job.questions


# ---- 6e: a printed line that hits a house exclusion is flagged ---------------------------------------------------

def _block(name):
    line = Device("EF.d1", "other_device", name, "Furnish and Install", "AME", "AME", "AME", Count(1, (REF,)),
                  (REF,))
    ef = System("EF", "Exhaust Fans", "Exhaust Fan", "field", (Family("Exhaust Fan", ("EF-1",), Count(1, (REF,))),),
                devices=(line,))
    return Job("Invented Job", (ef,))


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="6e design note: the app has no house-exclusion list; the owner must give "
                                       "it (wording.json 'house_exclusions' proposed)")
def test_6e_a_line_hitting_a_house_exclusion_is_flagged():
    found = [f for f in validate(_block("Gas Detection Sensor"), PLAYBOOK) if "xclusion" in f.rule]
    assert found and found[0].device_id == "EF.d1"


def test_6e_an_ordinary_line_is_not_flagged_as_an_exclusion():              # negative: before and after
    assert not [f for f in validate(_block("Space Temperature Sensor"), PLAYBOOK) if "xclusion" in f.rule]


# ---- 6f: devices the documents support are not written -------------------------------------------------------------
# The lines are written by the AI writer (`bms.ai.write_system`) from each system's evidence; the planner writes none
# (by design, "No standard or fallback lines"). Two deterministic halves are tested: (1) the supporting passage
# reaches the system's evidence; (2) the proposed deterministic step turns it into the line (design note 6f).
# Quantities still in dispute are not asserted beyond QA's own rule (one thermostat per indoor unit).

def _supported(job, dossier_text):
    """Proposed (design note 6f): (lines by system key, planner questions)."""
    from bms.supported import supported_lines          # proposed module; does not exist yet
    return supported_lines(job, dossier_text)


def _vrf_job(n=3):
    tags = tuple(f"IDU-{i}" for i in range(1, n + 1))
    src = Ref("S3", "VRF indoor unit schedule", "M-501, Invented.pdf page 6")
    # no BMS: the VRF runs on its maker's controls, AME installs and wires the maker's thermostats (field)
    vrf = System("VRF", "VRF System", "VRF System", "field", (Family("Indoor Unit", tags, Count(n, (src,))),))
    return Job("Invented Job", (vrf,))


VRF_DOSSIER = ("== 7. NOTES ==\n--- M-601, Invented.pdf page 9 ---\n"
               "[N1] VRF INDOOR UNIT WALL MOUNTING DETAIL. T'STAT PROVIDED BY UNIT MFGR.\n")
VRF_DOSSIER_BARE = "== 7. NOTES ==\n--- M-601, Invented.pdf page 9 ---\n[N1] T'STAT PROVIDED BY UNIT MFGR.\n"


def test_6f_i_a_vrf_detail_note_naming_the_indoor_unit_reaches_its_evidence():
    """REGRESSION GUARD (passes on current code): a detail note that names the indoor unit is given to the writer."""
    from bms import ai_evidence
    vrf = _vrf_job().systems[0]
    assert "N1" in ai_evidence.cited_ids(ai_evidence.evidence(vrf, VRF_DOSSIER, {}, {}, ()))


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="6f design note: a bare detail-sheet note ('T'STAT PROVIDED BY UNIT MFGR.') "
                                       "names no tag or system phrase, so `ai_evidence` never gives it to the writer")
def test_6f_i_a_bare_tstat_note_on_the_vrf_detail_sheet_reaches_the_vrf_evidence():
    from bms import ai_evidence
    vrf = _vrf_job().systems[0]
    assert "N1" in ai_evidence.cited_ids(ai_evidence.evidence(vrf, VRF_DOSSIER_BARE, {}, {}, ()))


TSTAT_NOTES = ("T'STAT PROVIDED BY UNIT MFGR.", "THERMOSTAT FURNISHED BY EQUIPMENT MANUFACTURER")


def _vrf_note(text):
    return f"== 7. NOTES ==\n--- M-601, Invented.pdf page 9 ---\n[N1] VRF INDOOR UNIT MOUNTING DETAIL. {text}\n"


@pytest.mark.xfail(strict=True, raises=ModuleNotFoundError, reason="6f design note: no deterministic supported-line step; the AI writer alone "
                                       "turns the note into lines")
@pytest.mark.parametrize("note", TSTAT_NOTES)
def test_6f_i_tstat_by_unit_mfr_gives_one_install_and_wire_line_per_indoor_unit(note):
    """Two wordings of the same meaning: a patch matching one exact string fails the other."""
    lines = _supported(_vrf_job(3), _vrf_note(note))[0]["VRF"]
    tstat = [d for d in lines if "thermostat" in d.name.lower()]
    assert len(tstat) == 1 and tstat[0].verb == "Install and Wire" and tstat[0].furnished_by == "Unit Mfr."
    assert tstat[0].quantity.value == 3                       # N indoor units, N thermostats


@pytest.mark.xfail(strict=True, raises=ModuleNotFoundError, reason="6f design note: same proposed step (live once it lands)")
def test_6f_i_thermostat_by_others_asks_who_installs_and_wires_it():
    """'BY OTHERS' says who furnishes it, not who installs and wires it: a question, never a silent drop."""
    lines, questions = _supported(_vrf_job(3), _vrf_note("THERMOSTAT BY OTHERS"))
    assert [q for q in questions if "thermostat" in q.lower() and ("install" in q.lower() or "wire" in q.lower())]
    assert not [d for d in lines.get("VRF", ()) if "thermostat" in d.name.lower() and d.furnished_by == "AME"]


@pytest.mark.xfail(strict=True, raises=ModuleNotFoundError, reason="6f design note: negative partner, same proposed step (live once it lands)")
def test_6f_i_a_thermostat_furnished_installed_and_wired_by_others_gives_no_ame_line():
    lines, _questions = _supported(_vrf_job(3), _vrf_note("THERMOSTAT FURNISHED, INSTALLED AND WIRED BY OTHERS"))
    assert not [d for d in lines.get("VRF", ()) if "thermostat" in d.name.lower()
                and "AME" in (d.furnished_by, d.installed_by, d.wired_by)], lines


def _vav_job():
    src = Ref("S3", "VAV schedule", "M-501, Invented.pdf page 6")
    return Job("Invented Job", (System("VAV", "VAV Boxes", "VAV / Fan VAV", "field",
                                       (Family("VAV", ("VAV-1", "VAV-2"), Count(2, (src,))),)),))


# same meaning: the box manufacturer furnishes the transformer (a VAV schedule note is the maker's, R10)
TRANSFORMER_NOTES = ("PROVIDE 24V TRANSFORMER", "24V CONTROL TRANSFORMER FURNISHED WITH UNIT")


def _vav_dossier(note="PROVIDE 24V TRANSFORMER"):
    rows = ["== 4. SCHEDULES ==", "--- M-501, Invented.pdf page 6 ---", "[S1] VAV BOX SCHEDULE",
            "[S2] VAV-1 | 400 CFM", "[S3] VAV-2 | 600 CFM"]
    if note:
        rows.append(f"[S4] Note: {note}")
    return "\n".join(rows) + "\n"


def test_6f_ii_the_vav_schedule_note_reaches_the_vav_evidence():
    """REGRESSION GUARD (passes on current code): the schedule's own note is given with its rows."""
    from bms import ai_evidence
    vav = _vav_job().systems[0]
    assert "S4" in ai_evidence.cited_ids(ai_evidence.evidence(vav, _vav_dossier(), {}, {}, ()))


def _is_24v(d):
    return "transformer" in d.name.lower() or re.search(r"24\s*v", d.name.lower())


@pytest.mark.xfail(strict=True, raises=ModuleNotFoundError, reason="6f design note: no deterministic supported-line step (see 6f i)")
@pytest.mark.parametrize("note", TRANSFORMER_NOTES)
def test_6f_ii_a_24v_transformer_furnished_with_the_unit_gives_the_24v_line(note):
    """Two wordings of the same meaning: both give the line, furnished by the box manufacturer."""
    lines = [d for d in _supported(_vav_job(), _vav_dossier(note))[0]["VAV"] if _is_24v(d)]
    assert len(lines) == 1 and lines[0].furnished_by == "Unit Mfr.", lines


@pytest.mark.xfail(strict=True, raises=ModuleNotFoundError, reason="6f design note: same proposed step (live once it lands)")
def test_6f_ii_a_24v_transformer_by_the_controls_contractor_is_ames_and_owned_differently():
    """A separate ownership case: the controls contractor (AME) furnishes it; the owner differs from the unit case."""
    ame = [d for d in _supported(_vav_job(), _vav_dossier("24 VAC TRANSFORMER BY CONTROLS CONTRACTOR"))[0]["VAV"]
           if _is_24v(d)]
    unit = [d for d in _supported(_vav_job(), _vav_dossier(TRANSFORMER_NOTES[0]))[0]["VAV"] if _is_24v(d)]
    assert len(ame) == 1 and ame[0].furnished_by == "AME"
    assert unit and ame[0].furnished_by != unit[0].furnished_by


@pytest.mark.xfail(strict=True, raises=ModuleNotFoundError, reason="6f design note: negative partner, same proposed step (live once it lands)")
def test_6f_ii_a_transformer_furnished_installed_and_wired_by_others_gives_no_ame_line():
    lines = _supported(_vav_job(), _vav_dossier("24V TRANSFORMER FURNISHED, INSTALLED AND WIRED BY OTHERS"))[0]
    assert not [d for d in lines.get("VAV", ()) if _is_24v(d) and "AME" in (d.furnished_by, d.installed_by,
                                                                                d.wired_by)], lines


def test_6f_ii_no_transformer_note_gives_no_24v_line():
    """REGRESSION GUARD (negative, passes on current code): with no such note the planner writes no 24V line."""
    job = _job()
    vav = next(s for s in job.systems if s.shape == "VAV / Fan VAV")
    assert not [d for d in vav.devices if "24v" in d.name.lower() or "transformer" in d.name.lower()]


@pytest.mark.xfail(strict=True, raises=ImportError, reason="6f design note: no riser tracing; a damper on a riser is never tied to the "
                                       "unit whose duct it is on (rules.md 'Dampers under their fan' needs a link)")
def test_6f_iii_an_outside_air_damper_on_a_riser_is_traced_to_the_unit_it_serves():
    riser = [("RTU-1", "OA DUCT UP"), ("OAD-1", "ON OA DUCT")]          # invented riser labels, same duct run
    from bms.counts import trace_riser_dampers          # proposed; does not exist yet (after the fixture, so a broken fixture fails loudly)
    assert trace_riser_dampers(riser) == {"OAD-1": "RTU-1"}
