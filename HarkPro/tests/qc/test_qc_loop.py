"""The independent QC (harkpro.qc): evidence log, checklists, revisions, the critic -> respond loop, report, grade.
Synthetic fixtures only (AGENTS.md rule 1)."""
import json
from pathlib import Path

import pytest

from harkpro.qc import checklist as cl
from harkpro.qc import scope as sc
from harkpro.qc.__main__ import main
from harkpro.qc.evidence import concepts, load_evidence, package_items
from harkpro.qc.grade import grade
from harkpro.qc.loop import run, screen
from harkpro.qc.schemas import CRITIC, RESPOND, schema_errors

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.fixture
def ledger():
    return load("ledger.json")


@pytest.fixture
def job():
    return load("job.json")


def answer(result, data):
    """Write `data` as the answer of the (single) waiting request."""
    assert result.status == "waiting", result.message
    (w,) = result.waiting
    Path(w["answer_file"]).parent.mkdir(parents=True, exist_ok=True)
    Path(w["answer_file"]).write_text(json.dumps(data), encoding="utf-8")
    return json.loads(json.loads(Path(w["file"]).read_text(encoding="utf-8"))["prompt"])


def cite(e, q):
    return {"evidence_id": e, "quote": q, "where": ""}


def thread(tid, sev="must_fix", sk="RTU", dev=None, ev=("E003",), quote="WIRED TO LOCAL ALARM PANEL", prop=None):
    return {"id": tid, "kind": "missing_line", "severity": sev, "system_key": sk, "device_id": dev,
            "evidence_ids": list(ev), "question": "Where is the local alarm panel?",
            "critique": "The leak detector reports to a local alarm panel; no line carries it (R5).",
            "proposed": prop, "citations": [cite(ev[0], quote)]}


def device(id, name, verb="Furnish and Install", qty=2, sid="S3", quote="DRIP PAN LEAK DETECTOR"):
    return {"id": id, "slot": "x", "name": name, "verb": verb, "furnished_by": "AME", "installed_by": "AME",
            "wired_by": "AME", "quantity": {"value": qty, "sources": [], "others": []},
            "refs": [{"source_id": sid, "quote": quote, "where": "M-501"}], "assumption": None, "flag": "none"}


def items(walked, raised=None):
    raised = raised or {}
    return [{"evidence_id": e, "status": "raised" if e in raised else "dismissed", "device_ids": [],
             "thread_ids": raised.get(e, []), "note": "" if e in raised else "not controls"} for e in walked]


def op(o, sk, dev=None, did=None, text=None):
    return {"op": o, "system_key": sk, "system_name": None, "device_id": did, "device": dev, "text": text}


# ---- evidence ------------------------------------------------------------------------------------------------

def test_evidence_numbers_every_ledger_fact_and_scans_concepts(ledger):
    ev = load_evidence(ledger)
    assert [e.id for e in ev] == ["E001", "E002", "E003", "E004", "E005"]
    assert ev[2].where.startswith("M-501") and ev[2].source_id == "S3"
    assert {"leak", "local_alarm"} <= set(ev[2].concepts)
    assert "other_party" in ev[3].concepts and "thermostat" in ev[3].concepts
    walked, screened = screen(ev)
    assert [e.id for e in screened] == ["E001", "E005"]          # no controls word: a family name, duct sealing


def test_package_rows_tables_not_found_and_citation_columns(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Notes"
    ws.append(["Sheet", "Number", "Note"])
    ws.append(["M-201", "4", "ATC CONTRACTOR TO PROVIDE CO2 SENSOR."])
    ws.append([])
    ws.append(["Second table"])
    ws.append(["Code", "What it means", "Sheet"])
    ws.append(["OS", "OCCUPANCY SENSOR", "M-002"])
    ws.append(["Training", "Not found", ""])
    c = wb.create_sheet("Citations")
    c.append(["System", "Used for", "Source id", "Quote"])
    c.append(["RTU", "writer column", "S9", "WIRE TO BMS."])
    wb.create_sheet("Scope lines").append(["#", "Printed line", "Verb"])
    path = tmp_path / "pkg.xlsx"
    wb.save(path)
    rows = package_items(path)
    texts = [r["text"] for r in rows]
    assert any("CO2 SENSOR" in t for t in texts)
    assert any("OCCUPANCY SENSOR" in t for t in texts)
    assert not any("Not found" in t for t in texts)                 # a not-found row is not evidence
    cit = [r for r in rows if r["origin"].endswith("Citations")]
    assert cit and "writer column" not in cit[0]["text"] and cit[0]["source_id"] == "S9"
    assert not any("Printed line" in t for t in texts)               # scope sheets are not read
    assert "co2" in concepts("CO₂ OCC ×5") and "occupancy" in concepts("OCC")


# ---- checklists ---------------------------------------------------------------------------------------------------

def test_families_from_scope_tags_and_evidence_words(job):
    ev = [{"text": "DRIP PAN LEAK DETECTOR WIRED TO LOCAL ALARM PANEL"}, {"text": "VAV-3 thru 5"}]
    ids = {f["id"] for f in cl.families_for(job, ev)}
    assert {"front_end", "exhaust_fan", "leak_detection", "vav", "packaged_unit"} <= ids
    assert "chilled_water_system" not in ids
    vav = cl.checklist(next(f for f in cl.families_for(job, ev) if f["id"] == "vav"))
    assert any(l["id"] == "vav.01" and "applies_when" in l for l in vav["lines"])


def test_template_match_fills_placeholders():
    assert cl.template_matches("Seamlessly Tie in to the Existing {existing_bms} BMS",
                               "Seamlessly Tie in to the Existing Niagara N4 BMS")
    assert cl.template_matches("Furnish and Install Leak Sensor", "furnish and install  leak sensor (Qty. 2 Total)")
    assert not cl.template_matches("Furnish and Install Leak Sensor", "Wire Leak Detector")


# ---- revisions ------------------------------------------------------------------------------------------------------

def test_operations_apply_to_a_copy(job):
    new = sc.apply_operations(job, [
        op("change", "RTU", device("RTU.d2", "Leak Sensor"), did="RTU.d2"),
        op("add", "EF", device("EF.d1", "Space Thermostat", qty=1)),
        op("add", "FE", device("FE.d1", "Furnish 3-D Graphics")),
        op("delete", "RTU", did="RTU.d1"),
        op("clarify", "RTU", text="Leak sensors per the detail."),
        op("except", "EF", text="Fan wiring by others.")])
    assert job["systems"][1]["devices"] == [] and job["systems"][1]["no_scope_reason"]      # original untouched
    ef = next(s for s in new["systems"] if s["key"] == "EF")
    assert ef["devices"][0]["id"] == "EF.d1" and ef["no_scope_reason"] is None
    rtu = next(s for s in new["systems"] if s["key"] == "RTU")
    assert [d["id"] for d in rtu["devices"]] == ["RTU.d2"] and rtu["devices"][0]["verb"] == "Furnish and Install"
    assert rtu["clarifications"] == [{"kind": "confirm", "text": "Leak sensors per the detail."}]
    assert new["front_end"]["devices"][0]["id"] == "FE.d1"
    assert new["exceptions"][0]["system_key"] == "EF"
    with pytest.raises(sc.OperationError):
        sc.apply_operations(job, [op("change", "RTU", device("RTU.d9", "x"), did="RTU.d9")])
    with pytest.raises(sc.OperationError):
        sc.apply_operations(job, [op("add", "RTU", device("RTU.d1", "dup"))])


def test_scope_concepts_and_view(job):
    assert "leak" in sc.scope_concepts(job) and "local_alarm" not in sc.scope_concepts(job)
    v = sc.view(job)
    assert v["systems"][-1]["key"] == "FE"
    assert v["systems"][0]["devices"][1]["line"] == "Wire Leak Detector (Furnished by Mechanical Contractor)"


# ---- the loop ---------------------------------------------------------------------------------------------------

def test_full_loop_critic_respond_verdict_report(tmp_path, ledger, job):
    out = tmp_path / "qc"
    res = run(ledger, job, out)
    assert res.exit_code == 2 and res.stage == "critic"
    req = json.loads(Path(res.waiting[0]["file"]).read_text())
    assert req["kind"] == "qc_critic" and "QC critic" in req["system_prompt"] or "critic" in req["system_prompt"]
    prompt = json.loads(req["prompt"])
    walked = [e["id"] for e in prompt["evidence"]]
    assert walked == ["E002", "E003", "E004"]
    assert {e["id"] for e in prompt["screened"]} == {"E001", "E005"}
    assert "local_alarm" in prompt["evidence"][1]["scope_lacks"]
    assert any(c["family_id"] == "leak_detection" for c in prompt["checklists"])
    assert "R5" in prompt["rulings"]

    # an answer quoting words that are not in the evidence is refused, with the reason in the new request
    bad = {"items": items(walked, {"E003": ["T1.1"]}),
           "threads": [thread("T1.1", quote="WIRED TO A REMOTE PANEL")], "verdicts": []}
    answer(res, bad)
    res = run(ledger, job, out)
    assert res.stage == "critic" and "not in E003" in res.waiting[0]["previous_problem"]
    assert list((out / "answers" / "rejected").iterdir())

    good = {"items": items(walked, {"E003": ["T1.1"], "E004": ["T1.2"]}),
            "threads": [thread("T1.1", prop={"line_id": "leak_detection.02", "text": "Furnish and Install Local RAM Module",
                                             "verb": "Furnish and Install", "furnished_by": "AME", "installed_by": "AME",
                                             "wired_by": "AME", "quantity": 2}),
                        dict(thread("T1.2", sk="EF", ev=("E004",), quote="WALL THERMOSTAT FOR STORAGE ROOM FAN"),
                             kind="left_out")],
            "verdicts": []}
    answer(res, good)
    res = run(ledger, job, out)
    assert res.stage == "respond" and len(res.state.open("must_fix")) == 2

    resp = answer(res, {"responses": [
        {"thread_id": "T1.1", "action": "revise", "text": "Added.",
         "operations": [op("add", "RTU", device("RTU.d3", "Local RAM Module"))], "citations": []},
        {"thread_id": "T1.2", "action": "justify", "text": "The thermostat is the MC's.",
         "operations": [], "citations": [cite("E004", "MECHANICAL CONTRACTOR TO PROVIDE")]}]})
    assert {t["id"] for t in resp["threads"]} == {"T1.1", "T1.2"}
    res = run(ledger, job, out)
    assert res.stage == "verdict"
    verdict_prompt = json.loads(json.loads(Path(res.waiting[0]["file"]).read_text())["prompt"])
    assert any(d["id"] == "RTU.d3" for s in verdict_prompt["scope"]["systems"] for d in s["devices"])

    answer(res, {"items": [], "threads": [], "verdicts": [
        {"thread_id": "T1.1", "verdict": "resolved", "reason": "RTU.d3 added.", "citations": []},
        {"thread_id": "T1.2", "verdict": "reopen", "reason": "R2: a thermostat by the MC is AME's.",
         "citations": [cite("E004", "MECHANICAL CONTRACTOR")]}]})
    res = run(ledger, job, out)
    assert res.stage == "respond"                                       # round 2: only the reopened thread
    p2 = answer(res, {"responses": [
        {"thread_id": "T1.2", "action": "revise", "text": "Added per R2.",
         "operations": [op("add", "EF", device("EF.d1", "Space Thermostat", qty=1, sid="S4",
                                                quote="MECHANICAL CONTRACTOR TO PROVIDE WALL THERMOSTAT"))],
         "citations": []}]})
    assert [t["id"] for t in p2["threads"]] == ["T1.2"]
    res = run(ledger, job, out)
    answer(res, {"items": [], "threads": [], "verdicts": [
        {"thread_id": "T1.2", "verdict": "resolved", "reason": "EF.d1 added.", "citations": []}]})
    res = run(ledger, job, out)
    assert res.status == "done" and res.exit_code == 0
    assert not list((out / "requests").glob("*.json"))
    revised = json.loads((out / "Job.qc.json").read_text())
    assert {d["id"] for _, d in sc.devices(revised)} >= {"RTU.d3", "EF.d1"}
    assert json.loads((FIX / "job.json").read_text()) == job                    # the writer's file is untouched
    report = (out / "QC_Report.md").read_text()
    assert "T1.2" in report and "fixed by revision" in report and "| E005" in report
    assert json.loads((out / "findings.json").read_text()) == []
    cov = {c["evidence_id"]: c["status"] for c in json.loads((out / "coverage.json").read_text())}
    assert cov == {"E001": "screened", "E002": "dismissed", "E003": "raised", "E004": "raised", "E005": "screened"}


def test_coverage_is_enforced(tmp_path, ledger, job):
    res = run(ledger, job, tmp_path)
    answer(res, {"items": items(["E002", "E003"]), "threads": [], "verdicts": []})
    res = run(ledger, job, tmp_path)
    assert "no entry for E004" in res.waiting[0]["previous_problem"]


def test_bad_template_line_and_unknown_device_refused(tmp_path, ledger, job):
    res = run(ledger, job, tmp_path)
    walked = ["E002", "E003", "E004"]
    t = thread("T1.1", dev="RTU.d7", prop={"line_id": "leak_detection.02", "text": "Furnish Alarm Thing",
                                           "verb": "Furnish", "furnished_by": "AME", "installed_by": "AME",
                                           "wired_by": "AME", "quantity": None})
    answer(res, {"items": items(walked, {"E003": ["T1.1"]}), "threads": [t], "verdicts": []})
    problem = run(ledger, job, tmp_path).waiting[0]["previous_problem"]
    assert "no device 'RTU.d7'" in problem and "not the template line leak_detection.02" in problem


def test_unsettled_threads_become_must_fix_and_questions(tmp_path, ledger, job):
    walked = ["E002", "E003", "E004"]
    res = run(ledger, job, tmp_path, rounds=1)
    answer(res, {"items": items(walked, {"E003": ["T1.1"], "E004": ["T1.2"]}),
                 "threads": [thread("T1.1"), dict(thread("T1.2", sk="EF", ev=("E004",),
                                                         quote="MECHANICAL CONTRACTOR"), severity="check")],
                 "verdicts": []})
    res = run(ledger, job, tmp_path, rounds=1)
    answer(res, {"responses": [
        {"thread_id": "T1.1", "action": "justify", "text": "The detector line covers it.", "operations": [],
         "citations": [cite("E003", "DRIP PAN LEAK DETECTOR")]},
        {"thread_id": "T1.2", "action": "estimator_question", "text": "Does AME wire the fan thermostat?",
         "operations": [], "citations": []}]})
    res = run(ledger, job, tmp_path, rounds=1)
    answer(res, {"items": [], "threads": [], "verdicts": [
        {"thread_id": "T1.1", "verdict": "reopen", "reason": "No line names the alarm panel.", "citations": []},
        {"thread_id": "T1.2", "verdict": "escalate", "reason": "R2 sub-case is PENDING.", "citations": []}]})
    res = run(ledger, job, tmp_path, rounds=1)
    assert res.status == "done"
    findings = json.loads((tmp_path / "findings.json").read_text())
    assert {(f["system_key"], f["severity"]) for f in findings} == {("RTU", "must_fix"), ("EF", "check")}
    assert set(findings[0]) == {"rule", "system_key", "device_id", "severity", "what", "fix"}   # bms Finding shape
    qs = json.loads((tmp_path / "estimator_questions.json").read_text())
    assert any(q["question"] == "Does AME wire the fan thermostat?" for q in qs)
    assert "## Must fix (unresolved)" in (tmp_path / "QC_Report.md").read_text()


def test_respond_must_answer_every_thread(tmp_path, ledger, job):
    walked = ["E002", "E003", "E004"]
    res = run(ledger, job, tmp_path)
    answer(res, {"items": items(walked, {"E003": ["T1.1"]}), "threads": [thread("T1.1")], "verdicts": []})
    res = run(ledger, job, tmp_path)
    answer(res, {"responses": [{"thread_id": "T1.1", "action": "revise", "text": "x", "operations": [],
                                "citations": []}]})
    problem = run(ledger, job, tmp_path).waiting[0]["previous_problem"]
    assert "revise gives no operations" in problem


def test_schemas_fit_the_apps_checker():
    try:
        from bms.model import schema_errors as app_errors
    except ImportError:
        pytest.skip("the app is not on the path")
    sample = {"items": [], "threads": [thread("T1.1")], "verdicts": []}
    assert app_errors(sample, CRITIC) == [] == schema_errors(sample, CRITIC)
    resp = {"responses": [{"thread_id": "T1.1", "action": "revise", "text": "x",
                           "operations": [op("add", "RTU", device("RTU.d3", "Local RAM Module"))], "citations": []}]}
    assert app_errors(resp, RESPOND) == [] == schema_errors(resp, RESPOND)
    assert schema_errors({"responses": [{"thread_id": "T1"}]}, RESPOND)


def test_grade_counts_raised_and_fixed(job):
    threads = [{"id": "T1.1", "question": "Where is the local alarm panel?", "critique": "R5",
                "proposed": {"text": "Furnish and Install Local RAM Module"}, "kind": "missing_line"},
               {"id": "T1.2", "question": "Is training included?", "critique": "", "proposed": None, "kind": "front_end"}]
    revised = sc.apply_operations(job, [op("add", "RTU", device("RTU.d3", "Local RAM Module"))])
    g = grade(threads, revised, [{"id": "K1", "label": "RAM", "patterns": ["RAM Module"]},
                                 {"id": "K2", "label": "occupancy", "patterns": ["occupancy"]}], job)
    assert g["recall"] == "1/2"
    assert g["known"][0]["fixed_in_scope"] == ["Furnish and Install Local RAM Module"]
    assert g["known"][0]["already_in_writer_scope"] == []
    assert [o["id"] for o in g["other"]] == ["T1.2"]


def test_cli_run_check_and_evidence(tmp_path, capsys):
    code = main(["run", "--ledger", str(FIX / "ledger.json"), "--job", str(FIX / "job.json"), "--out", str(tmp_path)])
    block = json.loads(capsys.readouterr().out)
    assert code == 2 and block["stage"] == "critic"
    req = block["waiting"][0]["file"]
    Path(block["waiting"][0]["answer_file"]).write_text('{"items": []}')
    assert main(["check", block["waiting"][0]["answer_file"], req]) == 1
    assert "missing threads" in capsys.readouterr().out
    assert main(["evidence", "--ledger", str(FIX / "ledger.json")]) == 0
    assert "E003" in capsys.readouterr().out
