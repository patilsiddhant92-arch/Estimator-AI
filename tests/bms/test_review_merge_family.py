"""RUN-1: a family Accept saved after a count change never erases the change. Save 1 changes the Exhaust Fan count;
the card comes back (the other counts are still there); save 2 accepts the family. The accept is not the same
answer as the change: the change stays in the history and the next run still prints the changed count.
Invented data only: the sample fixture."""
from __future__ import annotations

import dataclasses
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from bms import review
from bms.model import Decision, Job, OtherCount, Ref
from bms.review import SavedDecision

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def job() -> Job:
    """The sample job with a disputed Exhaust Fan count (one other count), so its family card shows."""
    job = Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))
    system = job.system("EF")
    family = dataclasses.replace(system.families[0], count=dataclasses.replace(
        system.families[0].count, others=(OtherCount(2, Ref("C1", "located on the sheet text", "invented")),)))
    return job.with_system(dataclasses.replace(system, families=(family, *system.families[1:])))


def _change(job: Job, value: int) -> Decision:
    count = dataclasses.replace(job.system("EF").families[0].count, value=value)
    return Decision("EF", "change", family_name="Exhaust Fan", count=count, reason=str(value))


def test_a_family_accept_after_a_count_change_keeps_the_change(job):
    change = _change(job, 5)
    accept = Decision("EF", "accept", family_name="Exhaust Fan")
    merged = review.merge_decisions([SavedDecision(change, 1)], [accept], job=job)
    assert [(h.decision.action, h.round) for h in merged] == [("change", 1), ("accept", 2)]
    applied = review.apply_seen(job, [h.decision for h in merged], review.copies_seen(merged))
    assert applied.system("EF").families[0].count.value == 5


def test_a_new_count_change_still_replaces_the_earlier_change(job):
    merged = review.merge_decisions([SavedDecision(_change(job, 5), 1)], [_change(job, 6)], job=job)
    assert [(h.decision.action, h.decision.count.value, h.round) for h in merged] == [("change", 6, 2)]


def test_a_family_accept_still_replaces_an_earlier_accept(job):
    accept = Decision("EF", "accept", family_name="Exhaust Fan")
    merged = review.merge_decisions([SavedDecision(_change(job, 5), 1), SavedDecision(accept, 2)], [accept,
                                    Decision("EF", "accept", device_id="EF.d1")], job=job)
    assert [(h.decision.action, h.round) for h in merged if h.decision.device_id is None] == [
        ("change", 1), ("accept", 3)]


# ---- the page's buildDecision: a count change settles the dispute; words alone are no count change ---------------

def _core() -> str:
    return review._SCRIPT_CORE


def test_the_page_script_clears_the_other_counts_on_a_count_change():
    core = _core()
    family = core[core.index('q.level === "family"'):]
    family = family[:family.index("d.count = c;")]
    assert "c.others = []" in family
    device = core[core.index('if (q.level === "device" && q.device)'):core.index('q.level === "family"')]
    assert "dev.quantity.others = []" in device


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_page_script_builds_family_and_device_count_changes_as_settled(tmp_path):
    count = {"value": 4, "sources": [], "others": [{"value": 2, "ref": {"source_id": "C1", "quote": "x",
                                                                        "where": "invented"}}]}
    family = {"system_key": "EF", "level": "family", "family_name": "Exhaust Fan", "count": count}
    device = {"system_key": "EF", "level": "device", "device_id": "EF.d1",
              "device": {"name": "Fan", "quantity": json.loads(json.dumps(count)), "flag": "quantity"}}
    harness = _core() + """
var f = %s, d = %s;
console.log(JSON.stringify([buildDecision(f, {action: "change", text: "5"}),
                            buildDecision(f, {action: "change", text: "only the roof fans"}),
                            buildDecision(d, {action: "change", text: "5"})]));
""" % (json.dumps(family), json.dumps(device))
    script = tmp_path / "h.js"
    script.write_text(harness, encoding="utf-8")
    done = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    number, words, line = json.loads(done.stdout)
    assert number["count"]["value"] == 5 and number["count"]["others"] == []
    assert words["count"] is None and words["reason"] == "only the roof fans"
    assert line["device"]["quantity"]["value"] == 5 and line["device"]["quantity"]["others"] == []
