"""Bug 5: a system the job names but AME does no work on vanished from the proposal. (a) The planner put only the
ledger's "exception" notes in `Job.exceptions`, so a system with no controls in the contract (control "none") was
planned as a block and no exception: the plan's exceptions list stayed empty. (b) The renderer turned a system the
writer left with no lines into an Evidence Package note only, never a named exception in the proposal.

The form is rules.md "Named exceptions": "EXCEPTION TO ANY WORK WITH Qty (n) <tags> - <reason>" (the reason
wording itself is R15, PENDING: the patch prints the source's / writer's own words, adds none of its own).
Invented ledger and job only; generic tags."""
import dataclasses
import datetime as dt

from estimator.ledger.facts import SETTLED, Ledger
from estimator.writing.dossier import Dossier

from bms.model import Count, Device, Family, FrontEnd, Header, Job, Ref, ScopeException, System
from bms.plan import plan_job
from bms.playbook import load_playbook
from bms.render import render

PLAYBOOK = load_playbook()
SOURCES = {"S3": "M-501, Invented.pdf page 6 (schedule)", "S4": "23 09 00, Invented Specs.pdf page 4"}
REF = Ref("S3", "invented quote", "M-501, Invented.pdf page 6")


def _dossier():
    return Dossier(job_name="Invented Job", text="", images=(), sources={}, families=(), device_totals={},
                   counts={}, stats={})


def _family(ledger, prefix, name, tags, count):
    ledger.add("family", prefix, name, "S3", f"{prefix} {name}", "schedules", SETTLED)
    ledger.add("unit", prefix, tags, "S3", f"Tags: {tags}", "schedules", SETTLED)
    ledger.add("count", prefix, count, "S3", f"{prefix} rows {count}", "schedules", SETTLED)


def _ledger():
    ledger = Ledger(dict(SOURCES))
    ledger.job_name = "Invented Job"
    ledger.add("front_end", "mode", "new-system", "S4", "new BMS", "spec", SETTLED)
    _family(ledger, "EF", "Exhaust Fan", "EF-1", 1)
    _family(ledger, "XP", "Transfer Pump", "XP-1, XP-2", 2)
    ledger.add("provider", "XP", "not in contract", "S4", "N.I.C.", "spec", SETTLED)
    return ledger


# ---- (a) the plan ------------------------------------------------------------------------------------------------

def test_a_system_with_no_controls_in_contract_is_a_plan_exception():
    job = plan_job(_ledger(), None, _dossier(), PLAYBOOK)
    assert job.exceptions, "the plan's exceptions list is empty"
    (x,) = [e for e in job.exceptions if e.system_key == "XP"]
    assert x.text.startswith("EXCEPTION TO ANY WORK WITH Qty (2) XP-1, XP-2")
    assert x.refs and x.refs[0].quote


def test_a_system_with_controls_is_no_exception():                       # negative: before and after
    job = plan_job(_ledger(), None, _dossier(), PLAYBOOK)
    assert not [e for e in job.exceptions if e.system_key == "EF"]


def test_an_exception_note_already_naming_the_system_is_not_repeated():
    ledger = _ledger()
    ledger.add("note", "exception", "Exception to any work with XP-1, XP-2 (by others)", "S4", "XP by others",
               "spec", SETTLED)
    job = plan_job(ledger, None, _dossier(), PLAYBOOK)
    assert len([e for e in job.exceptions if e.system_key == "XP"]) == 1


# ---- (b) the render ----------------------------------------------------------------------------------------------

def _header():
    return Header(quote_number="Q-0000", reference="Invented Job", mep_engineer="Invented Engineer",
                  based_on=("Invented drawings",), date=dt.date(2026, 10, 9).isoformat())


def _job(exceptions=()):
    line = Device("EF.d1", "start_stop", "Start/Stop", "Furnish and Wire", "AME", "AME", "AME", Count(1, (REF,)),
                  (REF,))
    ef = System("EF", "Exhaust Fans", "", "field", (Family("Exhaust Fan", ("EF-1",), Count(1, (REF,))),),
                devices=(line,))
    uh = System("UH", "Unit Heaters", "", "packaged", (Family("Unit Heater", ("UH-1", "UH-2"), Count(2, (REF,))),),
                no_scope_reason="integral thermostat")
    return Job("Invented Job", (ef, uh), front_end=FrontEnd(mode="new-system"), exceptions=tuple(exceptions),
               header=_header())


def test_a_system_left_with_no_lines_prints_as_a_named_exception():
    printed = render(_job(), PLAYBOOK).scope.named_exceptions
    assert "EXCEPTION TO ANY WORK WITH Qty (2) UH-1, UH-2 - INTEGRAL THERMOSTAT" in printed, printed


def test_a_system_with_lines_is_not_an_exception():                       # negative: before and after
    printed = render(_job(), PLAYBOOK).scope.named_exceptions
    assert not [t for t in printed if "EF-1" in t]


def test_a_system_already_excepted_by_the_plan_prints_once():             # negative: before and after
    x = ScopeException("UH", "Exception to any work with UH-1, UH-2 (by others)", (REF,))
    printed = render(_job((x,)), PLAYBOOK).scope.named_exceptions
    assert [t for t in printed if "UH-1" in t] == ["Exception to any work with UH-1, UH-2 (by others)"]


# ---- owner ruling 2026-10-09: every excluded or omitted system is in the exception list WITH its quantity --------

def test_untagged_fire_smoke_dampers_by_others_are_an_exception_with_their_quantity():
    ledger = _ledger()
    ledger.add("family", "FSD", "Fire/Smoke Damper", "S3", "FSD Fire/Smoke Damper", "schedules", SETTLED)
    ledger.add("count", "FSD", 12, "S3", "FSD rows 12", "schedules", SETTLED)
    ledger.add("provider", "FSD", "controls by others", "S4", "by others", "spec", SETTLED)
    job = plan_job(ledger, None, _dossier(), PLAYBOOK)
    fsd = [s for s in job.systems if any("Damper" in f.name for f in s.families)]
    assert fsd and fsd[0].control == "none", [(s.key, s.control) for s in job.systems]
    texts = [e.text for e in job.exceptions if e.system_key == fsd[0].key]
    assert len(texts) == 1 and "Qty (12)" in texts[0], job.exceptions


def test_every_omitted_system_in_the_rendered_list_carries_a_quantity():
    printed = render(_job(), PLAYBOOK).scope.named_exceptions
    assert printed and all("Qty (" in t for t in printed), printed
