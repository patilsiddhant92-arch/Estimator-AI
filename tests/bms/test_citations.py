"""The shared client-text cleanup (bms.citations), fix round 2: each case is a reviewer's failing input. Invented data."""
from __future__ import annotations

import inspect
import json
from dataclasses import replace
from pathlib import Path

import pytest

from bms.citations import SourceIds, strip_label
from bms.model import Clarification, Count, Device, Family, Job, OtherCount, Ref, ScopeException, System
from bms.playbook import load_playbook
from bms.render import RenderError, render
from bms.validate import RULE, validate

FIX = Path(__file__).resolve().parent / "fixtures"
ROOT = Path(__file__).resolve().parents[2]
S141 = Ref("S141", "q", "M-101, Invented.pdf page 2")
IDS = SourceIds.of(["S141", "S998", "S7"], ["EF-1", "F5-F8"])


@pytest.fixture(scope="module")
def job() -> Job:
    return Job.from_dict(json.loads((FIX / "sample_job.json").read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def pb():
    return load_playbook(ROOT / "playbook")


def _device(name="DDC Controller", refs=(S141,)) -> Device:
    return Device("EF.d1", "controller", name, "Furnish and Install", "AME", "AME", "AME", Count(2), refs)


def _system(clarifications=(), devices=None, tags=("EF-1", "EF-2"), count=None) -> System:
    return System("EF", "Exhaust Fans", "Exhaust Fan", "field", (Family("Exhaust Fan", tags, count or Count(2)),),
                  devices=tuple(devices or (_device(),)), clarifications=tuple(clarifications))


def _lines(job, pb, **kw):
    out = render(replace(job, systems=(_system(**kw),), exceptions=kw.pop("exceptions", ())), pb)
    return [l.text for l in out.lines if l.system_key == "EF"]


# ---- (1) a bracket glued to a word -----------------------------------------------------------------------------

@pytest.mark.parametrize("text, cleaned", [
    ("two valves[S141].", "two valves M-101."),
    ("[S141]valves open.", "M-101 valves open."),
    ("valves [S141]x open.", "valves M-101 x open."),
])
def test_a_bracket_glued_to_a_word_never_leaks_an_issued_id(job, text, cleaned):
    assert IDS.strip(text, (S141,)) == cleaned
    j = replace(job, systems=(_system((Clarification("note", text),)),))
    assert any(f.rule == RULE["ids"] and "S141" in f.what for f in validate(j, load_playbook(ROOT / "playbook")))


# ---- (2) real sheet numbers shaped like ids are places -----------------------------------------------------------

@pytest.mark.parametrize("where, place", [
    ("C101, Controls.pdf page 2", "C101"),          # the ledger's own sheet form: first, then a file part
    ("Sheet C501, Controls.pdf page 4", "C501"),    # after the word sheet
    ("sheets S101 and S102", "S101"),
    ("dwg F101", "F101"),
    ("schedule S9", ""),                            # not a sheet the ledger knows
    ("S141, Invented.pdf page 3", ""),              # an issued id is never a place
    ("Ledger fact F17", ""),                        # a ledger fact is never a place
])
def test_a_sheet_number_shaped_like_an_id_is_a_place_unless_issued(where, place):
    assert IDS.place(where) == place


def test_the_printed_count_keeps_its_sheet(job, pb):
    count = Count(5, (Ref("S5", "q", "Sheet C501, Controls.pdf page 4"),), (OtherCount(3, S141),))
    lines = _lines(job, pb, count=count, devices=(_device(refs=(Ref("S141", "q", "C101, Controls.pdf page 2"),)),),
                   clarifications=(Clarification("note", "Valves per S141."),))
    assert "**Valves per C101" in lines and "*Qty. (5) per C501; 3 per M-101." in lines


# ---- (3) a tag range inside a run --------------------------------------------------------------------------------

@pytest.mark.parametrize("text, cleaned", [
    ("per S141 and F5-F8", "per M-101 and F5-F8"),
    ("Fans F5 to F8, S141", "Fans F5 to F8 and M-101"),
    ("Fans (F5-F8, S141)", "Fans (F5-F8 and M-101)"),
])
def test_a_tag_range_joined_to_an_issued_id_stays_whole(text, cleaned):
    assert IDS.strip(text, (S141,)) == cleaned


# ---- (4) emptied brackets never print ----------------------------------------------------------------------------

@pytest.mark.parametrize("text, cleaned", [
    ("Two valves (see S999).", "Two valves."),
    ("Two valves (per S999).", "Two valves."),
    ("Two valves [see S999]", "Two valves"),
    ("[see S999]", ""),
    ("Two valves (per S7).", "Two valves."),         # issued, but its ref names no place
])
def test_an_emptied_bracket_never_prints(text, cleaned):
    assert IDS.strip(text, (S141, Ref("S7", "q", "ledger fact"))) == cleaned


def test_an_emptied_bracket_never_prints_in_a_device_name_or_an_exception(job, pb):
    j = replace(job, systems=(_system(devices=(_device(name="Valve (see S999)"),)),),
                exceptions=(ScopeException("EF", "Fire alarm (see S999)", ()),))
    out = render(j, pb)
    assert [l.text for l in out.lines if l.system_key == "EF"][1] == "Furnish and Install Valve"
    assert out.scope.named_exceptions == ("Fire alarm",)


# ---- (5) the tidy works only around the id, and takes a stripped id's cue word with it ---------------------------

@pytest.mark.parametrize("text, cleaned", [
    ("Fans per S999 stay on.", "Fans stay on."),
    ("valves per S999.", "valves."),
    ("Fans stay on, valves per S141.", "Fans stay on, valves per M-101."),
    ("Fans stay on, valves per S999.", "Fans stay on, valves."),
    ("Valves per S141; the fans are left on.", "Valves per M-101; the fans are left on."),
])
def test_the_tidy_takes_the_cue_word_and_nothing_far_away(text, cleaned):
    assert IDS.strip(text, (S141,)) == cleaned


# ---- minor ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("kind, text, cleaned", [
    ("assumed", "Assumed: -20 F outdoor design", "-20 F outdoor design"),
    ("note", "Note: -1 spare", "-1 spare"),
    ("assumed", "Assumed—two valves", "two valves"),
    ("confirm", "Confirm—ownership of valves", "ownership of valves"),
    ("confirm", "Confirm - ownership of valves", "ownership of valves"),
    ("assumed", "Assumption-based count", "Assumption-based count"),
])
def test_a_minus_sign_survives_and_a_dash_label_comes_off(kind, text, cleaned):
    assert strip_label(kind, text) == cleaned


@pytest.mark.parametrize("text", ["see S998 S999", "per S141/S999", "per S141 / S999", "S141—S999 per", "Fans per S999 stay on.",
                                  "Two valves (see S999).", "per S141 and F5-F8"])
def test_cleaning_is_idempotent(text):
    once = IDS.strip(text, (S141,))
    assert IDS.strip(once, (S141,)) == once


@pytest.mark.parametrize("text", ["per S141/S999", "per S141 / S999", "per S141‐S999", "per S141—S999"])
def test_more_joiners_join_a_run(text):
    assert IDS.strip(text, (S141,)) == "per M-101"


def test_a_device_name_or_exception_that_cleans_to_nothing_is_refused(job, pb):
    with pytest.raises(RenderError, match="no words left"):
        render(replace(job, systems=(_system(devices=(_device(name="S7", refs=(S141, Ref("S7", "q", "ledger fact"))),)),)),
               pb)
    with pytest.raises(RenderError, match="no words left"):
        render(replace(job, systems=(_system(),), exceptions=(ScopeException("EF", "S141", ()),)), pb)


def test_the_contract_pins_tags_as_keyword_only_with_an_empty_default():
    from bms import ai
    for function in (ai.write_system, ai.revise_system):
        tags = inspect.signature(function).parameters["tags"]
        assert tags.kind is tags.KEYWORD_ONLY and tags.default == ()
