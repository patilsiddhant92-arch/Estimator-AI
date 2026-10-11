"""The takeoff pass, Task 2.4 (plan 2026-10-11): `counts.cross_check` pictures no sheet the takeoff register says does not
count (`SheetClass.counts_units` false) when the job carries the register (`Job.sheets` not empty). On the invented
fixture of `takeoff_fixture` ("Invented Hall", 00-1111); every name and number here is invented."""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

import takeoff_fixture as fx
from bms import ai, counts, takeoff
from bms.plan import plan_job
from bms.playbook import load_playbook

PLAYBOOK = load_playbook(Path(__file__).parent / "fixtures" / "sample_playbook")


def _register():
    register, problems = takeoff.check_answer(fx.answer(), fx.ledger(), fx.catalogue(), fx.reading(),
                                              ai.evidence_index(fx.dossier()))
    assert register is not None, problems
    return register


def _without_demolition_type(catalogue):
    """The catalogue as if its sheet types had missed "Demolition" on every sheet: only the register knows them."""
    sheets = tuple(dataclasses.replace(s, types=tuple(t for t in s.types if t != "Demolition"))
                   for s in catalogue.sheets)
    return dataclasses.replace(catalogue, sheets=sheets)


@pytest.fixture
def pictured(monkeypatch):
    """Every (document, page) `cross_check` asks a picture of; no picture is drawn."""
    import estimator.writing.dossier as dossier

    asked: list[tuple[str, int]] = []

    def fake(catalogue, cache, keys, what):
        asked.extend(tuple(k) for k in keys)
        return [], []

    monkeypatch.setattr(dossier, "sheet_pictures", fake)
    return asked


def _excluded(job) -> set[tuple[str, int]]:
    return {(s.document, s.page) for s in job.sheets if not s.counts_units}


@pytest.mark.parametrize("catalogue", [fx.catalogue, lambda: _without_demolition_type(fx.catalogue())],
                         ids=["as-catalogued", "demolition-type-missed"])
def test_cross_check_pictures_no_sheet_the_register_sets_aside(tmp_path, pictured, catalogue):
    catalogue = catalogue()
    job = takeoff.attach(plan_job(fx.ledger(), catalogue, fx.dossier(), PLAYBOOK), _register())
    assert ("Mech.pdf", 6) in _excluded(job)                        # MD-401, the demolition plan of the attic
    counts.cross_check(job, catalogue, tmp_path / "cache")
    assert pictured                                                 # the new-work plans are still pictured
    assert not set(pictured) & _excluded(job)
    assert {("Mech.pdf", 2), ("Mech.pdf", 5)} <= set(pictured)       # M-401 and the part plan M-404


def test_without_a_register_the_sheet_filter_is_as_before(tmp_path, pictured):
    """No `Job.sheets`: the catalogue alone decides, so a demolition plan whose type the catalogue missed is pictured."""
    catalogue = _without_demolition_type(fx.catalogue())
    job = plan_job(fx.ledger(), catalogue, fx.dossier(), PLAYBOOK)
    assert job.sheets == ()
    counts.cross_check(job, catalogue, tmp_path / "cache")
    assert ("Mech.pdf", 6) in pictured
