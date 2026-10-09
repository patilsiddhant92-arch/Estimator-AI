"""Bug 1 (validate.py `_packaged`, ~224-234): the packaged-unit check demands the integration trio as must_fix even
when the job names no BMS at all (no front end source) and the block carries no integration line. With nothing to
integrate into, the integration lines are dropped entirely (owner ruling 2026-10-09): no finding demands them.
A block that already carries some integration lines still needs the whole trio (the writer found integration).
Invented fixtures only."""
from bms.model import Count, Device, Family, FrontEnd, Job, Ref, System
from bms.playbook import load_playbook
from bms.validate import validate

REF = Ref("S9", "invented quote", "M-901, Invented.pdf page 1")
PLAYBOOK = load_playbook()


def _packaged_shape():
    """A repo-Playbook packaged shape with the integration trio and an ordinary (non-integration) slot."""
    for shape in PLAYBOOK.shapes.values():
        trio = [s for s in shape.slots_of_kind("integration") if not s.startswith("vfd_")]
        other = [s for s, k in shape.slot_kinds.items() if k != "integration" and "vfd" not in s]
        if len(trio) >= 3 and other:
            return shape, trio, other[0]
    raise AssertionError("no packaged shape with an integration trio in the repo Playbook")


def _job(front_end, with_trio=False, partial=False):
    shape, trio, other = _packaged_shape()
    lines = [Device("ZZ.d1", other, "Invented line", "Install and Wire", "Unit Mfr.", "AME", "AME", Count(1, (REF,)),
                    (REF,))]
    slots = trio if with_trio else (trio[:1] if partial else [])
    lines += [Device(f"ZZ.t{n}", slot, "Invented integration line", "Wire", "AME", "AME", "AME", Count(1, (REF,)),
                     (REF,)) for n, slot in enumerate(slots, 1)]
    system = System("ZZ", "Invented Unit", shape.name, "packaged",
                    (Family("Invented Unit", ("ZZ-1",), Count(1, (REF,))),), devices=tuple(lines))
    return Job("Invented Job", (system,), front_end=front_end)


def _packaged(job):
    return [(f.what, f.severity) for f in validate(job, PLAYBOOK) if f.rule == "Packaged units"]


def test_no_bms_named_and_no_integration_lines_is_no_must_fix():
    got = _packaged(_job(front_end=None))
    assert [w for w, s in got if s == "must_fix" and "integration line" in w] == [], got


def test_no_bms_named_drops_the_integration_lines_entirely():
    """Owner ruling: no BMS means no integration lines, so nothing asks for them, not even a check."""
    got = _packaged(_job(front_end=None))
    assert [w for w, _s in got if "integration" in w] == [], got


def test_a_job_with_a_bms_still_demands_the_trio():
    got = _packaged(_job(front_end=FrontEnd(mode="new-system")))
    assert any(s == "must_fix" and "integration line is missing" in w for w, s in got), got


def test_a_partial_trio_is_still_must_fix_without_a_named_bms():
    got = _packaged(_job(front_end=None, partial=True))
    assert any(s == "must_fix" and "integration line is missing" in w for w, s in got), got


def test_the_full_trio_is_clean_either_way():
    for fe in (None, FrontEnd(mode="new-system")):
        assert [x for x in _packaged(_job(front_end=fe, with_trio=True)) if "integration" in x[0]] == []


def test_standalone_controls_by_the_mechanical_contractor_and_no_front_end_is_no_must_fix():
    """QA's case: a packaged unit on stand-alone controls the mechanical contractor furnishes (its own thermostat,
    no BMS front end anywhere in the documents). Nothing to integrate into: no must_fix for the trio."""
    shape, _trio, other = _packaged_shape()
    line = Device("ZZ.d1", other, "Stand-alone Space Thermostat", "Install and Wire", "Mechanical Contractor",
                  "AME", "AME", Count(1, (REF,)), (REF,))
    system = System("ZZ", "Invented Unit", shape.name, "packaged",
                    (Family("Invented Unit", ("ZZ-1",), Count(1, (REF,))),), devices=(line,))
    got = _packaged(Job("Invented Job", (system,), front_end=None))
    assert [w for w, _s in got if "integration" in w] == [], got
