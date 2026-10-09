import copy
import json
from pathlib import Path

import pytest

from harkpro import coverage
from harkpro.concepts import concepts
from harkpro.doctrine import load_lines, parse_lines
from harkpro.appio import tags_in

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def ledger():
    return json.loads((FIX / "ledger.json").read_text())


@pytest.fixture
def job():
    return json.loads((FIX / "job.json").read_text())


@pytest.fixture
def lib():
    return load_lines(FIX / "lines.json")


def by_id(result):
    return {f.fact_id: f for f in result.facts}


def test_concepts_consume_specific_before_generic():
    assert concepts("combination fire/smoke dampers") == {"fire_smoke"}
    assert "valve" not in concepts("RADIATOR CONTROL VALVES SHALL BE INTERLOCKED")
    assert {"radiation", "interlock"} <= concepts("RADIATOR CONTROL VALVES SHALL BE INTERLOCKED")
    assert "local_alarm" in concepts("WIRE TO BMS AND A TANK OVERFLOW ALARM. LOCAL ALARM.")
    assert "lighting_integration" in concepts("INTEGRATE VIA THE LUTRON VIVE HUB")
    assert concepts("T") == {"thermostat"} and concepts("OCC") == {"occupancy"}
    assert concepts("warranty terms") == set()


def test_tags_expand_runs():
    assert tags_in("AC-1-1, 2") >= {"AC11", "AC12"}
    assert tags_in("VAV-01 thru 03") >= {"VAV01", "VAV02", "VAV03"}


def test_count_reads_times_but_not_duct_size():
    assert coverage.fact_count({"value": "x", "quote": "40x10 RTU-1 M ×5"}) == 5
    assert coverage.fact_count({"value": "x", "quote": "50x12 duct"}) is None
    assert coverage.fact_count({"value": 19, "quote": ""}) == 19


def test_gate_fails_and_names_each_known_kind_of_miss(ledger, job, lib):
    r = coverage.check(ledger, job, lib, printed={})
    f = by_id(r)
    assert not r.passed
    assert f["F6"].status == "unaccounted" and f["F6"].uncovered == ["occupancy"]          # counted symbols
    assert f["F6"].suggestions[0].line_id == "occupancy_sensors.01"
    assert f["F12"].status == "unaccounted" and "lighting_integration" in f["F12"].uncovered  # Lutron
    assert f["F12"].suggestions[0].line_id == "front_end.21"
    assert f["F8"].status == "partial" and f["F8"].uncovered == ["local_alarm"]           # leak printed, RAM not
    assert f["F8"].suggestions[0].line_id == "packaged_unit.02"
    assert f["F16"].severity == "must_fix" and f["F16"].suggestions[0].line_id == "vav.03"
    assert f["F6"].citation == "device label OCC counted on the controls plan sheets"


def test_printed_lines_account_for_their_facts(ledger, job, lib):
    f = by_id(coverage.check(ledger, job, lib, printed={}))
    assert f["F11"].status == "accounted"                    # radiator interlock: printed on the VAV block
    assert {c.concept for c in f["F11"].covered_by} >= {"radiation", "interlock"}
    assert f["F9"].status == "accounted"                     # damper actuators
    assert f["F15"].status == "accounted"
    assert "F17" not in f and "F2" not in f


def test_radiator_interlock_flagged_when_not_printed(ledger, job, lib):
    job = copy.deepcopy(job)
    vav = job["systems"][1]
    vav["devices"] = [d for d in vav["devices"] if d["id"] != "VAV.d3"]
    f = by_id(coverage.check(ledger, job, lib, printed={}))
    assert set(f["F11"].uncovered) == {"radiation", "interlock"}
    assert f["F11"].severity == "must_fix"


def test_count_gaps(ledger, job, lib):
    r = coverage.check(ledger, job, lib, printed={})
    gaps = {(g["fact_id"], g["concept"]): g for g in r.count_gaps}
    assert gaps[("F10", "damper")]["fact_count"] == 5 and gaps[("F10", "damper")]["printed"] == 2
    assert gaps[("F7", "thermostat")]["printed"] == 3


def test_dismissals(ledger, job, lib):
    f = by_id(coverage.check(ledger, job, lib, printed={}))
    assert f["F4"].status == "dismissed"                     # a block left out with a real reason
    assert f["F14"].status == "dismissed"                    # smoke detector: the house template excludes it
    assert f["F3"].status == "unaccounted"                   # left out "by the MC" is rejected (rulings R2)
    assert "R2" in f["F3"].covered_by[0].reason
    assert f["F13"].status == "unaccounted" and any("R2" in n for n in f["F13"].notes)


def test_weak_reason_is_not_a_dismissal(ledger, job, lib):
    job = copy.deepcopy(job)
    job["systems"][3]["no_scope_reason"] = "The schedule could not be read; held as a question."
    f = by_id(coverage.check(ledger, job, lib, printed={}))
    assert f["F4"].status == "unaccounted" and f["F4"].severity == "must_fix"


def test_estimator_dismissal_file(ledger, job, lib, tmp_path):
    path = tmp_path / "d.json"
    path.write_text(json.dumps({"dismissals": [{"fact_id": "F6", "reason": "occupancy sensors by the EC"}]}))
    f = by_id(coverage.check(ledger, job, lib, coverage.load_dismissals(path), printed={}))
    assert f["F6"].status == "dismissed"
    assert f["F6"].covered_by[0].reason == "occupancy sensors by the EC"


def test_passes_when_everything_is_placed(ledger, job, lib):
    keep = {"F1", "F5", "F9", "F11", "F15", "F14"}
    ledger = dict(ledger, facts=[x for x in ledger["facts"] if x["id"] in keep])
    job["systems"][0]["devices"][2]["assumption"] = None      # else R6 flags the one-per-unit damper count
    r = coverage.check(ledger, job, lib, printed={})
    assert r.passed, coverage.markdown(r)


def test_judge_request_and_answer(ledger, job, lib, tmp_path):
    r = coverage.check(ledger, job, lib, printed={})
    req = coverage.judge_request(r, ledger, job, {})
    assert req["answer_schema"]["required"] == ["verdicts"]
    item = next(i for i in req["items"] if i["fact_id"] == "F8")
    assert item["uncovered"] == ["local_alarm"] and item["citation"]
    answer = {"verdicts": [
        {"fact_id": "F8", "concept": "local_alarm", "verdict": "missing", "sink_id": None,
         "line_id": "packaged_unit.02", "reason": "RAM module not printed"},
        {"fact_id": "F6", "concept": "occupancy", "verdict": "dismiss", "sink_id": None, "line_id": None,
         "reason": "lighting occupancy sensors are the EC's"}]}
    coverage.apply_judge(r, answer)
    f = by_id(r)
    assert f["F6"].status == "dismissed"
    assert f["F8"].status == "partial" and f["F8"].suggestions[0].line_id == "packaged_unit.02"


def test_run_writes_outputs(tmp_path):
    r = coverage.run(FIX / "ledger.json", FIX / "job.json", tmp_path, FIX / "lines.json", use_app_render=False)
    names = {p.name for p in tmp_path.iterdir()}
    assert {"sample-clinic coverage.json", "sample-clinic coverage.md",
            "sample-clinic coverage judge request.json"} <= names
    data = json.loads((tmp_path / "sample-clinic coverage.json").read_text())
    assert data["passed"] is False and data["summary"]["must_fix"] == r.summary()["must_fix"]
    assert "FAIL" in (tmp_path / "sample-clinic coverage.md").read_text()


def test_library_shapes():
    a = parse_lines({"families": [{"id": "vav", "family": "VAV", "aliases": ["VAV"],
                                   "lines": [{"id": "vav.01", "text": "Furnish DDC Controller"}]}]})
    b = parse_lines({"families": {"vav": {"name": "VAV", "lines": ["Furnish DDC Controller"]}}})
    assert a.lines[0].id == "vav.01" and a.lines[0].aliases == ("VAV",)
    assert b.lines[0].text == "Furnish DDC Controller" and b.families["vav"] == "VAV"
    assert not load_lines(FIX / "missing.json")


def test_real_doctrine_file_loads_when_present():
    lib = load_lines()
    if not lib:
        pytest.skip("HarkPro/doctrine/lines.json not written yet")
    assert any(l.id.startswith("vav.") for l in lib.lines)


def test_rulings_on_printed_lines_and_damper_gap(ledger, job, lib):
    job = copy.deepcopy(job)
    job["systems"][0]["devices"][1].update(verb="Wire", furnished_by="Mechanical Contractor",
                                           installed_by="Mechanical Contractor")
    job["systems"][0]["devices"][2]["assumption"] = {"what": "one damper actuator per unit", "why": "no tags"}
    r = coverage.check(ledger, job, lib, printed={})
    rulings = {(f.ruling, f.line_id) for f in r.rulings}
    assert ("R3", "RTU.d2") in rulings and ("R6", "RTU.d3") in rulings
    gap = next(g for g in r.count_gaps if g["concept"] == "damper")
    assert gap["severity"] == "must_fix" and gap["ruling"] == "R6"
    assert not r.passed and r.summary()["ruling_flags"] == 2


def test_ruling_lines_rank_first_in_suggestions(ledger, job):
    lib = load_lines()                        # the real Master Template data
    if not lib:
        pytest.skip("HarkPro/doctrine/lines.json not present")
    f = by_id(coverage.check(ledger, job, lib, printed={}))
    assert (f["F6"].suggestions[0].line_id, f["F6"].suggestions[0].ruling) == ("occupancy_sensors.01", "R8")
    assert (f["F12"].suggestions[0].line_id, f["F12"].suggestions[0].ruling) == ("front_end.21", "R9")
    assert f["F8"].suggestions[0].ruling == "R5" and "RAM" in f["F8"].suggestions[0].text


def test_a_shared_sheet_source_alone_does_not_account(ledger, job, lib):
    ledger = copy.deepcopy(ledger)
    ledger["facts"].append({"id": "F99", "kind": "device", "subject": "local control panel", "value": 1,
                            "source_id": "S4", "quote": "PROVIDE NEW LOCAL CONTROL PANEL WITH DEDICATED CIRCUIT.",
                            "stage": "plans", "state": "settled", "contradictions": [], "was_settled": True})
    f = by_id(coverage.check(ledger, job, lib, printed={}))
    assert f["F99"].status == "unaccounted" and f["F99"].severity == "check"     # RTU.d3 cites S4, another passage
