"""VAL-14, VAL-21 and RND-13: the 160-character line, the words the client never sees, and the integration trio's
depths in a block with no shape. Invented fixture only."""
from __future__ import annotations

import dataclasses as dc
import json
from pathlib import Path

import pytest

from bms.model import Clarification, Count, Family, Header, Job, ScopeException, System
from bms.playbook import load_playbook
from bms.render import render
from bms.validate import RULE, validate

FIX = Path(__file__).resolve().parent / "fixtures"
PB = load_playbook(FIX / "sample_playbook")


@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIX / "sample_job.json").read_text(encoding="utf-8")))


def _first_device(job: Job, **changes) -> tuple[Job, str, str]:
    system = job.systems[0]
    device = dc.replace(system.devices[0], **changes)
    return job.with_system(dc.replace(system, devices=(device,) + system.devices[1:])), system.key, device.id


def _hits(job: Job, rule: str):
    return [(f.system_key, f.device_id, f.severity) for f in validate(job, PB) if f.rule == RULE[rule]]


# ---- VAL-14: a line is at most 160 characters ----------------------------------------------------------------------

def test_a_line_over_160_characters_is_a_check(job):
    long, key, device_id = _first_device(job, name="Invented Sensor " + "x" * 284)
    assert RULE["long_line"] == "Line form"
    assert _hits(long, "long_line") == [(key, device_id, "check")]


def test_a_line_of_ordinary_length_is_no_check(job):
    assert _hits(job, "long_line") == []


# ---- VAL-21: the words the client never sees -----------------------------------------------------------------------

@pytest.mark.parametrize("text", ["Valves PENDING the schedule", "Allow $500 for the panel", "Counts per the GEM",
                                  "Seen in QC", "EXISTING dampers reused"])
def test_a_clarification_with_a_word_the_client_never_sees_is_a_check(job, text):
    system = job.systems[0]
    j = job.with_system(dc.replace(system, clarifications=(Clarification("note", text),)))
    assert RULE["client_words"] == "Words the client never sees"
    assert (system.key, None, "check") in _hits(j, "client_words")


def test_a_device_name_with_a_flag_word_is_a_check_and_title_case_is_not(job):
    flagged, key, device_id = _first_device(job, name="Invented Sensor CONFIRMED")
    assert _hits(flagged, "client_words") == [(key, device_id, "check")]
    plain, _, _ = _first_device(job, name="Existing Invented Sensor")
    assert _hits(plain, "client_words") == []


def test_a_named_exception_with_a_price_is_the_whole_jobs_check(job):
    j = dc.replace(job, exceptions=(ScopeException("EF", "Fire alarm by others, $1,200 allowance", ()),))
    assert _hits(j, "client_words") == [("", None, "check")]


def test_the_sample_job_has_no_word_the_client_never_sees(job):
    assert _hits(job, "client_words") == [] and _hits(job, "long_line") == []


# ---- RND-13: the trio's depths in a block with no shape ------------------------------------------------------------

def test_the_shapeless_map_and_rep_pair_prints_the_trio_depths():
    pb = load_playbook()
    trio = pb.wording.integration_trio
    base = Job.from_dict(json.loads((FIX / "sample_job.json").read_text(encoding="utf-8")))
    device = base.systems[0].devices[0]
    devices = (dc.replace(device, id="IU.d1", slot="map_points", name=trio[1], verb="Furnish"),
               dc.replace(device, id="IU.d2", slot="rep_assist", name=trio[2], verb="Furnish"))
    iu = System(key="IU", name="Invented Unit", shape="", control="integration",
                families=(Family("Invented Unit", ("IU-1",), Count(value=1)),), devices=devices)
    j = Job(name="Invented", systems=(iu,), header=Header("00-0000", "Invented", "Invented", ("A",), "2026-10-04"))
    items = render(j, pb).scope.blocks[0].items
    assert [i.depth for i in items if i.kind == "line"] == [pb.wording.integration_depths[1],
                                                            pb.wording.integration_depths[2]] == [1, 2]
