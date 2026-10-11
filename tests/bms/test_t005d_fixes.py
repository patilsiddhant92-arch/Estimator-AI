"""T-005d fixes (lead review 2026-10-11, HarkPro/inbox/T-005d-fixes.md): must fix 1-3 and should fix 1-6, each from
an invented copy of the failing pattern (tests/bms/fixtures/t005d_fixes.json). No job text."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from estimator.ledger.facts import Fact
from estimator.writing import dossier as dossier_module
from estimator.writing.dossier import Dossier

from bms import ai, ai_evidence
from bms.model import Count, Family, System
from bms.playbook import load_playbook

FIXTURES = Path(__file__).resolve().parent / "fixtures"
F = json.loads((FIXTURES / "t005d_fixes.json").read_text(encoding="utf-8"))
SRC = Path(ai.__file__).resolve().parents[1]


def _lines():
    lines = list(F["lines"])
    i = next(n for n, line in enumerate(lines) if line.startswith("[S20]"))
    lines[i] = lines[i] + F["controls_filler"] * F["controls_repeat"]
    return lines


def _dossier() -> Dossier:
    sections = {q: (h, tuple(ids)) for q, (h, ids) in F["sections"].items()}
    return Dossier(F["job"], "\n".join(_lines()) + "\n", (), {}, (), {}, {}, {}, sections)


def _unit() -> System:
    u = F["unit"]
    return System(key=u["key"], name=u["name"], shape="", control="field",
                  families=(Family(u["family"], (u["tag"],), Count(1)),), sequence_refs=())


class _Ledger:
    sources = {f["source_id"]: "23 09 93, Specs.pdf page 2" for f in F["facts"]}
    facts = {f["id"]: Fact(f["id"], f["kind"], f["subject"], f["value"], f["source_id"], f["quote"], "spec")
             for f in F["facts"]}


class _Fake:
    def __init__(self, *answers):
        self.answers, self.notes = list(answers), []

    def ask(self, kind, name, instructions, system_prompt, prompt, schema, extra=None, images=()):
        if not self.answers:
            raise ai.NoAnswer("no answer queued", waiting=True)
        return copy.deepcopy(self.answers.pop(0))

    def note_intake(self, name, change):
        self.notes.append((name, change))


@pytest.fixture
def playbook():
    return load_playbook(FIXTURES / "sample_playbook")


def _device(name, sid, quote, where, **more):
    d = {"id": "QX.d1", "slot": "sensor", "name": name, "verb": "Furnish and Install", "furnished_by": "AME",
         "installed_by": "AME", "wired_by": "AME",
         "quantity": {"value": 1, "sources": [], "others": [], "added_up": None},
         "refs": [{"source_id": sid, "quote": quote, "where": where}], "assumption": None, "flag": "none",
         "mark": "", "mark_note": ""}
    d.update(more)
    return d


def _write(playbook, device):
    data = _unit().to_dict()
    data.update(devices=[device], clarifications=[], tech_hours=None, no_scope_reason=None)
    t = _Fake(data)
    return ai.write_system(_unit(), ai.system_evidence(_unit(), _dossier(), _Ledger()), playbook, t), t


# ---- must fix 1: job-wide facts reach every writer under "Job-wide facts" -----------------------------------------

def test_the_general_sequence_section_is_given_under_job_wide_facts():
    text = ai.system_evidence(_unit(), _dossier(), _Ledger())
    part = text.split("\nJob-wide facts:\n", 1)[1].split("\n\n", 1)[0]
    assert "[S3]" in part and "[S4]" in part and "--- [Q1] A. GENERAL ---" in part
    assert "[S8]" not in part                                    # another unit's tagged section is not job-wide
    assert {"S3", "S4"} <= ai_evidence.stated_ids(text)          # a sequence passage states what it says


def test_a_job_wide_fact_of_the_reading_is_listed_and_a_tagged_one_is_not():
    text = ai.system_evidence(_unit(), _dossier(), _Ledger())
    part = text.split("Job-wide facts the reading found", 1)[1].split("\n\n", 1)[0]
    assert "[S3] “Provide one outside air temperature sensor" in part
    assert "WV-8" not in part


def test_every_writer_gets_the_job_wide_facts_the_front_end_too():
    other = System(key="WV", name="Exhaust Fans", shape="", control="field",
                   families=(Family("Exhaust Fan", ("WV-8",), Count(1)),), sequence_refs=())
    for system, front_end in ((other, False), (_unit(), True)):
        text = ai.system_evidence(system, _dossier(), _Ledger(), front_end=front_end)
        assert "Job-wide facts:" in text and "changeover aquastat" in text


def test_a_section_already_given_as_the_systems_own_is_not_repeated():
    text = ai.system_evidence(_unit(), _dossier(), _Ledger())
    assert text.count("[S6]") == 1


# ---- must fix 2: a controls sheet is never dropped silently -------------------------------------------------------

def test_a_controls_sheet_longer_than_the_notes_limit_is_given_whole():
    line = next(l for l in _lines() if l.startswith("[S20]"))
    assert len(line) > ai_evidence.NOTES_LIMIT
    text = ai.system_evidence(_unit(), _dossier(), _Ledger())
    assert line in text


def test_a_controls_sheet_past_the_controls_limit_is_given_as_excerpts(monkeypatch):
    monkeypatch.setattr(ai_evidence, "CONTROLS_LIMIT", 5_000)
    text = ai.system_evidence(_unit(), _dossier(), _Ledger())
    line = next(l for l in text.splitlines() if l.startswith("[S20]"))
    assert len(line) <= 5_000 and "(excerpts about it)" in line and "[FUTURE] SPACE CO2 SENSOR" in line


def test_a_controls_sheet_with_no_room_left_stops_the_run_with_a_plain_message(monkeypatch):
    monkeypatch.setattr(ai_evidence, "CONTROLS_LIMIT", 400)
    with pytest.raises(ValueError, match=r"^Stopped: the controls sheet .*CONTROLS_LIMIT"):
        ai.system_evidence(_unit(), _dossier(), _Ledger())


# ---- must fix 3: a negated "states" keeps the assumption -----------------------------------------------------------

@pytest.mark.parametrize("why", ["the schedule does not state the quantity", "the schedule shows no count",
                                 "the schedule note gives a quantity by others without a count",
                                 "the schedule doesn't state how many"])
def test_an_assumption_that_says_the_schedule_is_silent_is_kept(playbook, why):
    device = _device("Filter Switch", "S12", "FILTER SWITCH QUANTITY BY OTHERS", "M-602, Plans.pdf page 6",
                     flag="assumed", assumption={"what": "one switch per unit", "why": why})
    written, _ = _write(playbook, device)
    assert written.devices[0].assumption is not None and written.devices[0].flag == "assumed"


def test_the_stated_test_reads_negation_per_clause():
    assert ai._says_stated("the schedule states the controller is factory wired")
    assert not ai._says_stated("the schedule does not state the controller")
    assert ai._says_stated("no spare points; the sequence calls for one sensor")


# ---- should fix 1: FUTURE marks the item beside it -----------------------------------------------------------------

def test_a_future_item_beside_the_device_words_marks_the_line(playbook):
    device = _device("Space CO2 Sensor", "S20", "[FUTURE] SPACE CO2 SENSOR AI", "M-902, Plans.pdf page 9")
    written, _ = _write(playbook, device)
    assert written.devices[0].mark == "future" and written.devices[0].mark_note.startswith("FUTURE AS PER")


def test_a_future_word_about_something_else_is_not_in_the_future_checklist():
    text = ai.system_evidence(_unit(), _dossier(), _Ledger())
    part = text.split("Items its passages mark FUTURE", 1)[1].split("\n\n", 1)[0]
    assert "[S20]" in part and "[S21]" not in part


def test_future_items_needs_an_item_word_or_the_device_name():
    assert ai_evidence.future_items("[FUTURE] SPACE SENSOR")
    assert not ai_evidence.future_items("BLANK FLANGE FOR FUTURE CONNECTION BY OTHERS")
    assert not ai_evidence.future_items("[FUTURE] SPACE CO2 SENSOR", "Supply Fan Status")
    assert ai_evidence.future_items("[FUTURE] SPACE CO2 SENSOR", "Space CO2 Sensor")


# ---- should fix 2: an ownership assumption against a stated schedule row is dropped ---------------------------------

def test_an_ownership_assumption_against_the_schedule_row_is_dropped_whatever_its_reason(playbook):
    device = _device("Unit Controller", "S11", "UNIT CONTROLLER PROVIDED BY THE UNIT MANUFACTURER, FACTORY WIRED",
                     "M-602, Plans.pdf page 6", flag="assumed",
                     assumption={"what": "controller furnished by AME for the factory to wire",
                                 "why": "the controls specification gives unit controllers to the contractor"})
    written, transport = _write(playbook, device)
    assert written.devices[0].assumption is None and written.devices[0].flag == "none"
    assert any("states who furnishes" in change for _, change in transport.notes)


def test_an_ownership_assumption_on_a_stated_passage_that_names_no_owner_is_kept(playbook):
    device = _device("Supply Fan VFD", "S6", "start the supply fan VFD of QX-3", "23 09 93, Specs.pdf page 2",
                     flag="assumed", assumption={"what": "the VFD is furnished by the electrical contractor",
                                                 "why": "the specification gives drives to Division 26"})
    written, _ = _write(playbook, device)
    assert written.devices[0].assumption is not None and written.devices[0].flag == "assumed"


# ---- should fix 3: the checklist names end devices, never their owner ----------------------------------------------

def test_the_end_device_checklist_says_names_an_end_device():
    text = ai.system_evidence(_unit(), _dossier(), _Ledger())
    part = text.split("End devices its unit schedules list", 1)[1].split("\n\n", 1)[0]
    assert "- names an end device" in part and "S12" in part and "furnished with it;" not in part


# ---- should fix 5: no job-specific sheet in prompts or code --------------------------------------------------------

def test_no_real_sheet_number_in_the_prompts_or_the_code():
    for path in [*SRC.joinpath("bms").rglob("*.py"), *SRC.joinpath("bms", "prompts").glob("*.md"),
                 *SRC.joinpath("estimator").rglob("*.py")]:
        assert not re.search(r"M-?710", path.read_text(encoding="utf-8")), path


# ---- should fix 6: a large job's later sheets keep their text ------------------------------------------------------

def _sheet(n, title, discipline="Mechanical"):
    return SimpleNamespace(document="Plans.pdf", page=n, number=f"M-{n:03d}", title=title, discipline=discipline)


def test_the_plan_sheets_share_the_total_and_the_controls_sheets_keep_the_full_cut():
    chosen = {("Plans.pdf", n): _sheet(n, "FLOOR PLAN") for n in range(1, 31)}
    chosen[("Plans.pdf", 31)] = _sheet(31, "CONTROL DIAGRAMS")
    texts = {key: "X" * 30_000 for key in chosen}
    cuts = dossier_module._sheet_cuts(chosen, texts, dossier_module.PLAN_TEXT_TOTAL)
    assert cuts[("Plans.pdf", 31)] == dossier_module.PLAN_TEXT_LIMIT
    plans = {cuts[("Plans.pdf", n)] for n in range(1, 31)}
    assert len(plans) == 1 and dossier_module.PLAN_TEXT_FLOOR <= plans.pop()
    assert sum(min(30_000, c) for c in cuts.values()) <= dossier_module.PLAN_TEXT_TOTAL


def test_a_job_within_the_total_keeps_the_full_cut_on_every_sheet():
    chosen = {("Plans.pdf", n): _sheet(n, "FLOOR PLAN") for n in range(1, 6)}
    cuts = dossier_module._sheet_cuts(chosen, {key: "X" * 30_000 for key in chosen}, dossier_module.PLAN_TEXT_TOTAL)
    assert set(cuts.values()) == {dossier_module.PLAN_TEXT_LIMIT}


def test_every_sheet_of_a_large_job_reaches_7c(tmp_path):
    from estimator.writing.dossier import _Ids, _SheetText, _sheet_text_lines
    chosen = {("Plans.pdf", n): _sheet(n, "FLOOR PLAN") for n in range(1, 31)}
    texts = {key: f"SHEET {key[1]} " + "Y " * 15_000 for key in chosen}
    lines = _sheet_text_lines(chosen, texts, _Ids(), _SheetText(), "more sheet")
    assert not any(line.startswith("(Stopped") for line in lines)
    assert sum(1 for line in lines if line.startswith("[S")) == 30
