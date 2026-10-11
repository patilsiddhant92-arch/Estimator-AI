"""Task 2.5 of the takeoff pass (plan 2026-10-11): the writer sees the register. `takeoff.register_text` builds the
register of one system and `ai_evidence.evidence` prints it first. On the invented fixture of `takeoff_fixture`
("Invented Hall", 00-1111) only; every name and number is invented, and the expected words are read from the fixture."""
from __future__ import annotations

from pathlib import Path

import takeoff_fixture as fx
from bms import ai, takeoff
from bms.plan import plan_job
from bms.playbook import load_playbook

PLAYBOOK = load_playbook(Path(__file__).parent / "fixtures" / "sample_playbook")
HEADING = "Takeoff register for this system"


def _job():
    job = plan_job(fx.ledger(), fx.catalogue(), fx.dossier(), PLAYBOOK)
    return takeoff.attach(job, takeoff.Takeoff.from_dict(fx.answer()))


def test_the_ahu_register_holds_each_unit_row_the_future_item_and_the_plans_understanding():
    job, ledger = _job(), fx.ledger()
    text = takeoff.register_text(job, job.system("AHU"), ledger, devices=fx.reading().devices)
    assert text.startswith(HEADING)
    ahu = [u for u in job.units if u.family == "AHU"]
    assert len(ahu) == 6                                     # five new and one to be demolished
    for unit in ahu:
        row = next(line for line in text.splitlines() if line.startswith(f"- {unit.tag}: "))
        assert f"{unit.status}, count {unit.count}" in row
        assert all(f"[{ref.source_id}]" in row for ref in unit.refs)
    assert not any(line.startswith(f"- {u.tag}: ") for u in job.units if u.family != "AHU" for line in text.splitlines())
    (future,) = job.future_items
    assert future.item in text and f"[{future.refs[0].source_id}] “{future.refs[0].quote}”" in text
    assert ledger.understanding["plans"] in text
    assert "Thermostats" not in text                         # no device of its areas


def test_the_fcu_register_holds_the_thermostats_kept_and_set_aside():
    job = _job()
    text = takeoff.register_text(job, job.system("FCU"), fx.ledger(), devices=fx.reading().devices)
    assert "Thermostats: 30 on the new-work sheets; 9 set aside (demolition sheet)" in text
    assert "- FCU-1: new, count 55" in text


def test_a_device_set_aside_on_the_job_is_the_one_printed():
    """When the job carries the device's set-aside (Task 2.1's `device_tally`), that row is printed, not a recount."""
    import dataclasses

    from bms.model import Ref, SetAside
    job = _job()
    ref = Ref("S18", "T", "MD-201, Mech.pdf page 9")
    job = dataclasses.replace(job, set_aside=(SetAside("T", 7, ref, "demolition sheet", "invented"),))
    text = takeoff.register_text(job, job.system("FCU"), fx.ledger(), devices=fx.reading().devices)
    assert "Thermostats: 30 on the new-work sheets; 7 set aside (demolition sheet)" in text


def test_no_register_gives_no_text():
    job = plan_job(fx.ledger(), fx.catalogue(), fx.dossier(), PLAYBOOK)
    assert takeoff.register_text(job, job.system("AHU"), fx.ledger()) == ""


def test_the_evidence_prints_the_register_first():
    job, dossier, ledger = _job(), fx.dossier(), fx.ledger()
    system = job.system("AHU")
    register = takeoff.register_text(job, system, ledger)
    text = ai.evidence_for(system, dossier, register=register)
    assert text.startswith(register.rstrip("\n"))
    assert HEADING in text and ledger.understanding["plans"] in text
    plain = ai.evidence_for(system, dossier)
    assert HEADING not in plain and text.endswith(plain)
    with_ledger = ai.system_evidence(system, dossier, ledger, register=register)
    assert with_ledger.startswith(register.rstrip("\n"))


def test_the_writer_prompt_has_the_future_rule():
    words = (Path(ai.__file__).parent / "prompts" / "write_system.md").read_text(encoding="utf-8")
    assert "A device or unit the takeoff lists as future has mark “future” and mark_note “FUTURE AS PER <the " \
           "document in words>”." in words
