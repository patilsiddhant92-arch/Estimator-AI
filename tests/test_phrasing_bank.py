"""The phrasing bank: how systems were actually written in the Learn proposals."""
import importlib.util
import json
import sys
from pathlib import Path

import docx
from docx.shared import Twips

from estimator.writing.phrasing import BANK_FILE, examples_for, load_bank

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("build_phrasing_bank", ROOT / "tools" / "build_phrasing_bank.py")
builder = importlib.util.module_from_spec(_spec)
sys.modules["build_phrasing_bank"] = builder
_spec.loader.exec_module(builder)

SENT = ROOT / "tests" / "data" / "26-0246" / "sent-proposal.docx"


def _x_style_proposal(path: Path) -> Path:
    """A proposal in the "(xN)" style, the way 26-0352 is written: no outline numbering at all."""
    document = docx.Document()
    for text, indent in [
        ("SCOPE OF WORK – ", 1440),
        ("Front End Web Enabled BMS System", 832),
        ("Furnish Network Control Panel - (x1)", 1440),
        ("(x2) Hot Water Heater EWH-1, 2", 720),
        ("Furnish and Install Leak Sensor - (x2)", 1800),
        ("Interlock with Solenoid Valve (Valve by Others) - (x2)", 1800),
        ("Wire Solenoid Valve (Furnished by Others)", 2160),
        ("**Valves by the plumbing contractor", 1800),
        ("(x5) Exhaust Fans", 720),
        ("(x1) TX-1", 1440),
        ("(x4) EF-1 thru 4", 1440),
        ("Furnish Fan Start / Stop - (x5)", 1800),
        ("Furnish and Install 4 hours of programming", 1800),
        ("Furnish Fan Relay ($120 each)", 1800),
        ("ADD ALTERNATES:", 0),
        ("(x1) Should not be read", 720),
        ("Furnish Nothing", 1800),
    ]:
        paragraph = document.add_paragraph(text)
        paragraph.paragraph_format.left_indent = Twips(indent)
    document.save(path)
    return path


def test_the_x_style_fallback_reads_headers_lines_depths_and_notes(tmp_path):
    entries, reader = builder.read_blocks(_x_style_proposal(tmp_path / "26-9999.docx"), "26-9999")
    assert reader == "(xN) fallback"
    heater, fans = entries
    assert heater["job"] == "26-9999"
    assert heater["header"] == "(x2) Hot Water Heater EWH-1, 2"
    assert heater["prefixes"] == ["EWH"]
    assert heater["kind_words"] == ["Hot", "Water", "Heater"]
    assert heater["lines"] == [
        {"text": "Furnish and Install Leak Sensor", "depth": 1},
        {"text": "Interlock with Solenoid Valve (Valve by Others)", "depth": 1},
        {"text": "Wire Solenoid Valve (Furnished by Others)", "depth": 2},
    ]
    assert heater["notes"] == ["**Valves by the plumbing contractor"]

    # The sub-headers' tags belong to the block; hours and prices never enter the bank.
    assert fans["header"] == "(x5) Exhaust Fans / (x1) TX-1 / (x4) EF-1 thru 4"
    assert fans["prefixes"] == ["TX", "EF"]
    assert fans["kind_words"] == ["Exhaust", "Fans"]
    assert fans["lines"] == [{"text": "Furnish Fan Start / Stop", "depth": 1}]


def test_a_template_proposal_is_read_with_read_scope():
    entries, reader = builder.read_blocks(SENT, "26-0246")
    assert reader == "read_scope"
    assert len(entries) >= 30
    vav = next(e for e in entries if "VAV" in e["prefixes"])
    assert vav["header"].startswith("Qty (")
    assert "Qty" not in vav["kind_words"] and not any(w.startswith("VAV-") for w in vav["kind_words"])
    assert all(set(line) == {"text", "depth"} for e in entries for line in e["lines"])
    assert all(e["lines"] or e["notes"] for e in entries)


def test_the_revision_file_is_preferred(tmp_path):
    folder = tmp_path / "26-0001" / "3. Proposal" / "1. Base Proposal"
    folder.mkdir(parents=True)
    for name in ("26-0001.docx", "26-0001_ELEC.docx", "proposal template.docx", "AME_nordomatic Proposal Template.docx",
                 "~$-0001.docx", "26-0001+SP.docx"):
        (folder / name).write_bytes(b"")
    assert builder.choose_file(folder, "26-0001").name == "26-0001+SP.docx"
    (folder / "26-0001+SP.docx").unlink()
    assert builder.choose_file(folder, "26-0001").name == "26-0001.docx"
    (folder / "26-0001.docx").unlink()
    (folder / "26-0001_K.docx").write_bytes(b"")
    assert builder.choose_file(folder, "26-0001").name == "26-0001_K.docx"   # the only proposal left


def test_the_test_jobs_are_never_opened(tmp_path, monkeypatch):
    learn = tmp_path / "Learn"
    for job in ("26-0478", "26-0193, Somewhere", "26-0001"):
        (learn / job / "3. Proposal" / "1. Base Proposal").mkdir(parents=True)
    _x_style_proposal(learn / "26-0001" / "3. Proposal" / "1. Base Proposal" / "26-0001.docx")
    opened = []
    real = builder.read_blocks
    monkeypatch.setattr(builder, "read_blocks", lambda path, job, *rest: opened.append(job) or real(path, job, *rest))
    bank = builder.build(learn, sent=None)
    assert opened == ["26-0001"]
    assert {e["job"] for e in bank["blocks"]} == {"26-0001"}
    kept = json.dumps([bank["sources"], bank["skipped"], bank["blocks"]])
    assert not any(job in kept for job in ("26-0478", "26-0193"))


def test_the_committed_bank_is_there_and_holds_no_hours_or_prices():
    bank = json.loads(BANK_FILE.read_text(encoding="utf-8"))
    jobs = {e["job"] for e in bank["blocks"]}
    assert "26-0246" in jobs and len(jobs) >= 6
    assert not jobs & {"26-0478", "26-0193"}
    text = json.dumps(bank["blocks"])
    assert "$" not in text and "tech hour" not in text.lower()
    for entry in bank["blocks"]:
        assert set(entry) == {"job", "header", "prefixes", "kind_words", "lines", "notes"}


# --- picking examples ------------------------------------------------------------------------------

def _entry(job, header, prefixes, words, lines=("Furnish and Install DDC Controller",)):
    return {"job": job, "header": header, "prefixes": list(prefixes), "kind_words": list(words),
            "lines": [{"text": t, "depth": 1} for t in lines], "notes": []}


def test_examples_prefer_the_same_prefix_then_shared_kind_words():
    bank = [
        _entry("A", "Qty (2) Exhaust Fan EF-1, 2", ["EF"], ["Exhaust", "Fan"]),
        _entry("B", "Qty (1) Electric Duct Heater EDH-1", ["EDH"], ["Electric", "Duct", "Heater"]),
        _entry("C", "Qty (3) Unit Heater UH-1 thru 3", ["UH"], ["Unit", "Heater"]),
        _entry("D", "Qty (1) Electric Heater EH-1", ["EH"], ["Electric", "Heater"]),
        _entry("E", "Qty (1) Chiller CH-1", ["CH"], ["Chiller"]),
    ]
    picked = examples_for(["EDH"], "Electric Duct Heater", bank, k=4)
    assert [e["job"] for e in picked] == ["B", "D", "C"]
    assert examples_for(["EDH"], "Electric Duct Heater", bank, k=1)[0]["job"] == "B"
    assert examples_for(["ZZ"], "Gravity Ventilator", bank) == []


def test_the_committed_bank_loads():
    bank = load_bank()
    assert bank and all(e["header"] for e in bank)
