"""REVIEW-018e (review of record for lead/correct-018d, on the merge lead/merge-018d). Attacks on the new parts:
the settled digest, merge_decisions with job=, the accept's family, the atomic history save and the refusal
counter id. Failing attacks are strict xfail with the failing input in the docstring; guards pass.
Invented data only: the sample fixture and the invented job folder of test_run.py."""
from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bms import ai, review
from bms.model import Count, Decision, Job, Ref
from bms.playbook import load_playbook

from test_ai import FakeClient, _bad, _Response, skeleton
from test_ai import dossier, raw  # noqa: F401  (fixtures)
from test_review_018c import _run_with_reworded, _save, _system
from test_run import _reach, job_folder  # noqa: F401  (job_folder is a fixture)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def job() -> Job:
    return Job.from_dict(json.loads((FIXTURES / "sample_job.json").read_text(encoding="utf-8")))


# ---- (e) the refusal counter id: the same ask, asked again, keeps one counter --------------------------------------

_SEED_SCRIPT = r"""
import json, sys
from pathlib import Path
from bms import ai, review
from bms.model import Job, System, json_schema
from bms.playbook import load_playbook
fixtures = Path(sys.argv[1])
playbook = load_playbook(fixtures / "sample_playbook")
job = Job.from_dict(json.loads((fixtures / "sample_job.json").read_text(encoding="utf-8")))
system = job.system("EF")
shape = ai._shape(system, playbook)
cache = ai._Cache(Path("cache-folder"))
write = ai._question("claude-test", ai.WRITE_SYSTEM, system.name, playbook.rules_text, ai._instructions("write_system"),
                     ai._write_prompt(system, shape, "[S1] invented evidence"), json_schema(System),
                     {"step": "write", "plan_key": system.key}, ())
qc = ai._question("claude-test", ai.QC_JOB, "QC", playbook.rules_text, ai._instructions("qc_job"), "the job",
                  ai._qc_schema(job, playbook), {"step": "qc"}, ())
print(json.dumps([ai._attempt_file(cache, write).name, ai._attempt_file(cache, qc).name,
                  review.system_digest(job, "EF"), review.system_digest(job, "")]))
"""


def test_guard_the_counter_id_and_the_system_digest_are_the_same_in_every_process():
    """Each estimate run is a new Python process with its own hash seed. A set iterated into the schema, the rules
    text or the step instructions would give the same ask a new counter on every run, so the cap of 3 would never
    trip (an endless ask-refuse loop); a varying system digest would show the check card on every run."""
    import bms
    src = str(Path(bms.__file__).resolve().parents[1])
    seen = []
    for seed in ("0", "1", "12345"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": src}
        done = subprocess.run([sys.executable, "-c", _SEED_SCRIPT, str(FIXTURES)], env=env, capture_output=True,
                              text=True, timeout=120)
        assert done.returncode == 0, done.stderr
        seen.append(json.loads(done.stdout.strip().splitlines()[-1]))
    assert seen[0] == seen[1] == seen[2]


def test_guard_three_fresh_runs_of_the_same_refused_ask_trip_the_cap_and_the_fourth_asks_nothing(
        job, raw, dossier, tmp_path):
    """Every run builds a new transport and loads the Playbook again from disk: the counter still adds up. Run 1:
    the call and its one immediate retry (2 refusals); run 2: the third refusal stops; run 3 stops before any
    call, naming the counter file."""
    system = skeleton(job.system("EF"))
    bad = _bad(raw, lambda a: a["devices"][0].update(slot="gadget"))
    client = FakeClient(*(_Response(json.dumps(bad)) for _ in range(5)))
    evidence = ai.evidence_for(system, dossier)
    reasons = []
    for _ in range(3):
        playbook = load_playbook(FIXTURES / "sample_playbook")
        with pytest.raises(ai.NoAnswer) as failed:
            ai.write_system(system, evidence, playbook, ai.ApiTransport(tmp_path, model="claude-test", client=client))
        reasons.append(failed.value.reason)
    assert len(client.calls) == 3
    assert reasons[1].startswith("Stopped:") and reasons[2].startswith("Stopped:")
    assert len(list(tmp_path.rglob("attempts/*.json"))) == 1       # one counter for the one ask


# ---- (a) the settled digest is stored before the run reaches the end -------------------------------------------------

def _dampers(system: dict) -> list[dict]:
    return [d for d in system["devices"] if d["name"].startswith("Damper")]


@pytest.mark.xfail(strict=True, reason="REVIEW-018e F1: settled is saved before the review page is written")
def test_attack_a_run_that_crashes_after_the_history_save_does_not_lose_the_check_card(job_folder, tmp_path,
                                                                                       monkeypatch):
    """Failing input: round 1 deletes the damper (run 2 honors it); round 2 accepts the controller and the revise
    words the damper again ("Damper, motor driven"). Run 3 computes the should_fix check card and stores the new
    system digest in decisions history.json, then stops before the review page (here review_page raises, as a
    full disk or a locked Review.html would). Run 4, a plain re-run, finds the system as `settled` says and shows
    no card: the line is back and nothing on any page says so."""
    from bms import run
    out, cache, key, state, first = _run_with_reworded(
        job_folder, tmp_path, monkeypatch, ("Controller", "Start Stop", "Damper Actuator"), "Damper, motorized")
    (damper,) = _dampers(_system(first, key))
    _save(out, {"system_key": key, "action": "delete", "device_id": damper["id"], "was": damper, "reason": "x"})
    second = _system(_reach(job_folder, out, cache, "done"), key)
    assert not _dampers(second)
    controller = second["devices"][0]
    _save(out, {"system_key": key, "action": "accept", "device_id": controller["id"], "was": controller,
                "reason": "x"})
    state["wording"] = "Damper, motor driven"
    real_page = run.review_page

    def crash(*args, **kwargs):
        raise OSError("the review page could not be written (invented)")
    monkeypatch.setattr(run, "review_page", crash)
    with pytest.raises(OSError):
        _reach(job_folder, out, cache, "done")
    monkeypatch.setattr(run, "review_page", real_page)
    fourth = _reach(job_folder, out, cache, "done")
    assert [d["name"] for d in _dampers(_system(fourth, key))] == ["Damper, motor driven"]
    cards = [f for f in fourth.findings if f.rule == "decision not honored" and f.severity == "should_fix"]
    assert cards, "the re-worded line is back and no card says so"


# ---- (c) the family of an accept: a line that cites two families ----------------------------------------------------

@pytest.fixture
def two_counts(job) -> Job:
    """VRF.d1's quantity cites both the Indoor Unit count (S9) and the Condensing Unit count (S10)."""
    vrf = job.system("VRF")
    d1, *rest = vrf.devices
    s9 = Ref("S9", "FCU-1 THRU FCU-4", "M-002, Drawings.pdf page 3")
    s10 = Ref("S10", "CU-1", "M-002, Drawings.pdf page 3")
    d1 = dataclasses.replace(d1, quantity=dataclasses.replace(d1.quantity, sources=(s9, s10)), flag="quantity")
    return job.with_system(dataclasses.replace(vrf, devices=(d1, *rest)))


@pytest.mark.xfail(strict=True, reason="REVIEW-018e F2: accept_family takes the first cited family only")
def test_attack_an_accept_of_a_line_citing_two_families_falls_when_either_count_changes(two_counts):
    """Failing input: VRF.d1's quantity cites S9 (Indoor Unit) and S10 (Condensing Unit). One save accepts d1's
    quantity flag and changes the Condensing Unit count to 2. `accept_family` names only Indoor Unit (the first
    family whose sources meet the line's), so `_standing_accepts` keeps the accept, the run re-applies it after
    the rewrite, and the flag the new count raises on a line that cites it is cleared in silence."""
    from bms import run
    d1 = two_counts.system("VRF").devices[0]
    families = {f.name for f in two_counts.system("VRF").families}
    assert {"Indoor Unit", "Condensing Unit"} <= families
    accept = Decision("VRF", "accept", device_id=d1.id, was=d1)
    cited = review.accept_family(two_counts, accept)
    other = next(name for name in ("Indoor Unit", "Condensing Unit") if name != cited)
    count = Decision("VRF", "change", family_name=other, count=Count(2))
    entries = [review.SavedDecision(count, 1), review.SavedDecision(accept, 1)]
    assert run._standing_accepts(entries, "VRF", two_counts) == []


def test_guard_an_accept_of_a_line_citing_no_family_falls_when_any_count_of_its_system_changes(job):
    from bms import run
    vrf = job.system("VRF")
    d1 = dataclasses.replace(vrf.devices[0], quantity=dataclasses.replace(vrf.devices[0].quantity, sources=()),
                             flag="quantity")
    job = job.with_system(dataclasses.replace(vrf, devices=(d1, *vrf.devices[1:])))
    accept = Decision("VRF", "accept", device_id=d1.id, was=d1)
    assert review.accept_family(job, accept) is None
    entries = [review.SavedDecision(Decision("VRF", "change", family_name="Condensing Unit", count=Count(2)), 1),
               review.SavedDecision(accept, 1)]
    assert run._standing_accepts(entries, "VRF", job) == []
    later = [entries[0], review.SavedDecision(accept, 2)]          # accepted after it saw the new count: stands
    assert run._standing_accepts(later, "VRF", job) == [accept]


# ---- (b) merge_decisions with job=: twins and renumbering -----------------------------------------------------------

def _copies(job: Job, key: str, line) -> int:
    return sum(1 for d in job.system(key).devices if review._same_device((d,), line))


def test_guard_twins_renumbered_by_the_writer_keep_both_answers_and_one_copy(job):
    """Round 1 deletes EF.d9, the twin of EF.d1. The writer is asked again and now numbers the twins EF.d1 and
    EF.d2. Round 2 accepts EF.d2 (the copy the page shows). Both answers are kept (two lines have the content,
    the ids differ) and the job keeps exactly one copy."""
    ef = job.system("EF")
    x = ef.devices[0]
    first = job.with_system(dataclasses.replace(ef, devices=(*ef.devices, dataclasses.replace(x, id="EF.d9"))))
    history = review.merge_decisions([], [Decision("EF", "delete", device_id="EF.d9", was=x)], job=first)
    renumbered = job.with_system(dataclasses.replace(
        ef, devices=(x, dataclasses.replace(x, id="EF.d2"),
                     *(dataclasses.replace(d, id=f"EF.d{n}") for n, d in enumerate(ef.devices[1:], start=3)))))
    history = review.merge_decisions(history, [Decision("EF", "accept", device_id="EF.d2", was=x)], job=renumbered)
    assert [h.decision.action for h in history] == ["delete", "accept"]
    assert _copies(review.apply_decisions(renumbered, [h.decision for h in history]), "EF", x) == 1


@pytest.mark.xfail(strict=True, reason="REVIEW-018e F3: a twin's delete takes the only copy once the twin is gone")
def test_attack_the_delete_of_one_twin_does_not_take_the_only_copy_when_the_writer_drops_the_twin(job):
    """Failing input: the writer wrote EF.d1 twice (EF.d1, EF.d9); the estimator deleted EF.d9, meaning "one of
    these is enough". A later write (a Playbook edit, new evidence) writes the line once. The delete finds no
    EF.d9, falls back to the content, and removes EF.d1, the only copy; the honored check counts against that
    same result, so no card. The estimator's intent (keep one) is lost in silence."""
    ef = job.system("EF")
    x = ef.devices[0]
    delete = Decision("EF", "delete", device_id="EF.d9", was=x)
    after = review.apply_decisions(job, [delete])
    kept_one = _copies(after, "EF", x) == 1
    carded = bool(review.unhonored_decisions(job, [delete], after))
    assert kept_one or carded


# ---- (d) the atomic history save on Windows ----------------------------------------------------------------------------

@pytest.mark.skipif(os.name != "nt", reason="Windows file sharing")
@pytest.mark.xfail(strict=True, reason="REVIEW-018e F4: os.replace onto an open history raises PermissionError")
def test_attack_a_history_held_open_by_another_program_is_still_saved_or_stops_in_words(job, tmp_path):
    """Failing input: decisions history.json is open in another program (a viewer, a sync or virus scanner holding
    it) while the run saves it. Python's open() on Windows does not share delete, so os.replace raises a raw
    PermissionError (a traceback for the estimator) and leaves 'decisions history.json.tmp' behind. The old in-place
    write_text succeeded here. Expected: the history is saved, or a ModelError names the file in plain words."""
    from bms.model import ModelError
    d1 = job.system("EF").devices[0]
    first = [review.SavedDecision(Decision("EF", "delete", device_id=d1.id, was=d1), 1, took_effect=True)]
    review.save_history(tmp_path, first)
    second = [*first, review.SavedDecision(Decision("EF", "accept", device_id="EF.d2"), 2)]
    with open(tmp_path / review.DECISIONS_HISTORY, encoding="utf-8"):
        try:
            review.save_history(tmp_path, second)
        except ModelError as error:
            assert review.DECISIONS_HISTORY in str(error)
            return
    assert review.load_history(tmp_path) == second


@pytest.mark.skipif(os.name != "nt", reason="Windows file sharing")
def test_guard_a_failed_swap_leaves_the_old_history_readable(job, tmp_path):
    """Whatever the swap does, the history the next run reads is the old one, never the half-written .tmp."""
    d1 = job.system("EF").devices[0]
    first = [review.SavedDecision(Decision("EF", "delete", device_id=d1.id, was=d1), 1, took_effect=True)]
    review.save_history(tmp_path, first)
    second = [*first, review.SavedDecision(Decision("EF", "accept", device_id="EF.d2"), 2)]
    with open(tmp_path / review.DECISIONS_HISTORY, encoding="utf-8"):
        try:
            review.save_history(tmp_path, second)
        except OSError:
            pass
    assert review.load_history(tmp_path) in (first, second)
