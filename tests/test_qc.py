"""The proposal QC pass: it compares, it never rewrites; its findings become review rows and a tab."""
from estimator.writing.qc import QcBlock, QcReport, parse_qc, qc_prompt, qc_review_rows, qc_schema, split_blocks

RTU = QcBlock("RTU", "Rooftop Unit RTU-1, 2", 2, "packaged",
              ("Wire Supply Air Temperature Sensor (Furnished by Unit Mfr.) (Qty. 2 Total)", "Furnish BMS Communication Wiring to Factory Controls"),
              ("Install and wire Supply Air Temperature Sensor (Furnished by Unit Mfr.)", "Furnish BMS Communication Wiring to Factory Controls",
               "Map Available Points Via Mfr. Provided BMS Interface"), "16 h per unit", "F1 family RTU = Rooftop Unit …", "[Q6]")


def test_the_prompt_carries_the_brief_the_blocks_the_template_and_the_rules():
    text = qc_prompt("Job: 26-9999\nWhat the job is\nA school.", [RTU], "PACKAGED UNITS — WHAT AME DOES: …", "How AME writes a system")
    for s in ("What the job is", "Rooftop Unit RTU-1, 2", "Wire Supply Air Temperature Sensor", "Map Available Points",
              "PACKAGED UNITS — WHAT AME DOES", "How AME writes a system", "packaged"):
        assert s in text
    assert qc_schema()["required"] == ["findings", "block_notes", "job_note"]


def test_findings_are_parsed_and_the_unknown_ones_dropped():
    answer = {"findings": [
        {"system": "RTU", "line": "Wire Supply Air Temperature Sensor (Furnished by Unit Mfr.) (Qty. 2 Total)", "kind": "ownership",
         "say": "The sensor ships loose, so AME installs and wires it.", "fix": "Install and Wire Supply Air Temperature Sensor (Furnished by Unit Mfr.) (Qty. 2 Total)",
         "severity": "must-fix", "quote": "Install and wire Supply Air Temperature Sensor (Furnished by Unit Mfr.)"},
        {"system": "RTU", "line": "", "kind": "missing", "say": "The Map Available Points line is missing.", "fix": "Map Available Points Via Mfr. Provided BMS Interface", "severity": "must-fix", "quote": ""},
        {"system": "RTU", "line": "Furnish DX Cooling", "kind": "not-ame-scope", "say": "not a line of this block", "fix": "", "severity": "check", "quote": ""},
        {"system": "XYZ", "line": "", "kind": "count", "say": "no such system", "fix": "", "severity": "check", "quote": ""}],
        "block_notes": [{"system": "RTU", "note": "Shape is right once the verb is fixed."}], "job_note": "A clean small job."}
    report = parse_qc(answer, "m", [RTU])
    assert [f.kind for f in report.findings] == ["ownership", "missing"]
    assert len(report.dropped) == 2 and report.block_notes["RTU"].startswith("Shape is right")
    rows = qc_review_rows(report)
    assert rows[0].system == "RTU" and rows[0].category == "QC" and rows[0].tier == 1 and rows[0].action.startswith("Change to: Install and Wire")
    assert rows[1].action == "Add it: Map Available Points Via Mfr. Provided BMS Interface"


def test_blocks_are_split_whole_under_the_limit():
    parts = split_blocks([RTU] * 5, limit=len(qc_prompt("", [RTU, RTU], "", "")) + 10)
    assert all(len(p) <= 2 for p in parts) and sum(len(p) for p in parts) == 5
